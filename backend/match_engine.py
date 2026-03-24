"""
FaceFind Matching Engine
FAISS-powered vector similarity search for face embeddings.
"""
import os
import logging
import numpy as np
import faiss
from config import FAISS_INDEX_PATH, EMBEDDING_DIMENSION, SIMILARITY_THRESHOLD, TOP_K_RESULTS
import database as db

logger = logging.getLogger(__name__)


class MatchEngine:
    """FAISS-based face matching engine with cosine similarity."""

    def __init__(self, dimension: int = EMBEDDING_DIMENSION):
        self.dimension = dimension
        self.index = None
        self.face_ids = []    # Maps FAISS index position → face_embedding.id
        self.image_ids = []   # Maps FAISS index position → image.id
        self._loaded = False

    def build_index(self):
        """
        Build FAISS index from all stored embeddings in the database.
        Uses IndexFlatIP (inner product) with L2-normalized vectors = cosine similarity.
        """
        embeddings_data = db.get_all_embeddings()

        if not embeddings_data:
            logger.warning("No embeddings found in database. Index is empty.")
            self.index = faiss.IndexFlatIP(self.dimension)
            self.face_ids = []
            self.image_ids = []
            self._loaded = True
            return

        self.face_ids = [e[0] for e in embeddings_data]
        self.image_ids = [e[1] for e in embeddings_data]
        vectors = np.array([e[2] for e in embeddings_data]).astype("float32")

        # Normalize for cosine similarity via inner product
        faiss.normalize_L2(vectors)

        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(vectors)

        self._loaded = True
        logger.info(f"FAISS index built with {self.index.ntotal} face vectors")

    def save_index(self):
        """Persist FAISS index to disk."""
        if self.index and self.index.ntotal > 0:
            faiss.write_index(self.index, FAISS_INDEX_PATH)

            # Save mappings alongside
            mapping_path = FAISS_INDEX_PATH + ".meta.npz"
            np.savez(
                mapping_path,
                face_ids=np.array(self.face_ids),
                image_ids=np.array(self.image_ids)
            )
            logger.info(f"FAISS index saved to {FAISS_INDEX_PATH}")

    def load_index(self) -> bool:
        """Load FAISS index from disk. Returns True if successful."""
        mapping_path = FAISS_INDEX_PATH + ".meta.npz"

        if not os.path.exists(FAISS_INDEX_PATH) or not os.path.exists(mapping_path):
            logger.info("No saved FAISS index found, will need to build")
            return False

        try:
            self.index = faiss.read_index(FAISS_INDEX_PATH)
            meta = np.load(mapping_path)
            self.face_ids = meta["face_ids"].tolist()
            self.image_ids = meta["image_ids"].tolist()
            self._loaded = True
            logger.info(f"FAISS index loaded: {self.index.ntotal} vectors")
            return True
        except Exception as e:
            logger.error(f"Failed to load FAISS index: {e}")
            return False

    def ensure_loaded(self):
        """Ensure the index is loaded (from disk or freshly built)."""
        if self._loaded:
            return
        if not self.load_index():
            self.build_index()
            self.save_index()

    def search(self, query_embedding: np.ndarray, top_k: int = None,
               threshold: float = None) -> list[dict]:
        """
        Search for matching faces using cosine similarity.

        Args:
            query_embedding: 512-d face embedding from selfie
            top_k: Maximum number of results (default from config)
            threshold: Minimum similarity score (default from config)

        Returns:
            List of match dicts with image details and scores,
            deduplicated by image (best face match per image).
        """
        self.ensure_loaded()

        if self.index is None or self.index.ntotal == 0:
            logger.warning("FAISS index is empty, no matches possible")
            return []

        top_k = top_k or TOP_K_RESULTS
        threshold = threshold or SIMILARITY_THRESHOLD

        # Prepare query vector
        query = query_embedding.reshape(1, -1).astype("float32")
        faiss.normalize_L2(query)

        # Search
        k = min(top_k * 3, self.index.ntotal)  # Search more to allow dedup
        scores, indices = self.index.search(query, k)

        # Collect results, deduplicate by image (keep best score per image)
        image_best = {}  # image_id → best_score
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or score < threshold:
                continue

            image_id = self.image_ids[idx]
            face_id = self.face_ids[idx]

            if image_id not in image_best or score > image_best[image_id]["score"]:
                image_best[image_id] = {
                    "image_id": image_id,
                    "face_id": face_id,
                    "score": float(score)
                }

        # Sort by score descending
        matches = sorted(image_best.values(), key=lambda m: m["score"], reverse=True)

        # Limit to top_k
        matches = matches[:top_k]

        # Enrich with image metadata
        if matches:
            image_ids = [m["image_id"] for m in matches]
            images = {img["id"]: img for img in db.get_images_by_ids(image_ids)}

            for match in matches:
                img = images.get(match["image_id"], {})
                match["filename"] = img.get("filename", "unknown")
                match["drive_id"] = img.get("drive_id", "")
                match["thumbnail"] = img.get("thumbnail", "")
                match["web_link"] = img.get("web_link", "")

        logger.info(f"Found {len(matches)} matching images (threshold={threshold})")
        return matches

    @property
    def total_vectors(self) -> int:
        """Number of face vectors in the index."""
        if self.index:
            return self.index.ntotal
        return 0


# Singleton instance
match_engine = MatchEngine()
