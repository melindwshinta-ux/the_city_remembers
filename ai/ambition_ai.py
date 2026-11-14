"""Ambition AI for NPC career scheming and betrayals (GDD Sections 4, 7)."""

from __future__ import annotations

from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus
from core.random_generator import SeededRNG
from entities.character import Character


class AmbitionAI:
    """Evaluates NPC ambition, loyalty, and opportunity to initiate promotion schemes or betrayals."""

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

    def evaluate_npc_ambitions(self, character: Character, world: Any = None) -> dict[str, Any]:
        """Evaluate NPC ambition against faction leadership status."""
        active_world = world or self.world
        personality = getattr(character, "personality", {})
        ambition = float(personality.get("ambition", 50.0))
        loyalty = float(personality.get("loyalty", 50.0))

        if ambition >= 75.0 and loyalty <= 35.0:
            # Ambitious and disloyal officer schemes against superior
            return {
                "scheme_type": "betray_superior",
                "action": "betray_superior",
                "character_id": character.id,
                "target": "superior",
                "reason": "High ambition and low loyalty in an unstable command structure",
            }

        if ambition >= 65.0:
            return {
                "scheme_type": "seek_promotion",
                "action": "seek_promotion",
                "character_id": character.id,
            }

        return {
            "scheme_type": "perform_duty",
            "action": "perform_duty",
            "character_id": character.id,
        }

    def evaluate_ambition(self, character: Character, world: Any = None) -> dict[str, Any]:
        return self.evaluate_npc_ambitions(character, world)

    def select_ambition_action(self, character: Character, world: Any = None) -> dict[str, Any]:
        return self.evaluate_npc_ambitions(character, world)
