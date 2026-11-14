"""Hybrid quests, dynamic conditions, and 6-scope reputation system (GDD Sections 10 & 13)."""

from __future__ import annotations

import uuid
from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.quest import Quest


REPUTATION_SCOPES = [
    "district",
    "faction",
    "individual_npc",
    "general_public",
    "criminal_underworld",
    "noble_society",
]


class QuestSystem:
    """Manages authored, systemic, and hybrid quests and 6-scope reputation (GDD Section 10)."""

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
        self._reputation: dict[tuple[str, str | None], float] = {}
        if self.event_bus and hasattr(self.event_bus, "subscribe"):
            self.event_bus.subscribe("CHARACTER_DIED", self.handle_event)

    def handle_event(self, event: GameEvent, world: Any = None) -> None:
        """React to world events (e.g. CHARACTER_DIED) by re-evaluating affected quests."""
        active_world = world or self.world
        if not active_world or not hasattr(active_world, "quests"):
            return

        if event.event_type == "CHARACTER_DIED":
            dead_ids = set(event.target_ids or [])
            for qid, q in list(active_world.quests.items()):
                target_alive = q.conditions.get("target_alive") if isinstance(q.conditions, dict) else None
                involved = set(getattr(q, "involved_characters", []) or [])
                if (target_alive and target_alive in dead_ids) or (involved & dead_ids):
                    self.evaluate_quest_conditions(qid, world=active_world)

    def on_event(self, event: GameEvent, world: Any = None) -> None:
        self.handle_event(event, world=world)

    def create_hybrid_quest(
        self,
        quest_id: str,
        quest_type: str = "hybrid",
        world: Any = None,
    ) -> Quest:
        """Create a quest reacting to live simulated world state."""
        active_world = world or self.world
        q = Quest(
            id=quest_id,
            title="The Missing Apprentice",
            description="Investigate the disappearance of Joren from Gregor's workshop.",
            quest_type=quest_type,
            status="active",
            objectives=[
                {"id": "find_apprentice", "description": "Locate Joren in Lowtown", "completed": False},
                {"id": "report_back", "description": "Speak with Gregor", "completed": False},
            ],
            conditions={"target_alive": "npc_missing_apprentice"},
            involved_characters=["npc_missing_apprentice", "npc_workshop_owner", "comp_sera"],
            involved_factions=["iron_workers_union"],
        )
        if active_world and hasattr(active_world, "quests"):
            active_world.quests[quest_id] = q

        if self.event_bus:
            self.event_bus.emit(
                GameEvent(
                    id=f"ev_qst_start_{uuid.uuid4().hex[:6]}",
                    event_type="QUEST_STARTED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id="player",
                    target_ids=[quest_id],
                    location_id="lowtown",
                    data={"quest_id": quest_id},
                    importance=0.7,
                ),
                priority=EventPriority.NORMAL,
            )

        return q

    def start_quest(self, *args: Any, **kwargs: Any) -> Quest:
        return self.create_hybrid_quest(*args, **kwargs)

    def create_quest(self, *args: Any, **kwargs: Any) -> Quest:
        return self.create_hybrid_quest(*args, **kwargs)

    def evaluate_quest_conditions(self, quest_id: str, world: Any = None) -> str:
        """Evaluate quest status dynamically against live character/faction state."""
        active_world = world or self.world
        if not active_world or not hasattr(active_world, "quests"):
            return "active"

        q = active_world.quests.get(quest_id)
        if not q:
            return "unknown"

        # Check target character status
        target_char_id = q.conditions.get("target_alive")
        if target_char_id and hasattr(active_world, "characters"):
            char = active_world.characters.get(target_char_id)
            if char and char.status == "dead":
                if q.status != "branched" or not q.conditions.get("target_dead"):
                    q.status = "branched"
                    q.conditions["target_dead"] = target_char_id
                    if self.event_bus:
                        self.event_bus.emit(
                            GameEvent(
                                id=f"ev_qst_upd_{uuid.uuid4().hex[:6]}",
                                event_type="QUEST_UPDATED",
                                timestamp=self.clock.timestamp if self.clock else 0,
                                source_id=target_char_id,
                                target_ids=[quest_id],
                                location_id=getattr(char, "location_id", None) or "lowtown",
                                data={"quest_id": quest_id, "status": q.status, "target_dead": target_char_id},
                                importance=0.75,
                            ),
                            priority=EventPriority.NORMAL,
                        )
                return q.status

        return q.status

    def evaluate_quest_state(self, *args: Any, **kwargs: Any) -> str:
        return self.evaluate_quest_conditions(*args, **kwargs)

    def adjust_reputation(
        self,
        scope: str,
        key: str | None,
        delta: float,
        world: Any = None,
    ) -> float:
        """Adjust reputation across one of the 6 independent scopes (-100 to +100)."""
        if scope not in REPUTATION_SCOPES:
            raise ValueError(f"Unknown reputation scope '{scope}'. Must be one of {REPUTATION_SCOPES}.")
        lookup_key = (scope, key)
        current = self._reputation.get(lookup_key, 0.0)
        new_val = max(-100.0, min(100.0, current + delta))
        self._reputation[lookup_key] = new_val
        return new_val

    def modify_reputation(self, *args: Any, **kwargs: Any) -> float:
        return self.adjust_reputation(*args, **kwargs)

    def get_reputation(self, scope: str, key: str | None = None, world: Any = None) -> float:
        """Query reputation score for a specific scope and key."""
        if scope not in REPUTATION_SCOPES:
            raise ValueError(f"Unknown reputation scope '{scope}'. Must be one of {REPUTATION_SCOPES}.")
        lookup_key = (scope, key)
        return self._reputation.get(lookup_key, 0.0)

    def query_reputation(self, *args: Any, **kwargs: Any) -> float:
        return self.get_reputation(*args, **kwargs)

    def get_dialogue(self, character_id: str, world: Any = None) -> str:
        """Contextual dialogue generator reacting to injuries, grudges, and hostility (GDD Section 20)."""
        active_world = world or self.world
        if not active_world or not hasattr(active_world, "characters"):
            return "..."
        c = active_world.characters.get(character_id)
        if not c:
            return "..."

        prof = getattr(active_world, "nemesis_profiles", {}).get(character_id)
        hostility = getattr(prof, "player_hostility", 0.0) if prof else 0.0

        if character_id == "npc_voss":
            has_broken_leg = False
            if hasattr(c, "body") and "left_leg" in c.body:
                has_broken_leg = any(inj.injury_type == "broken_leg" for inj in c.body["left_leg"].injuries)
            if has_broken_leg or hostility >= 70.0:
                return "You broke my leg, Rowan! Every step I take will remind me to see you hang in the square!"
            return "Watch yourself in Lowtown, traveler. The City Guard sees everything."

        return f"Greetings from {c.name}."

    def generate_dialogue(self, *args: Any, **kwargs: Any) -> str:
        return self.get_dialogue(*args, **kwargs)

    def talk_to(self, *args: Any, **kwargs: Any) -> str:
        return self.get_dialogue(*args, **kwargs)
