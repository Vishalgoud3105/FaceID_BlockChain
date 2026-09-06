"""Face detection and encoding with InsightFace buffalo_l.

Follows the same shape as the reference FR service: one FaceAnalysis instance
loaded once at startup, ArcFace embeddings L2-normalised before use, and every
call made from a worker thread because ONNX inference blocks.

Two deliberate differences from that reference:

  * No anti-spoof / liveness pass. That model classifies still photographs as
    spoofs by design, which is exactly what this pipeline is fed.
  * Multiple faces are not rejected. The reference is an attendance system where
    ambiguity is dangerous; here, arbitrary photos routinely contain bystanders,
    so the largest face is selected and `face_count` is reported honestly.

The raw embedding never leaves this process. Only sha256(embedding) is exposed
for anchoring -- a face vector on a permanent public ledger is irreversible.
"""
import hashlib
from typing import Any

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from app.config import MIN_FACE_SCORE

_face_app: FaceAnalysis | None = None


class FaceError(ValueError):
    """No usable face in the supplied image."""


def load_model() -> FaceAnalysis:
    """Load buffalo_l once. Downloads the model pack on first run (~300 MB)."""
    global _face_app
    if _face_app is None:
        app = FaceAnalysis(
            name="buffalo_l",
            allowed_modules=["detection", "recognition"],
            providers=["CPUExecutionProvider"],
        )
        # 640 rather than the reference 320: these are single stills, so accuracy
        # matters more than throughput.
        app.prepare(ctx_id=0, det_size=(640, 640))
        _face_app = app
    return _face_app


def is_loaded() -> bool:
    return _face_app is not None


def encode_face(image_bytes: bytes) -> dict[str, Any]:
    """Detect the primary face and return its encoding metadata.

    Blocking (ONNX inference) -- always call via run_in_executor.
    Raises FaceError when there is no usable face.
    """
    app = load_model()

    buf = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise FaceError("could not decode the image (unsupported or corrupt file)")

    faces = app.get(img)
    if not faces:
        raise FaceError("no face detected in the image")

    # Largest bounding box wins -- the subject, not a bystander.
    def area(f):
        x1, y1, x2, y2 = f.bbox
        return float((x2 - x1) * (y2 - y1))

    face = max(faces, key=area)
    det_score = float(face.det_score)
    if det_score < MIN_FACE_SCORE:
        raise FaceError(
            f"best face scored {det_score:.3f}, below the {MIN_FACE_SCORE} threshold"
        )

    embedding = np.asarray(face.embedding, dtype=np.float32)
    embedding = embedding / (np.linalg.norm(embedding) + 1e-8)

    face_hash = "0x" + hashlib.sha256(embedding.astype(np.float32).tobytes()).hexdigest()

    h, w = img.shape[:2]
    x1, y1, x2, y2 = (round(float(v), 2) for v in face.bbox)

    return {
        "face_hash": face_hash,
        "embedding_dim": int(embedding.shape[0]),
        "embedding_model": "insightface/buffalo_l (ArcFace)",
        "normalisation": "L2",
        "bbox": [x1, y1, x2, y2],
        "det_score": round(det_score, 6),
        "face_count": len(faces),
        "image_size": [int(w), int(h)],
    }, embedding


def embedding_hash(embedding: np.ndarray) -> str:
    """sha256 of an L2-normalised float32 embedding."""
    vec = np.asarray(embedding, dtype=np.float32)
    vec = vec / (np.linalg.norm(vec) + 1e-8)
    return "0x" + hashlib.sha256(vec.astype(np.float32).tobytes()).hexdigest()
