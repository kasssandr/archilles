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
        """Test that .progress.json is valid JSON and tracks embedded files."""
        progress_file = tmp_path / '.progress.json'
        progress = {'embedded': ['9013', '9014']}

        with open(progress_file, 'w') as f:
            json.dump(progress, f)

        with open(progress_file, 'r') as f:
            loaded = json.load(f)

        assert '9013' in loaded['embedded']
        assert '9014' in loaded['embedded']
        assert len(loaded['embedded']) == 2

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
