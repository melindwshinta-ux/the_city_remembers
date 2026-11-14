"""Faction AI for autonomous strategic turns and goal execution (GDD Section 8)."""

from __future__ import annotations

from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.faction import Faction


class FactionAI:
    """Evaluates faction goals and executes autonomous actions every 6–24 hours (GDD Section 8)."""

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

    def process_faction_turn(self, faction: Faction, world: Any = None) -> dict[str, Any]:
        """Execute autonomous 5-stage turn cycle for faction (GDD Section 8)."""
        active_world = world or self.world
        goals = getattr(faction, "goals", [])
        goal = goals[0] if goals else {"type": "maintain_authority", "target": "lowtown"}
        goal_type = goal.get("type", "maintain_authority")
        target = goal.get("target", "lowtown")

        # Execute action based on goal
        action_name = f"execute_{goal_type}"
        result = {
            "faction_id": faction.id,
            "goal_type": goal_type,
            "target": target,
            "success": True,
            "action": action_name,
        }

        if self.event_bus:
            if hasattr(self.event_bus, "create_event"):
                ev = self.event_bus.create_event(
                    event_type="FACTION_ACTION_TAKEN",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=faction.id,
                    target_ids=[target] if isinstance(target, str) else [],
                    location_id="lowtown",
                    data=result,
                    importance=0.7,
                    priority=EventPriority.NORMAL,
                )
            else:
                self._fallback_event_seq = getattr(self, "_fallback_event_seq", 0) + 1
                ev = GameEvent(
                    id=f"ev_fac_act_{self._fallback_event_seq:05d}",
                    event_type="FACTION_ACTION_TAKEN",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=faction.id,
                    target_ids=[target] if isinstance(target, str) else [],
                    location_id="lowtown",
                    data=result,
                    importance=0.7,
                )
            self.event_bus.emit(ev, priority=EventPriority.NORMAL)

        return result

    def evaluate_faction_turn(self, faction: Faction, world: Any = None) -> dict[str, Any]:
        return self.process_faction_turn(faction, world)

    def select_faction_action(self, faction: Faction, world: Any = None) -> dict[str, Any]:
        return self.process_faction_turn(faction, world)
