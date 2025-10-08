from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
import pandas as pd
import zipfile, os, json, tempfile, shutil
from pathlib import Path

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
                # Silently skip invalid lines in this simplified version
                pass

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    # Drop rows where timestamp could not be parsed
    df.dropna(subset=['Timestamp'], inplace=True)
    
    cols = ["Service Id", "Vno", "Ano", "Rt Area", "URL", "Stayed Time", "App Version", "Timestamp"]
    return df[cols]


@app.post("/upload")
async def upload_zip(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    # Use a temporary directory that we can clean up later
    tmpdir = tempfile.mkdtemp()

    try:
        # Securely save the uploaded file by using its base name
        safe_filename = Path(file.filename).name
        zip_path = os.path.join(tmpdir, safe_filename)

        # Stream the file to disk to avoid high memory usage
        with open(zip_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Extract files
        extract_path = os.path.join(tmpdir, 'extracted')
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)

        log_files = list(Path(extract_path).rglob("*.txt")) + list(Path(extract_path).rglob("*.log"))
        if not log_files:
            return JSONResponse({"error": "No .txt or .log files found in the ZIP archive."}, status_code=400)

        all_dfs = [generate_df(log) for log in log_files]
        # Filter out empty dataframes
        valid_dfs = [df for df in all_dfs if not df.empty]

        if not valid_dfs:
            return JSONResponse({"error": "No valid log entries could be parsed from the files."}, status_code=400)

        merged_df = pd.concat(valid_dfs, ignore_index=True)
        merged_df.sort_values("Timestamp", inplace=True, ignore_index=True)

        # Create the output file within the unique temporary directory
        output_file = os.path.join(tmpdir, "merged_sorted.csv")
        merged_df.to_csv(output_file, index=False, date_format="%Y-%m-%d %H:%M:%S")

        # Add a background task to delete the entire temp directory after the response is sent
        background_tasks.add_task(shutil.rmtree, tmpdir)

        return FileResponse(output_file, filename="merged_sorted.csv", media_type="text/csv")

    except Exception as e:
        # Clean up the directory in case of an error before returning
        background_tasks.add_task(shutil.rmtree, tmpdir)
        return JSONResponse({"error": f"An unexpected error occurred: {str(e)}"}, status_code=500)


@app.get("/", response_class=HTMLResponse)
def main_form():
    try:
        with open("index.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "index.html not found"})