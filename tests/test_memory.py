"""Memory system unit tests (GDD Section 4 & 12)."""

import pytest
from core.event_bus import GameEvent
from entities.character import Character, Memory
from entities.quest import Rumor
from systems.memory_system import MemorySystem


def test_memory_creation_from_event():
    mem_sys = MemorySystem()
    ev = GameEvent(
        id="ev1",
        event_type="CHARACTER_RESCUED",
        timestamp=100,
        source_id="player",
        target_ids=["c1"],
        location_id="lowtown",
        data={"emotion": "Gratitude"},
        importance=0.9,
    )
    mem = mem_sys.create_memory_from_event(ev)
    assert mem.event_type == "CHARACTER_RESCUED"
    assert mem.importance == 0.9
    assert mem.confidence == 1.0


def test_memory_decay():
    mem_sys = MemorySystem()
    c = Character(id="c1", name="Observer", age=25)
    mem = Memory(
        id="m1",
        event_type="MINOR_INSULT",
        participants=["p", "c1"],
        importance=0.2,
        emotional_valence=-0.2,
        confidence=1.0,
        created_at=0,
        decay_rate=0.05,
    )
    c.memories.append(mem)
    mem_sys.decay_memories(c, days=5)
    assert len(c.memories) == 0 or c.memories[0].importance < 0.2


def test_memory_rumor_learning():
    mem_sys = MemorySystem()
    c = Character(id="c1", name="Listener", age=30)
    rumor = Rumor(
        id="r1",
        subject="player",
        claim="Player stole silver.",
        origin="npc_1",
        confidence=40.0,
    )
    mem = mem_sys.record_rumor_memory(c, rumor)
    assert 0.0 < mem.confidence < 1.0
