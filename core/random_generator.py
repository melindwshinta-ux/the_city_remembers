"""Seeded multi-stream deterministic RNG (GDD Section 14)."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence, Set
from typing import Any, TypeVar

from config import DEFAULT_WORLD_SEED, RNG_STREAMS

T = TypeVar("T")


def _derive_seed(master_seed: int, stream_name: str) -> int:
    """Derive an uncorrelated 64-bit integer seed from master_seed and stream_name."""
    digest = hashlib.sha256(f"{master_seed}:{stream_name}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


class SeededRNG:
    """Master seeded RNG managing isolated random.Random streams per simulation domain."""

    def __init__(self, master_seed: int = DEFAULT_WORLD_SEED) -> None:
        self.master_seed: int = int(master_seed)
        self._streams: dict[str, random.Random] = {}
        for name in RNG_STREAMS:
            self._streams[name] = random.Random(_derive_seed(self.master_seed, name))

    def stream(self, name: str = "world") -> random.Random:
        """Return the isolated random.Random instance for `name`."""
        if name not in self._streams:
            self._streams[name] = random.Random(_derive_seed(self.master_seed, name))
        return self._streams[name]

    @property
    def stream_names(self) -> list[str]:
        """Return sorted list of active stream names."""
        return sorted(self._streams.keys())

    def random(self, stream_name: str = "world") -> float:
        """Return uniform float in [0.0, 1.0) from `stream_name`."""
        return self.stream(stream_name).random()

    def randint(self, stream_name: str, a: int, b: int) -> int:
        """Return random integer N such that a <= N <= b from `stream_name`."""
        return self.stream(stream_name).randint(a, b)

    def uniform(self, stream_name: str, a: float, b: float) -> float:
        """Return random float in [a, b] from `stream_name`."""
        return self.stream(stream_name).uniform(a, b)

    def roll_chance(self, stream_name: str, probability: float) -> bool:
        """Return True with `probability` (0.0..1.0) using `stream_name`."""
        if probability <= 0.0:
            return False
        if probability >= 1.0:
            return True
        return self.stream(stream_name).random() < probability

    def choice(self, stream_name: str, seq: Sequence[T] | Set[T]) -> T:
        """Pick a random element from `seq`, sorting sets first to guarantee determinism."""
        if isinstance(seq, (set, frozenset)) or not isinstance(seq, Sequence):
            ordered: list[T] = sorted(seq, key=lambda x: (type(x).__name__, str(x)))
        else:
            ordered = list(seq)
        if not ordered:
            raise ValueError("Cannot choose from an empty collection")
        return self.stream(stream_name).choice(ordered)

    def shuffle(self, stream_name: str, items: list[T]) -> list[T]:
        """Return a deterministically shuffled shallow copy of `items`."""
        copied = list(items)
        self.stream(stream_name).shuffle(copied)
        return copied

    def weighted_pick(self, stream_name: str, table: Sequence[tuple[T, float]]) -> T:
        """Select an item from `(item, weight)` pairs proportional to positive weight."""
        total = sum(float(w) for _, w in table if w > 0)
        if total <= 0.0:
            raise ValueError("weighted_pick requires at least one item with positive weight")
        roll = self.stream(stream_name).uniform(0.0, total)
        upto = 0.0
        for item, weight in table:
            w = float(weight)
            if w <= 0.0:
                continue
            upto += w
            if roll < upto:
                return item
        return next(i for i, w in reversed(table) if w > 0)

    def get_state(self) -> dict[str, Any]:
        """Export JSON-safe state for all RNG streams."""
        streams_data: dict[str, Any] = {}
        for name in sorted(self._streams.keys()):
            st = self._streams[name].getstate()
            streams_data[name] = {
                "version": int(st[0]),
                "internalstate": [int(x) for x in st[1]],
                "gauss_next": float(st[2]) if st[2] is not None else None,
            }
        return {
            "master_seed": self.master_seed,
            "streams": streams_data,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore RNG master seed and all stream states from a JSON-deserialized dict."""
        if "master_seed" in state:
            self.master_seed = int(state["master_seed"])
        streams_data = state.get("streams", {})
        for name in RNG_STREAMS:
            if name not in self._streams:
                self._streams[name] = random.Random(_derive_seed(self.master_seed, name))
        for name, st_data in sorted(streams_data.items()):
            rng_inst = self.stream(name)
            if isinstance(st_data, (tuple, list)) and len(st_data) == 3:
                version = int(st_data[0])
                internal = tuple(int(x) for x in st_data[1])
                gauss = float(st_data[2]) if st_data[2] is not None else None
                rng_inst.setstate((version, internal, gauss))
            elif isinstance(st_data, dict):
                version = int(st_data["version"])
                internal = tuple(int(x) for x in st_data["internalstate"])
                gauss_raw = st_data.get("gauss_next")
                gauss = float(gauss_raw) if gauss_raw is not None else None
                rng_inst.setstate((version, internal, gauss))
            else:
                raise ValueError(f"Invalid RNG stream state format for stream '{name}'")
