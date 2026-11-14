"""Economy, prices, shortages, housing property, stealth, and city time events (GDD Sections 10, 11)."""

from __future__ import annotations

from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.character import Character


class EconomySystem:
    """Manages dynamic city economy, price index, housing property, stealth checks, and time events."""

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
            id=f"ev_econ_{self._fallback_event_seq:05d}",
            event_type=event_type,
            timestamp=timestamp,
            source_id=source_id,
            target_ids=list(target_ids) if target_ids else [],
            location_id=location_id,
            data=dict(data) if data else {},
            importance=importance,
            priority=priority.value if isinstance(priority, EventPriority) else (priority or "normal"),
        )

    def process_daily_tick(self, world: Any = None) -> dict[str, Any]:
        """Simulate daily market economy, price index, and food supply shortages (GDD Section 11)."""
        active_world = world or self.world
        if not active_world:
            return {"price_index": 1.0, "shortages": []}

        if not hasattr(active_world, "economy") or not isinstance(active_world.economy, dict):
            active_world.economy = {"price_index": 1.0, "shortages": [], "wages": 15.0}

        shortages: list[str] = []
        if hasattr(active_world, "districts"):
            for d in active_world.districts.values():
                if getattr(d, "food_supply", 50.0) < 30.0:
                    shortages.append("food")
                    break

        if shortages:
            active_world.economy["price_index"] = 1.45
            active_world.economy["shortages"] = shortages
        else:
            active_world.economy["price_index"] = 1.0
            active_world.economy["shortages"] = []

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="ECONOMY_UPDATED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=None,
                    target_ids=[],
                    location_id=None,
                    data=dict(active_world.economy),
                    importance=0.4,
                    priority=EventPriority.BACKGROUND,
                ),
                priority=EventPriority.BACKGROUND,
            )

        return dict(active_world.economy)

    def update_economy(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.process_daily_tick(*args, **kwargs)

    def step_economy(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.process_daily_tick(*args, **kwargs)

    def acquire_property(
        self,
        char_id: str,
        property_id: str,
        cost: float = 0.0,
        world: Any = None,
    ) -> dict[str, Any]:
        """Allow character to purchase safehouse, workshop, or business property (GDD Section 11)."""
        active_world = world or self.world
        char = active_world.characters.get(char_id) if active_world and hasattr(active_world, "characters") else None
        cost_val = max(0.0, float(cost))

        if cost_val > 0.0:
            wealth = float(char.needs.get("wealth", 0.0)) if char else 0.0
            if char is None or wealth < cost_val:
                return {
                    "success": False,
                    "reason": "insufficient_wealth",
                    "property_id": property_id,
                    "owner": char_id,
                    "cost": cost_val,
                    "wealth": wealth,
                }
            char.needs["wealth"] = max(0.0, wealth - cost_val)

        prop_data = {
            "success": True,
            "property_id": property_id,
            "owner": char_id,
            "type": "safehouse" if "safehouse" in property_id else "business",
            "cost": cost_val,
            "purchased_at": self.clock.timestamp if self.clock else 0,
        }

        if active_world and hasattr(active_world, "properties"):
            active_world.properties[property_id] = prop_data

        return prop_data

    def buy_property(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.acquire_property(*args, **kwargs)

    def purchase_housing(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.acquire_property(*args, **kwargs)

    def trigger_time_event(
        self,
        event_kind: str,
        district_id: str,
        world: Any = None,
    ) -> dict[str, Any]:
        """Trigger major city time event (elections, wars, festivals, riots) (GDD Section 11)."""
        active_world = world or self.world
        district = active_world.districts.get(district_id) if active_world and hasattr(active_world, "districts") else None

        if district:
            if event_kind == "riot":
                district.unrest = min(100.0, district.unrest + 30.0)
                district.security = max(0.0, district.security - 20.0)
            elif event_kind == "festival":
                district.unrest = max(0.0, district.unrest - 20.0)
            elif event_kind == "war":
                district.security = max(0.0, district.security - 35.0)

        ev_data = {
            "event_kind": event_kind,
            "district_id": district_id,
            "description": f"A major {event_kind} erupted in {district_id}!",
        }

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="TIME_EVENT_TRIGGERED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=None,
                    target_ids=[district_id],
                    location_id=district_id,
                    data=ev_data,
                    importance=0.85,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

        return ev_data

    def evaluate_time_events(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.trigger_time_event(*args, **kwargs)

    def calculate_stealth_check(
        self,
        character: Character,
        location_id: str = "lowtown_street",
    ) -> dict[str, float]:
        """Calculate stealth rating and suspicion score influenced by armor weight (GDD Section 11)."""
        skills = getattr(character, "skills", {}) or {}
        stealth_base = float(skills.get("stealth", 30.0))

        # Check armor encumbrance
        equipment = getattr(character, "equipment", {}) or {}
        armor_penalty = 0.0
        for item_name in equipment.values():
            if "plate" in str(item_name):
                armor_penalty += 45.0
            elif "chainmail" in str(item_name):
                armor_penalty += 25.0
            elif "leather" in str(item_name):
                armor_penalty += 5.0

        stealth_score = max(5.0, stealth_base - armor_penalty)
        suspicion = max(5.0, 100.0 - stealth_score)

        return {
            "stealth_score": stealth_score,
            "suspicion": suspicion,
        }

    def evaluate_stealth(self, *args: Any, **kwargs: Any) -> dict[str, float]:
        return self.calculate_stealth_check(*args, **kwargs)
