# FaceFind 🔍

**Privacy-first face recognition from Google Drive photos.** Upload a selfie and instantly find all photos where your face appears — with 100% local processing.

---

## Features

- 🖼️ **Selfie Matching** — Upload a selfie, get matching photos instantly
- 🔒 **100% Local** — Face processing runs entirely on your machine (InsightFace)
- ☁️ **Google Drive** — Syncs directly with your Drive photos
- ⚡ **Fast Search** — FAISS vector index for sub-second matching
- 📱 **Responsive UI** — Works on desktop and mobile
- 🎛️ **Adjustable Sensitivity** — Tune match threshold from strict to relaxed

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python FastAPI |
| Face AI | InsightFace (buffalo_l, 99.83% accuracy) |
| Vector Search | FAISS (cosine similarity) |
| Database | SQLite |
| Frontend | Vite + vanilla JS |
| Drive API | google-api-python-client |

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Google Cloud project with Drive API enabled

### 1. Setup Google Drive API

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use existing)
3. Enable **Google Drive API**
4. Create **OAuth 2.0 Client ID** (Desktop app)
5. Download `credentials.json` → place in `backend/credentials/`

### 2. Configure Environment

Edit `.env` in the project root:

```env
DRIVE_FOLDER_ID=your_google_drive_folder_id_here
SIMILARITY_THRESHOLD=0.4
```

To get your folder ID, open the Drive folder in browser — the ID is in the URL:
`https://drive.google.com/drive/folders/THIS_IS_THE_ID`

### 3. Install Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

### 4. Preprocess Images

Run once to sync and index all photos from Drive:

```bash
cd backend
python preprocessing.py
```

This will:
- Authenticate with Google Drive (opens browser on first run)
- Download all images from your folder
- Detect faces and generate 512-d embeddings
- Build FAISS search index

### 5. Start Backend

```bash
cd backend
python main.py
```

Backend runs at `http://localhost:8000`

### 6. Start Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`

### 7. Use It!

1. Open `http://localhost:3000`
2. Upload a selfie
3. Adjust match sensitivity if needed
4. Click **Find My Photos**
5. Download your matches!

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/match` | Upload selfie, get matches |
| GET | `/api/status` | System status & counts |
| POST | `/api/sync` | Trigger Drive sync |
| GET | `/api/download/{id}` | Download original image |
| GET | `/api/health` | Health check |

---

## Folder Structure

```
├── backend/
│   ├── main.py              # FastAPI app
│   ├── config.py            # Configuration
│   ├── database.py          # SQLite operations
│   ├── drive_service.py     # Google Drive API
│   ├── face_engine.py       # InsightFace wrapper
│   ├── match_engine.py      # FAISS matching
│   ├── preprocessing.py     # Batch processing script
│   ├── requirements.txt
│   └── credentials/         # Google OAuth files
├── frontend/
│   ├── index.html
│   ├── style.css
│   ├── main.js
│   └── vite.config.js
├── .env
└── README.md
```

---

## Security & Privacy

- ✅ All face processing runs locally (InsightFace + ONNX Runtime)
- ✅ Selfie images are never saved to disk
- ✅ Embeddings stored in local SQLite only
- ✅ Google Drive access uses read-only scope
- ⚠️ Face embeddings are biometric data — protect your database file

---

## Troubleshooting

| Issue | Fix |
|---|---|
| No face detected | Ensure clear, well-lit selfie with face visible |
| Drive auth fails | Re-download `credentials.json` from Cloud Console |
| Slow processing | Normal for first run (2000 images ≈ 20-40 min on CPU) |
| Low match quality | Try adjusting threshold slider (lower = more matches) |
