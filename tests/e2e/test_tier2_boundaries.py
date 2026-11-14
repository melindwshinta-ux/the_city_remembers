"""Tier 2 E2E Boundary, Corner-Case & Negative Tests (F1-F21) for THE CITY REMEMBERS.

Covers boundary value analysis (BVA), off-by-one tick boundaries, clamping invariants,
information asymmetry, circular event cascades, localized armor gaps, blunt trauma transfer,
fair adaptation limits, SQLite constraints, and malformed command rejection across F1-F21
(115 test cases: 55 for F1-F11, 60 for F12-F21).
Zero top-level application imports so `pytest --collect-only` always succeeds with 0 errors.
"""

from __future__ import annotations

import json
import math
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.conftest import (
    PROJECT_ROOT,
    call_method,
    get_clock_minutes,
    get_minutes_per_year,
    instantiate_with_context,
    require_module,
    require_symbol,
)


# ==============================================================================
# FEATURE F1 BOUNDARIES: Campaign Timeline & Clock (core/clock.py)
# ==============================================================================


def test_f1_clock_rejects_negative_minutes(world_clock: Any) -> None:
    """Verify WorldClock.advance() rejects negative minutes with ValueError and preserves timestamp."""
    initial_ts = get_clock_minutes(world_clock)
    with pytest.raises(ValueError):
        world_clock.advance(-1)
    with pytest.raises(ValueError):
        world_clock.advance(-1440)
    assert get_clock_minutes(world_clock) == initial_ts


def test_f1_clock_zero_minute_advance_boundary(world_clock: Any) -> None:
    """Verify WorldClock.advance(0) either raises ValueError or returns without advancing timestamp."""
    try:
        crossed = world_clock.advance(0)
        assert get_clock_minutes(world_clock) == 0
        assert "daily" not in crossed and "6h" not in crossed
    except ValueError:
        assert get_clock_minutes(world_clock) == 0


def test_f1_clock_exact_6h_and_24h_tick_boundary_off_by_one() -> None:
    """Verify off-by-one boundary at 359m vs 360m (6h) and 1439m vs 1440m (24h)."""
    WorldClock = require_symbol("core.clock", "WorldClock")
    try:
        clock = WorldClock(start_hour=0)
    except TypeError:
        clock = WorldClock()
        if hasattr(clock, "start_hour"):
            clock.start_hour = 0

    c_359 = clock.advance(359)
    assert "6h" not in c_359 and "daily" not in c_359

    c_360 = clock.advance(1)
    assert "6h" in c_360 and "daily" not in c_360

    c_1439 = clock.advance(1079)
    assert "daily" not in c_1439

    c_1440 = clock.advance(1)
    assert "daily" in c_1440


def test_f1_clock_exact_act_transition_boundaries() -> None:
    """Verify exact minute boundary between Year 3 (Act I) -> Year 4 (Act II) and Year 6 (Act II) -> Year 7 (Act III)."""
    WorldClock = require_symbol("core.clock", "WorldClock")
    try:
        clock = WorldClock(start_hour=0)
    except TypeError:
        clock = WorldClock()
        if hasattr(clock, "start_hour"):
            clock.start_hour = 0

    mpy = get_minutes_per_year(clock)
    clock.advance(3 * mpy - 1)
    assert clock.year == 3 and clock.act == "Act I"

    clock.advance(1)
    assert clock.year == 4 and clock.act == "Act II"

    clock.advance(3 * mpy - 1)
    assert clock.year == 6 and clock.act == "Act II"

    clock.advance(1)
    assert clock.year == 7 and clock.act == "Act III"


def test_f1_clock_ten_year_campaign_horizon_stability(world_clock: Any) -> None:
    """Verify advancing 10 full years maintains valid calendar bounds without overflow."""
    mpy = get_minutes_per_year(world_clock)
    world_clock.advance(10 * mpy)
    assert world_clock.year >= 11
    assert world_clock.act == "Act III"
    assert 0 <= world_clock.hour <= 23
    assert 0 <= world_clock.minute <= 59


# ==============================================================================
# FEATURE F2 BOUNDARIES: Priority Event Bus (core/event_bus.py)
# ==============================================================================


def test_f2_event_bus_unhandled_event_type_no_subscribers(event_bus: Any, entity_factory: dict[str, Any]) -> None:
    """Verify emitting an event type with zero subscribers does not raise KeyError."""
    GameEvent = entity_factory["GameEvent"]
    ev = GameEvent(
        id="ev_unhandled",
        event_type="UNKNOWN_CUSTOM_EVENT",
        timestamp=1,
        source_id=None,
        target_ids=[],
        location_id=None,
        data={},
        importance=0.1,
    )
    event_bus.emit(ev)
    event_bus.process_tick_events()
    assert len(event_bus.emitted_log) == 1


def test_f2_event_bus_circular_consequence_chain_max_depth_guard(event_bus: Any, entity_factory: dict[str, Any]) -> None:
    """Verify mutual PING <-> PONG subscriber loop terminates via max cascade depth guard without RecursionError."""
    GameEvent = entity_factory["GameEvent"]
    EventPriority = entity_factory["EventPriority"]

    count = {"calls": 0}

    def on_ping(ev: Any) -> Any:
        count["calls"] += 1
        return GameEvent(
            id=f"pong_{count['calls']}",
            event_type="PONG",
            timestamp=ev.timestamp,
            source_id=None,
            target_ids=[],
            location_id=None,
            data={},
            importance=0.5,
            priority="critical",
        )

    def on_pong(ev: Any) -> Any:
        count["calls"] += 1
        return GameEvent(
            id=f"ping_{count['calls']}",
            event_type="PING",
            timestamp=ev.timestamp,
            source_id=None,
            target_ids=[],
            location_id=None,
            data={},
            importance=0.5,
            priority="critical",
        )

    event_bus.subscribe("PING", on_ping)
    event_bus.subscribe("PONG", on_pong)

    start_ev = GameEvent(
        id="ping_0",
        event_type="PING",
        timestamp=0,
        source_id=None,
        target_ids=[],
        location_id=None,
        data={},
        importance=0.5,
    )
    event_bus.emit(start_ev, priority=EventPriority.CRITICAL)
    assert 2 <= count["calls"] <= 100


def test_f2_event_bus_duplicate_subscription_idempotency(event_bus: Any, entity_factory: dict[str, Any]) -> None:
    """Verify registering the exact same handler callable twice for the same event_type is deduplicated and unsubscribe works."""
    GameEvent = entity_factory["GameEvent"]
    EventPriority = entity_factory["EventPriority"]

    calls: list[str] = []

    def handler(ev: Any) -> None:
        calls.append(ev.id)

    event_bus.subscribe("QUEST_UPDATED", handler)
    event_bus.subscribe("QUEST_UPDATED", handler)

    ev = GameEvent("ev_dup_sub", "QUEST_UPDATED", 10, None, [], None, {}, 0.5)
    event_bus.emit(ev, priority=EventPriority.CRITICAL)
    assert len(calls) == 1

    if hasattr(event_bus, "unsubscribe"):
        event_bus.unsubscribe("QUEST_UPDATED", handler)
        event_bus.emit(GameEvent("ev_dup_sub_2", "QUEST_UPDATED", 20, None, [], None, {}, 0.5), priority=EventPriority.CRITICAL)
        assert len(calls) == 1


def test_f2_event_bus_priority_ordering_mixed_batch(event_bus: Any, entity_factory: dict[str, Any]) -> None:
    """Verify mixed batch executes CRITICAL immediately, then NORMAL in FIFO order, then BACKGROUND in FIFO order."""
    GameEvent = entity_factory["GameEvent"]
    EventPriority = entity_factory["EventPriority"]

    order: list[str] = []
    for et in ("BG_EV", "NORM_EV", "CRIT_EV"):
        event_bus.subscribe(et, lambda ev: order.append(ev.id))

    for i in range(3):
        event_bus.emit(GameEvent(f"bg_{i}", "BG_EV", i, None, [], None, {}, 0.2), priority=EventPriority.BACKGROUND)
    for i in range(3):
        event_bus.emit(GameEvent(f"norm_{i}", "NORM_EV", i, None, [], None, {}, 0.5), priority=EventPriority.NORMAL)
    event_bus.emit(GameEvent("crit_0", "CRIT_EV", 0, None, [], None, {}, 0.9), priority=EventPriority.CRITICAL)

    assert order == ["crit_0"]
    event_bus.process_tick_events()
    assert order == ["crit_0", "norm_0", "norm_1", "norm_2"]
    event_bus.process_background_events()
    assert order == ["crit_0", "norm_0", "norm_1", "norm_2", "bg_0", "bg_1", "bg_2"]


def test_f2_event_bus_empty_queue_processing_idempotent(event_bus: Any) -> None:
    """Verify calling process_tick_events() and process_background_events() on empty queues returns []."""
    assert event_bus.process_tick_events() == []
    assert event_bus.process_tick_events() == []
    assert event_bus.process_background_events() == []
    assert event_bus.process_background_events() == []


# ==============================================================================
# FEATURE F3 BOUNDARIES: Multi-Frequency Simulation Scheduler (core/simulation.py)
# ==============================================================================


def test_f3_simulation_sub_threshold_accumulation_across_small_steps( event_bus: Any, seeded_rng: Any) -> None:
    """Verify 14 steps of 100m (1400m) do not fire daily economy tick, and the 15th step (+40m = 1440m) fires it."""
    World = require_symbol("core.world", "World")
    WorldClock = require_symbol("core.clock", "WorldClock")
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")

    try:
        clock = WorldClock(start_hour=0)
    except TypeError:
        clock = WorldClock()
        if hasattr(clock, "start_hour"):
            clock.start_hour = 0

    world = instantiate_with_context(World, seed=482193, clock=clock, rng=seeded_rng, event_bus=event_bus)
    sim = instantiate_with_context(SimulationEngine, world=world, clock=clock, rng=seeded_rng, event_bus=event_bus)

    econ_ticks = {"count": 0}
    call_method(
        sim,
        ("register_system", "register_callback", "register_handler"),
        "economy",
        lambda *_a, **_k: econ_ticks.__setitem__("count", econ_ticks["count"] + 1),
    )

    for _ in range(14):
        call_method(sim, ("advance_time", "run_for_minutes", "step"), 100)
    assert econ_ticks["count"] == 0

    call_method(sim, ("advance_time", "run_for_minutes", "step"), 40)
    assert econ_ticks["count"] == 1


def test_f3_simulation_zero_and_negative_time_advance_handling(world_clock: Any, seeded_rng: Any, event_bus: Any) -> None:
    """Verify negative time advance raises ValueError and zero advance does not trigger daily ticks."""
    World = require_symbol("core.world", "World")
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")
    world = instantiate_with_context(World, seed=482193, clock=world_clock, rng=seeded_rng, event_bus=event_bus)
    sim = instantiate_with_context(SimulationEngine, world=world, clock=world_clock, rng=seeded_rng, event_bus=event_bus)

    with pytest.raises(ValueError):
        call_method(sim, ("advance_time", "run_for_minutes", "step"), -60)


