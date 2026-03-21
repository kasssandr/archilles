"""
ARCHILLES Remote Embedding Server

Standalone FastAPI server for BGE-M3 embedding on a GPU machine.

Usage:
    EMBEDDING_API_TOKEN=secret uvicorn embedding_server:app --host 0.0.0.0 --port 8000

Dependencies (install on GPU machine):
    pip install fastapi uvicorn sentence-transformers torch
"""

import os
import time
import logging

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import List, Optional

logger = logging.getLogger(__name__)

API_TOKEN = os.environ.get("EMBEDDING_API_TOKEN")

# --- Pydantic models ---

class EmbedRequest(BaseModel):
    texts: List[str]

class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    model: str
    dimension: int
    count: int
    duration_seconds: float

# --- App ---

app = FastAPI(title="ARCHILLES Embedding Server")

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


def _check_auth(authorization: Optional[str]):
    if not API_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    if authorization[7:] != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


@app.get("/health")
def health():
    import torch
    return {
        "model": _model_name,
        "dimension": _dimension,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "ready": _model is not None,
    }


@app.post("/embed", response_model=EmbedResponse)
def embed(
    request: EmbedRequest,
    authorization: Optional[str] = Header(None),
):
    _check_auth(authorization)

    if not request.texts:
        return EmbedResponse(
            embeddings=[], model=_model_name, dimension=_dimension,
            count=0, duration_seconds=0.0,
        )

    if len(request.texts) > 10000:
        raise HTTPException(status_code=400, detail="Max 10000 texts per request")

    model = _get_model()
    start = time.time()
    vectors = model.encode(
        request.texts,
        batch_size=64,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    duration = time.time() - start

    return EmbedResponse(
        embeddings=vectors.tolist(),
        model=_model_name,
        dimension=_dimension,
        count=len(request.texts),
        duration_seconds=round(duration, 3),
    )


@app.on_event("startup")
def startup():
    logger.info("Pre-loading model...")
    _get_model()
    logger.info("Server ready.")
