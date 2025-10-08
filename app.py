from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
import pandas as pd
import zipfile, os, json, tempfile, shutil
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

app = FastAPI()

# ---- Timezone config ----
LOCAL_TZ = ZoneInfo("Asia/Colombo")   # IST (UTC+05:30)
ASSUME_LOGS_ARE_UTC = True            # If True, convert parsed timestamps UTC -> IST

# ---- Health check (GET + HEAD) ----
@app.get("/health", tags=["Monitoring"])
@app.head("/health", tags=["Monitoring"])
async def health_check():
    """Health check endpoint to confirm the server is running and responsive."""
    return {"status": "healthy", "message": "Server is running"}


def generate_df(file_path: Path) -> pd.DataFrame:
    rows = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                # Example expected shape:
                # [2025-10-08 12:34:56 - INFO] [something ...] ... ] {"json":"payload"}
                first_part, rest = line.split("] [", 1)
                timestamp_str, _ = first_part.strip("[]").split(" - ", 1)

                # The remainder up to the JSON payload
                rest, json_payload = rest.rsplit("] ", 1)
                parts = rest.split()
                # Defensive: make sure we have enough parts
                if len(parts) < 5:
                    raise ValueError("Not enough parts in log line to parse URL/status/rt_ms")

                url, status, rt_ms = parts[2:5]

                data = json.loads(json_payload)

                try:
                    stayed_time = float(rt_ms) if status == "200" else None
                except ValueError:
                    stayed_time = None

                rows.append(
                    {
                        "Service Id":  data.get("sid"),
                        "Vno":         data.get("vno"),
                        "Ano":         data.get("ano"),
                        "Rt Area":     data.get("rtarea"),
                        "URL":         url,
                        "Stayed Time": stayed_time,
                        "App Version": data.get("appVer"),
                        "Timestamp":   timestamp_str,  # keep raw str; we’ll parse below in bulk
                    }
                )
            except Exception as e:
                # Log warning but skip malformed line
                print(f"Warning: Skipping malformed log line. Error: {e}")
                continue

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Parse timestamps and (optionally) convert UTC -> IST
    if ASSUME_LOGS_ARE_UTC:
        # Treat raw strings as UTC, then convert to IST and drop tzinfo for a clean local time column
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce", utc=True)
        df.dropna(subset=["Timestamp"], inplace=True)
        df["Timestamp"] = df["Timestamp"].dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)
    else:
        # If your logs are already local time strings (IST or other), just parse
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        df.dropna(subset=["Timestamp"], inplace=True)

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
        extract_path = os.path.join(tmpdir, "extracted")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)

        # Collect .txt and .log files (including nested dirs)
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

        # Create dynamic filename with local (IST) time
        timestamp_str = datetime.now(LOCAL_TZ).strftime("%Y%m%d_%H%M%S")
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
