"""
Generic base registry for named components.

All ARCHILLES registries (parsers, chunkers, embedders, annotation providers)
share the same core: register / unregister / get / list_names.
Subclasses add domain-specific lookup methods.
"""

import logging
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseRegistry(Generic[T]):
    """Registry that maps ``item.name`` → *item* for any named component."""

    _label: str = "item"  # human-readable, overridden by subclasses

    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    # -- core CRUD -----------------------------------------------------------

    def register(self, item: T) -> None:
        name = item.name  # type: ignore[attr-defined]
        if name in self._items:
            raise ValueError(f"{self._label} '{name}' is already registered")
        self._items[name] = item
        logger.debug("Registered %s: %s", self._label, name)

    def unregister(self, name: str) -> bool:
        if name in self._items:
            del self._items[name]
            return True
        return False

    def get(self, name: str) -> T | None:
        return self._items.get(name)

    def list_names(self) -> list[str]:
        return list(self._items.keys())

    # -- helpers for subclasses ----------------------------------------------

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, name: str) -> bool:
        return name in self._items

    def __iter__(self):
        return iter(self._items.values())
