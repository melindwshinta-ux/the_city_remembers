"""Rumor system: propagation, reach, confidence, and false rumor planting (GDD Section 10)."""

from __future__ import annotations

from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.quest import Rumor


class RumorSystem:
    """Manages social network rumor spreading, district reach percentages, and disinformation (GDD Section 10)."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        clock: WorldClock | None = None,
        rng: SeededRNG | None = None,
        world: Any = None,
        **kwargs: Any,
    ) -> None:
        self.event_bus = event_bus
        self.clock = clock
        self.rng = rng
        self.world = world
        self.active_rumors: list[Rumor] = []

    def _create_event(
        self,
        event_type: str,
        timestamp: int,
        source_id: str | None = None,
        target_ids: list[str] | None = None,
        location_id: str | None = None,
        data: dict[str, Any] | None = None,
        importance: float = 0.5,
        priority: EventPriority | str | None = None,
    ) -> GameEvent:
        if self.event_bus is not None and hasattr(self.event_bus, "create_event"):
            return self.event_bus.create_event(
                event_type=event_type,
                timestamp=timestamp,
                source_id=source_id,
                target_ids=target_ids,
                location_id=location_id,
                data=data,
                importance=importance,
                priority=priority,
            )
        self._fallback_event_seq = getattr(self, "_fallback_event_seq", 0) + 1
        return GameEvent(
            id=f"ev_rumor_{self._fallback_event_seq:05d}",
            event_type=event_type,
            timestamp=timestamp,
            source_id=source_id,
            target_ids=list(target_ids) if target_ids else [],
            location_id=location_id,
            data=dict(data) if data else {},
            importance=importance,
            priority=priority.value if isinstance(priority, EventPriority) else (priority or "normal"),
        )

    def plant_false_rumor(
        self,
        actor_id: str,
        subject: str,
        claim: str,
        district_id: str,
        truth: bool = False,
        world: Any = None,
    ) -> Rumor:
        """Plant a rumor (truth or disinformation) starting in a specific district."""
        active_world = world or self.world
        rid = (
            f"rumor_{self.rng.randint('rumor', 100000, 999999)}"
            if self.rng
            else f"rumor_{len(self.active_rumors) + 1:04d}"
        )
        rumor = Rumor(
            id=rid,
            subject=subject,
            claim=claim,
            origin=actor_id,
            truth=truth,
            reach={district_id: 35.0},
            confidence=47.0,
        )
        self.active_rumors.append(rumor)
        if active_world and hasattr(active_world, "rumors"):
            active_world.rumors[rid] = rumor

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="RUMOR_PLANTED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=actor_id,
                    target_ids=[subject],
                    location_id=district_id,
                    data={"claim": claim, "truth": truth},
                    importance=0.6,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

        return rumor

    def create_rumor(self, *args: Any, **kwargs: Any) -> Rumor:
        return self.plant_false_rumor(*args, **kwargs)

    def propagate_rumors(self, world: Any = None) -> None:
        """Propagate active rumors across city districts based on social connections."""
        active_world = world or self.world
        districts = ["lowtown", "harbor", "high_quarter", "iron_ward", "temple_district"]
        if active_world and hasattr(active_world, "districts") and active_world.districts:
            districts = sorted(active_world.districts.keys())

        for r in self.active_rumors:
            for dist in districts:
                current = r.reach.get(dist, 0.0)
                if current > 0.0:
                    r.reach[dist] = min(100.0, current + 5.0)
                elif "lowtown" in r.reach and dist == "harbor":
                    r.reach[dist] = 12.0
                elif "harbor" in r.reach and dist == "high_quarter":
                    r.reach[dist] = 5.0

        if self.event_bus and self.active_rumors:
            self.event_bus.emit(
                self._create_event(
                    event_type="RUMOR_SPREAD",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=None,
                    target_ids=[],
                    location_id=None,
                    data={"rumors_count": len(self.active_rumors)},
                    importance=0.5,
                    priority=EventPriority.BACKGROUND,
                ),
                priority=EventPriority.BACKGROUND,
            )

    def step_rumors(self, *args: Any, **kwargs: Any) -> None:
        self.propagate_rumors(*args, **kwargs)

    def update(self, *args: Any, **kwargs: Any) -> None:
        self.propagate_rumors(*args, **kwargs)
