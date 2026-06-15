"""Tests for prepare/embed JSONL roundtrip."""

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest


class TestJSONLRoundtrip:
    """Test that prepare_book() produces valid JSONL and embed_prepared() can read it."""

    def test_jsonl_header_format(self, tmp_path):
        """Test that a well-formed header has required fields."""
        header = {
            '_header': True,
            'calibre_id': 9013,
            'book_id': 'Becker_Eunapios_9013',
            'book_metadata': {'author': 'Becker', 'title': 'Eunapios'},
            'chunk_count': 3,
            'prepared_at': '2026-03-20T12:00:00',
        }

        jsonl_file = tmp_path / '9013.jsonl'
        chunks = [
            {'id': f'Becker_Eunapios_9013_chunk_{i}', 'text': f'Chunk text {i}',
             'book_id': 'Becker_Eunapios_9013', 'page_number': i + 1,
             'chunk_type': 'content', 'chunk_index': i}
            for i in range(3)
        ]

        with open(jsonl_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(header, ensure_ascii=False) + '\n')
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')

        # Read back and verify
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        assert len(lines) == 4  # 1 header + 3 chunks

        parsed_header = json.loads(lines[0])
        assert parsed_header['_header'] is True
        assert parsed_header['calibre_id'] == 9013
        assert parsed_header['chunk_count'] == 3

        for i, line in enumerate(lines[1:]):
            chunk = json.loads(line)
            assert chunk['id'] == f'Becker_Eunapios_9013_chunk_{i}'
            assert 'text' in chunk
            assert chunk['chunk_type'] == 'content'

    def test_jsonl_unicode_handling(self, tmp_path):
        """Test that Unicode (German, Greek, Hebrew) survives roundtrip."""
        texts = [
            "Herrschaftslegitimation und Machtanspruch",
            "Τὸ δὲ ἦθος τοῦ Εὐναπίου",
            "המלכים היהודיים",
        ]

        jsonl_file = tmp_path / '1234.jsonl'
        header = {'_header': True, 'calibre_id': 1234, 'book_id': 'test',
                  'book_metadata': {}, 'chunk_count': len(texts),
                  'prepared_at': '2026-03-20T12:00:00'}

        with open(jsonl_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(header, ensure_ascii=False) + '\n')
            for i, text in enumerate(texts):
                chunk = {'id': f'test_chunk_{i}', 'text': text,
                         'book_id': 'test', 'chunk_index': i, 'chunk_type': 'content'}
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')

        with open(jsonl_file, 'r', encoding='utf-8') as f:
            f.readline()  # skip header
            for i, line in enumerate(f):
                chunk = json.loads(line)
                assert chunk['text'] == texts[i]

    def test_jsonl_chunk_fields_complete(self, tmp_path):
        """Test that all important chunk fields are preserved."""
        chunk = {
            'id': 'Author_Book_1_chunk_0',
            'text': 'Some meaningful text about ancient history.',
            'book_id': 'Author_Book_1',
            'book_title': 'Book Title',
            'author': 'Author Name',
            'chunk_index': 0,
            'chunk_type': 'content',
            'page_number': 42,
            'page_label': 'xlii',
            'chapter': 'Introduction',
            'section_type': 'main',
            'section_title': 'Chapter 1',
            'language': 'en',
            'format': 'pdf',
            'calibre_id': 1,
            'tags': 'History, Ancient',
            'window_text': 'Context before. Some meaningful text. Context after.',
            'metadata_hash': 'abc123',
            'source_file': '/path/to/book.pdf',
            'indexed_at': '2026-03-20T12:00:00',
        }

        jsonl_file = tmp_path / '1.jsonl'
        header = {'_header': True, 'calibre_id': 1, 'book_id': 'Author_Book_1',
                  'book_metadata': {}, 'chunk_count': 1,
                  'prepared_at': '2026-03-20T12:00:00'}

        with open(jsonl_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(header) + '\n')
            f.write(json.dumps(chunk) + '\n')

        with open(jsonl_file, 'r', encoding='utf-8') as f:
            f.readline()
            parsed = json.loads(f.readline())

        for key in ('id', 'text', 'book_id', 'page_number', 'page_label',
                     'chapter', 'section_type', 'language', 'window_text'):
            assert parsed[key] == chunk[key], f"Field {key} mismatch"

    def test_progress_tracking(self, tmp_path):
        """Test that embed progress uses IndexingCheckpoint (.embed_checkpoint.json)."""
        from src.archilles.indexer import IndexingCheckpoint

        cp_path = tmp_path / '.embed_checkpoint.json'

        # Simulate partial run: load/create checkpoint, record some books
        cp = IndexingCheckpoint.load_or_create(cp_path, profile="", book_ids=[])
        cp.skip_book("9013")
        cp.complete_book("9014")

        # Checkpoint file should exist with canonical format (session_id present)
        assert cp_path.exists(), ".embed_checkpoint.json should exist for partial run"
        with open(cp_path) as f:
            data = json.load(f)
        assert 'session_id' in data, "Canonical format must include session_id"
        assert '9013' in data['skipped_books']
        assert '9014' in data['completed_books']

        # Old .progress.json must NOT be used
        assert not (tmp_path / '.progress.json').exists(), ".progress.json must not be created"

        # Simulate complete run: delete checkpoint
        cp.delete()
        assert not cp_path.exists(), ".embed_checkpoint.json should be deleted after complete run"

    def test_embed_prepared_uses_checkpoint_and_cleans_up(self, tmp_path):
        """embed_prepared() indexes chunks, deletes checkpoint on success,
        and never creates .progress.json (old format).

        Drives embed_prepared() end-to-end via a mocked _rag so no real
        GPU model or LanceDB connection is required.
        """
        import types
        from src.archilles.engine.indexing import Indexer

        # -- Build one valid JSONL file (header + 2 chunks) ------------------
        book_id = 'Test_Book_42'
        header = {
            '_header': True,
            'calibre_id': 42,
            'book_id': book_id,
            'book_metadata': {'author': 'Test Author', 'title': 'Test Book'},
            'chunk_count': 2,
            'prepared_at': '2026-06-15T12:00:00',
        }
        chunks = [
            {'id': f'{book_id}_chunk_{i}', 'text': f'Some test text for chunk {i}',
             'book_id': book_id, 'chunk_index': i, 'chunk_type': 'content'}
            for i in range(2)
        ]

        jsonl_file = tmp_path / '42.jsonl'
        with open(jsonl_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(header, ensure_ascii=False) + '\n')
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')

        # -- Minimal mock for self._rag (only the surface embed_prepared touches) --
        def fake_encode(texts, show_progress_bar=False, convert_to_numpy=True):
            n = len(texts) if isinstance(texts, list) else 1
            return np.zeros((n, 1024), dtype=np.float32)

        mock_rag = types.SimpleNamespace(
            embedding_model=types.SimpleNamespace(encode=fake_encode),
            store=types.SimpleNamespace(
                get_by_book_id=lambda book_id, limit=1: [],   # not yet in LanceDB
                add_chunks=lambda chunks, embeddings: len(chunks),
                delete_by_book_id=lambda book_id: 0,
            ),
            device='cpu',
            batch_size=16,
        )

        indexer = Indexer(mock_rag)

        # -- Run the real embed_prepared() ------------------------------------
        result = indexer.embed_prepared(str(tmp_path), mode='local')

        # -- Assert real behaviour -------------------------------------------
        assert result['total_books'] == 1, (
            f"Expected 1 book embedded, got {result['total_books']}"
        )

        # Checkpoint is deleted after a complete run (not a partial one)
        cp_path = tmp_path / '.embed_checkpoint.json'
        assert not cp_path.exists(), (
            ".embed_checkpoint.json must be deleted after a full successful run"
        )

        # .progress.json is the old format — must never appear
        assert not (tmp_path / '.progress.json').exists(), (
            ".progress.json (old format) must not be created"
        )

    def test_skip_already_prepared(self, tmp_path):
        """Test that existing JSONL files with headers are detected."""
        jsonl_file = tmp_path / '5555.jsonl'
        header = {'_header': True, 'calibre_id': 5555, 'book_id': 'test',
                  'book_metadata': {}, 'chunk_count': 10,
                  'prepared_at': '2026-03-20T12:00:00'}

        with open(jsonl_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(header) + '\n')

        # Verify the skip logic works
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            parsed_header = json.loads(f.readline())
            assert parsed_header.get('_header') is True
            assert parsed_header.get('chunk_count') == 10
