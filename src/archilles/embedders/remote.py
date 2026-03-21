"""
ARCHILLES Remote BGE Embedder

HTTP client that implements the TextEmbedder interface by sending texts
to a remote embedding server (scripts/embedding_server.py).
"""

import gzip
import json
import time
import logging
from typing import List, Optional

import numpy as np

from .base import TextEmbedder, EmbedderCapabilities, EmbeddingResult

logger = logging.getLogger(__name__)

try:
    import urllib.request
    import urllib.error
    _HTTP_AVAILABLE = True
except ImportError:
    _HTTP_AVAILABLE = False


class RemoteBGEEmbedder(TextEmbedder):
    """Sends text batches via HTTP to a remote embedding server, receives vectors."""

    def __init__(
        self,
        host: str,
        port: int = 8000,
        token: Optional[str] = None,
        batch_size: int = 100,
        timeout: int = 120,
        use_gzip: bool = True,
        max_retries: int = 3,
    ):
        self._host = host.rstrip("/")
        if not self._host.startswith("http"):
            self._host = f"http://{self._host}"
        if port and f":{port}" not in self._host:
            self._host = f"{self._host}:{port}"
        self._token = token
        self._batch_size = batch_size
        self._timeout = timeout
        self._use_gzip = use_gzip
        self._max_retries = max_retries
        self._server_info = None

    @property
    def name(self) -> str:
        return "bge-m3-remote"

    @property
    def capabilities(self) -> EmbedderCapabilities:
        return EmbedderCapabilities(
            model_name="BAAI/bge-m3",
            embedding_dimension=1024,
            max_tokens=8192,
            max_batch_size=self._batch_size,
            supports_cuda=False,
            supports_mps=False,
            supports_batching=True,
            normalized_embeddings=True,
            quality_tier=9,
            speed_tier=7,
            model_size_mb=0,
            vram_required_mb=0,
        )

    @property
    def device(self) -> str:
        return "remote"

    @property
    def is_loaded(self) -> bool:
        return True

    def load_model(self) -> None:
        self._check_health()

    def unload_model(self) -> None:
        pass

    def _check_health(self):
        url = f"{self._host}/health"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                self._server_info = json.loads(resp.read())
                logger.info(f"Remote server: {self._server_info}")
        except Exception as e:
            raise ConnectionError(f"Cannot reach embedding server at {url}: {e}")

    def _post_embed(self, texts: List[str]) -> List[List[float]]:
        url = f"{self._host}/embed"
        body = json.dumps({"texts": texts}).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        if self._use_gzip:
            body = gzip.compress(body)
            headers["Content-Encoding"] = "gzip"

        headers["Accept-Encoding"] = "gzip"

        last_err = None
        for attempt in range(1, self._max_retries + 1):
            try:
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    raw = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    data = json.loads(raw)
                    return data["embeddings"]
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                last_err = e
                if attempt < self._max_retries:
                    wait = 2 ** attempt
                    logger.warning(f"Attempt {attempt}/{self._max_retries} failed: {e}. Retrying in {wait}s...")
                    time.sleep(wait)

        raise ConnectionError(f"Failed after {self._max_retries} attempts: {last_err}")

    def embed_batch(self, texts: List[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(
                embeddings=np.array([], dtype=np.float32).reshape(0, 1024),
                model_name="BAAI/bge-m3",
                embedding_dimension=1024,
                texts_count=0,
                duration_seconds=0.0,
                device="remote",
            )

        start = time.time()
        all_embeddings = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            vectors = self._post_embed(batch)
            all_embeddings.extend(vectors)

        duration = time.time() - start
        embeddings_array = np.array(all_embeddings, dtype=np.float32)

        return EmbeddingResult(
            embeddings=embeddings_array,
            model_name="BAAI/bge-m3",
            embedding_dimension=1024,
            texts_count=len(texts),
            duration_seconds=duration,
            device="remote",
            metadata={"host": self._host, "batch_size": self._batch_size},
        )
