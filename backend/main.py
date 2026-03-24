"""
FaceFind — FastAPI Backend
Privacy-first face recognition from Google Drive photos.

Routes:
  POST /api/login        → Authenticate with shared password
  POST /api/match        → Upload selfie, get matching photos
  GET  /api/status       → Get system status (sync state, counts)
  POST /api/sync         → Trigger image sync from Google Drive
  GET  /api/download/{drive_id} → Download original image from Drive
  GET  /api/thumbnail/{drive_id} → Get thumbnail URL for an image
"""
import io
import hashlib
import secrets
import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from config import (
    BACKEND_PORT, DRIVE_FOLDER_ID, SIMILARITY_THRESHOLD,
    TOP_K_RESULTS, ALLOWED_ORIGINS, APP_PASSWORD, ENVIRONMENT
)
import database as db
from face_engine import face_engine
from match_engine import match_engine
from drive_service import DriveService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Google Drive service instance (authenticated lazily)
drive_service = DriveService()
_sync_lock = asyncio.Lock()

# Generate a session token on startup (valid until server restarts)
_valid_tokens: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info("🚀 FaceFind starting up...")
    logger.info(f"   Environment: {ENVIRONMENT}")
    logger.info(f"   Auth required: {bool(APP_PASSWORD)}")
    db.init_db()

    # Try to load existing FAISS index
    match_engine.load_index()
    logger.info(f"FAISS index: {match_engine.total_vectors} vectors loaded")

    yield

    # Shutdown
    logger.info("FaceFind shutting down")


app = FastAPI(
    title="FaceFind API",
    description="Privacy-first face recognition from Google Drive",
    version="1.0.0",
    lifespan=lifespan
)

# Auto-deploy webhook
from webhook import router as webhook_router
app.include_router(webhook_router)

# CORS — restrict to domain in production
origins = [o.strip() for o in ALLOWED_ORIGINS.split(",")]
if ENVIRONMENT == "local":
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Authentication ───────────────────────────────────────

async def verify_auth(request: Request):
    """
    Simple token-based auth for cloud deployment.
    Skipped entirely in local mode or when APP_PASSWORD is empty.
    """
    if ENVIRONMENT == "local" or not APP_PASSWORD:
        return True

    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()

    if not token or token not in _valid_tokens:
        raise HTTPException(status_code=401, detail="Unauthorized. Please login first.")

    return True


@app.post("/api/login")
async def login(request: Request):
    """
    Authenticate with the shared app password.
    Returns a session token for subsequent API calls.
    """
    try:
        body = await request.json()
        password = body.get("password", "")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    if not APP_PASSWORD:
        # No password configured, auth disabled
        return {"success": True, "token": "no-auth", "message": "Auth disabled"}

    if password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Incorrect password")

    # Generate session token
    token = secrets.token_urlsafe(32)
    _valid_tokens.add(token)

    logger.info("User authenticated successfully")
    return {"success": True, "token": token}


@app.get("/api/auth/check")
async def check_auth(request: Request):
    """Check if authentication is required and if current token is valid."""
    auth_required = ENVIRONMENT != "local" and bool(APP_PASSWORD)

    if not auth_required:
        return {"auth_required": False, "authenticated": True}

    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    is_valid = token in _valid_tokens if token else False

    return {"auth_required": True, "authenticated": is_valid}


# ─── Routes ───────────────────────────────────────────────