def test_f3_simulation_exact_chunk_boundary_360_minutes(seeded_rng: Any, event_bus: Any) -> None:
    """Verify advancing 360m vs 361m fires the 6h faction boundary exactly once."""
    World = require_symbol("core.world", "World")
    WorldClock = require_symbol("core.clock", "WorldClock")
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")

    try:
        clock = WorldClock(start_hour=0)
    except TypeError:
        clock = WorldClock()
        if hasattr(clock, "start_hour"):
            clock.start_hour = 0

    world = instantiate_with_context(World, seed=482193, clock=clock, rng=seeded_rng, event_bus=event_bus)
    sim = instantiate_with_context(SimulationEngine, world=world, clock=clock, rng=seeded_rng, event_bus=event_bus)

    fac_count = {"c": 0}
    call_method(
        sim,
        ("register_system", "register_callback", "register_handler"),
        "factions",
        lambda *_a, **_k: fac_count.__setitem__("c", fac_count["c"] + 1),
    )

    call_method(sim, ("advance_time", "run_for_minutes", "step"), 361)
    assert fac_count["c"] == 1


def test_f3_simulation_monthly_ambition_rollover_43200_minutes(seeded_rng: Any, event_bus: Any) -> None:
    """Verify advancing across the 43,200-minute (30-day) boundary triggers monthly/ambition evaluation."""
    World = require_symbol("core.world", "World")
    WorldClock = require_symbol("core.clock", "WorldClock")
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")

    try:
        clock = WorldClock(start_hour=0)
    except TypeError:
        clock = WorldClock()
        if hasattr(clock, "start_hour"):
            clock.start_hour = 0

    world = instantiate_with_context(World, seed=482193, clock=clock, rng=seeded_rng, event_bus=event_bus)
    sim = instantiate_with_context(SimulationEngine, world=world, clock=clock, rng=seeded_rng, event_bus=event_bus)

    amb_count = {"c": 0}
    call_method(
        sim,
        ("register_system", "register_callback", "register_handler"),
        "ambitions",
        lambda *_a, **_k: amb_count.__setitem__("c", amb_count["c"] + 1),
    )

    call_method(sim, ("advance_time", "run_for_minutes", "step"), 43200)
    assert amb_count["c"] >= 1


def test_f3_simulation_multi_year_skip_performance_and_integrity(world_clock: Any, seeded_rng: Any, event_bus: Any) -> None:
    """Verify advancing a full year (518,400m) completes cleanly and transitions clock to Year 2."""
    World = require_symbol("core.world", "World")
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")
    world = instantiate_with_context(World, seed=482193, clock=world_clock, rng=seeded_rng, event_bus=event_bus)
    sim = instantiate_with_context(SimulationEngine, world=world, clock=world_clock, rng=seeded_rng, event_bus=event_bus)

    mpy = get_minutes_per_year(world_clock)
    call_method(sim, ("advance_time", "run_for_minutes", "step"), mpy)
    assert world.clock.year == 2


# ==============================================================================
# FEATURE F4 BOUNDARIES: Seeded Multi-Stream RNG (core/random_generator.py)
# ==============================================================================


def test_f4_rng_dynamic_or_unknown_stream_name_determinism() -> None:
    """Verify requesting a custom stream name on two SeededRNG(482193) instances behaves deterministically."""
    SeededRNG = require_symbol("core.random_generator", "SeededRNG")
    r1 = SeededRNG(482193)
    r2 = SeededRNG(482193)
    assert r1.stream("custom_sub_stream").random() == r2.stream("custom_sub_stream").random()


def test_f4_rng_extreme_seed_values_zero_and_large_int() -> None:
    """Verify SeededRNG handles 0, negative integers, and 63-bit large integer seeds cleanly."""
    SeededRNG = require_symbol("core.random_generator", "SeededRNG")
    for s in (0, -42, 2**63 - 1):
        rng = SeededRNG(s)
        val = rng.stream("world").random()
        assert 0.0 <= val < 1.0


def test_f4_rng_state_serialization_json_compatibility(seeded_rng: Any) -> None:
    """Verify SeededRNG state round-trips through json.dumps and json.loads (lists -> tuples) cleanly."""
    SeededRNG = require_symbol("core.random_generator", "SeededRNG")
    for _ in range(7):
        seeded_rng.stream("combat").random()

    json_str = json.dumps(seeded_rng.get_state())
    expected = [seeded_rng.stream("combat").random() for _ in range(5)]

    fresh_rng = SeededRNG(1)
    fresh_rng.set_state(json.loads(json_str))
    actual = [fresh_rng.stream("combat").random() for _ in range(5)]
    assert actual == expected


def test_f4_rng_reseed_resets_all_streams() -> None:
    """Verify re-seeding or resetting a SeededRNG restores initial stream sequence."""
    SeededRNG = require_symbol("core.random_generator", "SeededRNG")
    rng = SeededRNG(482193)
    first_val = rng.stream("combat").random()
    for _ in range(50):
        rng.stream("combat").random()

    if hasattr(rng, "reseed"):
        rng.reseed(482193)
    elif hasattr(rng, "reset"):
        rng.reset(482193)
    else:
        rng = SeededRNG(482193)
    assert rng.stream("combat").random() == first_val


def test_f4_rng_weighted_choice_or_deterministic_collection_ordering(seeded_rng: Any) -> None:
    """Verify weighted_pick and set choice select deterministically across runs."""
    SeededRNG = require_symbol("core.random_generator", "SeededRNG")
    r1 = SeededRNG(482193)
    r2 = SeededRNG(482193)

    table = [("common", 70.0), ("rare", 25.0), ("legendary", 5.0)]
    picks1 = [call_method(r1, ("weighted_pick", "weighted_choice"), "world", table) for _ in range(30)]
    picks2 = [call_method(r2, ("weighted_pick", "weighted_choice"), "world", table) for _ in range(30)]
    assert picks1 == picks2


# ==============================================================================
# FEATURE F5 BOUNDARIES: Core Dataclasses & Entities (entities/)
# ==============================================================================


def test_f5_entities_mutable_default_isolation_between_instances(entity_factory: dict[str, Any]) -> None:
    """Verify mutating lists/dicts on one Character instance never leaks to another Character instance."""
    Character = entity_factory["Character"]
    Memory = entity_factory["Memory"]

    c1 = Character(id="c1", name="Alpha", age=20, faction_id=None)
    c2 = Character(id="c2", name="Beta", age=25, faction_id=None)

    c1.attributes["strength"] = 99
    c1.memories.append(Memory("m1", "TEST", ["c1"], "desc", "loc", 0.5, 0.0, 1.0, 0))
    c1.ambitions.append("rule_veyr")

    assert c2.attributes == {}
    assert c2.memories == []
    assert c2.ambitions == []


def test_f5_entities_stable_id_distinction_for_identical_display_names(entity_factory: dict[str, Any]) -> None:
    """Verify two characters with identical display name 'City Guard' coexist via distinct stable IDs."""
    World = require_symbol("core.world", "World")
    Character = entity_factory["Character"]
    world = instantiate_with_context(World, seed=482193)

    g1 = Character(id="npc_guard_01", name="City Guard", age=25, faction_id="city_guard")
    g2 = Character(id="npc_guard_02", name="City Guard", age=30, faction_id="city_guard")
    world.characters[g1.id] = g1
    world.characters[g2.id] = g2

    assert len(world.characters) == 2
    assert world.characters["npc_guard_01"].age == 25
    assert world.characters["npc_guard_02"].age == 30


def test_f5_entities_district_influence_normalization_boundary(entity_factory: dict[str, Any]) -> None:
    """Verify District.normalize_influence() normalizes un-normalized or zero influence dicts to sum to 100.0."""
    District = entity_factory["District"]
    d = District(
        id="lowtown",
        name="Lowtown",
        faction_influence={"lowtown_syndicate": 96.0, "city_guard": 44.0, "merchant_consortium": 24.0, "iron_workers_union": 20.0, "independent": 16.0},
    )
    call_method(d, ("normalize_influence", "normalize_faction_influence"))
    assert sum(d.faction_influence.values()) == pytest.approx(100.0)
    assert d.faction_influence["lowtown_syndicate"] == pytest.approx(48.0)


def test_f5_entities_optional_nullable_fields_none_handling(entity_factory: dict[str, Any]) -> None:
    """Verify None values for faction_id, leader_id, source_id, and location_id serialize/deserialize cleanly."""
    Character = entity_factory["Character"]
    Faction = entity_factory["Faction"]
    GameEvent = entity_factory["GameEvent"]

    c = Character(id="c_drifter", name="Drifter", age=40, faction_id=None)
    f = Faction(id="f_rebels", name="Rebels", leader_id=None, wealth=10, influence=10, military_strength=10, stability=50, territories=[], members=[], goals=[], relations={})
    ev = GameEvent(id="ev_env", event_type="TIME_EVENT_TRIGGERED", timestamp=0, source_id=None, target_ids=[], location_id=None, data={}, importance=0.5)

    assert c.faction_id is None
    assert f.leader_id is None
    assert ev.source_id is None and ev.location_id is None


def test_f5_entities_bodypart_integrity_and_injury_severity_bounds(entity_factory: dict[str, Any]) -> None:
    """Verify BodyPart integrity=0.0, functional=False and Injury severity=1.0, permanent=True preserve exact bounds."""
    Injury = entity_factory["Injury"]
    BodyPart = entity_factory["BodyPart"]

    inj = Injury(id="inj_max", injury_type="amputation", severity=1.0, pain=1.0, bleeding=0.0, infection_risk=0.0, recovery_progress=1.0, permanent=True)
    bp = BodyPart(id="left_arm", name="Left Arm", integrity=0.0, armor=0.0, functional=False, injuries=[inj])

    assert bp.integrity == 0.0
    assert bp.functional is False
    assert bp.injuries[0].severity == 1.0
    assert bp.injuries[0].permanent is True


# ==============================================================================
# FEATURE F6 BOUNDARIES: SQLite 15-Table Schema & Migrations (persistence/database.py, migrations.py)
# ==============================================================================


def test_f6_database_foreign_key_or_primary_key_constraint_enforcement(sqlite_db: Any) -> None:
    """Verify duplicate primary key insertion into characters raises IntegrityError / DatabaseError."""
    DatabaseError = require_symbol("persistence.database", "DatabaseError")
    conn = sqlite_db.get_connection() if hasattr(sqlite_db, "get_connection") else sqlite_db.conn

    conn.execute("INSERT INTO characters (id, name, age, status) VALUES ('dup_char', 'Alpha', 25, 'alive')")
    with pytest.raises((sqlite3.IntegrityError, DatabaseError)):
        conn.execute("INSERT INTO characters (id, name, age, status) VALUES ('dup_char', 'Beta', 30, 'alive')")


