"""Combat AI for 7 enemy archetypes and 6 morale states (GDD Section 6)."""

from __future__ import annotations

from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus
from core.random_generator import SeededRNG
from entities.enemy import EnemyCombatant


ARCHETYPE_COMMANDS = {
    "coward": "retreat",
    "duelist": "attack",
    "commander": "protect_ally",
    "berserker": "charge",
    "assassin": "stealth_attack",
    "medic": "apply_bandage",
    "opportunist": "flank",
}


class CombatAI:
    """Selects tactical combat actions based on enemy archetype, morale state, and context (GDD Section 6)."""

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

    def select_action(self, combatant: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Select a tactical command for the combatant."""
        ctx = context or {}
        archetype = str(getattr(combatant, "archetype", "duelist")).lower()
        morale_state = str(getattr(combatant, "morale_state", "steady")).lower()

        # If routing or panicking, retreat
        if morale_state in ("routing", "panicking"):
            return {"command": "retreat", "reason": "Morale broken"}

        # Medic prioritizes healing if ally is bleeding
        if archetype == "medic" and ctx.get("ally_bleeding"):
            return {"command": "apply_bandage", "target": "ally"}

        # Commander responds to commander down or rallies allies
        if archetype == "commander":
            return {"command": "protect_ally", "target": "formation"}

        cmd = ARCHETYPE_COMMANDS.get(archetype, "attack")
        return {"command": cmd, "target": "enemy"}

    def decide_combat_action(self, combatant: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.select_action(combatant, context)

    def choose_action(self, combatant: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.select_action(combatant, context)
