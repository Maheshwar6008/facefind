"""
FaceFind Configuration
Loads environment variables and provides app-wide settings.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "local")  # "local" or "production"
DOMAIN = os.getenv("DOMAIN", "localhost")

# Google Drive
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")
CREDENTIALS_PATH = str(PROJECT_ROOT / os.getenv("CREDENTIALS_PATH", "backend/credentials/credentials.json"))
TOKEN_PATH = str(PROJECT_ROOT / os.getenv("TOKEN_PATH", "backend/credentials/token.json"))

# Face Matching
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.4"))
TOP_K_RESULTS = int(os.getenv("TOP_K_RESULTS", "50"))
EMBEDDING_DIMENSION = 512

# Database & Index
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = str(DATA_DIR / "facefind.db")
FAISS_INDEX_PATH = str(DATA_DIR / "faiss_index.bin")

# Server
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "3000"))

# CORS — allowed origins
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")

# Authentication (simple shared password for cloud deployment)
APP_PASSWORD = os.getenv("APP_PASSWORD", "")

# Google Drive API scopes
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# InsightFace model
INSIGHTFACE_MODEL = "buffalo_l"

# Processing
BATCH_SIZE = 50  # Images per batch during preprocessing
MAX_IMAGE_SIZE = 1920  # Max dimension for processing (resize larger images)
