"""World and clock unit tests (GDD Section 2 & 12)."""

import pytest
from core.clock import WorldClock
from core.world import World


def test_world_clock_advancement():
    clock = WorldClock()
    assert clock.year == 1
    assert clock.act == "Prologue"
    clock.advance(518400)
    assert clock.year == 2
    assert clock.act == "Act I"


def test_world_initialization():
    world = World(seed=482193)
    assert world.clock is not None
    assert world.event_bus is not None
    assert world.rng is not None
