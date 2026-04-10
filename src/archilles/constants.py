"""
Shared constants for chunk and section type identifiers.

All components that read or write chunk_type / section_type values
should import from here rather than using string literals.
"""


class ChunkType:
    """Chunk type identifiers stored in the ``chunk_type`` column."""

    CONTENT = "content"
    PARENT = "parent"
    CHILD = "child"
    CALIBRE_COMMENT = "calibre_comment"
    ANNOTATION = "annotation"
    PHASE1_METADATA = "phase1_metadata"
    EXCHANGE = "exchange"

    # Virtual filter alias used by _build_filter — not stored in the DB
    ANNOTATIONS_AND_COMMENTS = "annotations_and_comments"

    # Sets for common membership tests
    CONTENT_TYPES = frozenset({CONTENT, CHILD})
    HIERARCHICAL_TYPES = frozenset({CONTENT, CHILD, PARENT})
    NON_CONTENT_TYPES = frozenset({CALIBRE_COMMENT, ANNOTATION, PHASE1_METADATA, PARENT})


class SectionType:
    """Section type identifiers stored in the ``section_type`` column."""

    MAIN_CONTENT = "main_content"
    FRONT_MATTER = "front_matter"
    BACK_MATTER = "back_matter"

    # Virtual filter alias — matches MAIN_CONTENT and empty string
    MAIN = "main"
