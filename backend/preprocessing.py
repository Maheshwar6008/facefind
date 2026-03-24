"""
FaceFind Batch Preprocessing Script
Fetches images from Google Drive, extracts face embeddings, stores in SQLite + FAISS.
Run this once to process all images, then incrementally for new images.

Usage:
    python preprocessing.py           # Full sync
    python preprocessing.py --incremental  # Only new/modified images
"""
import sys
import time
import logging
import argparse
from datetime import datetime, timezone

from config import DRIVE_FOLDER_ID, BATCH_SIZE
from drive_service import DriveService
from face_engine import face_engine
from match_engine import match_engine
import database as db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def sync_images_from_drive(drive: DriveService, incremental: bool = False):
    """
    Fetch image metadata from Google Drive and store in database.
    Returns the number of new images added.
    """
    modified_after = None
    if incremental:
        state = db.get_sync_state()
        modified_after = state.get("last_sync")
        if modified_after:
            logger.info(f"Incremental sync: fetching images modified after {modified_after}")
        else:
            logger.info("No previous sync found, doing full sync")

    logger.info(f"Listing images from Drive folder: {DRIVE_FOLDER_ID}")
    files = drive.list_all_images(modified_after=modified_after)
    logger.info(f"Found {len(files)} image(s) in Drive")

    new_count = 0
    for f in files:
        image_id = db.upsert_image(
            drive_id=f["id"],
            filename=f["name"],
            mime_type=f.get("mimeType", ""),
            web_link=f.get("webContentLink", ""),
            thumbnail=drive.get_thumbnail_url(f["id"]),
            modified_time=f.get("modifiedTime", "")
        )
        new_count += 1

    total = db.get_total_image_count()
    db.update_sync_state(total_images=total)
    logger.info(f"Synced {new_count} images. Total in DB: {total}")
    return new_count


def process_unprocessed_images(drive: DriveService):
    """
    Process all unprocessed images: download, detect faces, store embeddings.
    """
    unprocessed = db.get_unprocessed_images()
    total = len(unprocessed)

    if total == 0:
        logger.info("No unprocessed images found")
        return

    logger.info(f"Processing {total} unprocessed image(s)...")
    db.update_sync_state(is_syncing=True, sync_progress=0.0)

    total_faces = 0
    errors = 0

    for i, img in enumerate(unprocessed):
        try:
            # Download image from Drive
            logger.info(f"[{i+1}/{total}] Downloading: {img['filename']}")
            image_bytes = drive.download_image(img["drive_id"])

            # Detect faces and extract embeddings
            faces = face_engine.detect_faces(image_bytes)

            # Store each face embedding
            for face in faces:
                db.store_embedding(
                    image_id=img["id"],
                    embedding=face["embedding"],
                    bbox=face["bbox"],
                    confidence=face["confidence"]
                )

            db.mark_image_processed(img["id"], len(faces))
            total_faces += len(faces)

            if faces:
                logger.info(f"  → Found {len(faces)} face(s)")
            else:
                logger.info(f"  → No faces detected")

        except Exception as e:
            logger.error(f"  → Error processing {img['filename']}: {e}")
            errors += 1

        # Update progress
        progress = (i + 1) / total
        db.update_sync_state(sync_progress=progress)

        # Brief pause to avoid overwhelming Google Drive API
        if (i + 1) % BATCH_SIZE == 0:
            logger.info(f"  Batch complete ({i+1}/{total}), pausing briefly...")
            time.sleep(1)

    # Finalize
    db.update_sync_state(
        is_syncing=False,
        sync_progress=1.0,
        total_faces=db.get_face_count(),
        last_sync=datetime.now(timezone.utc).isoformat()
    )

    processed_count = db.get_processed_image_count()
    logger.info(
        f"\nProcessing complete!"
        f"\n  Images processed: {total - errors}/{total}"
        f"\n  Faces found: {total_faces}"
        f"\n  Errors: {errors}"
        f"\n  Total processed in DB: {processed_count}"
    )


def build_faiss_index():
    """Build and save FAISS index from all stored embeddings."""
    logger.info("Building FAISS index...")
    match_engine.build_index()
    match_engine.save_index()
    logger.info(f"FAISS index built with {match_engine.total_vectors} vectors")


def main():
    parser = argparse.ArgumentParser(description="FaceFind Image Preprocessing")
    parser.add_argument(
        "--incremental", action="store_true",
        help="Only process new/modified images since last sync"
    )
    parser.add_argument(
        "--index-only", action="store_true",
        help="Only rebuild FAISS index (skip Drive sync)"
    )
    args = parser.parse_args()

    # Initialize database
    db.init_db()

    if args.index_only:
        build_faiss_index()
        return

    # Authenticate with Google Drive
    drive = DriveService()
    if not drive.authenticate():
        logger.error("Failed to authenticate with Google Drive. Exiting.")
        sys.exit(1)

    # Step 1: Sync image metadata from Drive
    sync_images_from_drive(drive, incremental=args.incremental)

    # Step 2: Process unprocessed images (download + face detection)
    process_unprocessed_images(drive)

    # Step 3: Build FAISS index
    build_faiss_index()

    logger.info("\n✅ Preprocessing complete! You can now start the server.")


if __name__ == "__main__":
    main()
