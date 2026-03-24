"""
FaceFind Face Recognition Engine
Uses InsightFace (buffalo_l) for face detection and embedding generation.
100% local processing — no external API calls.
"""
import logging
import cv2
import numpy as np
from config import INSIGHTFACE_MODEL, MAX_IMAGE_SIZE

logger = logging.getLogger(__name__)

# Lazy import to avoid slow startup
_insightface = None


def _get_insightface():
    global _insightface
    if _insightface is None:
        import insightface
        _insightface = insightface
    return _insightface


class FaceEngine:
    """Face detection and embedding extraction using InsightFace."""

    def __init__(self):
        self.model = None
        self._initialized = False

    def initialize(self):
        """
        Load the InsightFace model. Called lazily on first use.
        Downloads model weights automatically on first run (~300MB).
        """
        if self._initialized:
            return

        insightface = _get_insightface()
        logger.info(f"Loading InsightFace model: {INSIGHTFACE_MODEL}...")

        self.model = insightface.app.FaceAnalysis(
            name=INSIGHTFACE_MODEL,
            providers=["CPUExecutionProvider"]
        )
        self.model.prepare(ctx_id=-1, det_size=(640, 640))

        self._initialized = True
        logger.info("InsightFace model loaded successfully")

    def _decode_image(self, image_bytes: bytes) -> np.ndarray | None:
        """Decode image bytes to OpenCV BGR array, with resize for large images."""
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                logger.warning("Failed to decode image")
                return None

            # Resize if too large (preserving aspect ratio)
            h, w = img.shape[:2]
            if max(h, w) > MAX_IMAGE_SIZE:
                scale = MAX_IMAGE_SIZE / max(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                logger.debug(f"Resized image from {w}x{h} to {new_w}x{new_h}")

            return img

        except Exception as e:
            logger.error(f"Error decoding image: {e}")
            return None

    def detect_faces(self, image_bytes: bytes) -> list[dict]:
        """
        Detect all faces in an image and extract embeddings.

        Args:
            image_bytes: Raw image file bytes (JPEG, PNG, etc.)

        Returns:
            List of face dicts, each containing:
              - embedding: 512-dimensional float32 numpy array
              - bbox: [x, y, w, h] bounding box
              - confidence: detection confidence score (0-1)
        """
        self.initialize()

        img = self._decode_image(image_bytes)
        if img is None:
            return []

        try:
            faces = self.model.get(img)
        except Exception as e:
            logger.error(f"Face detection failed: {e}")
            return []

        results = []
        for face in faces:
            # InsightFace returns bbox as [x1, y1, x2, y2]
            x1, y1, x2, y2 = face.bbox
            results.append({
                "embedding": face.embedding,  # numpy array, 512-d
                "bbox": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
                "confidence": float(face.det_score)
            })

        logger.debug(f"Detected {len(results)} face(s)")
        return results

    def get_selfie_embedding(self, image_bytes: bytes) -> np.ndarray | None:
        """
        Extract the primary face embedding from a selfie.
        Expects exactly one face; if multiple, uses the largest/most confident.

        Args:
            image_bytes: Raw selfie image bytes

        Returns:
            512-d numpy embedding vector, or None if no face found.
        """
        faces = self.detect_faces(image_bytes)

        if not faces:
            logger.warning("No face detected in selfie")
            return None

        if len(faces) == 1:
            return faces[0]["embedding"]

        # Multiple faces: pick the one with highest confidence
        best = max(faces, key=lambda f: f["confidence"])
        logger.info(f"Multiple faces in selfie ({len(faces)}), using best (confidence={best['confidence']:.3f})")
        return best["embedding"]


# Singleton instance
face_engine = FaceEngine()
