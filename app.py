from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
import pandas as pd
import zipfile, os, json, tempfile, shutil
from pathlib import Path
from datetime import datetime

app = FastAPI()

# Health check endpoint (GET + HEAD)
@app.get("/health", tags=["Monitoring"])
@app.head("/health", tags=["Monitoring"])
async def health_check():
    """Health check endpoint to confirm the server is running and responsive."""
    return {"status": "healthy", "message": "Server is running"}


def generate_df(file_path):
    rows = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                # Parse timestamp and message
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

            except Exception as e:
                # Log warning but skip malformed line
                print(f"Warning: Skipping malformed log line. Error: {e}")
                continue

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Ensure Timestamp is valid and drop invalid rows
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df.dropna(subset=['Timestamp'], inplace=True)

    cols = ["Service Id", "Vno", "Ano", "Rt Area", "URL", "Stayed Time", "App Version", "Timestamp"]
    return df[cols]


@app.post("/upload")
async def upload_zip(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    # Create a temporary working directory
    tmpdir = tempfile.mkdtemp()

    try:
        # Save uploaded ZIP file
        safe_filename = Path(file.filename).name
        zip_path = os.path.join(tmpdir, safe_filename)

        with open(zip_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Extract logs
        extract_path = os.path.join(tmpdir, 'extracted')
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)

        # Collect .txt and .log files
        log_files = list(Path(extract_path).rglob("*.txt")) + list(Path(extract_path).rglob("*.log"))
        if not log_files:
            return JSONResponse({"error": "No .txt or .log files found in the ZIP archive."}, status_code=400)

        # Parse logs into DataFrames
        all_dfs = [generate_df(log) for log in log_files]
        valid_dfs = [df for df in all_dfs if not df.empty]

        if not valid_dfs:
            return JSONResponse({"error": "No valid log entries could be parsed from the files."}, status_code=400)

        # Merge and sort logs
        merged_df = pd.concat(valid_dfs, ignore_index=True)
        merged_df.sort_values("Timestamp", inplace=True, ignore_index=True)

        # Create dynamic filename with timestamp
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"logs_{timestamp_str}.csv"
        output_file = os.path.join(tmpdir, output_filename)

        merged_df.to_csv(output_file, index=False, date_format="%Y-%m-%d %H:%M:%S")

        # Cleanup temp folder after response is sent
        background_tasks.add_task(shutil.rmtree, tmpdir)

        return FileResponse(output_file, filename=output_filename, media_type="text/csv")

    except Exception as e:
        # Ensure cleanup on error
        background_tasks.add_task(shutil.rmtree, tmpdir)
        return JSONResponse({"error": f"An unexpected error occurred: {str(e)}"}, status_code=500)


@app.get("/", response_class=HTMLResponse)
def main_form():
    """Serve the frontend upload form"""
    try:
        with open("index.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "index.html not found"})