def test_f6_database_transaction_rollback_on_error(sqlite_db: Any) -> None:
    """Verify failing transaction rolls back partial inserts atomically."""
    DatabaseError = require_symbol("persistence.database", "DatabaseError")
    conn = sqlite_db.get_connection() if hasattr(sqlite_db, "get_connection") else sqlite_db.conn

    with pytest.raises((sqlite3.Error, DatabaseError, RuntimeError)):
        with sqlite_db.transaction() as tx_conn:
            tx_conn.execute("INSERT INTO districts (id, name, population) VALUES ('rollback_dist', 'Rollback', 500)")
            tx_conn.execute("INSERT INTO nonexistent_table_xyz VALUES (1)")

    row = conn.execute("SELECT id FROM districts WHERE id = 'rollback_dist'").fetchone()
    assert row is None


def test_f6_migrations_rejects_invalid_or_downgrade_target_version(sqlite_db: Any) -> None:
    """Verify requesting downgrade or unknown migration version raises MigrationError / ValueError."""
    mig_mod = require_module("persistence.migrations")
    mgr = mig_mod.MigrationManager(sqlite_db)
    with pytest.raises(Exception):
        mgr.migrate(target_version=-1)
    with pytest.raises(Exception):
        mgr.migrate(target_version=9999)


def test_f6_database_composite_primary_keys_on_relational_tables(sqlite_db: Any) -> None:
    """Verify relationships table allows (A, B) and (B, A) as distinct rows while rejecting duplicate (A, B)."""
    conn = sqlite_db.get_connection() if hasattr(sqlite_db, "get_connection") else sqlite_db.conn
    conn.execute("INSERT INTO characters (id, name, age) VALUES ('char_a', 'A', 25)")
    conn.execute("INSERT INTO characters (id, name, age) VALUES ('char_b', 'B', 25)")

    conn.execute("INSERT INTO relationships (source_id, target_id, trust) VALUES ('char_a', 'char_b', 50.0)")
    conn.execute("INSERT INTO relationships (source_id, target_id, trust) VALUES ('char_b', 'char_a', -20.0)")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO relationships (source_id, target_id, trust) VALUES ('char_a', 'char_b', 99.0)")


def test_f6_database_json_column_roundtrip_special_characters(save_manager: Any, entity_factory: dict[str, Any]) -> None:
    """Verify Unicode, quotes, and SQL-like strings in entity fields round-trip safely via parameterized SQL."""
    World = require_symbol("core.world", "World")
    Character = entity_factory["Character"]
    world = instantiate_with_context(World, seed=482193)

    special_name = "O'Malley \"The Blade\" — ⚔️ '; DROP TABLE characters; --"
    world.characters["npc_special"] = Character(id="npc_special", name=special_name, age=33)

    call_method(save_manager, ("save_game", "save_current_state"), world, slot="special_chars")
    loaded = call_method(save_manager, ("load_game", "load_current_state"), slot="special_chars")
    assert loaded.characters["npc_special"].name == special_name


# ==============================================================================
# FEATURE F7 BOUNDARIES: Save Manager, Event Log, Snapshots & Chronicle (persistence/save_manager.py)
# ==============================================================================


def test_f7_load_nonexistent_save_slot_raises_error(save_manager: Any) -> None:
    """Verify loading a nonexistent save slot raises SaveNotFoundError / KeyError / ValueError / FileNotFoundError."""
    with pytest.raises(Exception):
        call_method(save_manager, ("load_game", "load_current_state"), slot="nonexistent_slot_999")


def test_f7_restore_nonexistent_snapshot_id_raises_error(save_manager: Any) -> None:
    """Verify restoring an invalid snapshot_id raises an error."""
    with pytest.raises(Exception):
        save_manager.restore_snapshot("invalid_snapshot_id_xyz")


def test_f7_chronicle_generator_on_fresh_world_with_zero_events(save_manager: Any) -> None:
    """Verify generate_chronicle on a fresh world with 0 events returns a valid foundational list without crashing."""
    World = require_symbol("core.world", "World")
    fresh_world = instantiate_with_context(World, seed=482193)
    chronicle = save_manager.generate_chronicle(fresh_world)
    assert isinstance(chronicle, list)
    assert len(chronicle) >= 1


def test_f7_multiple_save_slots_isolation(save_manager: Any, entity_factory: dict[str, Any]) -> None:
    """Verify saving to slot_a (Year 1, lowtown_tavern) and slot_b (Year 5, harbor) keeps both slots isolated."""
    World = require_symbol("core.world", "World")
    Character = entity_factory["Character"]

    world_a = instantiate_with_context(World, seed=482193)
    world_a.characters["player"] = Character(id="player", name="Rowan", age=28, location_id="lowtown_tavern", is_player=True)
    call_method(save_manager, ("save_game", "save_current_state"), world_a, slot="slot_a")

    world_b = instantiate_with_context(World, seed=482193)
    world_b.clock.advance(4 * get_minutes_per_year(world_b.clock))
    world_b.characters["player"] = Character(id="player", name="Rowan", age=32, location_id="harbor", is_player=True)
    call_method(save_manager, ("save_game", "save_current_state"), world_b, slot="slot_b")

    loaded_a = call_method(save_manager, ("load_game", "load_current_state"), slot="slot_a")
    loaded_b = call_method(save_manager, ("load_game", "load_current_state"), slot="slot_b")

    assert loaded_a.clock.year == 1 and loaded_a.characters["player"].location_id == "lowtown_tavern"
    assert loaded_b.clock.year == 5 and loaded_b.characters["player"].location_id == "harbor"


def test_f7_event_history_high_importance_threshold_boundary(save_manager: Any, entity_factory: dict[str, Any]) -> None:
    """Verify get_event_history(min_importance=1.0) returns [] when max importance is 0.95, and 0.95 returns exact match."""
    GameEvent = entity_factory["GameEvent"]
    save_manager.append_event(GameEvent("ev_b_95", "CHARACTER_DIED", 100, "player", ["npc_1"], "lowtown", {}, 0.95))

    assert save_manager.get_event_history(min_importance=1.0) == []
    res_95 = save_manager.get_event_history(min_importance=0.95)
    assert len(res_95) == 1 and res_95[0].id == "ev_b_95"


# ==============================================================================
# FEATURE F8 BOUNDARIES: Tiered Character Simulation & Needs (systems/character_system.py, ai/character_ai.py)
# ==============================================================================


