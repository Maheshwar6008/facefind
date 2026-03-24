"""
FaceFind Database Layer
SQLite setup, table creation, and CRUD operations for images and face embeddings.
"""
import sqlite3
import json
import numpy as np
from pathlib import Path
from config import DATABASE_PATH, EMBEDDING_DIMENSION


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS images (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            drive_id    TEXT UNIQUE NOT NULL,
            filename    TEXT NOT NULL,
            mime_type   TEXT,
            web_link    TEXT,
            thumbnail   TEXT,
            modified_time TEXT,
            processed   BOOLEAN DEFAULT 0,
            face_count  INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS face_embeddings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id    INTEGER NOT NULL,
            embedding   BLOB NOT NULL,
            bbox_x      REAL,
            bbox_y      REAL,
            bbox_w      REAL,
            bbox_h      REAL,
            confidence  REAL,
            FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sync_state (
            id              INTEGER PRIMARY KEY DEFAULT 1,
            last_sync       TIMESTAMP,
            total_images    INTEGER DEFAULT 0,
            total_faces     INTEGER DEFAULT 0,
            is_syncing      BOOLEAN DEFAULT 0,
            sync_progress   REAL DEFAULT 0.0
        );

        INSERT OR IGNORE INTO sync_state (id) VALUES (1);

        CREATE INDEX IF NOT EXISTS idx_images_drive_id ON images(drive_id);
        CREATE INDEX IF NOT EXISTS idx_images_processed ON images(processed);
        CREATE INDEX IF NOT EXISTS idx_face_embeddings_image_id ON face_embeddings(image_id);
    """)
    conn.commit()
    conn.close()


# ─── Image CRUD ───────────────────────────────────────────

def upsert_image(drive_id: str, filename: str, mime_type: str,
                 web_link: str = None, thumbnail: str = None,
                 modified_time: str = None) -> int:
    """Insert or update an image record. Returns the image ID."""
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO images (drive_id, filename, mime_type, web_link, thumbnail, modified_time)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(drive_id) DO UPDATE SET
            filename = excluded.filename,
            mime_type = excluded.mime_type,
            web_link = excluded.web_link,
            thumbnail = excluded.thumbnail,
            modified_time = excluded.modified_time
        RETURNING id
    """, (drive_id, filename, mime_type, web_link, thumbnail, modified_time))
    row = cursor.fetchone()
    image_id = row[0]
    conn.commit()
    conn.close()
    return image_id


def mark_image_processed(image_id: int, face_count: int):
    """Mark an image as processed with the number of faces found."""
    conn = get_connection()
    conn.execute(
        "UPDATE images SET processed = 1, face_count = ? WHERE id = ?",
        (face_count, image_id)
    )
    conn.commit()
    conn.close()


def get_unprocessed_images() -> list[dict]:
    """Get all images that haven't been processed yet."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, drive_id, filename, mime_type FROM images WHERE processed = 0"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_image_by_id(image_id: int) -> dict | None:
    """Get image details by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_image_by_drive_id(drive_id: str) -> dict | None:
    """Get image details by Drive file ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM images WHERE drive_id = ?", (drive_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_images_by_ids(image_ids: list[int]) -> list[dict]:
    """Get multiple images by their IDs."""
    if not image_ids:
        return []
    conn = get_connection()
    placeholders = ",".join(["?"] * len(image_ids))
    rows = conn.execute(
        f"SELECT * FROM images WHERE id IN ({placeholders})", image_ids
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Face Embedding CRUD ──────────────────────────────────

def store_embedding(image_id: int, embedding: np.ndarray,
                    bbox: list[float] = None, confidence: float = None) -> int:
    """Store a face embedding for an image. Returns the embedding ID."""
    conn = get_connection()
    embedding_blob = embedding.astype(np.float32).tobytes()
    bbox_x, bbox_y, bbox_w, bbox_h = bbox if bbox else (None, None, None, None)
    cursor = conn.execute("""
        INSERT INTO face_embeddings (image_id, embedding, bbox_x, bbox_y, bbox_w, bbox_h, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING id
    """, (image_id, embedding_blob, bbox_x, bbox_y, bbox_w, bbox_h, confidence))
    emb_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return emb_id


def get_all_embeddings() -> list[tuple[int, int, np.ndarray]]:
    """Load all face embeddings. Returns list of (face_id, image_id, embedding_vector)."""
    conn = get_connection()
    rows = conn.execute("SELECT id, image_id, embedding FROM face_embeddings").fetchall()
    conn.close()
    results = []
    for row in rows:
        vec = np.frombuffer(row["embedding"], dtype=np.float32)
        results.append((row["id"], row["image_id"], vec))
    return results


def get_face_count() -> int:
    """Get total number of stored face embeddings."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM face_embeddings").fetchone()[0]
    conn.close()
    return count


def delete_embeddings_for_image(image_id: int):
    """Delete all embeddings for a specific image (for reprocessing)."""
    conn = get_connection()
    conn.execute("DELETE FROM face_embeddings WHERE image_id = ?", (image_id,))
    conn.commit()
    conn.close()


# ─── Sync State ───────────────────────────────────────────

def get_sync_state() -> dict:
    """Get current sync state."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM sync_state WHERE id = 1").fetchone()
    conn.close()
    return dict(row) if row else {}


def update_sync_state(last_sync: str = None, total_images: int = None,
                      total_faces: int = None, is_syncing: bool = None,
                      sync_progress: float = None):
    """Update sync state fields (only non-None values are updated)."""
    conn = get_connection()
    updates = []
    values = []
    if last_sync is not None:
        updates.append("last_sync = ?")
        values.append(last_sync)
    if total_images is not None:
        updates.append("total_images = ?")
        values.append(total_images)
    if total_faces is not None:
        updates.append("total_faces = ?")
        values.append(total_faces)
    if is_syncing is not None:
        updates.append("is_syncing = ?")
        values.append(1 if is_syncing else 0)
    if sync_progress is not None:
        updates.append("sync_progress = ?")
        values.append(sync_progress)
    if updates:
        conn.execute(f"UPDATE sync_state SET {', '.join(updates)} WHERE id = 1", values)
        conn.commit()
    conn.close()


def get_total_image_count() -> int:
    """Get total number of images in the database."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    conn.close()
    return count


def get_processed_image_count() -> int:
    """Get number of processed images."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM images WHERE processed = 1").fetchone()[0]
    conn.close()
    return count
