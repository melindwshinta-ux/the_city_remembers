"""Directed 6-axis relationship and companion friendship/rivalry system (GDD Sections 4, 9, 13)."""

from __future__ import annotations

import uuid
from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.character import Character, Relationship
from entities.companion import Companion, CompanionProfile


class RelationshipSystem:
    """Manages directed relationships across trust, respect, affection, resentment, fear, and dependency."""

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
        self._relationships: dict[tuple[str, str], Relationship] = {}

        if self.event_bus:
            for ev in ("CHARACTER_RESCUED", "COMPANION_ABANDONED", "CRIMINAL_SOLD"):
                self.event_bus.subscribe(ev, self.handle_event)

    def derive_relationship_state(self, rel: Relationship) -> str:
        """Derive the qualitative descriptor from the 6 numerical axes (GDD Section 4)."""
        if rel.trust >= 60.0 and rel.respect >= 70.0 and rel.affection >= 40.0 and rel.resentment <= 20.0:
            return "Loyal associate"
        if rel.respect >= 60.0 and rel.resentment >= 50.0:
            return "Respected rival"
        if rel.affection >= 60.0 and rel.trust >= 50.0:
            return "Close friend"
        if rel.resentment >= 60.0 and rel.trust <= -20.0:
            return "Bitter enemy"
        if rel.fear >= 60.0:
            return "Terrified subordinate"
        if rel.trust >= 40.0:
            return "Friendly associate"
        if rel.resentment >= 40.0:
            return "Distrusted rival"
        return "Acquaintance"

    def set_relationship(
        self,
        source_id: str,
        target_id: str,
        trust: float | None = None,
        respect: float | None = None,
        affection: float | None = None,
        resentment: float | None = None,
        fear: float | None = None,
        dependency: float | None = None,
        relationship_state: str | None = None,
        shared_memories: list[str] | None = None,
    ) -> Relationship | None:
        """Create or update directed relationship from source_id to target_id."""
        if source_id == target_id:
            return None

        rel = self.get_relationship(source_id, target_id)
        if trust is not None:
            rel.trust = max(-100.0, min(100.0, float(trust)))
        if respect is not None:
            rel.respect = max(-100.0, min(100.0, float(respect)))
        if affection is not None:
            rel.affection = max(-100.0, min(100.0, float(affection)))
        if resentment is not None:
            rel.resentment = max(-100.0, min(100.0, float(resentment)))
        if fear is not None:
            rel.fear = max(-100.0, min(100.0, float(fear)))
        if dependency is not None:
            rel.dependency = max(-100.0, min(100.0, float(dependency)))
        if shared_memories is not None:
            rel.shared_memories = list(shared_memories)

        if relationship_state is not None:
            rel.relationship_state = str(relationship_state)
        else:
            rel.relationship_state = self.derive_relationship_state(rel)

        # Sync to source character if world is available
        if self.world and hasattr(self.world, "characters"):
            source_char = self.world.characters.get(source_id)
            if source_char:
                source_char.relationships[target_id] = rel

        return rel

    def trigger_breaking_point(
        self,
        companion_id: str,
        reason: str = "",
        world: Any = None,
    ) -> bool:
        """Trigger companion departure via breaking point (GDD Section 9)."""
        active_world = world or self.world
        comp = None
        if active_world and hasattr(active_world, "companions"):
            comp = active_world.companions.get(companion_id)
        if comp:
            comp.in_party = False
        if active_world and hasattr(active_world, "player_party") and companion_id in active_world.player_party:
            active_world.player_party.remove(companion_id)

        eb = self.event_bus or (getattr(active_world, "event_bus", None) if active_world else None)
        if eb:
            ev = GameEvent(
                id=f"ev_bp_{uuid.uuid4().hex[:6]}",
                event_type="COMPANION_BREAKING_POINT",
                timestamp=active_world.clock.timestamp if active_world and active_world.clock else 0,
                source_id="player",
                target_ids=[companion_id],
                location_id="",
                data={"reason": reason, "companion_id": companion_id},
                importance=0.9,
            )
            eb.emit(ev, priority=EventPriority.CRITICAL)
        return True

    def evaluate_breaking_point(
        self,
        companion_id: str,
        reason: str = "",
        world: Any = None,
        **kwargs: Any,
    ) -> bool:
        if reason:
            return self.trigger_breaking_point(companion_id, reason=reason, world=world)
        return self.check_companion_retention(companion_id, world=world)

    def check_breaking_point(
        self,
        companion_id: str,
        reason: str = "",
        world: Any = None,
        **kwargs: Any,
    ) -> bool:
        return self.evaluate_breaking_point(companion_id, reason=reason, world=world, **kwargs)

    def check_companion_retention(self, companion_id: str, world: Any = None) -> bool:
        """Check if companion remains in party based on rivalry/respect/resentment."""
        active_world = world or self.world
        comp = None
        if active_world and hasattr(active_world, "companions"):
            comp = active_world.companions.get(companion_id)
        if not comp:
            return True
        rel = self.get_relationship(companion_id, "player")
        if rel.resentment >= 90.0 and rel.respect < 30.0:
            return self.trigger_breaking_point(companion_id, reason="excessive_resentment", world=world)
        return True

    def update_relationship(self, source_id: str, target_id: str, **kwargs: Any) -> Relationship:
        return self.set_relationship(source_id, target_id, **kwargs)

    def modify_relationship(self, source_id: str, target_id: str, **kwargs: Any) -> Relationship:
        return self.set_relationship(source_id, target_id, **kwargs)

    def get_relationship(self, source_id: str, target_id: str) -> Relationship:
        """Get existing relationship or create default Acquaintance."""
        key = (source_id, target_id)
        if key in self._relationships:
            return self._relationships[key]

        # Check world characters
        if self.world and hasattr(self.world, "characters"):
            source_char = self.world.characters.get(source_id)
            if source_char and target_id in source_char.relationships:
                rel = source_char.relationships[target_id]
                self._relationships[key] = rel
                return rel

        new_rel = Relationship(
            source_id=source_id,
            target_id=target_id,
            trust=0.0,
            respect=0.0,
            affection=0.0,
            resentment=0.0,
            fear=0.0,
            dependency=0.0,
            relationship_state="Acquaintance",
        )
        self._relationships[key] = new_rel
        return new_rel

    def query_relationship(self, source_id: str, target_id: str) -> Relationship:
        return self.get_relationship(source_id, target_id)

    def adjust_companion_standing(
        self,
        companion_id: str,
        friendship_delta: float = 0.0,
        rivalry_delta: float = 0.0,
        respect_delta: float = 0.0,
        world: Any = None,
    ) -> None:
        """Adjust separate friendship and rivalry progression tracks for a companion."""
        active_world = world or self.world
        comp = None
        if active_world and hasattr(active_world, "companions"):
            comp = active_world.companions.get(companion_id)

        if comp is not None:
            if hasattr(comp, "friendship"):
                comp.friendship = max(0.0, min(100.0, comp.friendship + friendship_delta))
            if hasattr(comp, "rivalry"):
                comp.rivalry = max(0.0, min(100.0, comp.rivalry + rivalry_delta))

        # Also update relationship toward player
        rel = self.get_relationship(companion_id, "player")
        if friendship_delta != 0.0:
            rel.trust += friendship_delta * 0.8
            rel.affection += friendship_delta * 0.8
        if rivalry_delta != 0.0:
            rel.resentment += rivalry_delta * 0.5
            rel.respect += rivalry_delta * 0.5
        if respect_delta != 0.0:
            rel.respect += respect_delta
        rel.relationship_state = self.derive_relationship_state(rel)

    def update_companion_relationship(self, companion_id: str, **kwargs: Any) -> None:
        self.adjust_companion_standing(companion_id, **kwargs)

    def record_companion_reaction(self, companion_id: str, **kwargs: Any) -> None:
        self.adjust_companion_standing(companion_id, **kwargs)

    def handle_event(self, event: GameEvent, world: Any = None) -> None:
        """Update relationships from GameEvent (e.g. CHARACTER_RESCUED)."""
        active_world = world or self.world
        data = event.data or {}

        trust_d = float(data.get("trust_delta", 0.0))
        affection_d = float(data.get("affection_delta", 0.0))
        respect_d = float(data.get("respect_delta", 0.0))
        resentment_d = float(data.get("resentment_delta", 0.0))
        fear_d = float(data.get("fear_delta", 0.0))
        mem_id = data.get("memory_id")

        if event.source_id and event.target_ids:
            for target_id in event.target_ids:
                rel = self.get_relationship(target_id, event.source_id)
                rel.trust += trust_d
                rel.affection += affection_d
                rel.respect += respect_d
                rel.resentment += resentment_d
                rel.fear += fear_d
                if mem_id and mem_id not in rel.shared_memories:
                    rel.shared_memories.append(str(mem_id))
                rel.relationship_state = self.derive_relationship_state(rel)

                if self.event_bus:
                    change_ev = GameEvent(
                        id=f"rel_chg_{uuid.uuid4().hex[:6]}",
                        event_type="RELATIONSHIP_CHANGED",
                        timestamp=event.timestamp,
                        source_id=target_id,
                        target_ids=[event.source_id],
                        location_id=event.location_id,
                        data={
                            "relationship_state": rel.relationship_state,
                            "trust": rel.trust,
                            "affection": rel.affection,
                        },
                        importance=0.6,
                    )
                    self.event_bus.emit(change_ev, priority=EventPriority.NORMAL)

    def process_event(self, event: GameEvent, world: Any = None) -> None:
        self.handle_event(event, world=world)

    def on_event(self, event: GameEvent, world: Any = None) -> None:
        self.handle_event(event, world=world)