@app.post("/api/match")
async def match_selfie(
    request: Request,
    file: UploadFile = File(..., description="Selfie image file"),
    threshold: float = Query(default=None, description="Similarity threshold (0-1)"),
    top_k: int = Query(default=None, description="Max results to return"),
    _auth=Depends(verify_auth)
):
    """
    Upload a selfie and find matching photos from Google Drive.
    Returns ranked list of matching images with similarity scores.
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image (JPEG, PNG, etc.)")

    # Read image bytes
    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    if len(image_bytes) > 20 * 1024 * 1024:  # 20MB limit
        raise HTTPException(status_code=400, detail="File too large (max 20MB)")

    # Extract face embedding from selfie
    logger.info(f"Processing selfie: {file.filename} ({len(image_bytes)} bytes)")
    embedding = face_engine.get_selfie_embedding(image_bytes)

    if embedding is None:
        raise HTTPException(
            status_code=422,
            detail="No face detected in the uploaded image. Please upload a clear selfie with your face visible."
        )

    # Search for matches
    th = threshold if threshold is not None else SIMILARITY_THRESHOLD
    k = top_k if top_k is not None else TOP_K_RESULTS
    matches = match_engine.search(embedding, top_k=k, threshold=th)

    # Add thumbnail URLs
    for match in matches:
        if match.get("drive_id"):
            match["thumbnail_url"] = f"https://drive.google.com/thumbnail?id={match['drive_id']}&sz=s400"
            match["view_url"] = f"https://drive.google.com/uc?id={match['drive_id']}&export=view"

    return {
        "success": True,
        "total_matches": len(matches),
        "threshold": th,
        "matches": matches
    }


@app.get("/api/status")
async def get_status(_auth=Depends(verify_auth)):
    """Get current system status: sync state, image counts, index stats."""
    sync_state = db.get_sync_state()
    total_images = db.get_total_image_count()
    processed_images = db.get_processed_image_count()
    total_faces = db.get_face_count()

    return {
        "drive_folder_id": DRIVE_FOLDER_ID,
        "total_images": total_images,
        "processed_images": processed_images,
        "total_faces": total_faces,
        "index_vectors": match_engine.total_vectors,
        "last_sync": sync_state.get("last_sync"),
        "is_syncing": bool(sync_state.get("is_syncing", 0)),
        "sync_progress": sync_state.get("sync_progress", 0),
        "drive_configured": bool(DRIVE_FOLDER_ID),
    }


@app.post("/api/sync")
async def trigger_sync(incremental: bool = Query(default=True), _auth=Depends(verify_auth)):
    """
    Trigger a sync of images from Google Drive.
    This runs in the background and updates the sync state.
    """
    if _sync_lock.locked():
        return {"success": False, "message": "Sync already in progress"}

    async def run_sync():
        async with _sync_lock:
            try:
                db.update_sync_state(is_syncing=True, sync_progress=0.0)

                # Authenticate if needed
                if not drive_service.service:
                    if not drive_service.authenticate():
                        db.update_sync_state(is_syncing=False)
                        logger.error("Drive authentication failed")
                        return

                # Fetch image metadata
                modified_after = None
                if incremental:
                    state = db.get_sync_state()
                    modified_after = state.get("last_sync")

                files = drive_service.list_all_images(modified_after=modified_after)
                total_files = len(files)
                logger.info(f"Sync found {total_files} images")

                # Upsert image records
                for f in files:
                    db.upsert_image(
                        drive_id=f["id"],
                        filename=f["name"],
                        mime_type=f.get("mimeType", ""),
                        web_link=f.get("webContentLink", ""),
                        thumbnail=drive_service.get_thumbnail_url(f["id"]),
                        modified_time=f.get("modifiedTime", "")
                    )

                # Process unprocessed images
                unprocessed = db.get_unprocessed_images()
                total_unprocessed = len(unprocessed)

                for i, img in enumerate(unprocessed):
                    try:
                        image_bytes = drive_service.download_image(img["drive_id"])
                        faces = face_engine.detect_faces(image_bytes)

                        for face in faces:
                            db.store_embedding(
                                image_id=img["id"],
                                embedding=face["embedding"],
                                bbox=face["bbox"],
                                confidence=face["confidence"]
                            )
                        db.mark_image_processed(img["id"], len(faces))

                    except Exception as e:
                        logger.error(f"Error processing {img['filename']}: {e}")

                    progress = (i + 1) / max(total_unprocessed, 1)
                    db.update_sync_state(sync_progress=progress)

                # Rebuild FAISS index
                match_engine.build_index()
                match_engine.save_index()

                db.update_sync_state(
                    is_syncing=False,
                    sync_progress=1.0,
                    total_images=db.get_total_image_count(),
                    total_faces=db.get_face_count(),
                    last_sync=datetime.now(timezone.utc).isoformat()
                )
                logger.info("✅ Sync complete")

            except Exception as e:
                logger.error(f"Sync failed: {e}")
                db.update_sync_state(is_syncing=False)

    # Run sync in background
    asyncio.create_task(run_sync())

    return {
        "success": True,
        "message": "Sync started in background. Check /api/status for progress."
    }


@app.get("/api/download/{drive_id}")
async def download_image(drive_id: str, _auth=Depends(verify_auth)):
    """Download original image from Google Drive by file ID."""
    if not drive_service.service:
        if not drive_service.authenticate():
            raise HTTPException(status_code=503, detail="Google Drive not authenticated")

    try:
        image_bytes = drive_service.download_image(drive_id)
        img_record = db.get_image_by_drive_id(drive_id)
        filename = img_record["filename"] if img_record else f"{drive_id}.jpg"
        mime_type = img_record["mime_type"] if img_record else "image/jpeg"

        return StreamingResponse(
            io.BytesIO(image_bytes),
            media_type=mime_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        logger.error(f"Download error for {drive_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download image: {str(e)}")


@app.get("/api/thumbnail/{drive_id}")
async def get_thumbnail(drive_id: str, size: int = Query(default=400)):
    """Get thumbnail URL for an image."""
    return {"url": f"https://drive.google.com/thumbnail?id={drive_id}&sz=s{size}"}


# ─── Health Check ─────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "FaceFind", "environment": ENVIRONMENT}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=BACKEND_PORT, reload=True)
