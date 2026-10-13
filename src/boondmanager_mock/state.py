"""Mutable server state.

The public API — `state.dataset`, `state.fail_collections`,
`state.reset(seed=…)` — is kept. Two caches are added, invalidated together on
every mutation of the world (reset, evolution event, /__admin/mutate):

  • `entity_index()` — (type, id) → entity, for `included` and detail views;
  • `blobs(key)`      — the precomputed `keywords` search text per item.

Without them, every request would re-serialize the whole dataset (search) and
re-walk every collection (included).
"""

from __future__ import annotations

import json
import time
from typing import Any

from .evolution import Evolution
from .included import TYPE_TO_KEY
from .injection import engine
from .settings import settings


def build_dataset(seed: int = 42) -> dict[str, Any]:
    """Builds the « Boréal Conseil » dataset."""
    from .dataset.realistic import build_realistic_dataset

    return build_realistic_dataset(seed)


class MockState:
    """Mutable server state, to simulate remote changes and outages."""

    def __init__(self) -> None:
        self.dataset: dict[str, Any] = {}
        # Kept for compatibility: the historical injection lever, mutable
        # in-process. New failures go through `injection.engine`, which is
        # controllable over HTTP.
        self.fail_collections: set[str] = set()
        self.seed: int = settings.seed
        self.evolution: Evolution = Evolution(self.seed, time.time())
        self._index: dict[tuple[str, str], dict[str, Any]] | None = None
        self._blobs: dict[str, list[str]] = {}
        self.reset()

    def reset(self, seed: int | None = None) -> None:
        """Rebuilds the dataset and resets the counters to zero.

        ⚠️ Injection rules are reset TO THE BASELINE DECLARED BY THE
        ENVIRONMENT, not to empty: if a `reset` cleared the rules, the first
        request of a test suite would silently wipe out a rate limit
        configured at the compose level.

        Time evolution is REARMED: the timeline starts over from zero.
        """
        self.seed = settings.seed if seed is None else seed
        self.dataset = build_dataset(self.seed)
        self.fail_collections = set()
        engine.clear()
        engine.reset_counters()
        self.evolution = Evolution(self.seed, time.time())
        self.invalidate_caches()
        _apply_baseline_injections()

    # ── Dataset-derived caches ───────────────────────────────────────────────

    def invalidate_caches(self) -> None:
        """Call after ANY dataset mutation (admin, evolution)."""
        self._index = None
        self._blobs = {}

    def advance_evolution(self, now: float) -> None:
        """Advances the company's life; invalidates caches if it moved."""
        if self.evolution.advance(self.dataset, now):
            self.invalidate_caches()

    def entity_index(self) -> dict[tuple[str, str], dict[str, Any]]:
        """(type, id) → entity, across every served collection."""
        if self._index is None:
            index: dict[tuple[str, str], dict[str, Any]] = {}
            for key in TYPE_TO_KEY.values():
                elements = self.dataset.get(key)
                if isinstance(elements, list):
                    for element in elements:
                        index[(element["type"], element["id"])] = element
            self._index = index
        return self._index

    def blobs(self, dataset_key: str) -> list[str]:
        """The search text per item, aligned with the collection's list."""
        if dataset_key not in self._blobs:
            items = self.dataset.get(dataset_key, [])
            self._blobs[dataset_key] = [
                json.dumps(item, ensure_ascii=False).lower() for item in items
            ]
        return self._blobs[dataset_key]

    def totals(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.dataset.items() if isinstance(v, list)}


def _apply_baseline_injections() -> None:
    """Injection rules declared by the environment, reapplied on every reset.

    Lets a docker-compose or a sidecar keep the mock permanently degraded
    (e.g. a low rate limit) without a test inadvertently canceling it.
    """
    import os

    if (threshold := os.environ.get("BOOND_MOCK_RATE_LIMIT_AFTER")) is not None:
        engine.add(
            kind="rate_limit",
            scope="/api/*",
            after_requests=int(threshold),
            retry_after_seconds=int(os.environ.get("BOOND_MOCK_RETRY_AFTER", "1")),
        )


state = MockState()
