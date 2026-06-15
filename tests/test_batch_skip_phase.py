"""get_indexed_book_ids muss ohne ProgressTracker phase-aware bleiben (7.14)."""
from scripts.batch_index import get_indexed_book_ids
from src.archilles.constants import ChunkType


class _FakeStore:
    def __init__(self, chunks):
        self._chunks = chunks
    def get_book_ids_for_skip_check(self):
        return self._chunks


class _FakeRAG:
    def __init__(self, chunks):
        self.store = _FakeStore(chunks)


def test_phase2_skip_counts_only_content_books():
    # Buch 1: Volltext (CONTENT), Buch 2: nur phase1-Stub
    chunks = [
        {'book_id': '1', 'chunk_type': ChunkType.CONTENT},
        {'book_id': '2', 'chunk_type': ChunkType.PHASE1_METADATA},
    ]
    rag = _FakeRAG(chunks)
    assert get_indexed_book_ids(rag, phase='phase2') == {'1'}


def test_phase1_skip_counts_any_chunk():
    chunks = [
        {'book_id': '1', 'chunk_type': ChunkType.CONTENT},
        {'book_id': '2', 'chunk_type': ChunkType.PHASE1_METADATA},
    ]
    rag = _FakeRAG(chunks)
    # In phase1 gilt schon der Stub als "vorhanden" → beide überspringen
    assert get_indexed_book_ids(rag, phase='phase1') == {'1', '2'}
