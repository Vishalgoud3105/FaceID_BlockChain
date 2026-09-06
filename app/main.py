"""FastAPI surface over the pipeline.

Hosting is not required by the task -- the CLI in scripts/run_pipeline.py is the
canonical demo. This exists because it makes each stage inspectable and lets the
verification endpoint be re-run against a record at any time.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app import chain, config, face, pipeline

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the face model once at boot rather than on the first request.
    print("[startup] loading InsightFace buffalo_l ...")
    face.load_model()
    print("[startup] ready")
    yield
    pipeline.executor.shutdown(wait=False)


app = FastAPI(
    title="Face ID + Blockchain Verification",
    description=(
        "Detects and encodes a face, finds a real matching social media post via "
        "genuine reverse-image search, and anchors that match on Base Sepolia as a "
        "tamper-evident record."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


@app.get("/api/health")
async def health():
    return {
        "face_model_loaded": face.is_loaded(),
        "missing_config": config.missing_keys(),
        "search_provider": {
            "serpapi_google_lens": bool(config.SERPAPI_KEY),
        },
        "chain": chain.status(),
    }


@app.post("/api/verify")
async def verify_image(
    image: UploadFile = File(..., description="Photo containing a face"),
    image_url: str = Form(
        ...,
        description=(
            "Public URL of this same image. Required: Google Lens cannot search "
            "local bytes, and the photo is never auto-uploaded anywhere. The "
            "pipeline confirms this URL shows the same face before searching."
        ),
    ),
):
    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"image exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    try:
        result = await pipeline.run(
            data, filename=image.filename or "upload", image_url=image_url
        )
    except chain.ChainError as exc:
        raise HTTPException(status_code=502, detail=f"chain error: {exc}") from exc

    # no_face / no_social_match are legitimate outcomes, not server errors.
    return JSONResponse(result, status_code=200)


@app.get("/api/record/{record_id}")
async def verify_record(record_id: int):
    """Re-hash the stored record and compare it with the on-chain anchor."""
    try:
        return await pipeline.verify(record_id)
    except chain.ChainError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
