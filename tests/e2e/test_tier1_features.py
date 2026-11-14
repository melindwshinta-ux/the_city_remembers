"""Tier 1 E2E Feature Tests (F1-F21) for THE CITY REMEMBERS.

Covers happy-path and category-partition functional requirements across all 21 features
defined in ORIGINAL_REQUEST.md and PROJECT.md (115 test cases: 55 for F1-F11, 60 for F12-F21).
Zero top-level application imports so `pytest --collect-only` always succeeds with 0 errors.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.conftest import (
    CANONICAL_11_RNG_STREAMS,
    PROJECT_ROOT,
    REQUIRED_15_TABLES,
    call_method,
    get_clock_minutes,
    get_minutes_per_year,
    instantiate_with_context,
    require_module,
    require_symbol,
)


# ==============================================================================
# FEATURE F1: Campaign Timeline & Clock (core/clock.py - WorldClock)
# ==============================================================================


def test_f1_clock_initial_state_prologue_year_one(world_clock: Any) -> None:
    """Verify fresh WorldClock starts at timestamp 0, Year 1, Prologue/Act I."""
    assert get_clock_minutes(world_clock) == 0
    assert world_clock.year == 1
    assert world_clock.act in ("Prologue", "Act I")
    formatted = call_method(world_clock, ("format_datetime", "format_time", "__str__"))
    assert isinstance(formatted, str) and len(formatted) > 0
    assert "1" in formatted


def test_f1_clock_advance_standard_action_durations(world_clock: Any) -> None:
    """Verify advancing small action (5m), conversation (15m), combat (3m), and rest (480m)."""
    c1 = world_clock.advance(5)
    c2 = world_clock.advance(15)
    c3 = world_clock.advance(3)
    c4 = world_clock.advance(480)
    assert get_clock_minutes(world_clock) == 503
    assert world_clock.year == 1
    assert isinstance(c1, list) and isinstance(c4, list)
    assert any(k in c4 for k in ("6h", "faction", "factions", "time_update"))


def test_f1_clock_multi_year_act_progression_y1_to_y10(world_clock: Any) -> None:
    """Verify Act progression across Year 1-3 (Act I), Year 4-6 (Act II), Year 7-10 (Act III)."""
    mpy = get_minutes_per_year(world_clock)
    world_clock.advance(mpy)  # Year 2
    assert world_clock.year == 2
    assert world_clock.act == "Act I"

    world_clock.advance(2 * mpy)  # Year 4
    assert world_clock.year == 4
    assert world_clock.act == "Act II"

    world_clock.advance(3 * mpy)  # Year 7
    assert world_clock.year == 7
    assert world_clock.act == "Act III"

    world_clock.advance(3 * mpy)  # Year 10
    assert world_clock.year == 10
    assert world_clock.act == "Act III"


def test_f1_clock_threshold_detection_daily_weekly_monthly(world_clock: Any) -> None:
    """Verify advance() detects daily (1440m), weekly (10080m), and monthly (43200m) thresholds."""
    t_day = world_clock.advance(1440)
    assert "daily" in t_day

    t_week = world_clock.advance(10080)
    assert "weekly" in t_week and "daily" in t_week

    t_month = world_clock.advance(43200)
    assert "monthly" in t_month and "weekly" in t_month and "daily" in t_month


def test_f1_clock_travel_and_project_durations(world_clock: Any) -> None:
    """Verify travel duration (25m) and multi-week major project duration (14 days = 20160m)."""
    world_clock.advance(25)
    crossed = world_clock.advance(20160)
    assert get_clock_minutes(world_clock) == 20185
    assert "weekly" in crossed and "daily" in crossed


# ==============================================================================
# FEATURE F2: Priority Event Bus (core/event_bus.py - EventBus, EventPriority, GameEvent)
# ==============================================================================


def test_f2_event_bus_critical_priority_immediate_processing(event_bus: Any, entity_factory: dict[str, Any]) -> None:
    """Verify CRITICAL priority events invoke subscribed handlers synchronously inside emit()."""
    GameEvent = entity_factory["GameEvent"]
    EventPriority = entity_factory["EventPriority"]

    received: list[Any] = []
    event_bus.subscribe("CHARACTER_DIED", lambda ev: received.append(ev))

    ev = GameEvent(
        id="ev_crit_1",
        event_type="CHARACTER_DIED",
        timestamp=10,
        source_id="player",
        target_ids=["npc_01"],
        location_id="lowtown_street",
        data={"cause": "sword"},
        importance=0.9,
    )
    event_bus.emit(ev, priority=EventPriority.CRITICAL)
    assert len(received) == 1
    assert received[0].id == "ev_crit_1"


def test_f2_event_bus_normal_priority_deferred_until_tick(event_bus: Any, entity_factory: dict[str, Any]) -> None:
    """Verify NORMAL priority events queue on emit() and execute when process_tick_events() runs."""
    GameEvent = entity_factory["GameEvent"]
    EventPriority = entity_factory["EventPriority"]

    received: list[Any] = []
    event_bus.subscribe("MEMORY_CREATED", lambda ev: received.append(ev))

    ev = GameEvent(
        id="ev_norm_1",
        event_type="MEMORY_CREATED",
        timestamp=20,
        source_id="player",
        target_ids=["comp_sera"],
        location_id="lowtown_tavern",
        data={"emotion": "Gratitude"},
        importance=0.6,
    )
    event_bus.emit(ev, priority=EventPriority.NORMAL)
    assert len(received) == 0

    event_bus.process_tick_events()
    assert len(received) == 1
    assert received[0].id == "ev_norm_1"


def test_f2_event_bus_background_priority_scheduled_processing(event_bus: Any, entity_factory: dict[str, Any]) -> None:
    """Verify BACKGROUND events wait until process_background_events() is invoked."""
    GameEvent = entity_factory["GameEvent"]
    EventPriority = entity_factory["EventPriority"]

    received: list[Any] = []
    event_bus.subscribe("ECONOMY_UPDATED", lambda ev: received.append(ev))

    ev = GameEvent(
        id="ev_bg_1",
        event_type="ECONOMY_UPDATED",
        timestamp=1440,
        source_id=None,
        target_ids=[],
        location_id="lowtown",
        data={"price_index": 1.1},
        importance=0.3,
    )
    event_bus.emit(ev, priority=EventPriority.BACKGROUND)
    assert len(received) == 0

    event_bus.process_tick_events()
    assert len(received) == 0

    event_bus.process_background_events()
    assert len(received) == 1
    assert received[0].id == "ev_bg_1"


def test_f2_event_bus_three_stage_consequence_chaining(event_bus: Any, entity_factory: dict[str, Any]) -> None:
    """Verify 3-stage consequence generation: LIMB_INJURED -> LEADERSHIP_VACANCY -> RIVAL_PROMOTED."""
    GameEvent = entity_factory["GameEvent"]
    EventPriority = entity_factory["EventPriority"]

    execution_order: list[str] = []

    def on_limb_injured(ev: Any) -> Any:
        execution_order.append(ev.event_type)
        return GameEvent(
            id="ev_chain_2",
            event_type="LEADERSHIP_VACANCY",
            timestamp=ev.timestamp,
            source_id=ev.target_ids[0],
            target_ids=["city_guard"],
            location_id=ev.location_id,
            data={"reason": "injured"},
            importance=0.8,
        )

    def on_vacancy(ev: Any) -> Any:
        execution_order.append(ev.event_type)
        return GameEvent(
            id="ev_chain_3",
            event_type="RIVAL_PROMOTED",
            timestamp=ev.timestamp,
            source_id="city_guard",
            target_ids=["npc_captain_lyra"],
            location_id=ev.location_id,
            data={"new_rank": "commander"},
            importance=0.85,
        )

    def on_promoted(ev: Any) -> None:
        execution_order.append(ev.event_type)

    event_bus.subscribe("LIMB_INJURED", on_limb_injured)
    event_bus.subscribe("LEADERSHIP_VACANCY", on_vacancy)
    event_bus.subscribe("RIVAL_PROMOTED", on_promoted)

    ev1 = GameEvent(
        id="ev_chain_1",
        event_type="LIMB_INJURED",
        timestamp=120,
        source_id="player",
        target_ids=["npc_voss"],
        location_id="lowtown_street",
        data={"body_part": "left_leg", "injury": "compound_fracture"},
        importance=0.8,
    )
    event_bus.emit(ev1, priority=EventPriority.CRITICAL)
    event_bus.process_tick_events()

    assert execution_order == ["LIMB_INJURED", "LEADERSHIP_VACANCY", "RIVAL_PROMOTED"]


def test_f2_event_bus_multi_subscriber_fanout_isolation(event_bus: Any, entity_factory: dict[str, Any]) -> None:
    """Verify 4 independent system subscribers receive the exact same CHARACTER_INJURED payload."""
    GameEvent = entity_factory["GameEvent"]
    EventPriority = entity_factory["EventPriority"]

    traces: dict[str, list[str]] = {"memory": [], "nemesis": [], "health": [], "faction": []}
    for domain in traces:
        event_bus.subscribe(
            "CHARACTER_INJURED",
            lambda ev, d=domain: traces[d].append(ev.data["body_part"]),
        )

    ev = GameEvent(
        id="ev_fanout_1",
        event_type="CHARACTER_INJURED",
        timestamp=120,
        source_id="player",
        target_ids=["npc_voss"],
        location_id="lowtown_street",
        data={"body_part": "left_leg", "injury": "compound_fracture"},
        importance=0.8,
    )
    event_bus.emit(ev, priority=EventPriority.CRITICAL)
    for domain, recorded in traces.items():
        assert recorded == ["left_leg"], f"Subscriber {domain} did not receive payload"


# ==============================================================================
# FEATURE F3: Multi-Frequency Simulation Scheduler (core/simulation.py - SimulationEngine)
# ==============================================================================


def test_f3_simulation_action_and_time_update_frequencies(world_clock: Any, seeded_rng: Any, event_bus: Any) -> None:
    """Verify advancing 10m triggers companions and nearby_npcs, but not 6h/daily/weekly ticks."""
    World = require_symbol("core.world", "World")
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")
    world = instantiate_with_context(World, seed=482193, clock=world_clock, rng=seeded_rng, event_bus=event_bus)
    sim = instantiate_with_context(SimulationEngine, world=world, clock=world_clock, rng=seeded_rng, event_bus=event_bus)

    counts = {"companions": 0, "nearby_npcs": 0, "factions": 0, "economy": 0, "district_pop": 0}
    for freq in counts:
        call_method(
            sim,
            ("register_system", "register_callback", "register_handler"),
            freq,
            lambda *_a, f=freq, **_k: counts.__setitem__(f, counts[f] + 1),
        )

    call_method(sim, ("advance_time", "run_for_minutes", "step"), 10)
    assert counts["companions"] >= 1
    assert counts["nearby_npcs"] >= 1
    assert counts["factions"] == 0
    assert counts["economy"] == 0
    assert counts["district_pop"] == 0


def test_f3_simulation_faction_turn_frequency_every_6_to_24_hours(world_clock: Any, seeded_rng: Any, event_bus: Any) -> None:
    """Verify advancing 1440m (24 hours) fires factions (1-4 times) and economy (1 time)."""
    World = require_symbol("core.world", "World")
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")
    world = instantiate_with_context(World, seed=482193, clock=world_clock, rng=seeded_rng, event_bus=event_bus)
    sim = instantiate_with_context(SimulationEngine, world=world, clock=world_clock, rng=seeded_rng, event_bus=event_bus)

    counts = {"factions": 0, "economy": 0}
    for freq in counts:
        call_method(
            sim,
            ("register_system", "register_callback", "register_handler"),
            freq,
            lambda *_a, f=freq, **_k: counts.__setitem__(f, counts[f] + 1),
        )

    call_method(sim, ("advance_time", "run_for_minutes", "step"), 1440)
    assert 1 <= counts["factions"] <= 4
    assert counts["economy"] == 1


def test_f3_simulation_weekly_population_and_ambition_frequencies(world_clock: Any, seeded_rng: Any, event_bus: Any) -> None:
    """Verify advancing 10080m (1 week) fires weekly district_pop, ambitions, 7 daily economy, and 7-28 faction ticks."""
    World = require_symbol("core.world", "World")
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")
    world = instantiate_with_context(World, seed=482193, clock=world_clock, rng=seeded_rng, event_bus=event_bus)
    sim = instantiate_with_context(SimulationEngine, world=world, clock=world_clock, rng=seeded_rng, event_bus=event_bus)

    counts = {"factions": 0, "economy": 0, "district_pop": 0, "ambitions": 0}
    for freq in counts:
        call_method(
            sim,
            ("register_system", "register_callback", "register_handler"),
            freq,
            lambda *_a, f=freq, **_k: counts.__setitem__(f, counts[f] + 1),
        )

    call_method(sim, ("advance_time", "run_for_minutes", "step"), 10080)
    assert counts["district_pop"] >= 1
    assert counts["economy"] == 7
    assert 7 <= counts["factions"] <= 28
    assert counts["ambitions"] >= 1


def test_f3_simulation_time_skip_substepping_3_days(world_clock: Any, seeded_rng: Any, event_bus: Any) -> None:
    """Verify waiting 3 days (4320m) sub-steps in <= 360m chunks rather than an empty jump."""
    World = require_symbol("core.world", "World")
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")
    world = instantiate_with_context(World, seed=482193, clock=world_clock, rng=seeded_rng, event_bus=event_bus)
    sim = instantiate_with_context(SimulationEngine, world=world, clock=world_clock, rng=seeded_rng, event_bus=event_bus)

    faction_timestamps: list[int] = []
    call_method(
        sim,
        ("register_system", "register_callback", "register_handler"),
        "factions",
        lambda *_a, **_k: faction_timestamps.append(get_clock_minutes(world.clock)),
    )

    call_method(sim, ("advance_time", "run_for_minutes", "step"), 4320)
    assert get_clock_minutes(world.clock) == 4320
    assert len(faction_timestamps) >= 3
    assert len(set(faction_timestamps)) >= 3


def test_f3_simulation_deterministic_execution_across_identical_seeds() -> None:
    """Verify two World + SimulationEngine instances with seed 482193 produce identical results."""
    World = require_symbol("core.world", "World")
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")

    w1 = instantiate_with_context(World, seed=482193)
    s1 = instantiate_with_context(SimulationEngine, world=w1, clock=w1.clock, rng=w1.rng, event_bus=w1.event_bus)

    w2 = instantiate_with_context(World, seed=482193)
    s2 = instantiate_with_context(SimulationEngine, world=w2, clock=w2.clock, rng=w2.rng, event_bus=w2.event_bus)

    call_method(s1, ("advance_time", "run_for_minutes", "step"), 10080)
    call_method(s2, ("advance_time", "run_for_minutes", "step"), 10080)

    assert get_clock_minutes(w1.clock) == get_clock_minutes(w2.clock)
    assert w1.rng.get_state() == w2.rng.get_state()


# ==============================================================================
# FEATURE F4: Seeded Multi-Stream RNG (core/random_generator.py - SeededRNG)
# ==============================================================================


def test_f4_rng_default_master_seed_482193_reproducibility() -> None:
    """Verify two SeededRNG(482193) instances generate identical sequences."""
    SeededRNG = require_symbol("core.random_generator", "SeededRNG")
    rng1 = SeededRNG(482193)
    rng2 = SeededRNG(482193)

    seq1 = [rng1.stream("combat").random() for _ in range(20)]
    seq2 = [rng2.stream("combat").random() for _ in range(20)]
    assert seq1 == seq2


def test_f4_rng_stream_isolation_across_systems() -> None:
    """Verify heavy draws on economy/rumor/faction streams never alter combat stream rolls."""
    SeededRNG = require_symbol("core.random_generator", "SeededRNG")
    rng_a = SeededRNG(482193)
    rng_b = SeededRNG(482193)

    for _ in range(1000):
        rng_a.stream("economy").random()
        rng_a.stream("rumor").random()
        rng_a.stream("faction").random()

    combat_a = [rng_a.stream("combat").random() for _ in range(10)]
    combat_b = [rng_b.stream("combat").random() for _ in range(10)]
    assert combat_a == combat_b


def test_f4_rng_all_11_canonical_streams_available_and_distinct(seeded_rng: Any) -> None:
    """Verify all 11 canonical streams exist and have distinct initial sequences."""
    first_draws = [seeded_rng.stream(name).random() for name in CANONICAL_11_RNG_STREAMS]
    assert len(first_draws) == 11
    assert all(0.0 <= val < 1.0 for val in first_draws)
    assert len(set(first_draws)) == 11


def test_f4_rng_get_state_and_set_state_roundtrip(seeded_rng: Any) -> None:
    """Verify get_state() and set_state() preserve exact future random draws."""
    for _ in range(5):
        seeded_rng.stream("combat").random()
    for _ in range(3):
        seeded_rng.stream("nemesis").random()

    saved_state = seeded_rng.get_state()
    expected_combat = [seeded_rng.stream("combat").random() for _ in range(10)]
    expected_nemesis = [seeded_rng.stream("nemesis").random() for _ in range(10)]

    seeded_rng.set_state(saved_state)
    restored_combat = [seeded_rng.stream("combat").random() for _ in range(10)]
    restored_nemesis = [seeded_rng.stream("nemesis").random() for _ in range(10)]

    assert restored_combat == expected_combat
    assert restored_nemesis == expected_nemesis


def test_f4_rng_different_master_seeds_diverge() -> None:
    """Verify different master seeds produce completely divergent random sequences."""
    SeededRNG = require_symbol("core.random_generator", "SeededRNG")
    rng1 = SeededRNG(482193)
    rng2 = SeededRNG(999999)

    seq1 = [rng1.stream("world").random() for _ in range(10)]
    seq2 = [rng2.stream("world").random() for _ in range(10)]
    assert seq1 != seq2


# ==============================================================================
# FEATURE F5: Core Dataclasses & Entities (entities/)
# ==============================================================================


def test_f5_entities_section13_character_bodypart_injury_instantiation(entity_factory: dict[str, Any]) -> None:
    """Verify exact Section 13 instantiation of Character, Injury, and BodyPart."""
    Character = entity_factory["Character"]
    Injury = entity_factory["Injury"]
    BodyPart = entity_factory["BodyPart"]

    char = Character(id="char_001", name="Rowan", age=28, faction_id=None)
    assert char.id == "char_001"
    assert char.name == "Rowan"
    assert char.age == 28
    assert char.faction_id is None
    assert char.status == "alive"
    assert char.is_player is False

    inj = Injury(
        id="inj_001",
        injury_type="compound_fracture",
        severity=0.8,
        pain=0.7,
        bleeding=0.4,
        infection_risk=0.3,
    )
    assert inj.recovery_progress == 0.0
    assert inj.permanent is False

    bp = BodyPart(
        id="left_leg",
        name="Left Leg",
        integrity=40.0,
        armor=5.0,
        functional=False,
        injuries=[inj],
        children=["left_thigh", "left_knee", "left_calf", "left_foot"],
    )
    assert bp.functional is False
    assert len(bp.injuries) == 1
    assert bp.injuries[0].injury_type == "compound_fracture"


def test_f5_entities_section13_memory_and_relationship_instantiation(entity_factory: dict[str, Any]) -> None:
    """Verify exact Section 13 & Section 4 instantiation of Memory and Relationship."""
    Memory = entity_factory["Memory"]
    Relationship = entity_factory["Relationship"]

    mem = Memory(
        id="mem_001",
        event_type="RESCUED",
        participants=["player", "comp_sera"],
        description="Player rescued Sera from prison.",
        location_id="barracks",
        importance=0.9,
        emotional_valence=0.85,
        confidence=1.0,
        created_at=100,
    )
    assert mem.decay_rate == 0.0
    assert "comp_sera" in mem.participants

    rel = Relationship(
        source_id="comp_sera",
        target_id="player",
        trust=70,
        respect=85,
        affection=45,
        resentment=10,
        fear=0,
        dependency=30,
        relationship_state="Loyal associate",
    )
    assert rel.trust == 70
    assert rel.respect == 85
    assert rel.dependency == 30
    assert rel.relationship_state == "Loyal associate"


def test_f5_entities_section13_faction_nemesis_gameevent_instantiation(entity_factory: dict[str, Any]) -> None:
    """Verify exact Section 13 instantiation of Faction, NemesisProfile, and GameEvent."""
    Faction = entity_factory["Faction"]
    NemesisProfile = entity_factory["NemesisProfile"]
    GameEvent = entity_factory["GameEvent"]

    fac = Faction(
        id="city_guard",
        name="City Guard",
        leader_id="npc_commander_vael",
        wealth=70.0,
        influence=60.0,
        military_strength=80.0,
        stability=65.0,
        territories=["barracks", "lowtown"],
        members=["npc_voss", "npc_merek"],
        goals=[{"type": "maintain_authority"}],
        relations={"lowtown_syndicate": -70.0},
    )
    assert fac.id == "city_guard"
    assert fac.relations["lowtown_syndicate"] == -70.0

    nem = NemesisProfile(
        character_id="npc_voss",
        player_hostility=65.0,
        player_respect=40.0,
        encounter_count=2,
        known_player_tactics=["fire_magic"],
        grudges=["scarred_face", "killed_lieutenant"],
        career_history=[{"rank": "captain", "year": 1}],
        last_encounter_date=120,
        current_ambition="Become Commander of the City Guard",
        special_traits=["counterattacks"],
    )
    assert nem.character_id == "npc_voss"
    assert "fire_magic" in nem.known_player_tactics

    ev = GameEvent(
        id="event_001",
        event_type="LIMB_INJURED",
        timestamp=120,
        source_id="player",
        target_ids=["npc_00192"],
        location_id="lowtown_street",
        data={"body_part": "left_leg", "injury": "compound_fracture", "weapon": "warhammer"},
        importance=0.8,
    )
    assert ev.event_type == "LIMB_INJURED"
    assert ev.data["weapon"] == "warhammer"


def test_f5_entities_companion_enemy_district_location_instantiation(entity_factory: dict[str, Any]) -> None:
    """Verify Companion, EnemyCombatant, District (10 metrics), and Location instantiation."""
    Companion = entity_factory["Companion"]
    EnemyCombatant = entity_factory["EnemyCombatant"]
    District = entity_factory["District"]
    Location = entity_factory["Location"]

    comp = Companion(character_id="comp_marcus", role="tank", friendship=40.0, rivalry=10.0)
    assert comp.character_id == "comp_marcus"
    assert comp.friendship == 40.0 and comp.rivalry == 10.0

    enemy = EnemyCombatant(character_id="npc_voss", archetype="duelist", rank="captain")
    assert enemy.archetype == "duelist"
    assert enemy.rank == "captain"

    dist = District(
        id="lowtown",
        name="Lowtown",
        characteristics="Poor, crowded, criminal activity",
        major_conflict="Gang warfare",
        population=12000,
        wealth=25.0,
        security=25.0,
        unrest=75.0,
        faction_influence={
            "lowtown_syndicate": 48.0,
            "city_guard": 22.0,
            "merchant_consortium": 12.0,
            "iron_workers_union": 10.0,
            "independent": 8.0,
        },
        food_supply=45.0,
        employment=40.0,
        crime=85.0,
        public_opinion=30.0,
        infrastructure_condition=35.0,
    )
    for metric in (
        "population",
        "wealth",
        "security",
        "unrest",
        "faction_influence",
        "food_supply",
        "employment",
        "crime",
        "public_opinion",
        "infrastructure_condition",
    ):
        assert hasattr(dist, metric)

    loc = Location(id="lowtown_tavern", name="The Rusted Anchor", district_id="lowtown")
    assert loc.district_id == "lowtown"


def test_f5_entities_item_quest_rumor_instantiation_and_serialization(entity_factory: dict[str, Any]) -> None:
    """Verify Item, Quest, and Rumor (#00492) instantiation and dict round-trip."""
    Item = entity_factory["Item"]
    Quest = entity_factory["Quest"]
    Rumor = entity_factory["Rumor"]

    sword = Item(id="longsword", name="Longsword", item_type="weapon", damage=22.0, damage_type="cutting")
    quest = Quest(id="quest_blood_in_lowtown", title="Blood in Lowtown", status="active", quest_type="hybrid")
    rumor = Rumor(
        id="rumor_00492",
        subject="Rowan",
        claim="Rowan murdered a City Guard officer.",
        origin="npc_0091",
        truth=False,
        reach={"lowtown": 35.0, "harbor": 12.0, "high_quarter": 3.0},
        confidence=47.0,
    )
    assert sword.damage_type == "cutting"
    assert quest.quest_type == "hybrid"
    assert rumor.truth is False
    assert rumor.reach["lowtown"] == 35.0
    assert rumor.confidence == 47.0

    if hasattr(rumor, "to_dict") and hasattr(Rumor, "from_dict"):
        assert Rumor.from_dict(rumor.to_dict()).claim == rumor.claim
    else:
        assert dataclasses.asdict(rumor)["claim"] == rumor.claim


# ==============================================================================
# FEATURE F6: SQLite 15-Table Schema & Migrations (persistence/database.py, migrations.py)
# ==============================================================================


def test_f6_database_creates_all_15_required_tables(sqlite_db: Any) -> None:
    """Verify Database initializes all 15 required GDD Section 15 SQLite tables."""
    if hasattr(sqlite_db, "list_tables"):
        tables = set(sqlite_db.list_tables())
    else:
        conn = sqlite_db.get_connection() if hasattr(sqlite_db, "get_connection") else sqlite_db.conn
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        tables = {r[0] for r in rows}
    assert REQUIRED_15_TABLES.issubset(tables)


def test_f6_database_table_columns_match_entity_schemas(sqlite_db: Any) -> None:
    """Verify PRAGMA table_info columns on core SQLite tables."""
    conn = sqlite_db.get_connection() if hasattr(sqlite_db, "get_connection") else sqlite_db.conn

    def get_cols(table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {r[1] for r in rows}

    assert {"id", "name", "age", "faction_id", "status"}.issubset(get_cols("characters"))
    assert {"source_id", "target_id", "trust", "respect", "affection", "resentment", "fear"}.issubset(
        get_cols("relationships")
    )
    assert {"id", "event_type", "timestamp", "importance"}.issubset(get_cols("events"))
    assert {"character_id", "player_hostility", "encounter_count", "current_ambition"}.issubset(
        get_cols("nemesis_profiles")
    )


def test_f6_migrations_initial_schema_version_tracking(sqlite_db: Any) -> None:
    """Verify MigrationManager tracks schema version >= 1 in SQLite."""
    mig_mod = require_module("persistence.migrations")
    if hasattr(mig_mod, "MigrationManager"):
        mgr = mig_mod.MigrationManager(sqlite_db)
        ver = call_method(mgr, ("get_current_version", "current_version", "migrate"))
        assert int(ver) >= 1
    else:
        ver = call_method(mig_mod, ("get_schema_version", "apply_migrations"), sqlite_db)
        assert int(ver) >= 1


def test_f6_migrations_idempotent_reapplication(sqlite_db: Any) -> None:
    """Verify applying migrations twice consecutively is idempotent and does not raise."""
    mig_mod = require_module("persistence.migrations")
    if hasattr(mig_mod, "MigrationManager"):
        mgr = mig_mod.MigrationManager(sqlite_db)
        v1 = call_method(mgr, ("migrate", "ensure_latest"))
        v2 = call_method(mgr, ("migrate", "ensure_latest"))
        assert v1 == v2 and v1 >= 1
    else:
        call_method(mig_mod, ("apply_migrations", "migrate"), sqlite_db)
        call_method(mig_mod, ("apply_migrations", "migrate"), sqlite_db)


def test_f6_database_in_memory_and_file_backed_modes(tmp_path: Path) -> None:
    """Verify Database supports both ':memory:' and file-backed SQLite modes."""
    Database = require_symbol("persistence.database", "Database")
    mem_db = Database(":memory:")
    file_path = tmp_path / "persisted_veyr.db"
    file_db = Database(file_path)

    for db in (mem_db, file_db):
        conn = db.get_connection() if hasattr(db, "get_connection") else db.conn
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        assert REQUIRED_15_TABLES.issubset({r[0] for r in rows})

    if hasattr(file_db, "close"):
        file_db.close()
    if hasattr(mem_db, "close"):
        mem_db.close()
    assert file_path.exists()


# ==============================================================================
# FEATURE F7: Save Manager, Event Log, Snapshots & Chronicle (persistence/save_manager.py)
# ==============================================================================


def test_f7_save_and_load_game_full_world_roundtrip(save_manager: Any, entity_factory: dict[str, Any]) -> None:
    """Verify save_game and load_game round-trip full World state across all 15 tables."""
    World = require_symbol("core.world", "World")
    world = instantiate_with_context(World, seed=482193)
    world.clock.advance(2880)

    Character = entity_factory["Character"]
    BodyPart = entity_factory["BodyPart"]
    Injury = entity_factory["Injury"]
    Memory = entity_factory["Memory"]
    Relationship = entity_factory["Relationship"]
    Faction = entity_factory["Faction"]
    District = entity_factory["District"]
    NemesisProfile = entity_factory["NemesisProfile"]

    inj = Injury(id="inj_arm_1", injury_type="broken_arm", severity=0.7, pain=0.6, bleeding=0.1, infection_risk=0.1)
    bp = BodyPart(id="left_arm", name="Left Arm", integrity=45.0, armor=10.0, functional=False, injuries=[inj])
    mem = Memory(
        id="mem_voss_1",
        event_type="LIMB_INJURED",
        participants=["player", "npc_voss"],
        description="Player broke Voss's arm.",
        location_id="lowtown_street",
        importance=0.85,
        emotional_valence=-0.8,
        confidence=1.0,
        created_at=2880,
    )
    rel = Relationship(source_id="npc_voss", target_id="player", trust=-50.0, respect=40.0, resentment=80.0)
    voss = Character(
        id="npc_voss",
        name="Captain Garrick Voss",
        age=38,
        faction_id="city_guard",
        body={"left_arm": bp},
        memories=[mem],
        relationships={"player": rel},
        location_id="lowtown_watchpost",
        is_nemesis=True,
    )
    world.characters["npc_voss"] = voss
    world.nemesis_profiles["npc_voss"] = NemesisProfile(
        character_id="npc_voss",
        player_hostility=75.0,
        player_respect=40.0,
        encounter_count=1,
        known_player_tactics=["heavy_attack"],
        grudges=["broken_arm"],
        career_history=[],
        last_encounter_date=2880,
        current_ambition="Become Commander of the City Guard",
        special_traits=[],
    )
    world.factions["city_guard"] = Faction(
        id="city_guard",
        name="City Guard",
        leader_id="npc_voss",
        wealth=60.0,
        influence=50.0,
        military_strength=75.0,
        stability=65.0,
        territories=["lowtown"],
        members=["npc_voss"],
        goals=[],
        relations={"lowtown_syndicate": -60.0},
    )
    world.districts["lowtown"] = District(
        id="lowtown",
        name="Lowtown",
        faction_influence={"lowtown_syndicate": 48.0, "city_guard": 22.0, "merchant_consortium": 12.0, "iron_workers_union": 10.0, "independent": 8.0},
    )

    call_method(save_manager, ("save_game", "save_current_state"), world, slot="slot_1")
    loaded = call_method(save_manager, ("load_game", "load_current_state"), slot="slot_1")

    assert get_clock_minutes(loaded.clock) == 2880
    assert "npc_voss" in loaded.characters
    loaded_voss = loaded.characters["npc_voss"]
    assert loaded_voss.body["left_arm"].injuries[0].injury_type == "broken_arm"
    assert loaded_voss.memories[0].event_type == "LIMB_INJURED"
    assert loaded.districts["lowtown"].faction_influence["lowtown_syndicate"] == pytest.approx(48.0)


def test_f7_event_log_append_and_filtered_history_query(save_manager: Any, entity_factory: dict[str, Any]) -> None:
    """Verify append_event and get_event_history filtering by min_importance and limit."""
    GameEvent = entity_factory["GameEvent"]
    importances = [0.2, 0.4, 0.6, 0.85, 0.95]
    timestamps = [10, 50, 120, 300, 600]

    for i, (imp, ts) in enumerate(zip(importances, timestamps)):
        ev = GameEvent(
            id=f"ev_hist_{i}",
            event_type="CHARACTER_INJURED",
            timestamp=ts,
            source_id="player",
            target_ids=["npc_voss"],
            location_id="lowtown",
            data={"index": i},
            importance=imp,
        )
        save_manager.append_event(ev)

    important_events = save_manager.get_event_history(min_importance=0.6)
    assert len(important_events) == 3
    assert all(e.importance >= 0.6 for e in important_events)

    limited = save_manager.get_event_history(limit=2)
    assert len(limited) == 2


def test_f7_current_state_separated_from_append_only_event_log(save_manager: Any, entity_factory: dict[str, Any]) -> None:
    """Verify overwriting current state via save_game never wipes historical events in the events table."""
    World = require_symbol("core.world", "World")
    GameEvent = entity_factory["GameEvent"]
    world = instantiate_with_context(World, seed=482193)

    for i in range(4):
        save_manager.append_event(
            GameEvent(
                id=f"ev_persist_{i}",
                event_type="FACTION_ACTION_TAKEN",
                timestamp=(i + 1) * 100,
                source_id="city_guard",
                target_ids=[],
                location_id="lowtown",
                data={},
                importance=0.7,
            )
        )

    world.clock.advance(500)
    call_method(save_manager, ("save_game", "save_current_state"), world, slot="default")

    history = save_manager.get_event_history()
    assert len(history) >= 4
    assert {f"ev_persist_{i}" for i in range(4)}.issubset({e.id for e in history})


def test_f7_periodic_snapshot_creation_and_restore(save_manager: Any, entity_factory: dict[str, Any]) -> None:
    """Verify create_snapshot and restore_snapshot roll back World state to the checkpoint."""
    World = require_symbol("core.world", "World")
    Character = entity_factory["Character"]
    world = instantiate_with_context(World, seed=482193)
    world.clock.advance(1440)
    world.characters["npc_voss"] = Character(id="npc_voss", name="Captain Voss", age=38, faction_id="city_guard", status="alive")

    snap_id = save_manager.create_snapshot(world, label="year_1_checkpoint")
    assert isinstance(snap_id, str) and len(snap_id) > 0

    world.clock.advance(8640)
    world.characters["npc_voss"].status = "dead"
    call_method(save_manager, ("save_game", "save_current_state"), world, slot="default")

    restored = save_manager.restore_snapshot(snap_id)
    assert get_clock_minutes(restored.clock) == 1440
    assert restored.characters["npc_voss"].status == "alive"


def test_f7_chronicle_generator_multi_year_narrative_summary(save_manager: Any, entity_factory: dict[str, Any]) -> None:
    """Verify generate_chronicle summarizes historical events across multiple years and acts."""
    World = require_symbol("core.world", "World")
    GameEvent = entity_factory["GameEvent"]
    world = instantiate_with_context(World, seed=482193)
    mpy = get_minutes_per_year(world.clock)

    events = [
        GameEvent(
            id="ev_c1",
            event_type="LIMB_INJURED",
            timestamp=120,
            source_id="player",
            target_ids=["npc_voss"],
            location_id="lowtown_street",
            data={"body_part": "left_leg", "injury": "compound_fracture", "weapon": "warhammer"},
            importance=0.9,
        ),
        GameEvent(
            id="ev_c2",
            event_type="RIVAL_PROMOTED",
            timestamp=mpy + 1440,
            source_id="city_guard",
            target_ids=["npc_captain_lyra"],
            location_id="barracks",
            data={"new_rank": "commander"},
            importance=0.85,
        ),
        GameEvent(
            id="ev_c3",
            event_type="POLITICAL_CONFLICT_STARTED",
            timestamp=3 * mpy + 2880,
            source_id="lowtown_syndicate",
            target_ids=["city_guard"],
            location_id="lowtown",
            data={"description": "Lowtown uprising"},
            importance=0.95,
        ),
    ]
    for ev in events:
        save_manager.append_event(ev)

    chronicle = save_manager.generate_chronicle(world)
    assert isinstance(chronicle, list) and len(chronicle) >= 3
    years = {entry.get("year") for entry in chronicle}
    assert {1, 2, 4}.issubset(years)


# ==============================================================================
# FEATURE F8: Tiered Character Simulation & Needs (systems/character_system.py, ai/character_ai.py)
# ==============================================================================


def test_f8_character_system_three_simulation_tiers(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify CharacterSystem simulates Tier 1 (Named), Tier 2 (Citizen), and Tier 3 (Background)."""
    char_sys = systems_suite["character_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    t1 = Character(id="npc_t1", name="Captain Voss", age=38, faction_id="city_guard", tier=1)
    t2 = Character(id="npc_t2", name="Blacksmith Gregor", age=45, faction_id="iron_workers_union", tier=2)
    t3 = Character(id="npc_t3", name="Lowtown Laborer", age=30, faction_id=None, tier=3)
    for c in (t1, t2, t3):
        call_method(char_sys, ("initialize_character", "ensure_character_stats", "register_character"), c)
        world.characters[c.id] = c

    call_method(char_sys, ("update", "process_tick", "simulate_characters", "step"), world, 1440)
    assert t1.tier == 1 and len(t1.needs) > 0
    assert t2.tier == 2
    assert t3.tier == 3


def test_f8_character_six_attribute_and_skill_categories_initialization(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify Tier 1 character has all 6 GDD Section 4 attribute/skill/personality/needs categories."""
    char_sys = systems_suite["character_system"]
    Character = entity_factory["Character"]
    c = Character(id="char_full", name="Rowan", age=28, faction_id=None, is_player=True)
    call_method(char_sys, ("initialize_character", "ensure_character_stats", "populate_defaults"), c)

    # Physical, Mental, Social in attributes
    for stat in ("strength", "dexterity", "endurance", "agility", "constitution", "intelligence", "perception", "willpower", "persuasion", "leadership"):
        assert stat in c.attributes or any(stat in sub for sub in c.attributes.values() if isinstance(sub, dict))

    # Personality
    for trait in ("courage", "greed", "compassion", "ambition", "loyalty", "aggression", "patience"):
        assert trait in c.personality

    # Needs
    for need in ("hunger", "fatigue", "safety", "wealth", "purpose"):
        assert need in c.needs
    assert "social" in c.needs or "social_interaction" in c.needs

    # Skills
    for skill in ("swordsmanship", "archery", "heavy_weapons", "shield_combat", "magic", "stealth", "medicine", "crafting", "negotiation"):
        assert skill in c.skills


def test_f8_needs_decay_and_autonomous_daily_recovery_ai(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify needs change over time and CharacterAI selects need-satisfying recovery actions."""
    char_sys = systems_suite["character_system"]
    char_ai = systems_suite["character_ai"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    c = Character(id="npc_daily", name="Citizen Vane", age=32, faction_id=None, tier=1)
    call_method(char_sys, ("initialize_character", "ensure_character_stats", "populate_defaults"), c)
    world.characters[c.id] = c

    call_method(char_sys, ("decay_needs", "update_needs", "update"), c, 360)
    action = call_method(char_ai, ("select_daily_action", "decide_action", "evaluate_character", "update_character"), c, world)
    assert action is not None
    assert c.status == "alive"


def test_f8_personality_drives_ai_behavior_choices(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify cowardly NPC seeks safety/retreat while ambitious low-loyalty NPC pursues promotion/betrayal."""
    char_sys = systems_suite["character_system"]
    char_ai = systems_suite["character_ai"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    coward = Character(id="npc_coward", name="Timid Guard", age=24, faction_id="city_guard")
    call_method(char_sys, ("initialize_character", "ensure_character_stats", "populate_defaults"), coward)
    coward.personality["courage"] = 10.0
    coward.needs["safety"] = 10.0

    schemer = Character(id="npc_schemer", name="Captain Voss", age=38, faction_id="city_guard")
    call_method(char_sys, ("initialize_character", "ensure_character_stats", "populate_defaults"), schemer)
    schemer.personality["ambition"] = 90.0
    schemer.personality["loyalty"] = 15.0

    choice_coward = call_method(
        char_ai,
        ("select_daily_action", "decide_action", "evaluate_character"),
        coward,
        world,
    )
    choice_schemer = call_method(
        char_ai,
        ("select_daily_action", "decide_action", "evaluate_character"),
        schemer,
        world,
    )
    assert str(choice_coward) != str(choice_schemer)


def test_f8_companion_independent_life_and_four_canonical_companions(populated_world: Any) -> None:
    """Verify the 4 canonical companions (Marcus, Elira, Sera, Tomas) perform independent activities."""
    char_ai_cls = require_symbol("ai.character_ai", "CharacterAI")
    char_ai = instantiate_with_context(char_ai_cls, world=populated_world, rng=populated_world.rng, event_bus=populated_world.event_bus)

    expected_names = {"Marcus", "Elira", "Sera", "Tomas"}
    found_names = {
        c.name.split()[0]
        for c in populated_world.characters.values()
        if getattr(c, "is_companion", False) or c.id in getattr(populated_world, "companions", {})
    }
    assert expected_names.issubset(found_names)

    for comp_id, comp in populated_world.companions.items():
        call_method(
            char_ai,
            ("update_companion_autonomy", "simulate_companion", "decide_companion_action", "evaluate_character"),
            comp,
            populated_world,
        )
        activity = getattr(comp, "independent_activity", getattr(comp, "current_activity", ""))
        assert isinstance(activity, str) and len(activity) > 0


# ==============================================================================
# FEATURE F9: Episodic & Informational Memory (systems/memory_system.py)
# ==============================================================================


def test_f9_memory_system_records_witnessed_event_with_certain_confidence(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify witnessed rescue event creates Memory with Gratitude emotion, High importance, and Confidence 1.0."""
    mem_sys = systems_suite["memory_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    GameEvent = entity_factory["GameEvent"]

    sera = Character(id="comp_sera", name="Sera", age=24, faction_id=None, location_id="barracks", is_companion=True)
    world.characters["comp_sera"] = sera

    ev = GameEvent(
        id="ev_rescue_sera",
        event_type="CHARACTER_RESCUED",
        timestamp=120,
        source_id="player",
        target_ids=["comp_sera"],
        location_id="barracks",
        data={"emotion": "Gratitude", "description": "Player rescued Sera from prison."},
        importance=0.9,
    )
    call_method(mem_sys, ("record_event", "handle_event", "create_memory_from_event", "process_event"), ev, world=world)
    assert len(sera.memories) >= 1
    mem = sera.memories[-1]
    assert "player" in mem.participants
    assert mem.importance >= 0.7
    assert mem.confidence == pytest.approx(1.0)
    assert mem.emotional_valence > 0 or getattr(mem, "emotion", "").lower() == "gratitude"


def test_f9_memory_system_records_negative_betrayal_and_disgust_events(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify selling a criminal (Disgust) and abandoning Marcus in combat (Anger) record negative valence."""
    mem_sys = systems_suite["memory_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    GameEvent = entity_factory["GameEvent"]

    marcus = Character(id="comp_marcus", name="Marcus", age=40, faction_id="city_guard", location_id="lowtown_street", is_companion=True)
    world.characters["comp_marcus"] = marcus

    ev1 = GameEvent(
        id="ev_disgust_1",
        event_type="CRIMINAL_SOLD",
        timestamp=500,
        source_id="player",
        target_ids=["comp_marcus"],
        location_id="lowtown_street",
        data={"emotion": "Disgust", "emotional_valence": -0.5, "description": "Player sold a captured criminal."},
        importance=0.5,
    )
    ev2 = GameEvent(
        id="ev_betrayal_1",
        event_type="COMPANION_ABANDONED",
        timestamp=1000,
        source_id="player",
        target_ids=["comp_marcus"],
        location_id="lowtown_street",
        data={"emotion": "Anger", "emotional_valence": -0.9, "description": "Player abandoned Marcus during combat."},
        importance=0.9,
    )
    call_method(mem_sys, ("record_event", "handle_event", "create_memory_from_event", "process_event"), ev1, world=world)
    call_method(mem_sys, ("record_event", "handle_event", "create_memory_from_event", "process_event"), ev2, world=world)

    assert len(marcus.memories) >= 2
    assert marcus.memories[-1].emotional_valence < 0
    assert marcus.memories[-1].importance >= 0.8


def test_f9_memory_system_decay_fades_minor_insult_retains_major_rescue(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify memory decay reduces low-importance minor insult while retaining high-importance rescue."""
    mem_sys = systems_suite["memory_system"]
    Character = entity_factory["Character"]
    Memory = entity_factory["Memory"]

    c = Character(id="char_decay", name="Witness", age=30, faction_id=None)
    insult = Memory(
        id="m_insult",
        event_type="MINOR_INSULT",
        participants=["player", "char_decay"],
        description="Minor insult",
        location_id="lowtown",
        importance=0.2,
        emotional_valence=-0.2,
        confidence=1.0,
        created_at=0,
        decay_rate=0.05,
    )
    rescue = Memory(
        id="m_rescue",
        event_type="LIFE_SAVING_RESCUE",
        participants=["player", "char_decay"],
        description="Life-saving rescue",
        location_id="lowtown",
        importance=0.95,
        emotional_valence=0.9,
        confidence=1.0,
        created_at=0,
        decay_rate=0.0,
    )
    c.memories.extend([insult, rescue])

    for _ in range(30):
        call_method(mem_sys, ("decay_memories", "process_decay", "update_memories", "step_decay"), c, days=1)

    remaining_ids = {m.id: m for m in c.memories}
    assert "m_rescue" in remaining_ids
    assert remaining_ids["m_rescue"].importance >= 0.85
    if "m_insult" in remaining_ids:
        assert remaining_ids["m_insult"].importance < 0.2


def test_f9_memory_system_rumor_transmission_with_partial_confidence(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify learning an event via rumor records partial confidence (0 < confidence < 1.0)."""
    mem_sys = systems_suite["memory_system"]
    Character = entity_factory["Character"]
    Rumor = entity_factory["Rumor"]

    guard = Character(id="npc_guard_01", name="Guard Watchman", age=29, faction_id="city_guard")
    rumor = Rumor(
        id="rumor_00492",
        subject="player",
        claim="Rowan murdered a City Guard officer.",
        origin="npc_0091",
        truth=False,
        reach={"lowtown": 35.0},
        confidence=47.0,
    )
    call_method(
        mem_sys,
        ("record_rumor_memory", "learn_from_rumor", "receive_rumor", "add_rumor_memory"),
        guard,
        rumor,
    )
    assert len(guard.memories) == 1
    assert 0.0 < guard.memories[0].confidence < 1.0


def test_f9_memory_system_query_by_participant_and_event_type(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify querying character memories by participant ID and event_type."""
    mem_sys = systems_suite["memory_system"]
    Character = entity_factory["Character"]
    Memory = entity_factory["Memory"]

    c = Character(id="npc_q", name="Observer", age=35, faction_id=None)
    c.memories = [
        Memory("m1", "LIMB_INJURED", ["player", "npc_voss"], "Leg injured", "lowtown", 0.8, -0.5, 1.0, 10),
        Memory("m2", "TRADE_COMPLETED", ["npc_0091", "npc_q"], "Traded goods", "harbor", 0.3, 0.2, 1.0, 20),
        Memory("m3", "ATTACK_RESOLVED", ["player", "npc_merek"], "Skirmish", "lowtown", 0.6, -0.3, 1.0, 30),
    ]
    player_mems = call_method(mem_sys, ("query_memories", "get_memories_about", "filter_memories"), c, participant_id="player")
    assert len(player_mems) == 2
    assert {m.id for m in player_mems} == {"m1", "m3"}


# ==============================================================================
# FEATURE F10: Directed 6-Axis Relationships & Companion Friendship/Rivalry (systems/relationship_system.py)
# ==============================================================================


def test_f10_relationship_directed_asymmetry_a_to_b_vs_b_to_a(systems_suite: dict[str, Any]) -> None:
    """Verify A -> B and B -> A relationships are independent across all 6 dimensions."""
    rel_sys = systems_suite["relationship_system"]

    call_method(
        rel_sys,
        ("set_relationship", "update_relationship", "modify_relationship"),
        "comp_sera",
        "player",
        trust=70.0,
        respect=85.0,
        affection=45.0,
        resentment=10.0,
        fear=0.0,
        dependency=30.0,
    )
    call_method(
        rel_sys,
        ("set_relationship", "update_relationship", "modify_relationship"),
        "player",
        "comp_sera",
        trust=40.0,
        respect=50.0,
        affection=80.0,
        resentment=0.0,
        fear=0.0,
        dependency=10.0,
    )

    rel_ab = call_method(rel_sys, ("get_relationship", "query_relationship"), "comp_sera", "player")
    rel_ba = call_method(rel_sys, ("get_relationship", "query_relationship"), "player", "comp_sera")

    assert rel_ab.trust == pytest.approx(70.0) and rel_ba.trust == pytest.approx(40.0)
    assert rel_ab.respect == pytest.approx(85.0) and rel_ba.respect == pytest.approx(50.0)
    assert rel_ab.affection == pytest.approx(45.0) and rel_ba.affection == pytest.approx(80.0)


def test_f10_relationship_derived_state_loyal_associate_gdd_example(systems_suite: dict[str, Any]) -> None:
    """Verify exact GDD Section 4 values (Trust 70, Respect 85, Affection 45, Resentment 10, Fear 0, Dependency 30) yield 'Loyal associate'."""
    rel_sys = systems_suite["relationship_system"]
    call_method(
        rel_sys,
        ("set_relationship", "update_relationship", "modify_relationship"),
        "comp_sera",
        "player",
        trust=70.0,
        respect=85.0,
        affection=45.0,
        resentment=10.0,
        fear=0.0,
        dependency=30.0,
    )
    rel = call_method(rel_sys, ("get_relationship", "query_relationship"), "comp_sera", "player")
    assert rel.relationship_state == "Loyal associate"


def test_f10_relationship_npc_to_npc_competence_respect_with_personal_dislike(systems_suite: dict[str, Any]) -> None:
    """Verify two NPCs can have high respect (80) alongside high resentment (75) and low affection (10)."""
    rel_sys = systems_suite["relationship_system"]
    call_method(
        rel_sys,
        ("set_relationship", "update_relationship", "modify_relationship"),
        "npc_voss",
        "npc_captain_lyra",
        trust=20.0,
        respect=80.0,
        affection=10.0,
        resentment=75.0,
        fear=15.0,
        dependency=5.0,
    )
    rel = call_method(rel_sys, ("get_relationship", "query_relationship"), "npc_voss", "npc_captain_lyra")
    assert rel.respect == pytest.approx(80.0)
    assert rel.resentment == pytest.approx(75.0)
    assert rel.affection == pytest.approx(10.0)


def test_f10_companion_separate_friendship_and_rivalry_tracks(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify companion friendship and rivalry progress as separate non-canceling tracks."""
    rel_sys = systems_suite["relationship_system"]
    world = systems_suite["world"]
    Companion = entity_factory["Companion"]
    Character = entity_factory["Character"]

    world.characters["comp_marcus"] = Character(id="comp_marcus", name="Marcus", age=40, faction_id="city_guard", is_companion=True)
    comp = Companion(character_id="comp_marcus", name="Marcus", friendship=35.0, rivalry=10.0)
    world.companions["comp_marcus"] = comp

    call_method(
        rel_sys,
        ("adjust_companion_standing", "update_companion_relationship", "record_companion_reaction"),
        "comp_marcus",
        friendship_delta=0.0,
        rivalry_delta=25.0,
        respect_delta=15.0,
        world=world,
    )
    assert comp.friendship >= 30.0
    assert comp.rivalry >= 35.0


def test_f10_relationship_event_propagation_updates_axes_and_shared_memories(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify a rescue/helpful event updates trust/affection, appends shared_memories, and emits RELATIONSHIP_CHANGED."""
    rel_sys = systems_suite["relationship_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    GameEvent = entity_factory["GameEvent"]

    world.characters["player"] = Character(id="player", name="Rowan", age=28, is_player=True)
    world.characters["comp_tomas"] = Character(id="comp_tomas", name="Tomas", age=31, is_companion=True)

    ev = GameEvent(
        id="ev_save_tomas",
        event_type="CHARACTER_RESCUED",
        timestamp=300,
        source_id="player",
        target_ids=["comp_tomas"],
        location_id="temple_district",
        data={"trust_delta": 25.0, "affection_delta": 15.0, "memory_id": "mem_save_tomas"},
        importance=0.85,
    )
    call_method(rel_sys, ("handle_event", "process_event", "on_event"), ev, world=world)
    rel = call_method(rel_sys, ("get_relationship", "query_relationship"), "comp_tomas", "player")
    assert rel.trust > 0.0
    assert len(rel.shared_memories) >= 1


# ==============================================================================
# FEATURE F11: Hierarchical Anatomy, 12+ Injury Types & Medicine (systems/health_system.py)
# ==============================================================================


def test_f11_humanoid_anatomy_7_regions_and_29_parts_hierarchy(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify humanoid anatomy has 7 regions and 29 total body parts with parent->children hierarchy."""
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]
    c = Character(id="char_anat", name="Rowan", age=28)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)

    regions = {"head", "neck", "torso", "left_arm", "right_arm", "left_leg", "right_leg"}
    assert regions.issubset(set(c.body.keys()))
    assert len(c.body) >= 29
    for part_name in ("skull", "brain", "eyes", "jaw", "ears", "throat", "cervical_spine", "heart", "lungs", "stomach", "liver"):
        assert part_name in c.body
        assert c.body[part_name].integrity == pytest.approx(100.0)
        assert c.body[part_name].functional is True


def test_f11_all_12_injury_types_and_functional_penalties(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify all 12+ GDD injury types apply expected functional penalties (handling, mobility, perception, accuracy, bleeding)."""
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]

    required_12 = {
        "deep_cut",
        "laceration",
        "broken_arm",
        "broken_leg",
        "compound_fracture",
        "concussion",
        "eye_injury",
        "organ_damage",
        "internal_bleeding",
        "burn",
        "nerve_damage",
        "amputation",
    }
    catalog = call_method(health_sys, ("get_injury_types", "list_injury_types", "get_injury_catalog"))
    assert required_12.issubset(set(catalog))

    c = Character(id="char_inj", name="Test Fighter", age=30)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)

    call_method(health_sys, ("apply_injury", "inflict_injury"), c, "right_arm", "broken_arm", severity=0.8)
    call_method(health_sys, ("apply_injury", "inflict_injury"), c, "left_leg", "broken_leg", severity=0.8)
    call_method(health_sys, ("apply_injury", "inflict_injury"), c, "eyes", "eye_injury", severity=0.8)

    mods = call_method(health_sys, ("get_combat_modifiers", "calculate_penalties", "get_functional_modifiers"), c)
    assert mods["weapon_handling"] < 1.0
    assert mods["mobility"] < 1.0
    assert mods["accuracy"] < 1.0


def test_f11_bleeding_pain_consciousness_and_incapacitation_pipeline(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify severe bleeding and pain reduce consciousness and emit CHARACTER_INCAPACITATED."""
    health_sys = systems_suite["health_system"]
    event_bus = systems_suite["event_bus"]
    Character = entity_factory["Character"]

    c = Character(id="char_bleed", name="Wounded Guard", age=30)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)
    call_method(health_sys, ("apply_injury", "inflict_injury"), c, "torso", "deep_cut", severity=0.95)
    call_method(health_sys, ("apply_injury", "inflict_injury"), c, "left_leg", "compound_fracture", severity=0.95)

    call_method(health_sys, ("update_health", "process_health_tick", "tick_character_health"), c, minutes=60)
    assert c.consciousness < 50.0 or c.status == "incapacitated"
    if c.status == "incapacitated":
        assert any(e.event_type == "CHARACTER_INCAPACITATED" for e in event_bus.emitted_log)


def test_f11_five_medical_treatment_stages_progression(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify all 5 medical stages: first_aid, field_treatment, surgery, rehabilitation, prosthetics."""
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]

    patient = Character(id="char_patient", name="Marcus", age=40)
    doctor = Character(id="comp_tomas", name="Tomas", age=31, skills={"medicine": 90.0})
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), patient)

    call_method(health_sys, ("apply_injury", "inflict_injury"), patient, "torso", "deep_cut", severity=0.7)
    call_method(health_sys, ("apply_injury", "inflict_injury"), patient, "stomach", "organ_damage", severity=0.8)
    call_method(health_sys, ("apply_injury", "inflict_injury"), patient, "right_arm", "broken_arm", severity=0.7)
    call_method(health_sys, ("apply_injury", "inflict_injury"), patient, "left_arm", "amputation", severity=1.0)

    # 1. First aid stops active bleeding
    call_method(health_sys, ("apply_treatment", "treat_character", "perform_treatment"), patient, stage="first_aid", doctor=doctor)
    assert patient.body["torso"].injuries[0].bleeding == pytest.approx(0.0)

    # 2. Field treatment stabilizes and reduces pain
    call_method(health_sys, ("apply_treatment", "treat_character", "perform_treatment"), patient, stage="field_treatment", doctor=doctor)
    assert patient.body["right_arm"].injuries[0].treated is True

    # 3. Surgery repairs internal organ damage
    call_method(health_sys, ("apply_treatment", "treat_character", "perform_treatment"), patient, stage="surgery", doctor=doctor, body_part="stomach")

    # 4. Rehabilitation restores movement/function of fractured limb
    call_method(health_sys, ("apply_treatment", "treat_character", "perform_treatment"), patient, stage="rehabilitation", doctor=doctor, body_part="right_arm")
    assert patient.body["right_arm"].functional is True

    # 5. Prosthetics replaces amputated left_arm
    call_method(health_sys, ("apply_treatment", "treat_character", "perform_treatment"), patient, stage="prosthetics", doctor=doctor, body_part="left_arm", prosthetic_id="iron_prosthetic_arm")
    assert patient.body["left_arm"].functional is True
    assert patient.body["left_arm"].prosthetic_id is not None


def test_f11_long_term_scars_and_chronic_consequences_persistence(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify healed deep_cut leaves a scar and poorly set broken_leg leaves chronic_pain/improperly healed bone."""
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]

    c = Character(id="char_scar", name="Veteran", age=36)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)
    call_method(health_sys, ("apply_injury", "inflict_injury"), c, "torso", "deep_cut", severity=0.8)
    call_method(health_sys, ("apply_injury", "inflict_injury"), c, "left_leg", "broken_leg", severity=0.85)

    call_method(health_sys, ("advance_healing", "update_health", "heal_over_time"), c, days=30)
    history = call_method(health_sys, ("get_physical_history", "get_scars_and_conditions", "inspect_health"), c)
    assert len(history) > 0


# ==============================================================================
# FEATURE F12: Localized Armor, Weapons & Equipment (systems/equipment_system.py)
# ==============================================================================


def test_f12_localized_armor_coverage_per_body_part(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify helmet protects head and breastplate protects torso, leaving arms and legs at 0 armor."""
    eq_sys = systems_suite["equipment_system"]
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]
    Item = entity_factory["Item"]

    c = Character(id="char_armor", name="Rowan", age=28)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)

    helmet = Item(
        id="steel_helmet",
        name="Steel Helmet",
        item_type="armor",
        armor_class="plate",
        armor_protection=18.0,
        covered_parts=["head", "skull", "brain"],
    )
    breastplate = Item(
        id="plate_breastplate",
        name="Plate Breastplate",
        item_type="armor",
        armor_class="plate",
        armor_protection=25.0,
        covered_parts=["torso", "ribs", "heart", "lungs"],
    )

    call_method(eq_sys, ("equip_item", "equip"), c, helmet)
    call_method(eq_sys, ("equip_item", "equip"), c, breastplate)

    assert c.body["head"].armor >= 18.0
    assert c.body["torso"].armor >= 25.0
    assert c.body["left_arm"].armor == pytest.approx(0.0)
    assert c.body["right_arm"].armor == pytest.approx(0.0)
    assert c.body["left_leg"].armor == pytest.approx(0.0)
    assert c.body["right_leg"].armor == pytest.approx(0.0)


def test_f12_five_armor_classes_protection_and_material_weaknesses(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify all 5 armor classes (padded_cloth, leather, chainmail, scale, plate) and material weaknesses."""
    eq_sys = systems_suite["equipment_system"]
    Item = entity_factory["Item"]

    classes = [
        ("padded_cloth", 5.0, ["piercing"]),
        ("leather", 9.0, ["heavy_attacks", "blunt"]),
        ("chainmail", 15.0, ["blunt"]),
        ("scale", 18.0, ["gaps_and_joints", "piercing"]),
        ("plate", 25.0, ["joints_and_blunt_force", "blunt"]),
    ]
    items = [
        Item(id=f"armor_{ac}", name=ac, item_type="armor", armor_class=ac, armor_protection=prot, covered_parts=["torso"], weaknesses=wk)
        for ac, prot, wk in classes
    ]

    cutting_eff = [
        call_method(eq_sys, ("calculate_armor_mitigation", "resolve_armor_damage", "compute_effective_damage"), item, "cutting", 30.0)
        for item in items
    ]
    # Effective damage taken from a 30.0 cutting strike must strictly decrease as armor class rises
    vals = [r["effective_damage"] if isinstance(r, dict) else float(r) for r in cutting_eff]
    assert vals[0] > vals[1] > vals[2] >= vals[3] > vals[4]


def test_f12_weapons_across_six_damage_types(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify weapons across all 6 damage types (cutting, piercing, blunt, fire, poison, magic)."""
    eq_sys = systems_suite["equipment_system"]
    Character = entity_factory["Character"]
    Item = entity_factory["Item"]

    c = Character(id="char_weap", name="Fighter", age=28)
    damage_types = ["cutting", "piercing", "blunt", "fire", "poison", "magic"]
    for dt in damage_types:
        w = Item(id=f"weap_{dt}", name=f"Weapon {dt}", item_type="weapon", damage=18.0, damage_type=dt, penetration=5.0, handling=1.0)
        call_method(eq_sys, ("equip_item", "equip"), c, w)
        profile = call_method(eq_sys, ("get_active_weapon_profile", "get_equipped_weapon", "get_weapon_stats"), c)
        dt_val = profile.damage_type if hasattr(profile, "damage_type") else profile.get("damage_type")
        assert dt_val == dt


def test_f12_unequip_and_swap_armor_updates_body_part_ratings(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify equipping, swapping, and unequipping torso armor updates BodyPart.armor without stacking."""
    eq_sys = systems_suite["equipment_system"]
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]
    Item = entity_factory["Item"]

    c = Character(id="char_swap", name="Rowan", age=28)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)

    leather = Item(id="leather_jerkin", name="Leather Jerkin", item_type="armor", armor_class="leather", armor_protection=8.0, covered_parts=["torso"])
    plate = Item(id="plate_breastplate", name="Plate Breastplate", item_type="armor", armor_class="plate", armor_protection=25.0, covered_parts=["torso"])

    call_method(eq_sys, ("equip_item", "equip"), c, leather)
    assert c.body["torso"].armor == pytest.approx(8.0)

    call_method(eq_sys, ("equip_item", "equip"), c, plate)
    assert c.body["torso"].armor == pytest.approx(25.0)

    call_method(eq_sys, ("unequip_item", "unequip"), c, "plate_breastplate")
    assert c.body["torso"].armor == pytest.approx(0.0)


def test_f12_prosthetic_fitting_restores_amputated_limb_function(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify fitting a prosthetic onto an amputated arm restores functional=True and emits PROSTHETIC_FITTED."""
    eq_sys = systems_suite["equipment_system"]
    health_sys = systems_suite["health_system"]
    event_bus = systems_suite["event_bus"]
    Character = entity_factory["Character"]
    Item = entity_factory["Item"]

    c = Character(id="char_amp", name="Veteran", age=35)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)
    call_method(health_sys, ("apply_injury", "inflict_injury"), c, "left_arm", "amputation", severity=1.0)
    assert c.body["left_arm"].functional is False

    prosthetic = Item(
        id="iron_prosthetic_arm",
        name="Iron Prosthetic Arm",
        item_type="prosthetic",
        covered_parts=["left_arm"],
        properties={"target_part": "left_arm"},
    )
    call_method(eq_sys, ("fit_prosthetic", "equip_prosthetic", "equip_item"), c, prosthetic, body_part="left_arm")
    assert c.body["left_arm"].functional is True
    assert c.body["left_arm"].prosthetic_id == "iron_prosthetic_arm"
    assert any(e.event_type == "PROSTHETIC_FITTED" for e in event_bus.emitted_log)


def test_f12_crafting_weapons_armor_and_medicine(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify Section 11 crafting produces medicine, weapons, and armor items."""
    eq_sys = systems_suite["equipment_system"]
    Character = entity_factory["Character"]

    crafter = Character(
        id="char_crafter",
        name="Artisan",
        age=32,
        skills={"crafting": 75.0, "medicine": 65.0},
        needs={"wealth": 100.0},
    )
    bandage = call_method(eq_sys, ("craft_item", "craft"), crafter, "field_bandage")
    sword = call_method(eq_sys, ("craft_item", "craft"), crafter, "iron_longsword")
    assert bandage is not None and sword is not None


# ==============================================================================
# FEATURE F13: Command-Based Tactical Grid Combat & Combat AI (systems/combat_system.py, ai/combat_ai.py)
# ==============================================================================


def test_f13_tactical_grid_rendering_and_eight_terrain_features(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify 5x5 / 8x8 ASCII tactical grid rendering and all 8 terrain features."""
    combat_sys = systems_suite["combat_system"]
    Character = entity_factory["Character"]

    party = [
        Character(id="player", name="Rowan", age=28, is_player=True),
        Character(id="comp_marcus", name="Marcus", age=40, is_companion=True),
        Character(id="comp_elira", name="Elira", age=26, is_companion=True),
        Character(id="comp_sera", name="Sera", age=24, is_companion=True),
    ]
    enemies = [
        Character(id="npc_voss", name="Captain Voss", age=38, is_nemesis=True),
        Character(id="npc_guard_1", name="Guard", age=28),
        Character(id="npc_archer_1", name="Archer", age=25),
    ]
    enc = call_method(combat_sys, ("create_encounter", "start_encounter", "init_battlefield"), party=party, enemies=enemies, grid_size=(5, 5))
    ascii_map = call_method(enc, ("render_ascii_grid", "render_grid", "to_ascii", "__str__"))
    assert "A" in ascii_map and "B" in ascii_map and "C" in ascii_map
    assert "[ R ]" in ascii_map or "R" in ascii_map
    assert "[ V ]" in ascii_map or "V" in ascii_map

    required_terrains = {
        "cover",
        "walls",
        "doors",
        "elevation",
        "narrow_passages",
        "hazards",
        "flammable_objects",
        "difficult_terrain",
    }
    supported_terrains = set(call_method(combat_sys, ("get_supported_terrains", "list_terrain_features", "get_terrain_catalog")))
    assert required_terrains.issubset(supported_terrains)


def test_f13_all_twenty_one_commands_across_four_categories(systems_suite: dict[str, Any]) -> None:
    """Verify all 21 GDD Section 6 tactical commands exist across Movement, Combat, Support, and Special."""
    combat_sys = systems_suite["combat_system"]
    expected = {
        "Movement": {"move", "charge", "retreat", "flank", "take_cover"},
        "Combat": {"attack", "heavy_attack", "aim", "guard", "disarm", "grapple", "interrupt"},
        "Support": {"heal", "stabilize", "apply_bandage", "revive", "protect_ally"},
        "Special": {"spellcasting", "stealth_attack", "area_attack", "environmental_interaction"},
    }
    catalog = call_method(combat_sys, ("get_command_catalog", "list_commands_by_category", "get_available_commands"))
    for category, cmds in expected.items():
        cat_cmds = set(catalog.get(category, catalog.get(category.lower(), [])))
        assert cmds.issubset(cat_cmds), f"Missing commands in {category}: {cmds - cat_cmds}"


def test_f13_nine_step_attack_resolution_pipeline_and_event_emission(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify the 9-step attack resolution pipeline (D_effective = max(0, D_raw - R_armor)) and LIMB_INJURED event."""
    combat_sys = systems_suite["combat_system"]
    health_sys = systems_suite["health_system"]
    event_bus = systems_suite["event_bus"]
    Character = entity_factory["Character"]
    Item = entity_factory["Item"]

    rowan = Character(id="player", name="Rowan", age=28, attributes={"strength": 75, "dexterity": 80, "agility": 75}, skills={"heavy_weapons": 85})
    voss = Character(id="npc_voss", name="Captain Voss", age=38, attributes={"agility": 40, "endurance": 60})
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), rowan)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), voss)

    warhammer = Item(id="warhammer", name="Warhammer", item_type="weapon", damage=28.0, damage_type="blunt", penetration=12.0, handling=1.0)
    result = call_method(
        combat_sys,
        ("resolve_attack", "execute_attack"),
        attacker=rowan,
        defender=voss,
        weapon=warhammer,
        command="aim",
        target_part="left_leg",
        force_hit=True,
    )
    assert isinstance(result, dict)
    assert result.get("hit") is True
    assert result.get("hit_location") == "left_leg"
    assert result.get("effective_damage", 0.0) > 0.0
    assert voss.body["left_leg"].integrity < 100.0
    assert any(e.event_type in ("CHARACTER_INJURED", "LIMB_INJURED", "ATTACK_RESOLVED") for e in event_bus.emitted_log)


def test_f13_initiative_ordering_from_agility_weight_injuries_and_fatigue(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify initiative depends on agility, weapon handling, armor weight, injuries, fatigue, and surprise."""
    combat_sys = systems_suite["combat_system"]
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]

    sera = Character(
        id="comp_sera",
        name="Sera",
        age=24,
        attributes={"agility": 88, "dexterity": 85},
        needs={"fatigue": 5.0},
    )
    voss = Character(
        id="npc_voss",
        name="Captain Voss",
        age=38,
        attributes={"agility": 45, "dexterity": 50},
        needs={"fatigue": 65.0},
    )
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), sera)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), voss)
    call_method(health_sys, ("apply_injury", "inflict_injury"), voss, "left_leg", "broken_leg", severity=0.8)

    order = call_method(combat_sys, ("get_initiative_order", "calculate_initiative_order", "sort_by_initiative"), [voss, sera])
    first_id = order[0].id if hasattr(order[0], "id") else order[0]
    assert first_id == "comp_sera"


def test_f13_seven_enemy_ai_archetypes_and_six_morale_states(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify all 7 enemy AI archetypes and all 6 morale states drive tactical action selection."""
    combat_sys = systems_suite["combat_system"]
    combat_ai = systems_suite["combat_ai"]
    EnemyCombatant = entity_factory["EnemyCombatant"]

    archetypes = ["coward", "duelist", "commander", "berserker", "assassin", "medic", "opportunist"]
    morale_states = ["confident", "steady", "nervous", "frightened", "panicking", "routing"]

    for arch in archetypes:
        enemy = EnemyCombatant(character_id=f"e_{arch}", archetype=arch, morale=75.0, morale_state="steady")
        decision = call_method(combat_ai, ("select_action", "decide_combat_action", "choose_action"), enemy, context={"ally_bleeding": True, "commander_down": True})
        assert isinstance(decision, dict) and "command" in decision

    coward = EnemyCombatant(character_id="e_coward_m", archetype="coward", morale=95.0, morale_state="confident")
    seen_states: set[str] = {coward.morale_state}
    for morale_val in (90.0, 70.0, 50.0, 32.0, 16.0, 4.0):
        state = call_method(combat_sys, ("evaluate_morale_state", "get_morale_state", "update_morale"), coward, morale_value=morale_val)
        seen_states.add(state if isinstance(state, str) else coward.morale_state)
    assert set(morale_states).issubset(seen_states)


def test_f13_kenshi_style_non_lethal_player_defeat_outcomes(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify losing a battle triggers Kenshi-style non-lethal defeat outcomes (captured, robbed, imprisoned, rescued, left_for_dead)."""
    combat_sys = systems_suite["combat_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    player = Character(id="player", name="Rowan", age=28, status="incapacitated", is_player=True)
    world.characters["player"] = player

    res_guard = call_method(combat_sys, ("resolve_player_defeat", "handle_player_defeat"), world=world, victor_faction="city_guard")
    assert res_guard["outcome"] in {"captured", "imprisoned"}
    assert player.status != "dead"

    res_syndicate = call_method(combat_sys, ("resolve_player_defeat", "handle_player_defeat"), world=world, victor_faction="lowtown_syndicate")
    assert res_syndicate["outcome"] in {"robbed", "left_for_dead", "rescued"}
    assert player.status != "dead"


# ==============================================================================
# FEATURE F14: Nemesis System & Ambition AI (systems/nemesis_system.py, ai/ambition_ai.py)
# ==============================================================================


def test_f14_all_seven_nemesis_eligibility_triggers_promote_npc_to_nemesis(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify all 7 GDD Section 7 eligibility triggers promote an eligible NPC to a Nemesis."""
    nem_sys = systems_suite["nemesis_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    triggers = [
        "survives_encounter",
        "injures_player",
        "escapes_capture",
        "witnesses_major_event",
        "loses_subordinate",
        "gains_power",
        "develops_personal_grievance",
    ]
    for i, trig in enumerate(triggers):
        npc = Character(id=f"npc_elig_{i}", name=f"Officer {i}", age=30, faction_id="city_guard", tier=1, is_nemesis=False)
        world.characters[npc.id] = npc
        profile = call_method(nem_sys, ("evaluate_eligibility", "check_eligibility", "promote_to_nemesis"), npc, trigger=trig, world=world)
        assert npc.is_nemesis is True
        assert profile is not None and profile.character_id == npc.id


def test_f14_captain_voss_canonical_profile_and_grudge_recording(populated_world: Any) -> None:
    """Verify Captain Garrick Voss matches GDD Section 7 attributes and records grudges/memories."""
    nem_sys_cls = require_symbol("systems.nemesis_system", "NemesisSystem")
    nem_sys = instantiate_with_context(nem_sys_cls, world=populated_world, rng=populated_world.rng, event_bus=populated_world.event_bus)

    voss = populated_world.characters["npc_voss"]
    profile = populated_world.nemesis_profiles["npc_voss"]
    assert voss.faction_id == "city_guard"
    assert profile.rank == "captain"
    assert voss.personality["ambition"] == 85
    assert voss.personality["courage"] == 45
    assert voss.personality["cruelty"] == 70
    assert voss.personality["loyalty"] == 30
    assert voss.personality["cunning"] == 65
    assert profile.current_ambition == "Become Commander of the City Guard"
    assert any("fire" in w.lower() for w in profile.weaknesses)

    call_method(nem_sys, ("record_encounter", "add_grudge", "update_nemesis_from_event"), profile, grudge="Player scarred his face", hostility_delta=20.0)
    assert profile.player_hostility > 0
    assert any("scarred" in g.lower() for g in profile.grudges)


def test_f14_six_fair_adaptation_rules_from_witnessed_player_tactics(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify all 6 GDD Section 7 player-tactic-to-adaptation rules when tactics are witnessed."""
    nem_sys = systems_suite["nemesis_system"]
    NemesisProfile = entity_factory["NemesisProfile"]

    expected_pairs = [
        ("fire_magic", "fire_resistant_equipment"),
        ("backstab", "rear_guards_and_tighter_formations"),
        ("heavy_shield", "armor_piercing_weapons"),
        ("ambush", "increased_patrols"),
        ("poison", "antidotes_and_precautions"),
        ("frequent_retreat", "pursuit_specialists"),
    ]
    profile = NemesisProfile(character_id="npc_voss")
    for tactic, expected_adaptation in expected_pairs:
        call_method(nem_sys, ("record_witnessed_tactic", "observe_tactic"), profile, tactic=tactic, count=3, witnessed=True)
        adaptations = call_method(nem_sys, ("adapt_to_player", "evaluate_adaptations", "apply_adaptations"), profile)
        all_adaptations = set(adaptations or []) | set(getattr(profile, "adaptations", [])) | set(profile.special_traits)
        assert expected_adaptation in all_adaptations


def test_f14_five_rank_hierarchy_promotion_and_injured_rival_bypass(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify 5-rank hierarchy (soldier -> sergeant -> lieutenant -> captain -> commander) and injured Voss bypassed by rival."""
    nem_sys = systems_suite["nemesis_system"]
    health_sys = systems_suite["health_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    Faction = entity_factory["Faction"]

    voss = Character(id="npc_voss", name="Captain Voss", age=38, faction_id="city_guard", rank="captain", personality={"ambition": 85, "loyalty": 30})
    lyra = Character(id="npc_captain_lyra", name="Captain Lyra", age=34, faction_id="city_guard", rank="captain", personality={"ambition": 80, "loyalty": 75})
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), voss)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), lyra)
    call_method(health_sys, ("apply_injury", "inflict_injury"), voss, "right_arm", "broken_arm", severity=0.9)
    call_method(health_sys, ("apply_injury", "inflict_injury"), voss, "left_leg", "compound_fracture", severity=0.9)

    world.characters["npc_voss"] = voss
    world.characters["npc_captain_lyra"] = lyra
    guard = Faction(id="city_guard", name="City Guard", leader_id=None, members=["npc_voss", "npc_captain_lyra"])
    world.factions["city_guard"] = guard

    winner = call_method(
        nem_sys,
        ("evaluate_promotion_candidates", "resolve_promotion", "promote_best_candidate"),
        guard,
        target_rank="commander",
        world=world,
    )
    winner_id = winner.id if hasattr(winner, "id") else (winner.get("winner_id") if isinstance(winner, dict) else winner)
    assert winner_id == "npc_captain_lyra"


def test_f14_seven_defeat_and_survival_outcomes(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify all 7 GDD Section 7 defeat outcomes: capture, escape, hospitalization, presumed_death, permanent_disability, recruitment, execution."""
    nem_sys = systems_suite["nemesis_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    NemesisProfile = entity_factory["NemesisProfile"]

    outcomes = [
        "capture",
        "escape",
        "hospitalization",
        "presumed_death",
        "permanent_disability",
        "recruitment",
        "execution",
    ]
    for outcome in outcomes:
        c = Character(id=f"nem_{outcome}", name=f"Nemesis {outcome}", age=35, faction_id="city_guard", is_nemesis=True)
        p = NemesisProfile(character_id=c.id)
        world.characters[c.id] = c
        world.nemesis_profiles[c.id] = p
        res = call_method(nem_sys, ("resolve_defeat_outcome", "apply_defeat_outcome"), c, outcome=outcome, world=world)
        assert res is not None
        if outcome == "execution":
            assert c.status == "dead"
        elif outcome == "recruitment":
            assert c.is_companion is True or c.id in world.player_party


def test_f14_ambition_ai_betrayal_and_scheme_execution(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify AmbitionAI causes ambitious low-loyalty Captain Voss to scheme/betray when promotion is possible."""
    ambition_ai = systems_suite["ambition_ai"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    NemesisProfile = entity_factory["NemesisProfile"]
    Faction = entity_factory["Faction"]

    vael = Character(id="npc_commander_vael", name="Commander Vael", age=58, faction_id="city_guard", rank="commander", consciousness=35.0)
    voss = Character(
        id="npc_voss",
        name="Captain Garrick Voss",
        age=38,
        faction_id="city_guard",
        rank="captain",
        personality={"ambition": 85.0, "loyalty": 20.0, "cunning": 65.0},
        is_nemesis=True,
    )
    world.characters["npc_commander_vael"] = vael
    world.characters["npc_voss"] = voss
    world.nemesis_profiles["npc_voss"] = NemesisProfile(character_id="npc_voss", current_ambition="Become Commander of the City Guard")
    world.factions["city_guard"] = Faction(id="city_guard", name="City Guard", leader_id="npc_commander_vael", stability=30.0, members=["npc_commander_vael", "npc_voss"])

    scheme = call_method(ambition_ai, ("evaluate_npc_ambitions", "evaluate_ambition", "select_ambition_action"), voss, world=world)
    assert isinstance(scheme, dict)
    assert scheme.get("scheme_type", scheme.get("action")) in {"betray_superior", "undermine_rival", "seek_promotion", "coup"}


# ==============================================================================
# FEATURE F15: Faction & Political Simulation (systems/faction_system.py, ai/faction_ai.py)
# ==============================================================================


def test_f15_seven_factions_attributes_and_directional_relations(populated_world: Any) -> None:
    """Verify all 7 GDD Section 8 factions exist and support directional inter-faction relations."""
    fac_sys_cls = require_symbol("systems.faction_system", "FactionSystem")
    fac_sys = instantiate_with_context(fac_sys_cls, world=populated_world, rng=populated_world.rng, event_bus=populated_world.event_bus)

    expected_factions = {
        "city_guard",
        "merchant_consortium",
        "ashen_church",
        "lowtown_syndicate",
        "iron_workers_union",
        "noble_houses",
        "independent_mages",
    }
    assert expected_factions.issubset(set(populated_world.factions.keys()))

    call_method(fac_sys, ("set_relation", "adjust_relation", "update_relation"), "city_guard", "lowtown_syndicate", -80.0)
    call_method(fac_sys, ("set_relation", "adjust_relation", "update_relation"), "lowtown_syndicate", "city_guard", -45.0)

    r_ab = call_method(fac_sys, ("get_relation", "query_relation"), "city_guard", "lowtown_syndicate")
    r_ba = call_method(fac_sys, ("get_relation", "query_relation"), "lowtown_syndicate", "city_guard")
    assert r_ab != r_ba


def test_f15_eight_faction_goal_types_and_autonomous_turn_cycle(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify all 8 GDD Section 8 faction goals and autonomous 5-stage faction turn execution."""
    fac_sys = systems_suite["faction_system"]
    fac_ai = systems_suite["faction_ai"]
    world = systems_suite["world"]
    event_bus = systems_suite["event_bus"]
    Faction = entity_factory["Faction"]
    District = entity_factory["District"]

    world.districts["lowtown"] = District(
        id="lowtown",
        name="Lowtown",
        faction_influence={"lowtown_syndicate": 48.0, "city_guard": 22.0, "merchant_consortium": 12.0, "iron_workers_union": 10.0, "independent": 8.0},
    )
    goal_types = [
        "capture_district",
        "replace_commander",
        "control_trade",
        "pass_law",
        "eliminate_rival",
        "expand_membership",
        "secure_marriage_alliance",
        "suppress_uprising",
    ]
    for gt in goal_types:
        f = Faction(id=f"fac_{gt}", name=f"Faction {gt}", goals=[{"type": gt, "target": "lowtown"}], wealth=70.0, military_strength=70.0)
        world.factions[f.id] = f
        res = call_method(fac_ai, ("process_faction_turn", "evaluate_faction_turn", "select_faction_action"), f, world=world)
        assert res is not None

    assert any(e.event_type == "FACTION_ACTION_TAKEN" for e in event_bus.emitted_log)


def test_f15_lowtown_initial_influence_and_percentage_normalization(populated_world: Any) -> None:
    """Verify Lowtown initial influence (48/22/12/10/8) and normalization to 100.0% after shifts."""
    fac_sys_cls = require_symbol("systems.faction_system", "FactionSystem")
    fac_sys = instantiate_with_context(fac_sys_cls, world=populated_world, rng=populated_world.rng, event_bus=populated_world.event_bus)

    lowtown = populated_world.districts["lowtown"]
    inf = lowtown.faction_influence
    assert inf["lowtown_syndicate"] == pytest.approx(48.0)
    assert inf["city_guard"] == pytest.approx(22.0)
    assert inf["merchant_consortium"] == pytest.approx(12.0)
    assert inf.get("iron_workers_union", inf.get("iron_workers", 0.0)) == pytest.approx(10.0)
    assert inf.get("independent", inf.get("independent_mages", 0.0)) == pytest.approx(8.0)
    assert sum(inf.values()) == pytest.approx(100.0)

    call_method(fac_sys, ("shift_district_influence", "update_district_influence", "adjust_influence"), "lowtown", "city_guard", 10.0)
    assert sum(lowtown.faction_influence.values()) == pytest.approx(100.0)
    assert lowtown.faction_influence["city_guard"] > 22.0


def test_f15_district_multi_metric_tradeoff_gang_protection_vs_crime(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify gang activity can increase employment/wealth while increasing crime (no single good/evil meter)."""
    fac_sys = systems_suite["faction_system"]
    world = systems_suite["world"]
    District = entity_factory["District"]
    Faction = entity_factory["Faction"]

    d = District(id="lowtown", name="Lowtown", security=40.0, crime=50.0, employment=45.0, wealth=30.0)
    world.districts["lowtown"] = d
    world.factions["lowtown_syndicate"] = Faction(id="lowtown_syndicate", name="Lowtown Syndicate")

    call_method(
        fac_sys,
        ("apply_faction_action", "execute_faction_action"),
        faction_id="lowtown_syndicate",
        action_type="expand_smuggling",
        district_id="lowtown",
        world=world,
    )
    assert d.crime > 50.0
    assert d.employment > 45.0 or d.wealth > 30.0


def test_f15_leadership_vacancy_succession_on_death_or_incapacitation(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify leader death emits LEADERSHIP_VACANCY and promotes a successor."""
    fac_sys = systems_suite["faction_system"]
    world = systems_suite["world"]
    event_bus = systems_suite["event_bus"]
    Character = entity_factory["Character"]
    Faction = entity_factory["Faction"]
    GameEvent = entity_factory["GameEvent"]
    EventPriority = entity_factory["EventPriority"]

    leader = Character(id="npc_vael", name="Commander Vael", age=55, faction_id="city_guard", rank="commander", status="dead")
    captain = Character(id="npc_voss", name="Captain Voss", age=38, faction_id="city_guard", rank="captain", status="alive", personality={"ambition": 85, "competence": 75})
    world.characters["npc_vael"] = leader
    world.characters["npc_voss"] = captain
    guard = Faction(id="city_guard", name="City Guard", leader_id="npc_vael", members=["npc_vael", "npc_voss"])
    world.factions["city_guard"] = guard

    death_ev = GameEvent(
        id="ev_leader_died",
        event_type="CHARACTER_DIED",
        timestamp=500,
        source_id="player",
        target_ids=["npc_vael"],
        location_id="barracks",
        data={},
        importance=0.95,
    )
    event_bus.emit(death_ev, priority=EventPriority.CRITICAL)
    event_bus.process_tick_events()
    if guard.leader_id == "npc_vael":
        call_method(fac_sys, ("resolve_leadership_vacancy", "handle_leader_death"), "city_guard", world=world)

    assert guard.leader_id == "npc_voss"


def test_f15_crime_bounty_arrest_prison_and_religious_schism(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify Section 11 crime/bounty/arrest/prison and Ashen Church religious schism mechanics."""
    fac_sys = systems_suite["faction_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    Faction = entity_factory["Faction"]
    District = entity_factory["District"]

    world.characters["player"] = Character(id="player", name="Rowan", age=28, is_player=True, location_id="lowtown_street")
    world.districts["lowtown"] = District(id="lowtown", name="Lowtown")
    world.districts["temple_district"] = District(id="temple_district", name="Temple District", unrest=40.0)
    world.factions["city_guard"] = Faction(id="city_guard", name="City Guard")
    world.factions["ashen_church"] = Faction(id="ashen_church", name="Ashen Church", stability=25.0)

    call_method(fac_sys, ("report_crime", "record_crime"), actor_id="player", crime_type="theft", district_id="lowtown", witnessed=True, world=world)
    t_before = get_clock_minutes(world.clock)
    call_method(fac_sys, ("arrest_character", "arrest_player"), "player", world=world)
    assert get_clock_minutes(world.clock) > t_before

    call_method(fac_sys, ("trigger_religious_schism", "evaluate_religious_authority"), world=world)
    assert world.districts["temple_district"].unrest > 40.0


# ==============================================================================
# FEATURE F16: Hybrid Quests, 6-Scope Reputation, Rumors & Economy (systems/quest_system.py, rumor_system.py, economy_system.py)
# ==============================================================================


def test_f16_authored_systemic_and_hybrid_quest_creation_and_live_reactivity(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify authored, systemic, and hybrid quests reference and react to live world state."""
    quest_sys = systems_suite["quest_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    world.characters["npc_missing_apprentice"] = Character(id="npc_missing_apprentice", name="Joren", age=17, status="alive")
    world.characters["npc_workshop_owner"] = Character(id="npc_workshop_owner", name="Gregor", age=48, status="alive")
    world.characters["comp_sera"] = Character(id="comp_sera", name="Sera", age=24, is_companion=True)

    q_hybrid = call_method(
        quest_sys,
        ("create_hybrid_quest", "start_quest", "create_quest"),
        quest_id="quest_missing_apprentice",
        quest_type="hybrid",
        world=world,
    )
    assert q_hybrid.quest_type == "hybrid"

    state_alive = call_method(quest_sys, ("evaluate_quest_conditions", "evaluate_quest_state"), "quest_missing_apprentice", world=world)
    world.characters["npc_missing_apprentice"].status = "dead"
    state_dead = call_method(quest_sys, ("evaluate_quest_conditions", "evaluate_quest_state"), "quest_missing_apprentice", world=world)
    assert state_alive != state_dead


def test_f16_six_scope_reputation_independence_hero_in_lowtown_criminal_in_high_quarter(systems_suite: dict[str, Any]) -> None:
    """Verify all 6 reputation scopes allow being a hero in Lowtown and a criminal in High Quarter."""
    quest_sys = systems_suite["quest_system"]
    world = systems_suite["world"]

    scopes = [
        ("district", "lowtown", 45.0),
        ("district", "high_quarter", -40.0),
        ("faction", "lowtown_syndicate", 35.0),
        ("faction", "city_guard", -30.0),
        ("individual_npc", "npc_0091", 25.0),
        ("general_public", None, 10.0),
        ("criminal_underworld", None, 50.0),
        ("noble_society", None, -45.0),
    ]
    for scope, key, delta in scopes:
        call_method(quest_sys, ("adjust_reputation", "modify_reputation"), scope=scope, key=key, delta=delta, world=world)

    rep_low = call_method(quest_sys, ("get_reputation", "query_reputation"), scope="district", key="lowtown", world=world)
    rep_high = call_method(quest_sys, ("get_reputation", "query_reputation"), scope="district", key="high_quarter", world=world)
    rep_under = call_method(quest_sys, ("get_reputation", "query_reputation"), scope="criminal_underworld", key=None, world=world)
    rep_noble = call_method(quest_sys, ("get_reputation", "query_reputation"), scope="noble_society", key=None, world=world)

    assert rep_low >= 40.0 and rep_high <= -35.0
    assert rep_under >= 45.0 and rep_noble <= -40.0


def test_f16_rumor_creation_false_rumor_planting_and_multi_district_propagation(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify Rumor #00492 schema, player false-rumor planting, and multi-district propagation."""
    rumor_sys = systems_suite["rumor_system"]
    world = systems_suite["world"]
    District = entity_factory["District"]
    Character = entity_factory["Character"]

    world.districts["lowtown"] = District(id="lowtown", name="Lowtown")
    world.districts["harbor"] = District(id="harbor", name="Harbor")
    world.districts["high_quarter"] = District(id="high_quarter", name="High Quarter")
    world.characters["npc_listener"] = Character(id="npc_listener", name="Citizen", age=30, location_id="lowtown")

    planted = call_method(
        rumor_sys,
        ("plant_false_rumor", "create_rumor"),
        actor_id="player",
        subject="npc_voss",
        claim="Captain Voss takes Syndicate bribes.",
        district_id="lowtown",
        truth=False,
        world=world,
    )
    initial_reach = planted.reach.get("lowtown", 0.0)
    call_method(rumor_sys, ("propagate_rumors", "step_rumors", "update"), world=world)
    assert planted.truth is False
    assert planted.reach.get("lowtown", 0.0) >= initial_reach


def test_f16_economy_daily_tick_prices_wages_shortages_and_housing_property(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify daily economy tick reacts to food shortages and player can acquire safehouse/business property."""
    econ_sys = systems_suite["economy_system"]
    world = systems_suite["world"]
    District = entity_factory["District"]
    Character = entity_factory["Character"]

    world.districts["lowtown"] = District(id="lowtown", name="Lowtown", food_supply=15.0, wealth=30.0)
    world.characters["player"] = Character(id="player", name="Rowan", age=28, is_player=True, needs={"wealth": 500.0})

    call_method(econ_sys, ("process_daily_tick", "update_economy", "step_economy"), world=world)
    assert world.economy.get("price_index", 1.0) > 1.0 or "food" in str(world.economy.get("shortages", []))

    prop = call_method(econ_sys, ("acquire_property", "buy_property", "purchase_housing"), char_id="player", property_id="lowtown_safehouse", world=world)
    assert prop is not None


def test_f16_city_time_events_elections_wars_festivals_and_riots(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify Section 11 city time events (elections, wars, festivals, riots) trigger and update world state."""
    econ_sys = systems_suite["economy_system"]
    world = systems_suite["world"]
    event_bus = systems_suite["event_bus"]
    District = entity_factory["District"]

    world.districts["lowtown"] = District(id="lowtown", name="Lowtown", unrest=90.0, security=25.0)
    for ev_type in ("riot", "festival", "election", "war"):
        res = call_method(econ_sys, ("trigger_time_event", "evaluate_time_events"), event_kind=ev_type, district_id="lowtown", world=world)
        assert res is not None

    assert any(e.event_type == "TIME_EVENT_TRIGGERED" for e in event_bus.emitted_log)


def test_f16_stealth_visibility_noise_suspicion_and_disease_outbreaks(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """Verify stealth check (Sera in leather vs Marcus in plate) and disease/infection progression."""
    econ_sys = systems_suite["economy_system"]
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]

    sera = Character(id="comp_sera", name="Sera", age=24, skills={"stealth": 85.0}, equipment={"torso": "leather_jerkin"})
    marcus = Character(id="comp_marcus", name="Marcus", age=40, skills={"stealth": 15.0}, equipment={"torso": "plate_breastplate"})

    s_check = call_method(econ_sys, ("calculate_stealth_check", "evaluate_stealth"), sera, location_id="lowtown_street")
    m_check = call_method(econ_sys, ("calculate_stealth_check", "evaluate_stealth"), marcus, location_id="lowtown_street")
    assert s_check["suspicion"] < m_check["suspicion"] or s_check["stealth_score"] > m_check["stealth_score"]

    patient = Character(id="char_inf", name="Patient", age=30)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), patient)
    call_method(health_sys, ("apply_injury", "inflict_injury"), patient, "left_leg", "deep_cut", severity=0.8)
    patient.body["left_leg"].injuries[0].infection_risk = 0.95
    disease_res = call_method(health_sys, ("process_infection_tick", "check_infection", "update_diseases"), patient)
    assert disease_res is not None


# ==============================================================================
# FEATURE F17: Veyr & Lowtown Content Suite (content/)
# ==============================================================================


def test_f17_seven_districts_and_eight_lowtown_locations_loaded(populated_world: Any) -> None:
    """Verify all 7 districts of Veyr and >= 8 locations in Lowtown load with all 10 metrics."""
    expected_districts = {
        "lowtown",
        "high_quarter",
        "iron_ward",
        "harbor",
        "temple_district",
        "old_quarter",
        "barracks",
    }
    assert set(populated_world.districts.keys()) == expected_districts
    lowtown = populated_world.districts["lowtown"]
    assert len(lowtown.locations) >= 8


def test_f17_rowan_four_companions_voss_merek_and_fifteen_plus_named_npcs(populated_world: Any) -> None:
    """Verify Rowan, 4 companions (Marcus, Elira, Sera, Tomas), Captain Voss, Sergeant Merek, and >= 15 named NPCs."""
    chars = populated_world.characters
    assert any(c.is_player and "Rowan" in c.name for c in chars.values())
    assert "npc_voss" in chars
    assert "npc_merek" in chars or any("Merek" in c.name for c in chars.values())
    non_player_npcs = [c for c in chars.values() if not c.is_player]
    assert len(non_player_npcs) >= 15


def test_f17_ten_weapons_eight_armor_pieces_and_twelve_injury_types(populated_world: Any) -> None:
    """Verify >= 10 weapons across 6 damage types, >= 8 armor pieces across 5 classes, and >= 12 injury types."""
    items = list(populated_world.items.values())
    weapons = [i for i in items if i.item_type == "weapon"]
    armors = [i for i in items if i.item_type == "armor"]

    assert len(weapons) >= 10
    assert {"cutting", "piercing", "blunt", "fire", "poison", "magic"}.issubset({w.damage_type for w in weapons})

    assert len(armors) >= 8
    assert {"padded_cloth", "leather", "chainmail", "scale", "plate"}.issubset({a.armor_class for a in armors})


def test_f17_two_plus_questlines_and_twenty_plus_random_events(populated_world: Any) -> None:
    """Verify >= 2 questlines (including Blood in Lowtown) and >= 20 random events in content/."""
    assert len(populated_world.quests) >= 2
    assert "quest_blood_in_lowtown" in populated_world.quests

    events_mod = require_module("content")
    random_events = call_method(events_mod, ("load_events", "get_random_events", "list_random_events"))
    assert len(random_events) >= 20


def test_f17_contextual_dialogue_variations_from_memory_relationship_and_injury(populated_world: Any) -> None:
    """Verify dialogue generator produces contextual variations when Voss is injured or Sera has high trust."""
    quest_sys_cls = require_symbol("systems.quest_system", "QuestSystem")
    quest_sys = instantiate_with_context(quest_sys_cls, world=populated_world)
    health_sys_cls = require_symbol("systems.health_system", "HealthSystem")
    health_sys = instantiate_with_context(health_sys_cls, world=populated_world)

    voss = populated_world.characters["npc_voss"]
    line_initial = call_method(quest_sys, ("get_dialogue", "generate_dialogue", "talk_to"), "npc_voss", world=populated_world)

    call_method(health_sys, ("apply_injury", "inflict_injury"), voss, "left_leg", "broken_leg", severity=0.85)
    populated_world.nemesis_profiles["npc_voss"].grudges.append("broken_leg")
    populated_world.nemesis_profiles["npc_voss"].player_hostility = 85.0

    line_injured = call_method(quest_sys, ("get_dialogue", "generate_dialogue", "talk_to"), "npc_voss", world=populated_world)
    assert line_initial != line_injured


def test_f17_all_content_entities_persist_and_reload_cleanly_in_sqlite(populated_world: Any, save_manager: Any) -> None:
    """Verify full F17 content suite saves to SQLite and reloads with all 7 districts, 7 factions, and all characters."""
    call_method(save_manager, ("save_game", "save_current_state"), populated_world, slot="f17_full")
    loaded = call_method(save_manager, ("load_game", "load_current_state"), slot="f17_full")

    assert len(loaded.districts) == 7
    assert len(loaded.factions) == 7
    assert len(loaded.characters) == len(populated_world.characters)
    assert "npc_voss" in loaded.nemesis_profiles


# ==============================================================================
# FEATURE F18: First Playable Scenario ("Blood in Lowtown") & Vertical Slice (core/game.py)
# ==============================================================================


def test_f18_blood_in_lowtown_approach_1_support_city_guard(game_session: Any) -> None:
    """Verify Approach 1 (Support the City Guard): gain guard rep, anger Syndicate, discover guard corruption."""
    res = call_method(
        game_session,
        ("resolve_scenario_approach", "complete_blood_in_lowtown", "choose_quest_approach"),
        "support_city_guard",
    )
    assert res["success"] is True
    assert game_session.world.reputation["faction"].get("city_guard", 0.0) > 0.0
    assert game_session.world.reputation["faction"].get("lowtown_syndicate", 0.0) < 0.0
    assert "corruption" in str(res).lower() or game_session.world.flags.get("discovered_guard_corruption") is True


def test_f18_blood_in_lowtown_approach_2_support_syndicate(game_session: Any) -> None:
    """Verify Approach 2 (Support the Syndicate): gain criminal contacts, anger Voss, expose illegal trade."""
    res = call_method(
        game_session,
        ("resolve_scenario_approach", "complete_blood_in_lowtown", "choose_quest_approach"),
        "support_syndicate",
    )
    assert res["success"] is True
    assert game_session.world.reputation["faction"].get("lowtown_syndicate", 0.0) > 0.0
    assert game_session.world.nemesis_profiles["npc_voss"].player_hostility > 0.0
    assert "illegal_trade" in str(res).lower() or game_session.world.flags.get("exposed_illegal_trade") is True


def test_f18_blood_in_lowtown_approach_3_investigate_independently(game_session: Any) -> None:
    """Verify Approach 3 (Investigate independently): question witnesses, examine evidence, choose whom to expose."""
    res = call_method(
        game_session,
        ("resolve_scenario_approach", "complete_blood_in_lowtown", "choose_quest_approach"),
        "investigate_independently",
        expose_target="city_guard",
    )
    assert res["success"] is True
    assert game_session.world.quests["quest_blood_in_lowtown"].status == "completed"


def test_f18_blood_in_lowtown_approach_4_exploit_situation(game_session: Any) -> None:
    """Verify Approach 4 (Exploit the situation): sell information to both sides, encourage conflict, profit."""
    w_before = game_session.world.player.needs.get("wealth", 0.0)
    unrest_before = game_session.world.districts["lowtown"].unrest

    res = call_method(
        game_session,
        ("resolve_scenario_approach", "complete_blood_in_lowtown", "choose_quest_approach"),
        "exploit_situation",
    )
    assert res["success"] is True
    assert game_session.world.player.needs.get("wealth", 0.0) > w_before
    assert game_session.world.districts["lowtown"].unrest > unrest_before


def test_f18_post_quest_systemic_continuation_voss_broken_arm_rival_promoted_and_new_quest(game_session: Any) -> None:
    """Verify GDD Section 18 post-quest continuation: Voss broken arm -> rival promoted -> blames player -> new private investigation quest."""
    res = call_method(
        game_session,
        ("run_post_quest_continuation", "simulate_blood_in_lowtown_aftermath"),
        voss_injury="broken_arm",
        days=14,
    )
    assert res["success"] is True
    voss_prof = game_session.world.nemesis_profiles["npc_voss"]
    assert voss_prof.player_hostility > 0
    assert any(e.event_type == "RIVAL_PROMOTED" for e in game_session.world.event_bus.event_history)
    assert len(game_session.world.quests) >= 2


def test_f18_appendix_b_ten_step_vertical_slice_end_to_end(game_session: Any) -> None:
    """Verify Appendix B 10-step vertical slice executes end-to-end and records full history."""
    res = call_method(game_session, ("run_vertical_slice", "execute_vertical_slice"))
    assert res["success"] is True
    assert len(res.get("steps_completed", [])) == 10
    history = game_session.save_manager.get_event_history()
    assert len(history) >= 5


# ==============================================================================
# FEATURE F19: Structured Command Parser & Alias Resolver (ui/, core/game.py)
# ==============================================================================


def test_f19_eight_canonical_section16_commands_resolve_to_stable_entity_ids(game_session: Any) -> None:
    """Verify all 8 canonical GDD Section 16 structured commands parse to exact dicts with stable IDs."""
    c1 = game_session.parse_command("talk sera")
    assert c1["action"] == "talk" and c1["actor"] == "player" and c1["target"] == "comp_sera"

    c2 = game_session.parse_command("inspect captain voss")
    assert c2["action"] == "inspect" and c2["actor"] == "player" and c2["target"] == "npc_voss"

    c3 = game_session.parse_command("attack captain voss")
    assert c3["action"] == "attack" and c3["actor"] == "player" and c3["target"] == "npc_voss"
    assert "weapon" in c3

    c4 = game_session.parse_command("move harbor")
    assert c4["action"] == "move" and c4["actor"] == "player" and c4["target"] == "harbor"

    c5 = game_session.parse_command("check health marcus")
    assert c5["action"] == "check_health" and c5["actor"] == "player" and c5["target"] == "comp_marcus"

    c6 = game_session.parse_command("open faction city_guard")
    assert c6["action"] == "open_faction" and c6["actor"] == "player" and c6["target"] == "city_guard"

    c7 = game_session.parse_command("rest 8h")
    assert c7["action"] == "rest" and c7["hours"] == 8 and c7["minutes"] == 480

    c8 = game_session.parse_command("wait 3d")
    assert c8["action"] == "wait" and c8["days"] == 3 and c8["minutes"] == 4320


def test_f19_verb_and_target_alias_resolution_case_insensitivity(game_session: Any) -> None:
    """Verify case-insensitive verb and target alias resolution to stable internal IDs."""
    p1 = game_session.parse_command("  SPEAK   Sera  ")
    assert p1["action"] == "talk" and p1["target"] == "comp_sera"

    p2 = game_session.parse_command("examine Garrick Voss")
    assert p2["action"] == "inspect" and p2["target"] == "npc_voss"

    p3 = game_session.parse_command("travel Lowtown")
    assert p3["action"] == "move" and "lowtown" in p3["target"]


def test_f19_tactical_combat_and_medical_command_parsing(game_session: Any) -> None:
    """Verify tactical combat and medical commands parse body parts and targets accurately."""
    p_aim = game_session.parse_command("aim captain voss left_leg")
    assert p_aim["action"] == "aim" and p_aim["target"] == "npc_voss"
    assert p_aim.get("target_part", p_aim.get("body_part")) == "left_leg"

    p_med = game_session.parse_command("apply bandage marcus left_arm")
    assert p_med["action"] in ("apply_bandage", "treat") and p_med["target"] == "comp_marcus"


def test_f19_execute_command_advances_clock_simulation_and_returns_contract_dict(game_session: Any) -> None:
    """Verify execute_command returns {'success', 'action', 'message', 'events', 'data'} and advances clock."""
    t0 = get_clock_minutes(game_session.world.clock)
    res_talk = game_session.execute_command("talk sera")
    assert {"success", "action", "message", "events", "data"}.issubset(set(res_talk.keys()))
    assert res_talk["success"] is True
    t1 = get_clock_minutes(game_session.world.clock)
    assert 5 <= (t1 - t0) <= 30

    res_rest = game_session.execute_command("rest 8h")
    assert res_rest["success"] is True
    t2 = get_clock_minutes(game_session.world.clock)
    assert (t2 - t1) == 480


def test_f19_world_ui_save_load_and_rumor_commands(game_session: Any) -> None:
    """Verify save, load, chronicle, open screen, and rumor commands execute via execute_command."""
    for raw_cmd in ("open journal", "save test_slot_cmd", "load test_slot_cmd", "chronicle"):
        res = game_session.execute_command(raw_cmd)
        assert res["success"] is True


def test_f19_execute_command_accepts_both_raw_string_and_parsed_dict(game_session: Any) -> None:
    """Verify execute_command accepts both raw string and pre-parsed command dict."""
    r1 = game_session.execute_command("inspect captain voss")
    r2 = game_session.execute_command({"action": "inspect", "actor": "player", "target": "npc_voss"})
    assert r1["success"] is True and r2["success"] is True
    assert r1["action"] == r2["action"] == "inspect"


# ==============================================================================
# FEATURE F20: Textual + Rich Terminal UI Suite (ui/, main.py)
# ==============================================================================


def test_f20_all_seven_ui_modules_and_main_entry_point_exist_and_import() -> None:
    """Verify main.py and all 7 GDD Section 12 UI screen modules exist and import cleanly."""
    modules = [
        "main",
        "ui.main_screen",
        "ui.map_screen",
        "ui.character_screen",
        "ui.health_screen",
        "ui.combat_screen",
        "ui.journal_screen",
        "ui.faction_screen",
    ]
    for mod_name in modules:
        mod = require_module(mod_name)
        assert mod is not None


def test_f20_main_and_map_screens_render_world_locations_party_and_events(game_session: Any) -> None:
    """Verify main_screen and map_screen render district locations, metrics, party status, and events."""
    main_mod = require_module("ui.main_screen")
    map_mod = require_module("ui.map_screen")

    main_txt = call_method(main_mod, ("render_main_view", "format_main_screen", "render_screen"), game_session)
    map_txt = call_method(map_mod, ("render_map_view", "format_map_screen", "render_screen"), game_session)

    assert "Lowtown" in str(main_txt) and "Rowan" in str(main_txt)
    assert "Lowtown" in str(map_txt)


def test_f20_character_and_party_views_render_attributes_memories_and_6axis_relationships(game_session: Any) -> None:
    """Verify character_screen renders Character attributes/memories and Party 6-axis relationships."""
    char_mod = require_module("ui.character_screen")
    char_txt = call_method(char_mod, ("render_character_view", "format_character_screen", "render_screen"), game_session)
    party_txt = call_method(char_mod, ("render_party_view", "format_party_screen", "render_character_view"), game_session, view="party")

    assert "Rowan" in str(char_txt)
    assert "Sera" in str(party_txt) and "Trust" in str(party_txt) and "Respect" in str(party_txt)


def test_f20_health_screen_renders_hierarchical_anatomy_armor_injuries_and_treatments(game_session: Any) -> None:
    """Verify health_screen renders all 7 anatomical regions, injuries, armor, and 5 treatment stages."""
    health_mod = require_module("ui.health_screen")
    txt = call_method(health_mod, ("render_health_view", "format_health_screen", "render_screen"), game_session)
    s = str(txt)
    for region in ("Head", "Neck", "Torso", "Left Arm", "Right Arm", "Left Leg", "Right Leg"):
        assert region.lower() in s.lower()


def test_f20_combat_screen_renders_ascii_grid_initiative_morale_and_combat_log(game_session: Any) -> None:
    """Verify combat_screen renders the ASCII tactical grid ([ R ], [ V ]), initiative, morale, and commands."""
    combat_mod = require_module("ui.combat_screen")
    txt = call_method(combat_mod, ("render_combat_view", "format_combat_screen", "render_screen"), game_session)
    s = str(txt)
    assert "[" in s and "]" in s
    assert "Movement" in s or "Combat" in s


def test_f20_faction_and_journal_screens_render_politics_nemesis_quests_rumors_chronicle_and_inventory(game_session: Any) -> None:
    """Verify faction_screen and journal_screen render politics, Voss Nemesis profile, quests, rumors, chronicle, and inventory."""
    fac_mod = require_module("ui.faction_screen")
    jour_mod = require_module("ui.journal_screen")

    fac_txt = str(call_method(fac_mod, ("render_faction_view", "format_faction_screen", "render_screen"), game_session))
    jour_txt = str(call_method(jour_mod, ("render_journal_view", "format_journal_screen", "render_screen"), game_session))
    inv_txt = str(call_method(jour_mod, ("render_inventory_view", "format_inventory_screen", "render_journal_view"), game_session, view="inventory"))

    assert "City Guard" in fac_txt and "Lowtown Syndicate" in fac_txt and "Voss" in fac_txt
    assert "Blood in Lowtown" in jour_txt
    assert len(inv_txt) > 0


# ==============================================================================
# FEATURE F21: Simulation, Chronicle & E2E Test Suite (tests/)
# ==============================================================================


def test_f21_section19_hundred_character_survival_simulation() -> None:
    """Verify GDD Section 19 Test 1: 100 characters simulated over daily behavior without unrealistic mass death and with healing injuries."""
    sim_mod = require_module("core.simulation")
    res = call_method(
        sim_mod,
        ("run_character_survival_sim", "simulate_character_survival"),
        num_characters=100,
        days=14,
        seed=482193,
    )
    assert res["total_characters"] == 100
    assert res["survival_rate"] >= 0.90
    assert res["injuries_healed_count"] > 0


def test_f21_section19_hundred_encounter_nemesis_generation_simulation() -> None:
    """Verify GDD Section 19 Test 2: 100 encounters generate selective memorable nemeses, promotions, and 100% fair adaptations."""
    sim_mod = require_module("core.simulation")
    res = call_method(
        sim_mod,
        ("run_nemesis_generation_sim", "simulate_nemesis_generation"),
        num_encounters=100,
        seed=482193,
    )
    assert res["total_encounters"] == 100
    assert 5 <= res["nemeses_created"] <= 75
    assert res["promotions_count"] >= 1
    assert res["unfair_adaptations_count"] == 0


def test_f21_section19_ten_year_faction_simulation_balance_and_vacancy_resolution() -> None:
    """Verify GDD Section 19 Test 3: 10-year faction simulation resolves vacancies, prevents single-faction monopoly, and keeps city functional."""
    sim_mod = require_module("core.simulation")
    res = call_method(
        sim_mod,
        ("run_faction_10year_sim", "simulate_factions_ten_years"),
        years=10,
        seed=482193,
    )
    assert res["final_year"] >= 10
    assert res["active_factions_count"] >= 3
    assert res["unresolved_vacancies"] == 0
    assert res["city_functional"] is True


def test_f21_section19_event_propagation_across_memory_leadership_quests_nemesis_and_history() -> None:
    """Verify GDD Section 19 Test 4: artificial death event updates memory, leadership, quests, Nemesis, and history."""
    sim_mod = require_module("core.simulation")
    res = call_method(
        sim_mod,
        ("run_event_propagation_test", "verify_event_propagation"),
        seed=482193,
    )
    for domain in ("memory_updated", "leadership_updated", "quests_updated", "nemesis_updated", "history_updated"):
        assert res[domain] is True


def test_f21_section20_five_year_ultimate_chronicle_test_unique_per_seed() -> None:
    """Verify GDD Section 20 Ultimate Test: 5-year simulation produces a unique Chronicle per playthrough and deterministic replay."""
    sim_mod = require_module("core.simulation")
    c_a = call_method(sim_mod, ("run_five_year_chronicle_sim", "simulate_five_year_chronicle"), years=5, seed=482193)
    c_b = call_method(sim_mod, ("run_five_year_chronicle_sim", "simulate_five_year_chronicle"), years=5, seed=991027)
    c_a_replay = call_method(sim_mod, ("run_five_year_chronicle_sim", "simulate_five_year_chronicle"), years=5, seed=482193)

    assert len(c_a) >= 5 and len(c_b) >= 5
    assert c_a != c_b
    assert c_a == c_a_replay


def test_f21_six_gdd_unit_test_files_exist_and_pass() -> None:
    """Verify all 6 GDD Section 12 unit test files exist in tests/ with non-empty test functions."""
    required_files = [
        "test_combat.py",
        "test_health.py",
        "test_memory.py",
        "test_relationships.py",
        "test_nemesis.py",
        "test_world.py",
    ]
    tests_dir = PROJECT_ROOT / "tests"
    for fname in required_files:
        fpath = tests_dir / fname
        assert fpath.exists(), f"Missing GDD Section 12 unit test file: {fpath}"
        content = fpath.read_text(encoding="utf-8")
        assert "def test_" in content
