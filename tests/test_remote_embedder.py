"""Tests for RemoteBGEEmbedder."""

import gzip
import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import patch

import numpy as np
import pytest

from src.archilles.embedders.remote import RemoteBGEEmbedder


class MockEmbeddingHandler(BaseHTTPRequestHandler):
    """Mock HTTP handler that returns fake embeddings."""

    # Class-level config
    token = None
    fail_count = 0  # Number of times to fail before succeeding
    _call_count = 0

    def log_message(self, format, *args):
        pass  # Suppress logs

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "model": "BAAI/bge-m3", "dimension": 1024,
                "device": "cpu", "ready": True,
            }).encode())

    def do_POST(self):
        if self.path == '/embed':
            # Check auth
            if self.token:
                auth = self.headers.get('Authorization', '')
                if auth != f'Bearer {self.token}':
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b'{"detail":"Invalid token"}')
                    return

            # Simulate failures for retry testing
            MockEmbeddingHandler._call_count += 1
            if MockEmbeddingHandler._call_count <= MockEmbeddingHandler.fail_count:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b'Server error')
                return

            # Read body
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)

            if self.headers.get('Content-Encoding') == 'gzip':
                body = gzip.decompress(body)

            data = json.loads(body)
            texts = data['texts']

            # Generate deterministic fake embeddings
            embeddings = np.random.RandomState(42).randn(len(texts), 1024).tolist()

            response = json.dumps({
                "embeddings": embeddings,
                "model": "BAAI/bge-m3",
                "dimension": 1024,
                "count": len(texts),
                "duration_seconds": 0.01,
            }).encode()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(response)


@pytest.fixture
def mock_server():
    """Start a mock embedding server on a random port."""
    MockEmbeddingHandler.token = None
    MockEmbeddingHandler.fail_count = 0
    MockEmbeddingHandler._call_count = 0

    server = HTTPServer(('127.0.0.1', 0), MockEmbeddingHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, port
    server.shutdown()


class TestRemoteBGEEmbedder:
    def test_basic_embedding(self, mock_server):
        server, port = mock_server
        embedder = RemoteBGEEmbedder(host='127.0.0.1', port=port, use_gzip=False)

        result = embedder.embed_batch(["Hello world", "Test text"])
        assert result.embeddings.shape == (2, 1024)
        assert result.texts_count == 2
        assert result.model_name == "BAAI/bge-m3"
        assert result.device == "remote"

    def test_empty_batch(self, mock_server):
        _, port = mock_server
        embedder = RemoteBGEEmbedder(host='127.0.0.1', port=port)

        result = embedder.embed_batch([])
        assert result.embeddings.shape == (0, 1024)
        assert result.texts_count == 0

    def test_gzip_compression(self, mock_server):
        _, port = mock_server
        embedder = RemoteBGEEmbedder(host='127.0.0.1', port=port, use_gzip=True)

        result = embedder.embed_batch(["Compressed text"])
        assert result.embeddings.shape == (1, 1024)

    def test_bearer_auth(self, mock_server):
        _, port = mock_server
        MockEmbeddingHandler.token = "test-secret"

        # Without token should fail
        embedder_no_auth = RemoteBGEEmbedder(
            host='127.0.0.1', port=port, use_gzip=False, max_retries=1,
        )
        with pytest.raises(ConnectionError):
            embedder_no_auth.embed_batch(["test"])

        # With correct token should work
        embedder = RemoteBGEEmbedder(
            host='127.0.0.1', port=port, token="test-secret", use_gzip=False,
        )
        result = embedder.embed_batch(["test"])
        assert result.embeddings.shape == (1, 1024)

    def test_batching(self, mock_server):
        _, port = mock_server
        embedder = RemoteBGEEmbedder(
            host='127.0.0.1', port=port, batch_size=3, use_gzip=False,
        )

        texts = [f"text {i}" for i in range(7)]
        result = embedder.embed_batch(texts)
        assert result.embeddings.shape == (7, 1024)

    def test_health_check(self, mock_server):
        _, port = mock_server
        embedder = RemoteBGEEmbedder(host='127.0.0.1', port=port)
        embedder.load_model()
        assert embedder._server_info is not None
        assert embedder._server_info['model'] == 'BAAI/bge-m3'

    def test_capabilities(self):
        embedder = RemoteBGEEmbedder(host='localhost', port=9999)
        caps = embedder.capabilities
        assert caps.embedding_dimension == 1024
        assert caps.model_name == "BAAI/bge-m3"

    def test_name(self):
        embedder = RemoteBGEEmbedder(host='localhost')
        assert embedder.name == "bge-m3-remote"

    def test_single_embed(self, mock_server):
        _, port = mock_server
        embedder = RemoteBGEEmbedder(host='127.0.0.1', port=port, use_gzip=False)
        vec = embedder.embed("single text")
        assert vec.shape == (1024,)

    def test_unreachable_server(self):
        embedder = RemoteBGEEmbedder(
            host='127.0.0.1', port=1, max_retries=1, timeout=1,
        )
        with pytest.raises(ConnectionError):
            embedder.embed_batch(["test"])
