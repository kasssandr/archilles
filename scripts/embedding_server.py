"""
ARCHILLES Remote Embedding Server

Standalone FastAPI server for BGE-M3 embedding on a GPU machine.

Usage:
    EMBEDDING_API_TOKEN=secret uvicorn embedding_server:app --host 0.0.0.0 --port 8000

Dependencies (install on GPU machine):
    pip install fastapi uvicorn sentence-transformers torch
"""

import gzip as gzip_module
import json
import os
import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from starlette.middleware.gzip import GZipMiddleware

logger = logging.getLogger(__name__)

API_TOKEN = os.environ.get("EMBEDDING_API_TOKEN")

_model = None
_model_name = "BAAI/bge-m3"
_dimension = 1024


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading {_model_name} on {device}...")
        _model = SentenceTransformer(_model_name, device=device)
        logger.info("Model loaded.")
    return _model


def _check_auth(authorization: str | None):
    if not API_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    if authorization[7:] != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("Pre-loading model...")
    _get_model()
    logger.info("Server ready.")
    yield


# --- App ---

app = FastAPI(title="ARCHILLES Embedding Server", lifespan=_lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.get("/health")
def health():
    import torch
    return {
        "model": _model_name,
        "dimension": _dimension,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "ready": _model is not None,
    }


@app.post("/embed")
async def embed(
    request: Request,
    authorization: str | None = Header(None),
):
    _check_auth(authorization)

    body = await request.body()
    if request.headers.get("content-encoding") == "gzip":
        body = gzip_module.decompress(body)
    data = json.loads(body)
    texts = data.get("texts", [])

    if not texts:
        return {"embeddings": [], "model": _model_name, "dimension": _dimension,
                "count": 0, "duration_seconds": 0.0}

    if len(texts) > 10000:
        raise HTTPException(status_code=400, detail="Max 10000 texts per request")

    model = _get_model()
    start = time.time()
    vectors = model.encode(
        texts,
        batch_size=64,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    duration = time.time() - start

    return {
        "embeddings": vectors.tolist(),
        "model": _model_name,
        "dimension": _dimension,
        "count": len(texts),
        "duration_seconds": round(duration, 3),
    }
