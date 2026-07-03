"""ARCHILLES Index Recipe — single source of truth for *what goes into the DB*.

An ``IndexRecipe`` describes the **identity** and **chunk schema** of an index:
the embedding model and dimension (which must never vary across machines, or
vectors become incompatible) and the chunk layout (hierarchical yes/no plus
child/parent sizes). It is deliberately **hardware-independent** — throughput
concerns (batch size, device, local vs. remote embedding) live elsewhere
(``IndexingProfile`` today; an ``ExecutionPlan`` in a later stage).

This consolidates the chunk-parameter sprawl previously scattered across the
codebase (live ``index_book`` 512/128, ``prepare_book`` 1024/128, the refresh
CLI 512/64, the hard-coded parent budget 2048). The canonical defaults match
the effective values of the running full-corpus refresh, so unifying does not
change those values.

See docs/internal/CONCEPT_2026-06-23_HARDWARE_TIERS_V2.md (§3, §10.1).

Note: in this stage the ``hierarchical`` field declares the *target* schema, but
the runtime decision is still driven by the existing ``--hierarchical`` flag;
wiring ``mode``/auto and the watchdog to honour it is a later stage (§10.3/§10.4).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class IndexRecipe:
    """Hardware-independent description of an index's identity and chunk schema.

    Attributes:
        embedding_model: Embedding model id (identity layer — never varies).
        embedding_dimension: Vector dimension (identity layer — never varies).
        hierarchical: Whether the index uses parent/child (Small-to-Big) chunks.
        child_chunk_size: Child chunk size in tokens.
        child_overlap: Child chunk overlap in tokens.
        parent_size: Parent budget in tokens (children grouped up to this size).
    """

    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    hierarchical: bool = True
    child_chunk_size: int = 512
    child_overlap: int = 64
    parent_size: int = 2048


def default_recipe() -> IndexRecipe:
    """Return the canonical index recipe.

    The values match the effective parameters of the running full-corpus
    refresh (child 512 / overlap 64 / parent 2048, hierarchical, BGE-M3 1024).
    """
    return IndexRecipe()
