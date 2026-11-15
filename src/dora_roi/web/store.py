"""Bounded, thread-safe in-memory store for workspaces and wizards (per-owner budgets)."""

from __future__ import annotations

import os
from collections import OrderedDict
from collections.abc import Callable
from threading import Lock
from typing import Generic, TypeVar

from fastapi import HTTPException

T = TypeVar("T")


class LRUStore(Generic[T]):
    """Thread-safe bounded store.

    Bounded by item count and, optionally, by a total ``weight`` (for workspaces: the number
    of rows, which drives memory – roughly 2 KB per row once parsed and validated). With an
    ``owner`` function each owner additionally gets its own count and weight budget, and an
    owner over budget loses its *own* least recently used items first – one user loading
    large registers cannot push everyone else's work out. The most recently added item is
    always kept; ``on_evict`` is called for every evicted item (outside the lock).
    """

    def __init__(self, capacity: int, *, max_weight: int | None = None,
                 weight: Callable[[T], int] | None = None,
                 owner: Callable[[T], str] | None = None, owner_capacity: int | None = None,
                 owner_weight: int | None = None,
                 on_evict: Callable[[T], None] | None = None) -> None:
        self.capacity = capacity
        self.max_weight = max_weight
        self.owner_capacity = owner_capacity
        self.owner_weight = owner_weight
        self._weight = weight
        self._owner = owner
        self._on_evict = on_evict
        self._items: OrderedDict[str, T] = OrderedDict()
        self._lock = Lock()

    def _total_weight(self, keys: list[str] | None = None) -> int:
        weigh = self._weight
        if weigh is None:
            return 0
        items = self._items.values() if keys is None else [self._items[k] for k in keys]
        return sum(weigh(v) for v in items)

    def _evict_own(self, key: str, item: T) -> list[T]:
        owner = self._owner
        if owner is None:
            return []
        mine = owner(item)
        evicted: list[T] = []
        while True:
            others = [k for k, v in self._items.items() if k != key and owner(v) == mine]
            over_count = self.owner_capacity is not None and len(others) >= self.owner_capacity
            over_weight = (self.owner_weight is not None and others
                           and self._total_weight([*others, key]) > self.owner_weight)
            if not others or not (over_count or over_weight):
                return evicted
            evicted.append(self._items.pop(others[0]))

    def add(self, key: str, item: T) -> None:
        with self._lock:
            self._items[key] = item
            self._items.move_to_end(key)
            evicted = self._evict_own(key, item)
            while len(self._items) > self.capacity:
                evicted.append(self._items.popitem(last=False)[1])
            if self.max_weight is not None:
                while len(self._items) > 1 and self._total_weight() > self.max_weight:
                    evicted.append(self._items.popitem(last=False)[1])
        if self._on_evict is not None:
            for gone in evicted:
                self._on_evict(gone)

    def remove(self, key: str) -> T | None:
        with self._lock:
            return self._items.pop(key, None)

    def peek(self, key: str) -> T | None:
        """The item without marking it as used (``None`` if absent)."""
        with self._lock:
            return self._items.get(key)

    def contains(self, key: str) -> bool:
        with self._lock:
            return key in self._items

    def get(self, key: str) -> T:
        with self._lock:
            if key not in self._items:
                raise HTTPException(status_code=404, detail="not found")
            self._items.move_to_end(key)
            return self._items[key]

    def values(self) -> list[T]:
        with self._lock:
            return list(reversed(self._items.values()))


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def max_store_rows() -> int:
    """Row budget for all workspaces held in memory (``ROI_MAX_STORE_ROWS``)."""
    return _env_int("ROI_MAX_STORE_ROWS", 500_000)

