"""Tests for annotation provider base types and registry."""

import pytest
from src.calibre_mcp.annotation_providers.base import Annotation, AnnotationProvider
from src.calibre_mcp.annotation_providers.registry import AnnotationProviderRegistry


# ── Annotation dataclass tests ──────────────────────────────────────


def test_annotation_build_text_highlight_only():
    a = Annotation(source="kindle", type="highlight", text="Important passage")
    assert a._build_text() == "Important passage"


def test_annotation_build_text_with_note():
    a = Annotation(
        source="kindle", type="highlight", text="Important", note="My thoughts"
    )
    assert a._build_text() == "Important\n[Note: My thoughts]"


def test_annotation_build_text_empty():
    a = Annotation(source="kindle", type="bookmark", text="")
    assert a._build_text() == ""


def test_annotation_to_chunk_dict():
    a = Annotation(
        source="pdf", type="highlight", text="Hello", page_number=42, chapter="Ch1"
    )
    d = a.to_chunk_dict()
    assert d["chunk_type"] == "annotation"
    assert d["annotation_type"] == "highlight"
    assert d["annotation_source"] == "pdf"
    assert d["page_number"] == 42
    assert d["chapter"] == "Ch1"


def test_annotation_to_legacy_dict():
    a = Annotation(source="pdf", type="highlight", text="Hello", note="world")
    d = a.to_legacy_dict()
    assert d["type"] == "highlight"
    assert d["highlighted_text"] == "Hello"
    assert d["notes"] == "world"
    assert d["source"] == "pdf"


def test_provider_is_abstract():
    with pytest.raises(TypeError):
        AnnotationProvider()


# ── Registry tests ──────────────────────────────────────────────────


class DummyProvider(AnnotationProvider):
    @property
    def name(self) -> str:
        return "dummy"

    def extract(self, path, **kwargs):
        return [Annotation(source="dummy", type="highlight", text=f"from {path}")]

    def can_handle(self, path):
        return path.endswith(".dummy")


def test_registry_register_and_get():
    reg = AnnotationProviderRegistry()
    reg.register(DummyProvider())
    assert reg.get("dummy") is not None
    assert reg.get("nonexistent") is None


def test_registry_duplicate_raises():
    reg = AnnotationProviderRegistry()
    reg.register(DummyProvider())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(DummyProvider())


def test_registry_detect():
    reg = AnnotationProviderRegistry()
    reg.register(DummyProvider())
    assert reg.detect("file.dummy") is not None
    assert reg.detect("file.txt") is None


def test_registry_extract_all_by_source():
    reg = AnnotationProviderRegistry()
    reg.register(DummyProvider())
    results = reg.extract_all("test.dummy", source="dummy")
    assert len(results) == 1
    assert results[0].text == "from test.dummy"


def test_registry_extract_all_auto_detect():
    reg = AnnotationProviderRegistry()
    reg.register(DummyProvider())
    results = reg.extract_all("test.dummy")
    assert len(results) == 1


def test_registry_extract_all_unknown_source():
    reg = AnnotationProviderRegistry()
    with pytest.raises(ValueError, match="Unknown annotation provider"):
        reg.extract_all("test.txt", source="nonexistent")


def test_registry_extract_all_no_provider():
    reg = AnnotationProviderRegistry()
    reg.register(DummyProvider())
    with pytest.raises(ValueError, match="No provider can handle"):
        reg.extract_all("test.txt")


def test_registry_available():
    reg = AnnotationProviderRegistry()
    assert reg.available == []
    reg.register(DummyProvider())
    assert reg.available == ["dummy"]


# ── PDF Provider tests ──────────────────────────────────────────────


def test_pdf_provider_can_handle():
    from src.calibre_mcp.annotation_providers.pdf_provider import PdfAnnotationProvider

    p = PdfAnnotationProvider()
    assert p.name == "pdf"
    assert p.can_handle("book.pdf")
    assert p.can_handle("BOOK.PDF")
    assert not p.can_handle("book.epub")


def test_pdf_provider_nonexistent_file():
    from src.calibre_mcp.annotation_providers.pdf_provider import PdfAnnotationProvider

    p = PdfAnnotationProvider()
    assert p.extract("/nonexistent/file.pdf") == []


# ── Calibre Provider tests ──────────────────────────────────────────


def test_calibre_provider_name():
    from src.calibre_mcp.annotation_providers.calibre_provider import (
        CalibreViewerProvider,
    )

    p = CalibreViewerProvider()
    assert p.name == "calibre_viewer"


def test_calibre_provider_nonexistent_dir():
    from src.calibre_mcp.annotation_providers.calibre_provider import (
        CalibreViewerProvider,
    )

    p = CalibreViewerProvider(annotations_dir="/nonexistent/path")
    assert p.extract("somebook.epub") == []
