from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
import pandas as pd
import zipfile, os, json
from pathlib import Path
import tempfile
from fastapi.responses import HTMLResponse

app = FastAPI()

def generate_df(file_path):
    rows = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                first_part, rest = line.split("] [", 1)
                timestamp_str, _ = first_part.strip("[]").split(" - ", 1)
                timestamp = pd.to_datetime(timestamp_str, errors="coerce")

                rest, json_payload = rest.rsplit("] ", 1)
                parts = rest.split()
                url, status, rt_ms = parts[2:5]

                data = json.loads(json_payload)

                try:
                    stayed_time = float(rt_ms) if status == "200" else None
                except ValueError:
                    stayed_time = None

                rows.append({
                    "Service Id":  data.get("sid"),
                    "Vno":         data.get("vno"),
                    "Ano":         data.get("ano"),
                    "Rt Area":     data.get("rtarea"),
                    "URL":         url,
                    "Stayed Time": stayed_time,
                    "App Version": data.get("appVer"),
                    "Timestamp":   timestamp
                })
            except Exception:
                # skip invalid line
                pass

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    cols = ["Service Id", "Vno", "Ano", "Rt Area", "URL", "Stayed Time", "App Version", "Timestamp"]
    return df[cols]


@app.post("/upload")
async def upload_zip(file: UploadFile = File(...)):
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, file.filename)
            with open(zip_path, "wb") as f:
                f.write(await file.read())

            # extract
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            log_files = list(Path(tmpdir).glob("*.txt")) + list(Path(tmpdir).glob("*.log"))
            if not log_files:
                return JSONResponse({"error": "No .txt or .log files found."}, status_code=400)

            dfs = []
            for log in log_files:
                df = generate_df(log)
                if not df.empty:
                    dfs.append(df)

            if not dfs:
                return JSONResponse({"error": "No valid log entries parsed."}, status_code=400)

            merged_df = pd.concat(dfs, ignore_index=True)
            merged_df.sort_values("Timestamp", inplace=True, ignore_index=True)

            output_file = os.path.join(tmpdir, "merged_sorted.csv")
            merged_df.to_csv(output_file, index=False, date_format="%Y-%m-%d %H:%M:%S")

            return FileResponse(output_file, filename="merged_sorted.csv", media_type="text/csv")

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/")
def home():
    return {"message": "Upload your log ZIP via POST /upload"}


@app.get("/", response_class=HTMLResponse)
def main_form():
    return """
    <html>
        <head>
            <title>Log Converter</title>
        </head>
        <body style="font-family: sans-serif; margin: 40px;">
            <h2>Upload ZIP file → Get CSV</h2>
            <form action="/upload" enctype="multipart/form-data" method="post">
                <input type="file" name="file" accept=".zip" required>
                <button type="submit">Convert</button>
            </form>
        </body>
    </html>
    """