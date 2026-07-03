"""Tests for `_should_skip_model` (review 2026-07-03, finding 5.2).

`embed --mode remote` used to load the local BGE-M3 embedding model anyway:
`skip_model` was only true for the `prepare` command, and the embedder
settings (config `embedder` block vs CLI `--mode`) were resolved *after*
`ArchillesRAG` was already constructed. On the weak machine `full-external`
exists for, this cost a model load and VRAM for a run that then embeds over
HTTP — potentially colliding with a resident MCP server.

`_should_skip_model` is the pure decision extracted from `main()`: skip the
local model for `prepare` (no embeddings at all) and for `embed` when the
resolved mode is `remote`; `embed --mode local` still needs it.
"""

from scripts.rag_demo import _should_skip_model


def test_prepare_always_skips_model():
    assert _should_skip_model('prepare', None) is True
    assert _should_skip_model('prepare', 'local') is True
    assert _should_skip_model('prepare', 'remote') is True


def test_embed_remote_skips_model():
    assert _should_skip_model('embed', 'remote') is True


def test_embed_local_loads_model():
    assert _should_skip_model('embed', 'local') is False


def test_other_commands_load_model():
    assert _should_skip_model('index', None) is False
    assert _should_skip_model('query', None) is False
    assert _should_skip_model('stats', None) is False