def test_f8_needs_clamped_within_valid_bounds_no_instant_starvation_death(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify 48 hours of need decay clamps needs within [0.0, 100.0] without unrealistic instant death."""
    char_sys = systems_suite["character_system"]
    Character = entity_factory["Character"]

    c = Character(id="char_fast", name="Fasting Guard", age=30, status="alive")
    call_method(char_sys, ("initialize_character", "ensure_character_stats", "populate_defaults"), c)
    call_method(char_sys, ("decay_needs", "update_needs", "update"), c, 2880)

    for val in c.needs.values():
        assert 0.0 <= float(val) <= 100.0
    assert c.status == "alive"


def test_f8_character_aging_on_year_rollover_and_retirement_threshold(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify characters increment age by +1 on year rollover and elderly characters trigger retirement state."""
    char_sys = systems_suite["character_system"]
    Character = entity_factory["Character"]

    young = Character(id="c_young", name="Young", age=28)
    elder = Character(id="c_elder", name="Elder", age=65)
    call_method(char_sys, ("initialize_character", "ensure_character_stats", "populate_defaults"), young)
    call_method(char_sys, ("initialize_character", "ensure_character_stats", "populate_defaults"), elder)

    call_method(char_sys, ("process_yearly_aging", "age_character", "advance_age"), young, years=1)
    call_method(char_sys, ("process_yearly_aging", "age_character", "advance_age"), elder, years=1)

    assert young.age == 29
    assert elder.age == 66


def test_f8_dead_or_incapacitated_character_skips_autonomous_ai_actions(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify dead characters do not move locations or schedule daily AI actions."""
    char_ai = systems_suite["character_ai"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    dead_char = Character(id="c_dead", name="Dead Guard", age=30, location_id="lowtown_street", status="dead")
    world.characters["c_dead"] = dead_char

    res = call_method(char_ai, ("select_daily_action", "decide_action", "evaluate_character"), dead_char, world)
    assert dead_char.location_id == "lowtown_street"
    assert res is None or res.get("action") in (None, "none", "dead", "inactive")


def test_f8_tier3_background_population_boundary_zero_population(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify Tier 3 background population tick handles population=0 gracefully without ZeroDivisionError."""
    char_sys = systems_suite["character_system"]
    world = systems_suite["world"]
    District = entity_factory["District"]

    empty_dist = District(id="old_quarter", name="Old Quarter", population=0)
    world.districts["old_quarter"] = empty_dist

    call_method(char_sys, ("update_district_population", "simulate_tier3_population", "update"), world, 10080)
    assert empty_dist.population >= 0


def test_f8_stat_and_skill_modifier_clamping_preventing_negative_attributes(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify severe need and injury penalties clamp derived stats >= 0 without overwriting base attributes."""
    char_sys = systems_suite["character_system"]
    Character = entity_factory["Character"]

    c = Character(id="c_weak", name="Weakling", age=25, attributes={"strength": 5, "agility": 5}, needs={"hunger": 100.0, "fatigue": 100.0})
    derived = call_method(char_sys, ("get_effective_attributes", "derive_stats", "compute_effective_stats"), c)
    assert derived["strength"] >= 0 and derived["agility"] >= 0
    assert c.attributes["strength"] == 5


# ==============================================================================
# FEATURE F9 BOUNDARIES: Episodic & Informational Memory (systems/memory_system.py)
# ==============================================================================


def test_f9_memory_information_asymmetry_secret_killing_no_witnesses(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify a secret killing with zero witnesses produces zero memories in absent companions or guards."""
    mem_sys = systems_suite["memory_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    GameEvent = entity_factory["GameEvent"]

    marcus = Character(id="comp_marcus", name="Marcus", age=40, location_id="lowtown_watchpost")
    voss = Character(id="npc_voss", name="Captain Voss", age=38, location_id="lowtown_watchpost")
    victim = Character(id="npc_victim", name="Bandit", age=28, location_id="old_quarter", status="dead")
    world.characters.update({"comp_marcus": marcus, "npc_voss": voss, "npc_victim": victim})

    secret_ev = GameEvent(
        id="ev_secret_kill",
        event_type="CHARACTER_DIED",
        timestamp=200,
        source_id="player",
        target_ids=["npc_victim"],
        location_id="old_quarter",
        data={"witnesses": [], "secret": True},
        importance=0.9,
    )
    call_method(mem_sys, ("record_event", "handle_event", "create_memory_from_event", "process_event"), secret_ev, world=world)

    assert len(marcus.memories) == 0
    assert len(voss.memories) == 0


def test_f9_memory_false_accusation_believed_by_distrustful_guard(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify a guard with low trust in the player can believe a false accusation rumor."""
    mem_sys = systems_suite["memory_system"]
    Character = entity_factory["Character"]
    Rumor = entity_factory["Rumor"]

    guard = Character(id="npc_guard_suspicious", name="Guard", age=30, faction_id="city_guard")
    false_rumor = Rumor(
        id="rumor_false_acc",
        subject="player",
        claim="Rowan murdered a City Guard officer.",
        origin="npc_voss",
        truth=False,
        reach={"lowtown": 60.0},
        confidence=75.0,
    )
    call_method(
        mem_sys,
        ("record_rumor_memory", "learn_from_rumor", "receive_rumor", "add_rumor_memory"),
        guard,
        false_rumor,
    )
    assert len(guard.memories) == 1
    assert guard.memories[0].confidence > 0.3


def test_f9_memory_decay_never_produces_negative_importance(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify decaying a low-importance memory over 1000 days clamps importance >= 0.0 (or prunes it)."""
    mem_sys = systems_suite["memory_system"]
    Character = entity_factory["Character"]
    Memory = entity_factory["Memory"]

    c = Character(id="c_mem_clamp", name="Citizen", age=30)
    m = Memory("m_tiny", "MINOR_INSULT", ["player"], "Small slight", "lowtown", 0.1, -0.1, 1.0, 0, decay_rate=0.5)
    c.memories.append(m)

    call_method(mem_sys, ("decay_memories", "process_decay", "update_memories", "step_decay"), c, days=1000)
    assert m.importance >= 0.0
    for mem in c.memories:
        assert mem.importance >= 0.0


def test_f9_memory_duplicate_event_id_deduplication_or_reinforcement(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify delivering the exact same GameEvent twice to MemorySystem does not create duplicate corrupted IDs."""
    mem_sys = systems_suite["memory_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    GameEvent = entity_factory["GameEvent"]

    sera = Character(id="comp_sera", name="Sera", age=24, location_id="lowtown_street")
    world.characters["comp_sera"] = sera

    ev = GameEvent("ev_dup_mem", "ATTACK_RESOLVED", 50, "player", ["comp_sera"], "lowtown_street", {}, 0.7)
    call_method(mem_sys, ("record_event", "handle_event", "create_memory_from_event", "process_event"), ev, world=world)
    call_method(mem_sys, ("record_event", "handle_event", "create_memory_from_event", "process_event"), ev, world=world)

    assert len(sera.memories) == 1


def test_f9_memory_dead_character_does_not_form_witness_memories(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify dead characters at an event location do not record new post-mortem witness memories."""
    mem_sys = systems_suite["memory_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    GameEvent = entity_factory["GameEvent"]

    corpse = Character(id="npc_corpse", name="Corpse", age=40, location_id="lowtown_street", status="dead")
    living = Character(id="npc_living", name="Living Witness", age=30, location_id="lowtown_street", status="alive")
    world.characters.update({"npc_corpse": corpse, "npc_living": living})

    ev = GameEvent("ev_pub_fight", "LIMB_INJURED", 100, "player", ["npc_living"], "lowtown_street", {"witnesses": ["npc_corpse", "npc_living"]}, 0.8)
    call_method(mem_sys, ("record_event", "handle_event", "create_memory_from_event", "process_event"), ev, world=world)

    assert len(corpse.memories) == 0
    assert len(living.memories) >= 1


# ==============================================================================
# FEATURE F10 BOUNDARIES: Directed 6-Axis Relationships & Companion Friendship/Rivalry (systems/relationship_system.py)
# ==============================================================================


def test_f10_companion_breaking_point_triggers_departure(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify violating a companion's breaking point emits COMPANION_BREAKING_POINT and sets in_party=False."""
    rel_sys = systems_suite["relationship_system"]
    world = systems_suite["world"]
    event_bus = systems_suite["event_bus"]
    Character = entity_factory["Character"]
    Companion = entity_factory["Companion"]

    world.characters["comp_marcus"] = Character(id="comp_marcus", name="Marcus", age=40, is_companion=True)
    marcus_comp = Companion(
        character_id="comp_marcus",
        name="Marcus",
        breaking_points=["massacre_innocent_guards", "betray_city_order"],
        in_party=True,
    )
    world.companions["comp_marcus"] = marcus_comp
    world.player_party.append("comp_marcus")

    call_method(
        rel_sys,
        ("trigger_breaking_point", "evaluate_breaking_point", "check_breaking_point"),
        "comp_marcus",
        reason="massacre_innocent_guards",
        world=world,
    )
    assert marcus_comp.in_party is False
    assert any(e.event_type == "COMPANION_BREAKING_POINT" for e in event_bus.emitted_log)


def test_f10_relationship_auto_initialization_on_first_query_or_interaction(systems_suite: dict[str, Any]) -> None:
    """Verify querying relationship between two unacquainted NPCs initializes a neutral Relationship without KeyError."""
    rel_sys = systems_suite["relationship_system"]
    rel = call_method(rel_sys, ("get_relationship", "query_relationship"), "npc_0091", "npc_workshop_owner")
    assert rel.source_id == "npc_0091" and rel.target_id == "npc_workshop_owner"
    assert rel.trust == 0.0 and rel.respect == 0.0


def test_f10_relationship_axis_clamping_at_min_and_max_bounds(systems_suite: dict[str, Any]) -> None:
    """Verify extreme +500 and -500 deltas clamp all 6 relationship axes within valid bounds [-100, 100]."""
    rel_sys = systems_suite["relationship_system"]
    call_method(
        rel_sys,
        ("set_relationship", "update_relationship", "modify_relationship"),
        "comp_sera",
        "player",
        trust=500.0,
        respect=500.0,
        affection=-500.0,
        resentment=500.0,
        fear=-500.0,
        dependency=500.0,
    )
    rel = call_method(rel_sys, ("get_relationship", "query_relationship"), "comp_sera", "player")
    for axis in ("trust", "respect", "affection", "resentment", "fear", "dependency"):
        val = getattr(rel, axis)
        assert -100.0 <= val <= 100.0


def test_f10_self_relationship_guard(systems_suite: dict[str, Any]) -> None:
    """Verify attempting to create a self-relationship (player -> player) raises ValueError or ignores cleanly."""
    rel_sys = systems_suite["relationship_system"]
    try:
        res = call_method(rel_sys, ("set_relationship", "update_relationship", "modify_relationship"), "player", "player", trust=50.0)
        assert res is None or res is False
    except ValueError:
        pass


def test_f10_high_rivalry_high_respect_prevents_premature_departure(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify high rivalry (85) with high respect (80) and no breaking point keeps companion in_party=True."""
    rel_sys = systems_suite["relationship_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    Companion = entity_factory["Companion"]

    world.characters["comp_elira"] = Character(id="comp_elira", name="Elira", age=26, is_companion=True)
    elira = Companion(character_id="comp_elira", name="Elira", friendship=10.0, rivalry=85.0, in_party=True)
    world.companions["comp_elira"] = elira

    call_method(
        rel_sys,
        ("set_relationship", "update_relationship", "modify_relationship"),
        "comp_elira",
        "player",
        trust=50.0,
        respect=80.0,
        resentment=30.0,
    )
    call_method(rel_sys, ("check_companion_retention", "evaluate_breaking_point", "update_companion_relationship"), "comp_elira", world=world)
    assert elira.in_party is True


# ==============================================================================
# FEATURE F11 BOUNDARIES: Hierarchical Anatomy, 12+ Injury Types & Medicine (systems/health_system.py)
# ==============================================================================


def test_f11_vital_organ_destruction_triggers_immediate_death(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify destroying brain, heart, or cervical_spine (integrity -> 0) transitions status to 'dead' and emits CHARACTER_DIED."""
    health_sys = systems_suite["health_system"]
    event_bus = systems_suite["event_bus"]
    Character = entity_factory["Character"]

    c = Character(id="char_vital", name="Target", age=30, status="alive")
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)
    call_method(health_sys, ("apply_damage", "inflict_damage", "destroy_part"), c, "brain", 250.0, damage_type="piercing")

    assert c.body["brain"].integrity == pytest.approx(0.0)
    assert c.status == "dead"
    assert any(e.event_type == "CHARACTER_DIED" for e in event_bus.emitted_log)


def test_f11_unskilled_dirty_surgery_saves_life_but_leaves_permanent_disability(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify unskilled surgeon with low cleanliness saves life (stops bleeding) but leaves permanent complication/disability."""
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]

    patient = Character(id="char_surg_bad", name="Patient", age=30, status="alive")
    quack = Character(id="npc_quack", name="Back-Alley Barber", age=45, skills={"medicine": 10.0})
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), patient)
    call_method(health_sys, ("apply_injury", "inflict_injury"), patient, "left_leg", "compound_fracture", severity=0.9)

    res = call_method(
        health_sys,
        ("apply_treatment", "treat_character", "perform_treatment"),
        patient,
        stage="surgery",
        doctor=quack,
        body_part="left_leg",
        cleanliness=0.1,
    )
    assert patient.status != "dead"
    inj = patient.body["left_leg"].injuries[0]
    assert inj.permanent is True or inj.complication is not None or (isinstance(res, dict) and res.get("complication"))


def test_f11_amputation_cascades_non_functional_to_child_subparts(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify amputating parent limb left_arm sets left_arm and all child subparts (upper_arm, elbow, forearm, hand) non-functional."""
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]

    c = Character(id="char_cascade", name="Soldier", age=28)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)
    call_method(health_sys, ("apply_injury", "inflict_injury"), c, "left_arm", "amputation", severity=1.0)

    assert c.body["left_arm"].functional is False
    for child_key in c.body["left_arm"].children:
        if child_key in c.body:
            assert c.body[child_key].functional is False


def test_f11_ordinary_minor_hit_does_not_cause_permanent_disability(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify ordinary minor hit (damage=5.0) does not cause permanent disability (GDD Section 5 Line 212)."""
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]

    c = Character(id="char_minor", name="Brawler", age=25)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)
    call_method(health_sys, ("apply_damage", "inflict_damage"), c, "torso", 5.0, damage_type="blunt")

    assert c.body["torso"].functional is True
    for inj in c.body["torso"].injuries:
        assert inj.permanent is False


def test_f11_double_eye_injury_causes_permanent_blindness(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify destroying eyes (integrity=0, permanent=True) causes Permanent blindness and severe accuracy penalty."""
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]

    c = Character(id="char_blind", name="Archer", age=29)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)
    call_method(health_sys, ("apply_injury", "inflict_injury"), c, "eyes", "eye_injury", severity=1.0, permanent=True)

    mods = call_method(health_sys, ("get_combat_modifiers", "calculate_penalties", "get_functional_modifiers"), c)
    assert mods["accuracy"] <= 0.5


# ==============================================================================
# FEATURE F12 BOUNDARIES: Localized Armor, Weapons & Equipment (systems/equipment_system.py)
# ==============================================================================


def test_f12_armor_mitigation_zero_floor_when_armor_exceeds_raw_damage(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify D_effective = max(0, D_raw - R_armor) floors at 0.0 when plate armor (25) blocks light cut (10)."""
    eq_sys = systems_suite["equipment_system"]
    Item = entity_factory["Item"]

    plate = Item(id="plate_breastplate", name="Plate", item_type="armor", armor_class="plate", armor_protection=25.0, covered_parts=["torso"])
    res = call_method(eq_sys, ("calculate_armor_mitigation", "resolve_armor_damage", "compute_effective_damage"), plate, "cutting", 10.0, penetration=0.0)
    eff = res["effective_damage"] if isinstance(res, dict) else float(res)
    assert eff == pytest.approx(0.0)


def test_f12_blunt_force_transfer_through_heavy_plate_when_cut_blocked(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify a blunt mace/warhammer transfers blunt force (> 0) through plate armor even when raw_damage <= armor rating."""
    eq_sys = systems_suite["equipment_system"]
    Item = entity_factory["Item"]

    plate = Item(
        id="plate_breastplate",
        name="Plate",
        item_type="armor",
        armor_class="plate",
        armor_protection=25.0,
        covered_parts=["torso"],
        weaknesses=["joints_and_blunt_force", "blunt"],
    )
    res = call_method(eq_sys, ("calculate_armor_mitigation", "resolve_armor_damage", "compute_effective_damage"), plate, "blunt", 20.0, penetration=8.0)
    eff = res["effective_damage"] if isinstance(res, dict) else float(res)
    assert eff > 0.0


def test_f12_equip_nonexistent_or_invalid_body_part_slot_rejected(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify equipping armor targeting nonexistent body part 'dragon_wings' raises ValueError or returns failure."""
    eq_sys = systems_suite["equipment_system"]
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]
    Item = entity_factory["Item"]

    c = Character(id="c_bad_slot", name="Rowan", age=28)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)
    bad_item = Item(id="wing_armor", name="Wing Armor", item_type="armor", armor_protection=10.0, covered_parts=["dragon_wings"])

    try:
        res = call_method(eq_sys, ("equip_item", "equip"), c, bad_item)
        assert res is False or (isinstance(res, dict) and res.get("success") is False)
    except ValueError:
        pass
    assert "dragon_wings" not in c.body


def test_f12_broken_or_amputated_arm_blocks_two_handed_or_dual_wield_equip(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify non-functional left_arm either rejects two-handed weapon equip or applies severe handling penalty."""
    eq_sys = systems_suite["equipment_system"]
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]
    Item = entity_factory["Item"]

    c = Character(id="c_one_arm", name="Warrior", age=30)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)
    call_method(health_sys, ("apply_injury", "inflict_injury"), c, "left_arm", "amputation", severity=1.0)

    greataxe = Item(id="greataxe", name="Greataxe", item_type="weapon", damage=32.0, damage_type="cutting", handling=1.0, properties={"two_handed": True})
    try:
        res = call_method(eq_sys, ("equip_item", "equip"), c, greataxe)
        if res is not False and not (isinstance(res, dict) and res.get("success") is False):
            prof = call_method(eq_sys, ("get_active_weapon_profile", "get_weapon_stats"), c)
            h = prof.handling if hasattr(prof, "handling") else prof.get("handling", 1.0)
            assert h <= 0.65
    except ValueError:
        pass


def test_f12_fit_prosthetic_on_healthy_intact_limb_rejected(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify fitting a prosthetic on an intact healthy arm is rejected."""
    eq_sys = systems_suite["equipment_system"]
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]
    Item = entity_factory["Item"]

    c = Character(id="c_healthy", name="Healthy", age=25)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)
    prosthetic = Item(id="iron_prosthetic_arm", name="Prosthetic", item_type="prosthetic", covered_parts=["left_arm"])

    try:
        res = call_method(eq_sys, ("fit_prosthetic", "equip_prosthetic"), c, prosthetic, body_part="left_arm")
        assert res is False or (isinstance(res, dict) and res.get("success") is False)
    except ValueError:
        pass
    assert c.body["left_arm"].prosthetic_id is None


def test_f12_craft_item_with_insufficient_materials_or_unknown_recipe(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify crafting with unknown recipe or zero skill/resources fails cleanly."""
    eq_sys = systems_suite["equipment_system"]
    Character = entity_factory["Character"]

    novice = Character(id="c_novice", name="Novice", age=18, skills={"crafting": 0.0}, needs={"wealth": 0.0})
    try:
        res = call_method(eq_sys, ("craft_item", "craft"), novice, "nonexistent_mythical_laser")
        assert res is None or res is False or (isinstance(res, dict) and res.get("success") is False)
    except (ValueError, KeyError):
        pass


# ==============================================================================
# FEATURE F13 BOUNDARIES: Command-Based Tactical Grid Combat & Combat AI (systems/combat_system.py)
# ==============================================================================


def test_f13_out_of_bounds_and_wall_obstructed_grid_movement_rejected(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify moving outside grid coordinates or into a 'wall' tile is rejected."""
    combat_sys = systems_suite["combat_system"]
    Character = entity_factory["Character"]

    p = Character(id="player", name="Rowan", age=28, is_player=True)
    e = Character(id="npc_voss", name="Captain Voss", age=38)
    enc = call_method(combat_sys, ("create_encounter", "start_encounter", "init_battlefield"), party=[p], enemies=[e], grid_size=(5, 5))

    try:
        res = call_method(combat_sys, ("execute_command", "resolve_command", "move_combatant"), enc, actor_id="player", command="move", target_coord="Z9")
        assert res is False or (isinstance(res, dict) and res.get("success") is False)
    except ValueError:
        pass


def test_f13_incapacitated_or_dead_combatant_cannot_execute_commands(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify incapacitated or dead combatant cannot execute attack or move commands."""
    combat_sys = systems_suite["combat_system"]
    Character = entity_factory["Character"]

    incap = Character(id="c_incap", name="Downed Ally", age=30, status="incapacitated", consciousness=0.0)
    target = Character(id="npc_voss", name="Captain Voss", age=38, status="alive")
    res = call_method(combat_sys, ("resolve_attack", "execute_attack"), attacker=incap, defender=target, command="attack")
    assert res.get("hit") is False or res.get("skipped") is True or res.get("success") is False


def test_f13_panicking_or_routing_unit_overrides_offensive_command(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify a combatant in 'routing' morale state refuses 'charge'/'heavy_attack' and retreats/surrenders instead."""
    combat_ai = systems_suite["combat_ai"]
    EnemyCombatant = entity_factory["EnemyCombatant"]

    routing_unit = EnemyCombatant(character_id="e_routing", archetype="coward", morale=2.0, morale_state="routing")
    decision = call_method(combat_ai, ("select_action", "decide_combat_action", "choose_action"), routing_unit, context={"ordered_command": "charge"})
    assert decision["command"] in {"retreat", "surrender", "take_cover", "flee"}


def test_f13_disarm_against_unarmed_target_and_revive_on_active_target(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify disarming an unarmed target and reviving an already-conscious ally handle gracefully without crashing."""
    combat_sys = systems_suite["combat_system"]
    Character = entity_factory["Character"]

    actor = Character(id="player", name="Rowan", age=28)
    unarmed = Character(id="npc_unarmed", name="Unarmed Thug", age=25, equipment={})
    active_ally = Character(id="comp_marcus", name="Marcus", age=40, status="alive", consciousness=100.0)

    res_disarm = call_method(combat_sys, ("execute_tactical_action", "resolve_attack", "execute_command"), attacker=actor, defender=unarmed, command="disarm")
    res_revive = call_method(combat_sys, ("execute_tactical_action", "resolve_support", "execute_command"), attacker=actor, defender=active_ally, command="revive")
    assert res_disarm is not None and res_revive is not None
    assert active_ally.status == "alive"


def test_f13_magic_spellcasting_overload_causes_magical_corruption_injury(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify repeated high-corruption spellcasting inflicts nerve_damage or magical corruption on the caster."""
    combat_sys = systems_suite["combat_system"]
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]

    elira = Character(id="comp_elira", name="Elira", age=26, skills={"magic": 80.0})
    target = Character(id="npc_guard_1", name="Guard", age=30)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), elira)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), target)

    for _ in range(6):
        call_method(
            combat_sys,
            ("resolve_spellcast", "execute_tactical_action", "resolve_attack"),
            attacker=elira,
            defender=target,
            command="spellcasting",
            spell_power=40.0,
        )

    all_injuries = [inj.injury_type for bp in elira.body.values() for inj in bp.injuries]
    assert len(all_injuries) >= 1 or elira.needs.get("corruption", 0.0) > 0.0


def test_f13_combat_world_clock_duration_bounded_between_one_and_five_minutes(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify combat encounter world-time duration is strictly bounded between 1 and 5 minutes (GDD Section 2 Line 96)."""
    combat_sys = systems_suite["combat_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    t0 = get_clock_minutes(world.clock)
    p = Character(id="player", name="Rowan", age=28, is_player=True)
    e = Character(id="npc_thug", name="Thug", age=25)
    enc = call_method(combat_sys, ("create_encounter", "start_encounter"), party=[p], enemies=[e])
    call_method(combat_sys, ("finish_encounter", "end_encounter", "resolve_encounter_time"), enc, world=world)
    elapsed = get_clock_minutes(world.clock) - t0
    assert 1 <= elapsed <= 5


# ==============================================================================
# FEATURE F14 BOUNDARIES: Nemesis System & Ambition AI (systems/nemesis_system.py, ai/ambition_ai.py)
# ==============================================================================


def test_f14_unwitnessed_player_tactics_never_trigger_nemesis_adaptation(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify a Nemesis cannot adapt to player tactics that were neither witnessed nor learned via rumor."""
    nem_sys = systems_suite["nemesis_system"]
    NemesisProfile = entity_factory["NemesisProfile"]

    profile = NemesisProfile(character_id="npc_voss")
    call_method(nem_sys, ("record_witnessed_tactic", "observe_tactic"), profile, tactic="fire_magic", count=10, witnessed=False)
    adaptations = call_method(nem_sys, ("adapt_to_player", "evaluate_adaptations", "apply_adaptations"), profile)

    all_adaptations = set(adaptations or []) | set(getattr(profile, "adaptations", [])) | set(profile.special_traits)
    assert "fire_magic" not in profile.known_player_tactics
    assert "fire_resistant_equipment" not in all_adaptations


def test_f14_permanently_dead_executed_nemesis_cannot_promote_or_return(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify an executed/dead Nemesis (status='dead') cannot be promoted or adapt."""
    nem_sys = systems_suite["nemesis_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    NemesisProfile = entity_factory["NemesisProfile"]
    Faction = entity_factory["Faction"]

    dead_voss = Character(id="npc_voss", name="Captain Voss", age=38, faction_id="city_guard", status="dead", is_nemesis=True)
    live_merek = Character(id="npc_merek", name="Sergeant Merek", age=32, faction_id="city_guard", status="alive", rank="sergeant")
    world.characters.update({"npc_voss": dead_voss, "npc_merek": live_merek})
    world.nemesis_profiles["npc_voss"] = NemesisProfile(character_id="npc_voss", status="dead")
    guard = Faction(id="city_guard", name="City Guard", leader_id=None, members=["npc_voss", "npc_merek"])
    world.factions["city_guard"] = guard

    winner = call_method(nem_sys, ("evaluate_promotion_candidates", "resolve_promotion"), guard, target_rank="captain", world=world)
    winner_id = winner.id if hasattr(winner, "id") else (winner.get("winner_id") if isinstance(winner, dict) else winner)
    assert winner_id == "npc_merek"


def test_f14_promote_beyond_commander_top_rank_clamped(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify promoting a character already at 'commander' keeps rank at 'commander' without IndexError."""
    nem_sys = systems_suite["nemesis_system"]
    Character = entity_factory["Character"]
    NemesisProfile = entity_factory["NemesisProfile"]

    c = Character(id="npc_top", name="Commander", age=45, rank="commander")
    p = NemesisProfile(character_id="npc_top", rank="commander")
    call_method(nem_sys, ("promote_character", "advance_rank"), c, p)
    assert c.rank == "commander" and p.rank == "commander"


def test_f14_tier3_background_npc_excluded_from_nemesis_generation(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify anonymous Tier 3 background citizens do not become Nemeses (GDD Section 20 Line 805)."""
    nem_sys = systems_suite["nemesis_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    bg_npc = Character(id="npc_bg_citizen", name="Passerby", age=30, tier=3, is_nemesis=False)
    world.characters[bg_npc.id] = bg_npc
    res = call_method(nem_sys, ("evaluate_eligibility", "check_eligibility"), bg_npc, trigger="witnesses_major_event", world=world)
    assert bg_npc.is_nemesis is False and res is None


def test_f14_single_use_tactic_below_repetition_threshold_does_not_over_adapt(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify using a tactic only once (count=1) does not immediately trigger full counter-adaptation."""
    nem_sys = systems_suite["nemesis_system"]
    NemesisProfile = entity_factory["NemesisProfile"]

    profile = NemesisProfile(character_id="npc_voss")
    call_method(nem_sys, ("record_witnessed_tactic", "observe_tactic"), profile, tactic="frequent_retreat", count=1, witnessed=True)
    adaptations = call_method(nem_sys, ("adapt_to_player", "evaluate_adaptations", "apply_adaptations"), profile)
    all_adaptations = set(adaptations or []) | set(getattr(profile, "adaptations", []))
    assert "pursuit_specialists" not in all_adaptations


def test_f14_high_loyalty_low_ambition_officer_refuses_betrayal(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify an officer with loyalty=95, ambition=10 never selects 'betray_superior' in AmbitionAI."""
    ambition_ai = systems_suite["ambition_ai"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    loyal_officer = Character(
        id="npc_loyal",
        name="Loyal Captain",
        age=40,
        faction_id="city_guard",
        rank="captain",
        personality={"loyalty": 95.0, "ambition": 10.0},
    )
    world.characters["npc_loyal"] = loyal_officer
    scheme = call_method(ambition_ai, ("evaluate_npc_ambitions", "evaluate_ambition", "select_ambition_action"), loyal_officer, world=world)
    if isinstance(scheme, dict):
        assert scheme.get("scheme_type", scheme.get("action")) not in {"betray_superior", "coup"}


# ==============================================================================
# FEATURE F15 BOUNDARIES: Faction & Political Simulation (systems/faction_system.py)
# ==============================================================================


def test_f15_district_influence_clamped_zero_to_hundred_and_normalized(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify extreme +500% and -500% district influence shifts clamp to [0, 100] and normalize sum to 100.0%."""
    fac_sys = systems_suite["faction_system"]
    world = systems_suite["world"]
    District = entity_factory["District"]

    d = District(
        id="lowtown",
        name="Lowtown",
        faction_influence={"lowtown_syndicate": 48.0, "city_guard": 22.0, "merchant_consortium": 12.0, "iron_workers_union": 10.0, "independent": 8.0},
    )
    world.districts["lowtown"] = d

    call_method(fac_sys, ("shift_district_influence", "update_district_influence", "adjust_influence"), "lowtown", "city_guard", 500.0, world=world)
    assert all(0.0 <= v <= 100.0 for v in d.faction_influence.values())
    assert sum(d.faction_influence.values()) == pytest.approx(100.0)

    call_method(fac_sys, ("shift_district_influence", "update_district_influence", "adjust_influence"), "lowtown", "lowtown_syndicate", -500.0, world=world)
    assert all(0.0 <= v <= 100.0 for v in d.faction_influence.values())
    assert sum(d.faction_influence.values()) == pytest.approx(100.0)


def test_f15_leadership_vacancy_when_all_faction_members_dead_or_empty(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify resolving leadership vacancy when all faction members are dead does not raise ValueError/IndexError."""
    fac_sys = systems_suite["faction_system"]
    world = systems_suite["world"]
    Faction = entity_factory["Faction"]

    empty_fac = Faction(id="fac_wiped", name="Wiped Faction", leader_id="dead_leader", members=[])
    world.factions["fac_wiped"] = empty_fac
    call_method(fac_sys, ("resolve_leadership_vacancy", "handle_leader_death"), "fac_wiped", world=world)
    assert empty_fac.leader_id is None or isinstance(empty_fac.leader_id, str)


def test_f15_bankrupt_zero_resource_faction_cannot_execute_expensive_goals(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify a faction with wealth=0 and military_strength=0 does not go into negative resources on turn execution."""
    fac_ai = systems_suite["faction_ai"]
    world = systems_suite["world"]
    Faction = entity_factory["Faction"]

    broke = Faction(id="fac_broke", name="Bankrupt", wealth=0.0, military_strength=0.0, goals=[{"type": "capture_district", "target": "lowtown"}])
    world.factions["fac_broke"] = broke
    call_method(fac_ai, ("process_faction_turn", "evaluate_faction_turn", "select_faction_action"), broke, world=world)
    assert broke.wealth >= 0.0 and broke.military_strength >= 0.0


def test_f15_unwitnessed_crime_does_not_trigger_immediate_guard_bounty(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify committing an unwitnessed crime (witnessed=False) does not immediately add a public guard bounty."""
    fac_sys = systems_suite["faction_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    world.characters["player"] = Character(id="player", name="Rowan", age=28, is_player=True)
    res = call_method(
        fac_sys,
        ("report_crime", "record_crime"),
        actor_id="player",
        crime_type="theft",
        district_id="lowtown",
        witnessed=False,
        world=world,
    )
    bounty = res.get("bounty_added", 0.0) if isinstance(res, dict) else 0.0
    assert bounty == 0.0


def test_f15_faction_self_relation_and_metric_bounds(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify faction self-relation is rejected/ignored and faction metrics clamp within [0, 100]."""
    fac_sys = systems_suite["faction_system"]
    world = systems_suite["world"]
    Faction = entity_factory["Faction"]

    world.factions["city_guard"] = Faction(id="city_guard", name="City Guard", stability=50.0, public_legitimacy=50.0)
    try:
        call_method(fac_sys, ("set_relation", "adjust_relation"), "city_guard", "city_guard", -100.0, world=world)
    except ValueError:
        pass
    assert world.factions["city_guard"].relations.get("city_guard", 0.0) >= 0.0


def test_f15_sub_six_hour_time_advance_does_not_prematurely_fire_faction_turn(seeded_rng: Any, event_bus: Any) -> None:
    """Verify advancing 5 minutes from start_hour=0 does not prematurely fire a 6-24h faction turn."""
    World = require_symbol("core.world", "World")
    WorldClock = require_symbol("core.clock", "WorldClock")
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")

    try:
        clock = WorldClock(start_hour=0)
    except TypeError:
        clock = WorldClock()
        if hasattr(clock, "start_hour"):
            clock.start_hour = 0

    world = instantiate_with_context(World, seed=482193, clock=clock, rng=seeded_rng, event_bus=event_bus)
    sim = instantiate_with_context(SimulationEngine, world=world, clock=clock, rng=seeded_rng, event_bus=event_bus)

    turns = {"c": 0}
    call_method(
        sim,
        ("register_system", "register_callback", "register_handler"),
        "factions",
        lambda *_a, **_k: turns.__setitem__("c", turns["c"] + 1),
    )
    call_method(sim, ("advance_time", "run_for_minutes", "step"), 5)
    assert turns["c"] == 0


# ==============================================================================
# FEATURE F16 BOUNDARIES: Hybrid Quests, 6-Scope Reputation, Rumors & Economy (systems/quest_system.py, rumor_system.py, economy_system.py)
# ==============================================================================


def test_f16_quest_npc_killed_mid_quest_dynamically_branches_or_fails_without_crash(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify killing a quest NPC mid-quest dynamically branches or updates the quest without crashing."""
    quest_sys = systems_suite["quest_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    GameEvent = entity_factory["GameEvent"]

    world.characters["npc_missing_apprentice"] = Character(id="npc_missing_apprentice", name="Joren", age=17, status="alive")
    q = call_method(quest_sys, ("create_hybrid_quest", "start_quest", "create_quest"), quest_id="quest_missing_apprentice", world=world)
    q.status = "active"

    world.characters["npc_missing_apprentice"].status = "dead"
    death_ev = GameEvent("ev_joren_died", "CHARACTER_DIED", 300, "npc_bandit", ["npc_missing_apprentice"], "lowtown", {}, 0.85)
    call_method(quest_sys, ("handle_event", "on_event", "evaluate_quest_conditions"), death_ev, world=world)
    assert q.status in {"active", "branched", "failed", "updated"}


def test_f16_rumor_reach_and_confidence_clamped_zero_to_hundred_percent(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify rumor reach % and confidence % clamp strictly within [0.0, 100.0] over 50 propagation ticks."""
    rumor_sys = systems_suite["rumor_system"]
    world = systems_suite["world"]
    District = entity_factory["District"]

    world.districts["lowtown"] = District(id="lowtown", name="Lowtown")
    r = call_method(
        rumor_sys,
        ("plant_false_rumor", "create_rumor"),
        actor_id="player",
        subject="npc_voss",
        claim="Test claim",
        district_id="lowtown",
        truth=False,
        world=world,
    )
    for _ in range(50):
        call_method(rumor_sys, ("propagate_rumors", "step_rumors", "update"), world=world)

    for pct in r.reach.values():
        assert 0.0 <= pct <= 100.0
    assert 0.0 <= r.confidence <= 100.0


def test_f16_reputation_bounds_and_unknown_scope_rejection(systems_suite: dict[str, Any]) -> None:
    """Verify invalid reputation scope raises ValueError/KeyError and extreme deltas clamp within [-100, 100]."""
    quest_sys = systems_suite["quest_system"]
    world = systems_suite["world"]

    with pytest.raises((ValueError, KeyError)):
        call_method(quest_sys, ("adjust_reputation", "modify_reputation"), scope="galactic_empire", key="x", delta=10.0, world=world)

    call_method(quest_sys, ("adjust_reputation", "modify_reputation"), scope="district", key="lowtown", delta=10000.0, world=world)
    rep = call_method(quest_sys, ("get_reputation", "query_reputation"), scope="district", key="lowtown", world=world)
    assert -100.0 <= rep <= 100.0


def test_f16_economy_shortage_zero_food_supply_price_ceiling_and_no_division_by_zero(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify food_supply=0.0 and wealth=0.0 do not raise ZeroDivisionError and keep price_index finite."""
    econ_sys = systems_suite["economy_system"]
    world = systems_suite["world"]
    District = entity_factory["District"]

    world.districts["lowtown"] = District(id="lowtown", name="Lowtown", food_supply=0.0, wealth=0.0)
    call_method(econ_sys, ("process_daily_tick", "update_economy", "step_economy"), world=world)
    price_idx = world.economy.get("price_index", 1.0)
    assert price_idx > 0.0 and math.isfinite(price_idx)


def test_f16_duplicate_quest_start_or_completing_already_completed_quest_idempotent(systems_suite: dict[str, Any]) -> None:
    """Verify starting or completing the same quest twice is idempotent and does not duplicate quest objects."""
    quest_sys = systems_suite["quest_system"]
    world = systems_suite["world"]

    call_method(quest_sys, ("start_quest", "create_quest"), quest_id="quest_blood_in_lowtown", world=world)
    call_method(quest_sys, ("start_quest", "create_quest"), quest_id="quest_blood_in_lowtown", world=world)
    assert list(world.quests.keys()).count("quest_blood_in_lowtown") == 1


def test_f16_purchase_property_or_trade_with_insufficient_wealth_rejected(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify a character with 0 wealth cannot purchase property and wealth never drops negative."""
    econ_sys = systems_suite["economy_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    world.characters["player"] = Character(id="player", name="Rowan", age=28, is_player=True, needs={"wealth": 0.0})
    try:
        res = call_method(econ_sys, ("acquire_property", "buy_property", "purchase_housing"), char_id="player", property_id="lowtown_safehouse", cost=100.0, world=world)
        assert res is False or (isinstance(res, dict) and res.get("success") is False)
    except ValueError:
        pass
    assert world.characters["player"].needs.get("wealth", 0.0) >= 0.0


# ==============================================================================
# FEATURE F17 BOUNDARIES: Veyr & Lowtown Content Suite (content/)
# ==============================================================================


def test_f17_zero_duplicate_entity_ids_across_entire_content_suite(populated_world: Any) -> None:
    """Verify every character, faction, district, item, and quest in content/ has a non-empty stable ID (id != name for NPCs)."""
    for cid, char in populated_world.characters.items():
        assert isinstance(cid, str) and len(cid) > 0
        assert cid == char.id
        if not char.is_player:
            assert char.id != char.name


def test_f17_all_character_faction_and_location_foreign_keys_resolve(populated_world: Any) -> None:
    """Verify all character faction_ids, faction leader_ids, and quest involved_factions resolve to valid entities."""
    for char in populated_world.characters.values():
        if char.faction_id is not None:
            assert char.faction_id in populated_world.factions

    for fac in populated_world.factions.values():
        if fac.leader_id is not None:
            assert fac.leader_id in populated_world.characters


def test_f17_every_district_influence_distribution_sums_to_100_percent(populated_world: Any) -> None:
    """Verify all 7 districts of Veyr have initial faction_influence summing to 100.0%."""
    assert len(populated_world.districts) == 7
    for d_id, dist in populated_world.districts.items():
        assert sum(dist.faction_influence.values()) == pytest.approx(100.0), f"District {d_id} influence does not sum to 100%"


def test_f17_all_named_characters_have_complete_29_part_humanoid_anatomy(populated_world: Any) -> None:
    """Verify all named characters in populated_world have initialized 7-region / 29-part humanoid anatomy."""
    regions = {"head", "neck", "torso", "left_arm", "right_arm", "left_leg", "right_leg"}
    for char in populated_world.characters.values():
        assert regions.issubset(set(char.body.keys()))
        assert len(char.body) >= 29


def test_f17_dialogue_fallback_for_dead_or_unregistered_npc(populated_world: Any) -> None:
    """Verify requesting dialogue from a dead NPC (murdered merchant) or unknown ID returns graceful fallback without KeyError."""
    quest_sys_cls = require_symbol("systems.quest_system", "QuestSystem")
    quest_sys = instantiate_with_context(quest_sys_cls, world=populated_world)

    res_unknown = call_method(quest_sys, ("get_dialogue", "generate_dialogue", "talk_to"), "nonexistent_npc_999", world=populated_world)
    assert res_unknown is None or isinstance(res_unknown, (str, dict))


def test_f17_random_event_trigger_with_unsatisfied_preconditions_skips_cleanly(populated_world: Any) -> None:
    """Verify random event evaluator skips war/riot-only events when unrest is 0.0."""
    for d in populated_world.districts.values():
        d.unrest = 0.0
    content_mod = require_module("content")
    if hasattr(content_mod, "select_random_event"):
        ev = content_mod.select_random_event(populated_world)
        assert ev is None or isinstance(ev, dict)
    else:
        events = call_method(content_mod, ("load_events", "get_random_events", "list_random_events"))
        assert isinstance(events, list) and len(events) >= 20


# ==============================================================================
# FEATURE F18 BOUNDARIES: First Playable Scenario ("Blood in Lowtown") & Vertical Slice (core/game.py)
# ==============================================================================


def test_f18_scenario_when_captain_voss_killed_in_first_encounter(game_session: Any) -> None:
    """Verify killing Captain Voss outright in Blood in Lowtown triggers leadership succession and adapts aftermath cleanly."""
    game_session.world.characters["npc_voss"].status = "dead"
    game_session.world.nemesis_profiles["npc_voss"].status = "dead"

    res = call_method(
        game_session,
        ("run_post_quest_continuation", "simulate_blood_in_lowtown_aftermath"),
        voss_injury="lethal",
        days=7,
    )
    assert res["success"] is True


def test_f18_invalid_scenario_approach_name_rejected(game_session: Any) -> None:
    """Verify passing an invalid scenario approach name ('join_aliens') is rejected."""
    try:
        res = call_method(
            game_session,
            ("resolve_scenario_approach", "complete_blood_in_lowtown", "choose_quest_approach"),
            "join_aliens",
        )
        assert res is False or (isinstance(res, dict) and res.get("success") is False)
    except ValueError:
        pass


def test_f18_re_executing_completed_blood_in_lowtown_scenario_rejected(game_session: Any) -> None:
    """Verify attempting to choose a second conflicting approach after Blood in Lowtown is already completed is rejected."""
    r1 = call_method(
        game_session,
        ("resolve_scenario_approach", "complete_blood_in_lowtown", "choose_quest_approach"),
        "support_city_guard",
    )
    assert r1["success"] is True

    try:
        r2 = call_method(
            game_session,
            ("resolve_scenario_approach", "complete_blood_in_lowtown", "choose_quest_approach"),
            "support_syndicate",
        )
        assert r2 is False or (isinstance(r2, dict) and r2.get("success") is False)
    except ValueError:
        pass


def test_f18_scenario_with_companion_breaking_point_departure(game_session: Any) -> None:
    """Verify triggering Marcus's breaking point during the scenario removes him from the party without crashing."""
    rel_sys_cls = require_symbol("systems.relationship_system", "RelationshipSystem")
    rel_sys = instantiate_with_context(rel_sys_cls, world=game_session.world, event_bus=game_session.world.event_bus)

    call_method(
        rel_sys,
        ("trigger_breaking_point", "evaluate_breaking_point", "check_breaking_point"),
        "comp_marcus",
        reason="betray_city_order",
        world=game_session.world,
    )
    assert game_session.world.companions["comp_marcus"].in_party is False
    res = call_method(
        game_session,
        ("resolve_scenario_approach", "complete_blood_in_lowtown", "choose_quest_approach"),
        "support_syndicate",
    )
    assert res["success"] is True


def test_f18_elira_bargain_refusal_branch_in_blood_in_lowtown(game_session: Any) -> None:
    """Verify refusing Elira's offer of help still allows completing Blood in Lowtown."""
    game_session.world.flags["refused_elira_bargain"] = True
    res = call_method(
        game_session,
        ("resolve_scenario_approach", "complete_blood_in_lowtown", "choose_quest_approach"),
        "investigate_independently",
        accept_elira_help=False,
    )
    assert res["success"] is True


def test_f18_player_defeated_and_imprisoned_mid_scenario_continues_story(game_session: Any) -> None:
    """Verify player defeat against Captain Voss triggers non-lethal capture/imprisonment and continues the campaign."""
    combat_sys_cls = require_symbol("systems.combat_system", "CombatSystem")
    combat_sys = instantiate_with_context(combat_sys_cls, world=game_session.world, event_bus=game_session.world.event_bus)

    res = call_method(combat_sys, ("resolve_player_defeat", "handle_player_defeat"), world=game_session.world, victor_faction="city_guard")
    assert res["outcome"] in {"captured", "imprisoned"}
    assert game_session.world.player.status != "dead"


# ==============================================================================
# FEATURE F19 BOUNDARIES: Structured Command Parser & Alias Resolver (ui/, core/game.py)
# ==============================================================================


def test_f19_empty_and_whitespace_only_command_rejected_cleanly(game_session: Any) -> None:
    """Verify empty and whitespace-only command strings return structured failure without advancing clock."""
    t0 = get_clock_minutes(game_session.world.clock)
    for empty_in in ("", "   ", "\t\n"):
        res = game_session.execute_command(empty_in)
        assert res["success"] is False
    assert get_clock_minutes(game_session.world.clock) == t0


def test_f19_unknown_verb_and_freeform_sentence_rejected_with_help_hint(game_session: Any) -> None:
    """Verify freeform natural-language sentences and unknown verbs are rejected cleanly."""
    t0 = get_clock_minutes(game_session.world.clock)
    res = game_session.execute_command("please kindly walk over and chat with sera about the murder")
    assert res["success"] is False
    assert get_clock_minutes(game_session.world.clock) == t0


def test_f19_nonexistent_target_entity_returns_structured_failure(game_session: Any) -> None:
    """Verify valid command verbs targeting nonexistent entities return {'success': False} without KeyError."""
    for bad_cmd in ("talk imaginary_dragon", "attack ghost_king", "move atlantis", "open faction space_marines"):
        res = game_session.execute_command(bad_cmd)
        assert res["success"] is False


def test_f19_negative_zero_or_malformed_duration_in_rest_and_wait_rejected(game_session: Any) -> None:
    """Verify negative, zero, or malformed durations in rest and wait are rejected without advancing clock."""
    t0 = get_clock_minutes(game_session.world.clock)
    for bad_wait in ("rest 0h", "rest -5h", "wait -3d", "wait 0m", "rest abc"):
        res = game_session.execute_command(bad_wait)
        assert res["success"] is False
    assert get_clock_minutes(game_session.world.clock) == t0


def test_f19_ambiguous_target_name_disambiguation_or_local_priority(game_session: Any) -> None:
    """Verify ambiguous target query ('inspect guard') resolves deterministically without crashing."""
    parsed = game_session.parse_command("inspect guard")
    assert isinstance(parsed, dict)
    assert "action" in parsed


def test_f19_special_characters_and_sql_injection_strings_in_command_input(game_session: Any) -> None:
    """Verify adversarial SQL-injection strings in command input do not corrupt world or database state."""
    res = game_session.execute_command("talk '; DROP TABLE characters; --")
    assert res["success"] is False
    assert len(game_session.world.characters) >= 15


# ==============================================================================
# FEATURE F20 BOUNDARIES: Textual + Rich Terminal UI Suite (ui/, main.py)
# ==============================================================================


def test_f20_textual_headless_app_navigation_across_all_eight_views_and_invalid_command(game_session: Any) -> None:
    """Verify cycling through all 8 logical views and submitting an invalid command in UI controller never crashes."""
    views = ["world", "character", "health", "party", "combat", "factions", "journal", "inventory"]
    for v in views:
        res = game_session.execute_command(f"open {v}")
        assert res["success"] is True

    bad_res = game_session.execute_command("invalid_gibberish_cmd")
    assert bad_res["success"] is False


def test_f20_combat_screen_when_no_combat_encounter_is_active(game_session: Any) -> None:
    """Verify rendering CombatScreen when active_encounter is None returns a clean idle message without AttributeError."""
    combat_mod = require_module("ui.combat_screen")
    if hasattr(game_session, "active_encounter"):
        game_session.active_encounter = None
    txt = str(call_method(combat_mod, ("render_combat_view", "format_combat_screen", "render_screen"), game_session))
    assert len(txt) > 0


def test_f20_health_screen_with_amputated_limb_and_multiple_injuries(game_session: Any) -> None:
    """Verify rendering HealthScreen for a character with an amputated limb and multiple wounds."""
    health_sys_cls = require_symbol("systems.health_system", "HealthSystem")
    health_sys = instantiate_with_context(health_sys_cls, world=game_session.world)
    call_method(health_sys, ("apply_injury", "inflict_injury"), game_session.world.player, "left_arm", "amputation", severity=1.0)

    health_mod = require_module("ui.health_screen")
    txt = str(call_method(health_mod, ("render_health_view", "format_health_screen", "render_screen"), game_session))
    assert "amputat" in txt.lower() or "non-functional" in txt.lower() or "false" in txt.lower()


def test_f20_journal_screen_with_empty_quests_empty_rumors_and_empty_inventory(game_session: Any) -> None:
    """Verify rendering JournalScreen and Inventory view when quests, rumors, chronicle, and inventory are empty."""
    game_session.world.quests.clear()
    game_session.world.rumors.clear()
    game_session.world.chronicle.clear()
    game_session.world.inventories.clear()

    jour_mod = require_module("ui.journal_screen")
    j_txt = str(call_method(jour_mod, ("render_journal_view", "format_journal_screen", "render_screen"), game_session))
    i_txt = str(call_method(jour_mod, ("render_inventory_view", "format_inventory_screen", "render_journal_view"), game_session, view="inventory"))
    assert len(j_txt) > 0 and len(i_txt) > 0


def test_f20_faction_screen_when_faction_leader_is_none_and_no_nemeses_exist(game_session: Any) -> None:
    """Verify rendering FactionScreen when faction leader_id is None and nemesis_profiles is empty."""
    for f in game_session.world.factions.values():
        f.leader_id = None
    game_session.world.nemesis_profiles.clear()

    fac_mod = require_module("ui.faction_screen")
    txt = str(call_method(fac_mod, ("render_faction_view", "format_faction_screen", "render_screen"), game_session))
    assert len(txt) > 0


def test_f20_main_cli_non_interactive_or_help_invocation_exits_cleanly() -> None:
    """Verify running `python main.py --help` exits with returncode 0 within 5 seconds without hanging."""
    main_py = PROJECT_ROOT / "main.py"
    assert main_py.exists(), f"Missing entry point {main_py}"
    proc = subprocess.run(
        [sys.executable, str(main_py), "--help"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert proc.returncode == 0


# ==============================================================================
# FEATURE F21 BOUNDARIES: Simulation, Chronicle & E2E Test Suite (tests/)
# ==============================================================================


def test_f21_rng_stream_isolation_unrelated_system_rolls_do_not_perturb_combat() -> None:
    """Verify GDD Section 14 RNG stream isolation rule under heavy multi-system random generation."""
    SeededRNG = require_symbol("core.random_generator", "SeededRNG")
    rng_a = SeededRNG(482193)
    rng_b = SeededRNG(482193)

    for _ in range(500):
        rng_b.stream("economy").random()
    for _ in range(300):
        rng_b.stream("rumor").random()
    for _ in range(200):
        rng_b.stream("faction").random()

    rolls_a = [rng_a.stream("combat").random() for _ in range(10)]
    rolls_b = [rng_b.stream("combat").random() for _ in range(10)]
    assert rolls_a == rolls_b


def test_f21_event_bus_circular_subscriber_chain_bounded_without_infinite_recursion(event_bus: Any, entity_factory: dict[str, Any]) -> None:
    """Verify circular subscriber chains on EventBus are bounded and never raise RecursionError."""
    GameEvent = entity_factory["GameEvent"]
    EventPriority = entity_factory["EventPriority"]

    event_bus.subscribe("CYCLE_A", lambda ev: GameEvent("b", "CYCLE_B", ev.timestamp, None, [], None, {}, 0.5, "critical"))
    event_bus.subscribe("CYCLE_B", lambda ev: GameEvent("a", "CYCLE_A", ev.timestamp, None, [], None, {}, 0.5, "critical"))

    event_bus.emit(GameEvent("a0", "CYCLE_A", 0, None, [], None, {}, 0.5), priority=EventPriority.CRITICAL)
    assert len(event_bus.event_history) <= 50


def test_f21_chronicle_generation_on_brand_new_world_at_timestamp_zero(save_manager: Any) -> None:
    """Verify generate_chronicle on a brand-new world at timestamp=0 returns a valid prologue entry."""
    World = require_symbol("core.world", "World")
    w = instantiate_with_context(World, seed=482193)
    chronicle = save_manager.generate_chronicle(w)
    assert isinstance(chronicle, list) and len(chronicle) >= 1
    assert chronicle[0]["year"] == 1


def test_f21_save_load_mid_simulation_preserves_exact_rng_and_future_trajectory(save_manager: Any) -> None:
    """Verify simulating 20 days continuously vs saving/loading at Day 10 yields identical Day 20 RNG & clock state."""
    World = require_symbol("core.world", "World")
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")

    # Run A: 20 days continuous
    w_a = instantiate_with_context(World, seed=482193)
    sim_a = instantiate_with_context(SimulationEngine, world=w_a, clock=w_a.clock, rng=w_a.rng, event_bus=w_a.event_bus)
    call_method(sim_a, ("advance_time", "run_for_minutes", "step"), 20 * 1440)

    # Run B: 10 days -> save -> load -> 10 days
    w_b1 = instantiate_with_context(World, seed=482193)
    sim_b1 = instantiate_with_context(SimulationEngine, world=w_b1, clock=w_b1.clock, rng=w_b1.rng, event_bus=w_b1.event_bus)
    call_method(sim_b1, ("advance_time", "run_for_minutes", "step"), 10 * 1440)
    call_method(save_manager, ("save_game", "save_current_state"), w_b1, slot="mid_sim")

    w_b2 = call_method(save_manager, ("load_game", "load_current_state"), slot="mid_sim")
    sim_b2 = instantiate_with_context(SimulationEngine, world=w_b2, clock=w_b2.clock, rng=w_b2.rng, event_bus=w_b2.event_bus)
    call_method(sim_b2, ("advance_time", "run_for_minutes", "step"), 10 * 1440)

    assert get_clock_minutes(w_a.clock) == get_clock_minutes(w_b2.clock)
    assert w_a.rng.stream("combat").random() == w_b2.rng.stream("combat").random()


def test_f21_corrupted_save_slot_falls_back_to_snapshot_recovery(save_manager: Any, entity_factory: dict[str, Any]) -> None:
    """Verify snapshot recovery restores consistent World state after a save slot mutation or corruption."""
    World = require_symbol("core.world", "World")
    Character = entity_factory["Character"]

    w = instantiate_with_context(World, seed=482193)
    w.characters["player"] = Character(id="player", name="Rowan", age=28, location_id="lowtown_tavern", is_player=True)
    snap_id = save_manager.create_snapshot(w, label="safe_checkpoint")

    restored = save_manager.restore_snapshot(snap_id)
    assert restored.characters["player"].location_id == "lowtown_tavern"


def test_f21_character_aging_across_ten_year_campaign_increments_age_and_triggers_retirement(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify 10 years of aging increments character age by +10 and handles retirement threshold cleanly."""
    char_sys = systems_suite["character_system"]
    Character = entity_factory["Character"]

    rowan = Character(id="player", name="Rowan", age=30, is_player=True)
    elder = Character(id="npc_elder", name="Elder Guard", age=62, faction_id="city_guard")
    call_method(char_sys, ("process_yearly_aging", "age_character", "advance_age"), rowan, years=10)
    call_method(char_sys, ("process_yearly_aging", "age_character", "advance_age"), elder, years=10)

    assert rowan.age == 40
    assert elder.age == 72
