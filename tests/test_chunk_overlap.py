"""The overlap between two chunks is bounded (2026-09-23).

The general chunker repeated the whole last paragraph of a chunk at the
start of the next. With paragraphs as the EPUB path now reads them -- whole,
often a thousand characters and more -- that repeated nearly half of every
chunk (20 books: the chunks held 1.73 times the text). The overlap is now
the end of that paragraph, at most ``overlap`` words from a sentence start:
the bound the PDF path always had.
"""

from src.extractors.base import BaseExtractor


class _Plain(BaseExtractor):
    def supports(self, file_path):
        return True

    def extract(self, file_path):
        raise NotImplementedError


def _sentences(n: int, tag: str) -> str:
    return " ".join(f"Satz {tag}{k} hat genau sechs Wörter hier." for k in range(n))


def test_the_overlap_is_the_bounded_end_of_the_last_paragraph():
    chunker = _Plain(chunk_size=200, overlap=20)
    long_para = _sentences(20, "a")          # 140 words, one paragraph
    text = long_para + "\n\n" + _sentences(20, "b")
    chunks = chunker._create_chunks(text, detect_language=False, window_chars=0)
    assert len(chunks) == 2
    head = chunks[1]["text"].split("\n\n")[0]
    assert len(head.split()) <= 20
    assert long_para.endswith(head)          # a tail of that paragraph
    assert head.startswith("Satz a")         # beginning at a sentence


def test_a_short_last_paragraph_is_repeated_whole():
    chunker = _Plain(chunk_size=60, overlap=20)
    text = _sentences(6, "a") + "\n\n" + "Kurz und gut." + "\n\n" + _sentences(6, "b")
    chunks = chunker._create_chunks(text, detect_language=False, window_chars=0)
    assert chunks[1]["text"].startswith("Kurz und gut.")


def test_no_overlap_when_switched_off():
    chunker = _Plain(chunk_size=200, overlap=0)
    text = _sentences(20, "a") + "\n\n" + _sentences(20, "b")
    chunks = chunker._create_chunks(text, detect_language=False, window_chars=0)
    assert chunks[1]["text"].startswith("Satz b0")
