"""Character & companion daily autonomous behavior and ambition AI (GDD Sections 4, 8, 9)."""

from __future__ import annotations

from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus
from core.random_generator import SeededRNG
from entities.character import Character
from entities.companion import Companion, CompanionProfile


class CharacterAI:
    """Evaluates character personality, needs, and ambitions to choose daily autonomous actions."""

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

    def select_daily_action(self, character: Character, world: Any = None) -> dict[str, Any] | None:
        """Select a need-driven and personality-driven daily action for an NPC."""
        if getattr(character, "status", "alive") in ("dead", "incapacitated"):
            return {"action": "none"}
        active_world = world or self.world
        personality = getattr(character, "personality", {})
        needs = getattr(character, "needs", {})

        courage = float(personality.get("courage", 50.0))
        ambition = float(personality.get("ambition", 50.0))
        loyalty = float(personality.get("loyalty", 50.0))
        greed = float(personality.get("greed", 30.0))

        safety_need = float(needs.get("safety", 100.0))
        hunger_need = float(needs.get("hunger", 100.0))
        fatigue_need = float(needs.get("fatigue", 100.0))

        # Critical physical needs first
        if hunger_need < 25.0:
            return {"action": "eat_meal", "location": "tavern", "target_need": "hunger"}
        if fatigue_need < 25.0:
            return {"action": "sleep_and_rest", "location": "safehouse", "target_need": "fatigue"}

        # Cowardice or high danger
        if courage <= 20.0 or safety_need <= 20.0:
            return {
                "action": "seek_safety_and_shelter",
                "reason": "Fear and low courage",
                "location": "barracks_interior",
            }

        # High ambition & low loyalty -> political scheming / betrayal
        if ambition >= 75.0 and loyalty <= 30.0:
            return {
                "action": "scheme_for_promotion",
                "reason": "High ambition and low loyalty",
                "target": "commander",
            }

        if greed >= 70.0:
            return {"action": "pursue_shady_trade", "location": "lowtown_market"}

        # Default duty
        return {"action": "patrol_district", "location": character.location_id or "lowtown"}

    def decide_action(self, character: Character, world: Any = None) -> dict[str, Any]:
        return self.select_daily_action(character, world)

    def evaluate_character(self, character: Character, world: Any = None) -> dict[str, Any]:
        return self.select_daily_action(character, world)

    def update_character(self, character: Character, world: Any = None) -> dict[str, Any]:
        return self.select_daily_action(character, world)

    def update_companion_autonomy(self, companion: Any, world: Any = None) -> None:
        """Assign autonomous independent activities to companions (GDD Section 9)."""
        active_world = world or self.world
        cid = getattr(companion, "character_id", getattr(companion, "id", ""))
        name = getattr(companion, "name", "")

        activities = {
            "comp_marcus": "Drilling city guards and inspecting defense perimeter",
            "comp_elira": "Transcribing forbidden magical research in quiet archives",
            "comp_sera": "Scouting alleyways and gathering criminal whispers in Lowtown",
            "comp_tomas": "Administering poultices and treating destitute patients at the temple",
        }

        # Match by ID or name
        matched_activity = None
        for key, act in activities.items():
            if key in cid or key.replace("comp_", "").lower() in name.lower():
                matched_activity = act
                break

        if not matched_activity:
            matched_activity = "Wandering the market and conferring with local contacts"

        if hasattr(companion, "independent_activity"):
            companion.independent_activity = matched_activity
        if hasattr(companion, "current_activity"):
            companion.current_activity = matched_activity

    def simulate_companion(self, companion: Any, world: Any = None) -> None:
        self.update_companion_autonomy(companion, world)

    def decide_companion_action(self, companion: Any, world: Any = None) -> None:
        self.update_companion_autonomy(companion, world)
