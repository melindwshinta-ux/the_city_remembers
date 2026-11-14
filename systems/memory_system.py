"""Episodic and informational memory system (GDD Sections 4, 10, 13)."""

from __future__ import annotations

import uuid
from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.character import Character, Memory
from entities.quest import Rumor


EMOTION_VALENCE_DEFAULTS = {
    "CHARACTER_RESCUED": ("Gratitude", 0.85, 0.9),
    "RESCUED": ("Gratitude", 0.85, 0.9),
    "CRIMINAL_SOLD": ("Disgust", -0.5, 0.6),
    "COMPANION_ABANDONED": ("Anger", -0.9, 0.9),
    "LIMB_INJURED": ("Pain", -0.8, 0.85),
    "CHARACTER_INJURED": ("Fear", -0.7, 0.8),
    "CHARACTER_DIED": ("Grief", -0.95, 0.95),
    "TRADE_COMPLETED": ("Satisfaction", 0.3, 0.3),
    "MINOR_INSULT": ("Annoyance", -0.2, 0.2),
    "LIFE_SAVING_RESCUE": ("Gratitude", 0.9, 0.95),
}


class MemorySystem:
    """Manages memory creation, decay, queries, and rumor learning (GDD Section 4)."""

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

        if self.event_bus:
            for ev_type in (
                "CHARACTER_RESCUED",
                "CRIMINAL_SOLD",
                "COMPANION_ABANDONED",
                "CHARACTER_INJURED",
                "LIMB_INJURED",
                "CHARACTER_DIED",
                "ATTACK_RESOLVED",
            ):
                self.event_bus.subscribe(ev_type, self.handle_event)

    def create_memory_from_event(
        self,
        event: GameEvent,
        world: Any = None,
        character: Character | None = None,
    ) -> Memory:
        """Create a Memory object from a GameEvent."""
        active_world = world or self.world
        data = event.data or {}

        def_emotion, def_valence, def_imp = EMOTION_VALENCE_DEFAULTS.get(
            event.event_type, ("Neutral", 0.0, event.importance)
        )
        emotion = str(data.get("emotion", def_emotion))
        valence = float(data.get("emotional_valence", def_valence))
        importance = float(data.get("importance", event.importance if event.importance > 0 else def_imp))

        desc = data.get("description", f"{event.event_type} at {event.location_id}")
        participants = list(event.target_ids)
        if event.source_id and event.source_id not in participants:
            participants.insert(0, event.source_id)

        mem = Memory(
            id=f"mem_{event.id}_{uuid.uuid4().hex[:6]}",
            event_type=event.event_type,
            participants=participants,
            description=desc,
            location_id=event.location_id or "",
            importance=importance,
            emotional_valence=valence,
            confidence=1.0,
            created_at=event.timestamp,
            decay_rate=0.01 if importance >= 0.7 else 0.05,
            emotion=emotion,
        )
        return mem

    def record_event(self, event: GameEvent, world: Any = None) -> list[Memory]:
        """Record memories for all participants and witnesses in the same location."""
        active_world = world or self.world
        created: list[Memory] = []
        if not active_world:
            return created

        data = event.data or {}
        recipients: set[str] = set()

        if data.get("secret") is True:
            # Secret events: only explicit witnesses or targets learn of it
            for tid in event.target_ids:
                recipients.add(tid)
            for w in data.get("witnesses", []):
                recipients.add(w)
        else:
            if event.source_id:
                recipients.add(event.source_id)
            for tid in event.target_ids:
                recipients.add(tid)
            if "witnesses" in data:
                for w in data["witnesses"]:
                    recipients.add(w)
            elif event.location_id:
                for c_id, char in active_world.characters.items():
                    if getattr(char, "location_id", "") == event.location_id:
                        recipients.add(c_id)

        for char_id in recipients:
            char = active_world.characters.get(char_id)
            if char:
                # Dead characters do not form memories
                if getattr(char, "status", "alive") == "dead":
                    continue

                # Deduplication: check if character already recorded this event
                already_has = any(
                    m.id.startswith(f"mem_{event.id}_") or getattr(m, "event_id", "") == event.id
                    for m in char.memories
                )
                if already_has:
                    continue

                mem = self.create_memory_from_event(event, world=active_world, character=char)
                mem.character_id = char_id
                mem.event_id = event.id
                char.memories.append(mem)
                created.append(mem)

        return created

    def handle_event(self, event: GameEvent, world: Any = None) -> None:
        self.record_event(event, world=world)

    def process_event(self, event: GameEvent, world: Any = None) -> None:
        self.record_event(event, world=world)

    def record_rumor_memory(self, character: Character, rumor: Rumor) -> Memory:
        """Record an informational memory learned via rumor with partial confidence."""
        raw_conf = float(getattr(rumor, "confidence", 50.0))
        # Clamp to 0 < confidence < 1.0
        if raw_conf > 1.0:
            conf = min(0.95, max(0.05, raw_conf / 100.0))
        else:
            conf = min(0.95, max(0.05, raw_conf))

        mem = Memory(
            id=f"mem_rumor_{rumor.id}_{uuid.uuid4().hex[:6]}",
            event_type="RUMOR_HEARD",
            participants=[rumor.subject] if rumor.subject else [],
            description=f"Rumor: {rumor.claim}",
            location_id="",
            importance=0.5,
            emotional_valence=0.0,
            confidence=conf,
            created_at=self.clock.timestamp if self.clock else 0,
            decay_rate=0.02,
            emotion="Curiosity",
            source_type="rumor",
        )
        character.memories.append(mem)
        return mem

    def learn_from_rumor(self, character: Character, rumor: Rumor) -> Memory:
        return self.record_rumor_memory(character, rumor)

    def receive_rumor(self, character: Character, rumor: Rumor) -> Memory:
        return self.record_rumor_memory(character, rumor)

    def add_rumor_memory(self, character: Character, rumor: Rumor) -> Memory:
        return self.record_rumor_memory(character, rumor)

    def decay_memories(self, character: Character, days: int = 1) -> None:
        """Decay character memories over elapsed days."""
        remaining: list[Memory] = []
        for mem in character.memories:
            if mem.decay_rate > 0.0:
                mem.importance = max(0.0, mem.importance - (mem.decay_rate * days))
                # Only prune if importance drops near 0 and it had active decay
                if mem.importance <= 0.05:
                    continue
            remaining.append(mem)
        character.memories = remaining

    def process_decay(self, character: Character, days: int = 1) -> None:
        self.decay_memories(character, days)

    def update_memories(self, character: Character, days: int = 1) -> None:
        self.decay_memories(character, days)

    def step_decay(self, character: Character, days: int = 1) -> None:
        self.decay_memories(character, days)

    def query_memories(
        self,
        character: Character,
        participant_id: str | None = None,
        event_type: str | None = None,
    ) -> list[Memory]:
        """Query character memories filtered by participant and/or event_type."""
        results: list[Memory] = []
        for mem in character.memories:
            if participant_id and participant_id not in mem.participants:
                continue
            if event_type and mem.event_type != event_type:
                continue
            results.append(mem)
        return results

    def get_memories_about(self, character: Character, participant_id: str) -> list[Memory]:
        return self.query_memories(character, participant_id=participant_id)

    def filter_memories(self, character: Character, **kwargs: Any) -> list[Memory]:
        return self.query_memories(
            character,
            participant_id=kwargs.get("participant_id"),
            event_type=kwargs.get("event_type"),
        )
