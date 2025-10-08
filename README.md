# 📊 Log to CSV Converter

A simple **FastAPI web service** that takes a ZIP file of `.log` / `.txt` files, parses them, and generates a merged, timestamp-sorted **CSV** for download.

Hosted on [Render](https://render.com), so colleagues can upload their ZIPs directly via the browser — no manual Colab runs needed.

---

## 🚀 Features

* Upload a `.zip` containing `.log` or `.txt` files.
* Parses logs line by line, extracting structured fields:

  * **Service Id**
  * **Vno**
  * **Ano**
  * **Rt Area**
  * **URL**
  * **Stayed Time**
  * **App Version**
  * **Timestamp**
* Merges all logs into a single dataframe.
* Sorts rows by timestamp.
* Returns a downloadable **CSV file**.

---

## 🖥 How It Works

1. Go to your deployment URL (e.g. `https://logs-conversion.onrender.com`).
2. Upload a `.zip` file containing log files.
3. The service will:

   * Extract logs
   * Parse valid entries
   * Merge & sort them
4. Your browser will download the result as **`merged_sorted.csv`**.

---

## 📦 Project Structure

```
.
├── app.py              # Main FastAPI app
├── requirements.txt    # Dependencies
└── README.md           # Documentation
```

---

## 🔧 Local Development

If you want to run locally:

```bash
# Clone the repo
git clone https://github.com/<your-org>/<repo-name>.git
cd <repo-name>

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn app:app --reload --port 8000
```

Open: [http://127.0.0.1:8000](http://127.0.0.1:8000)

* Upload page → `/`
* API docs → `/docs`
* Upload endpoint → `/upload`

---

## 📤 Deployment on Render

1. Push this repo to GitHub.
2. On Render:

   * **New → Web Service**
   * Build Command:

     ```bash
     pip install -r requirements.txt
     ```
   * Start Command:

     ```bash
     uvicorn app:app --host 0.0.0.0 --port 10000
     ```
3. Render will give you a public URL (e.g. `https://logs-conversion.onrender.com`).

---

## ⚠️ Notes

* Only `.zip` uploads are supported.
* If no valid logs are parsed, you’ll see an error message.
* CSV filename defaults to `merged_sorted.csv` (you can customize if needed).

---

## ✅ Tech Stack

* **FastAPI** — lightweight web framework
* **Pandas** — log parsing & CSV generation
* **Uvicorn** — ASGI server
* **Render** — hosting

---

Would you like me to also add a **“Usage GIF” or screenshots section** in the README (so your colleagues see exactly what the upload page looks like)?
