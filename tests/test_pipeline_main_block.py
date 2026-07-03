"""Regression test for pipeline.py's __main__ block (review 2026-07-03,
finding 5.4).

``python -m src.archilles.pipeline <file> [profile]`` called the undefined
``process_document(file_path, profile)`` — a NameError on the very first
invocation. The documented API is ``ModularPipeline.from_profile(profile)
.process(file_path)`` (see the class docstring's own usage example).
"""

from pathlib import Path

PIPELINE_SRC = (
    Path(__file__).resolve().parent.parent / "src" / "archilles" / "pipeline.py"
).read_text(encoding="utf-8")


def test_main_block_does_not_reference_undefined_process_document():
    assert "process_document(" not in PIPELINE_SRC, (
        "process_document is not defined anywhere in pipeline.py — the "
        "__main__ block must not call it (NameError)"
    )


def test_main_block_uses_documented_modular_pipeline_api():
    main_block = PIPELINE_SRC.split('if __name__ == "__main__":', 1)[1]
    assert "ModularPipeline.from_profile(" in main_block
    assert ".process(" in main_block
