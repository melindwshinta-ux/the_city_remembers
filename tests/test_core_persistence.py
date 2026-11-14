"""Comprehensive unit tests for Milestone M1: Core Simulation, Entities & SQLite Persistence (F1-F7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config import (
    ACT_I,
    ACT_II,
    ACT_III,
    ACT_PROLOGUE,
    CANONICAL_EVENT_TYPES,
    DEFAULT_WORLD_SEED,
    EVENT_CHARACTER_DIED,
    EVENT_DISTRICT_INFLUENCE_CHANGED,
    EVENT_LEADERSHIP_VACANCY,
    EVENT_LIMB_INJURED,
    EVENT_NEMESIS_ADAPTED,
    EVENT_NEMESIS_CREATED,
    EVENT_POLITICAL_CONFLICT_STARTED,
    EVENT_QUEST_COMPLETED,
    EVENT_RIVAL_PROMOTED,
    EVENT_RUMOR_SPREAD,
    FREQ_COMBAT,
    FREQ_COMPANIONS,
    FREQ_DISTRICT_POPULATION,
    FREQ_ECONOMY,
    FREQ_FACTION_DECISIONS,
    FREQ_LONG_TERM_AMBITIONS,
    FREQ_NEARBY_NPCS,
    MINUTES_PER_DAY,
    MINUTES_PER_MONTH,
    MINUTES_PER_WEEK,
    MINUTES_PER_YEAR,
    RNG_STREAMS,
)
from core import (
    EventBus,
    EventPriority,
    GameEvent,
    SeededRNG,
    SimulationEngine,
    World,
    WorldClock,
)
from entities import (
    CANONICAL_COMPANIONS,
    HUMANOID_ANATOMY_SPEC,
    BodyPart,
    Character,
    Companion,
    CompanionProfile,
    District,
    Enemy,
    EnemyCombatant,
    Faction,
    Injury,
    InventoryEntry,
    Item,
    Location,
    Memory,
    NemesisProfile,
    Quest,
    Relationship,
    Rumor,
    create_humanoid_body,
)
from persistence import (
    CURRENT_SCHEMA_VERSION,
    REQUIRED_TABLES,
    Database,
    DatabaseError,
    MigrationError,
    MigrationManager,
    NewerSaveVersionError,
    SaveCorruptedError,
    SaveManager,
    SaveNotFoundError,
)


# ==============================================================================
# F1: Campaign Timeline & WorldClock Tests
# ==============================================================================


def test_world_clock_initial_state_and_properties() -> None:
    clock = WorldClock()
    assert clock.timestamp == 0
    assert clock.total_minutes == 0
    assert clock.year == 1
    assert clock.month == 1
    assert clock.week == 1
    assert clock.day == 1
    assert clock.day_of_year == 1
    assert clock.hour == 8
    assert clock.minute == 0
    assert clock.act == ACT_PROLOGUE
    assert clock.act_theme == "Arrival and survival"
    assert "Year 1" in clock.format_date()
    assert "Prologue" in clock.format_date()


def test_world_clock_threshold_crossings_and_act_transitions() -> None:
    clock = WorldClock()

    # Small action (5 minutes): 08:00 -> 08:05
    crossed = clock.advance(5)
    assert crossed == ["action", "time_update"]
    assert clock.hour == 8
    assert clock.minute == 5

    # Advance to cross 12:00 (6h boundary from 08:05 is 235m -> 12:00)
    crossed_6h = clock.advance(235)
    assert "6h" in crossed_6h
    assert "daily" not in crossed_6h
    assert clock.hour == 12
    assert clock.minute == 0

    # Advance 12 hours to midnight (Day 2, 00:00) -> crosses 6h and daily
    crossed_daily = clock.advance_hours(12)
    assert "6h" in crossed_daily
    assert "daily" in crossed_daily
    assert clock.day == 2
    assert clock.hour == 0

    # Complete Prologue -> transitions to Act I
    assert clock.act == ACT_PROLOGUE
    clock.complete_prologue()
    assert clock.act == ACT_I

    # Advance 1 week -> crosses weekly
    crossed_weekly = clock.advance_weeks(1)
    assert "weekly" in crossed_weekly
    assert "daily" in crossed_weekly
    assert "6h" in crossed_weekly

    # Advance 1 month -> crosses monthly
    crossed_monthly = clock.advance(MINUTES_PER_MONTH)
    assert "monthly" in crossed_monthly

    # Advance 3 years into Year 4 -> transitions to Act II
    crossed_years = clock.advance_years(3)
    assert "yearly" in crossed_years
    assert clock.year == 4
    assert clock.act == ACT_II

    # Advance 3 more years into Year 7 -> transitions to Act III
    clock.advance_years(3)
    assert clock.year == 7
    assert clock.act == ACT_III

    # Serialization round-trip
    restored = WorldClock.from_dict(clock.to_dict())
    assert restored == clock
    assert restored.year == 7
    assert restored.act == ACT_III


def test_world_clock_action_durations_and_negative_validation() -> None:
    rng = SeededRNG(DEFAULT_WORLD_SEED).stream("world")
    assert 1 <= WorldClock.get_action_duration("small_action", rng) <= 10
    assert 5 <= WorldClock.get_action_duration("conversation", rng) <= 30
    assert 1 <= WorldClock.get_action_duration("combat", rng) <= 5
    assert 360 <= WorldClock.get_action_duration("rest", rng) <= 720
    assert 1440 <= WorldClock.get_action_duration("major_project", rng) <= 20160

    # Travel duration increases with distance and leg injury penalty
    base_travel = WorldClock.calculate_travel_duration(distance=2, condition_modifier=1.0, leg_injury_penalty=0.0)
    injured_travel = WorldClock.calculate_travel_duration(distance=2, condition_modifier=1.0, leg_injury_penalty=0.5)
    assert base_travel == 20
    assert injured_travel == 30

    clock = WorldClock()
    with pytest.raises(ValueError, match="negative"):
        clock.advance(-10)


# ==============================================================================
# F4: Seeded Multi-Stream RNG Tests
# ==============================================================================


def test_seeded_rng_determinism_stream_isolation_and_state_roundtrip() -> None:
    rng1 = SeededRNG(DEFAULT_WORLD_SEED)
    rng2 = SeededRNG(DEFAULT_WORLD_SEED)

    # All 11 required streams are initialized and reproducible
    for stream_name in RNG_STREAMS:
        assert rng1.randint(stream_name, 1, 100000) == rng2.randint(stream_name, 1, 100000)

    # Stream isolation: 1,000 draws on "combat" must NEVER affect "faction" or "nemesis"
    for _ in range(1000):
        rng1.random("combat")

    assert rng1.randint("faction", 1, 1000000) == rng2.randint("faction", 1, 1000000)
    assert rng1.randint("nemesis", 1, 1000000) == rng2.randint("nemesis", 1, 1000000)
    assert rng1.randint("world", 1, 1000000) == rng2.randint("world", 1, 1000000)

    # Set-sorting determinism in choice()
    options_set = {"lowtown", "harbor", "high_quarter", "iron_ward", "temple_district"}
    picks_1 = [rng1.choice("world", options_set) for _ in range(20)]
    picks_2 = [rng2.choice("world", options_set) for _ in range(20)]
    assert picks_1 == picks_2

    # Weighted pick determinism
    loot_table = [("common", 70.0), ("rare", 25.0), ("legendary", 5.0)]
    w_picks_1 = [rng1.weighted_pick("economy", loot_table) for _ in range(30)]
    w_picks_2 = [rng2.weighted_pick("economy", loot_table) for _ in range(30)]
    assert w_picks_1 == w_picks_2

    # JSON state persistence round-trip
    json_state_str = json.dumps(rng1.get_state())
    restored_rng = SeededRNG(999999)
    restored_rng.set_state(json.loads(json_state_str))
    assert restored_rng.master_seed == DEFAULT_WORLD_SEED
    for stream_name in RNG_STREAMS:
        assert restored_rng.random(stream_name) == rng1.random(stream_name)


# ==============================================================================
# F2: Priority Event Bus Tests
# ==============================================================================


def test_event_bus_priorities_and_three_stage_consequence_propagation() -> None:
    bus = EventBus()
    execution_order: list[str] = []

    # Exact GDD Section 13 (lines 599-612) GameEvent instantiation
    limb_event = GameEvent(
        id="event_001",
        event_type="LIMB_INJURED",
        timestamp=120,
        source_id="player",
        target_ids=["npc_00192"],
        location_id="lowtown_street",
        data={
            "body_part": "left_leg",
            "injury": "compound_fracture",
            "weapon": "warhammer",
        },
        importance=0.8,
    )
    assert limb_event.to_dict()["data"]["weapon"] == "warhammer"
    assert GameEvent.from_dict(limb_event.to_dict()) == limb_event

    # Subscribe consequence chain matching GDD Section 14 diagram (lines 618-641):
    # LIMB_INJURED -> LEADERSHIP_VACANCY -> RIVAL_PROMOTED -> POLITICAL_CONFLICT_STARTED
    def on_limb_injured(ev: GameEvent) -> GameEvent:
        execution_order.append(ev.event_type)
        return GameEvent(
            id="event_002",
            event_type=EVENT_LEADERSHIP_VACANCY,
            timestamp=ev.timestamp,
            source_id="city_guard",
            target_ids=ev.target_ids,
            location_id=ev.location_id,
            data={"reason": "voss_absent_from_duty"},
            importance=0.75,
        )

    def on_vacancy(ev: GameEvent) -> GameEvent:
        execution_order.append(ev.event_type)
        return GameEvent(
            id="event_003",
            event_type=EVENT_RIVAL_PROMOTED,
            timestamp=ev.timestamp,
            source_id="city_guard",
            target_ids=["npc_merek"],
            location_id=ev.location_id,
            data={"new_rank": "captain"},
            importance=0.8,
        )

    def on_rival_promoted(ev: GameEvent) -> GameEvent:
        execution_order.append(ev.event_type)
        return GameEvent(
            id="event_004",
            event_type=EVENT_POLITICAL_CONFLICT_STARTED,
            timestamp=ev.timestamp,
            source_id="npc_00192",
            target_ids=["npc_merek"],
            location_id=ev.location_id,
            data={"conflict": "guard_command_rivalry"},
            importance=0.85,
        )

    def on_conflict(ev: GameEvent) -> None:
        execution_order.append(ev.event_type)

    bus.subscribe(EVENT_LIMB_INJURED, on_limb_injured)
    bus.subscribe(EVENT_LEADERSHIP_VACANCY, on_vacancy)
    bus.subscribe(EVENT_RIVAL_PROMOTED, on_rival_promoted)
    bus.subscribe(EVENT_POLITICAL_CONFLICT_STARTED, on_conflict)

    # Emit CRITICAL event -> processes immediately along with its consequence chain
    processed = bus.emit(limb_event, priority=EventPriority.CRITICAL)
    assert [e.event_type for e in processed] == [
        EVENT_LIMB_INJURED,
        EVENT_LEADERSHIP_VACANCY,
        EVENT_RIVAL_PROMOTED,
        EVENT_POLITICAL_CONFLICT_STARTED,
    ]
    assert execution_order == [
        EVENT_LIMB_INJURED,
        EVENT_LEADERSHIP_VACANCY,
        EVENT_RIVAL_PROMOTED,
        EVENT_POLITICAL_CONFLICT_STARTED,
    ]

    # NORMAL event queues until process_tick_events()
    normal_ran: list[str] = []
    bus.subscribe("QUEST_STARTED", lambda ev: normal_ran.append(ev.id))
    q_ev = bus.create_event("QUEST_STARTED", timestamp=130, priority=EventPriority.NORMAL)
    assert bus.emit(q_ev) == []
    assert normal_ran == []
    assert bus.pending_normal_count == 1
    bus.process_tick_events()
    assert normal_ran == [q_ev.id]
    assert bus.pending_normal_count == 0

    # BACKGROUND event queues until process_background_events()
    bg_ran: list[str] = []
    bus.subscribe("ECONOMY_UPDATED", lambda ev: bg_ran.append(ev.id))
    bg_ev = bus.create_event("ECONOMY_UPDATED", timestamp=1440, priority=EventPriority.BACKGROUND)
    assert bus.emit(bg_ev) == []
    bus.process_tick_events()
    assert bg_ran == []
    assert bus.pending_background_count == 1
    bus.process_background_events()
    assert bg_ran == [bg_ev.id]
    assert bus.pending_background_count == 0


def test_event_bus_recursion_limit_guard() -> None:
    bus = EventBus(max_depth=5)
    call_count = 0

    def infinite_loop_handler(ev: GameEvent) -> GameEvent:
        nonlocal call_count
        call_count += 1
        return GameEvent(
            id=f"loop_{call_count}",
            event_type="LOOP_EVENT",
            timestamp=ev.timestamp,
            priority="critical",
        )

    bus.subscribe("LOOP_EVENT", infinite_loop_handler)
    trigger = GameEvent(id="loop_0", event_type="LOOP_EVENT", timestamp=10, priority="critical")
    processed = bus.emit(trigger)
    # Depth 0..5 -> 6 events total, stopping cleanly without RecursionError
    assert call_count == 6
    assert len(processed) == 6


# ==============================================================================
# F3: Multi-Frequency Simulation Scheduler & Time-Skip Sub-Stepping Tests
# ==============================================================================


def test_simulation_engine_frequencies_and_time_skip_substepping() -> None:
    world = World(seed=DEFAULT_WORLD_SEED)
    sim = SimulationEngine(world)

    counts = {
        FREQ_COMBAT: 0,
        FREQ_COMPANIONS: 0,
        FREQ_NEARBY_NPCS: 0,
        FREQ_FACTION_DECISIONS: 0,
        FREQ_ECONOMY: 0,
        FREQ_DISTRICT_POPULATION: 0,
        FREQ_LONG_TERM_AMBITIONS: 0,
    }

    for freq in counts:
        sim.register_system(freq, lambda w, mins, f=freq: counts.__setitem__(f, counts[f] + 1))

    # 1. Combat action tick (0 minutes, in_combat=True)
    sim.run_action_tick(meaningful=True, in_combat=True, minutes=0)
    assert counts[FREQ_COMBAT] == 1
    assert counts[FREQ_COMPANIONS] == 1
    assert counts[FREQ_NEARBY_NPCS] == 0

    # 2. Rest 8 hours (480 minutes): sub-steps into 360m + 120m (2 steps)
    sim.advance_time(480)
    assert counts[FREQ_NEARBY_NPCS] == 2
    assert counts[FREQ_FACTION_DECISIONS] == 1  # Crossed 12:00 6h mark

    # 3. Wait 3 days (4320 minutes = 72 hours = 12 * 6h): sub-steps into 12 chunks of 360m
    before_factions = counts[FREQ_FACTION_DECISIONS]
    before_economy = counts[FREQ_ECONOMY]
    sim.advance_time(3 * MINUTES_PER_DAY)
    assert counts[FREQ_FACTION_DECISIONS] - before_factions == 12
    assert counts[FREQ_ECONOMY] - before_economy == 3

    # 4. Advance 1 full week (10080 minutes = 28 * 6h = 7 days)
    before_pop = counts[FREQ_DISTRICT_POPULATION]
    before_amb = counts[FREQ_LONG_TERM_AMBITIONS]
    sim.advance_time(MINUTES_PER_WEEK)
    assert counts[FREQ_DISTRICT_POPULATION] - before_pop == 1
    assert counts[FREQ_LONG_TERM_AMBITIONS] - before_amb >= 1


# ==============================================================================
# F5: Entities Dataclasses, 29-Part Anatomy, District Influence & World Lookups
# ==============================================================================


def test_entities_section_13_instantiation_anatomy_and_serialization() -> None:
    # 1. 7-region / 30-subpart (37 total BodyPart nodes >= 29) humanoid anatomy
    body = create_humanoid_body("player")
    assert len(body) == 37
    assert len(HUMANOID_ANATOMY_SPEC) == 37
    top_regions = [k for k, bp in body.items() if bp.parent_key is None]
    assert set(top_regions) == {"head", "neck", "torso", "left_arm", "right_arm", "left_leg", "right_leg"}
    subparts = [k for k, bp in body.items() if bp.parent_key is not None]
    assert len(subparts) == 30
    vital_parts = {k for k, bp in body.items() if bp.vital}
    assert vital_parts == {"brain", "throat", "cervical_spine", "heart", "lungs"}

    # 2. Injury & BodyPart
    inj = Injury("inj_001", "compound_fracture", 0.85, 65.0, 20.0, 0.35, 0.0, True)
    body["left_leg"].injuries.append(inj)
    body["left_leg"].integrity = 35.0
    body["left_leg"].functional = False
    assert BodyPart.from_dict(body["left_leg"].to_dict()) == body["left_leg"]

    # 3. Memory & Relationship (exact Section 13 positional arguments)
    mem = Memory(
        "mem_001",
        "PRISON_RESCUE",
        ["player", "comp_sera"],
        "[Year 1] Player rescued Sera from prison.",
        "lowtown_prison",
        0.9,
        0.85,
        1.0,
        60,
        0.0,
        emotion="Gratitude",
    )
    assert mem.emotion_label == "Gratitude"
    assert Memory.from_dict(mem.to_dict()) == mem

    rel = Relationship(
        "comp_sera",
        "player",
        70.0,
        85.0,
        45.0,
        10.0,
        0.0,
        ["mem_001"],
        dependency=30.0,
        relationship_state="Loyal associate",
    )
    assert Relationship.from_dict(rel.to_dict()) == rel

    # 4. Character (exact Section 13 fields)
    sera_char = Character(
        id="comp_sera",
        name="Sera",
        age=24,
        faction_id="lowtown_syndicate",
        attributes={"dexterity": 16, "perception": 15},
        skills={"stealth": 80.0, "dual_wielding": 75.0},
        personality={"courage": 65.0, "compassion": 40.0},
        needs={"hunger": 10.0, "fatigue": 15.0, "safety": 60.0},
        body=body,
        memories=[mem],
        relationships={"player": rel},
        ambitions=["escape_syndicate_past"],
        location_id="lowtown_market",
        status="alive",
        is_player=False,
        is_companion=True,
        is_nemesis=False,
    )
    assert Character.from_dict(sera_char.to_dict()) == sera_char

    # 5. CompanionProfile & CANONICAL_COMPANIONS
    assert set(CANONICAL_COMPANIONS.keys()) == {"comp_marcus", "comp_elira", "comp_sera", "comp_tomas"}
    comp = CompanionProfile.from_dict(CANONICAL_COMPANIONS["comp_sera"])
    assert isinstance(comp, Companion)
    assert CompanionProfile.from_dict(comp.to_dict()) == comp

    # 6. NemesisProfile & EnemyCombatant (GDD Section 7 Captain Garrick Voss)
    voss_nem = NemesisProfile(
        character_id="npc_voss",
        player_hostility=80.0,
        player_respect=45.0,
        encounter_count=2,
        known_player_tactics=["fire_magic", "flanking"],
        grudges=["Player scarred his face", "Killed his lieutenant", "Humiliated him publicly"],
        career_history=[{"year": 1, "rank": "captain", "event": "Assigned to Lowtown"}],
        last_encounter_date=120,
        current_ambition="Become Commander of the City Guard",
        special_traits=["counterattacker"],
        strengths=["Shield defense", "Heavy armor", "Guard support"],
        weaknesses=["Fire", "Poor ranged defense"],
        rank="captain",
        status="active",
    )
    assert NemesisProfile.from_dict(voss_nem.to_dict()) == voss_nem

    enemy = EnemyCombatant(
        character_id="npc_voss",
        archetype="commander",
        rank="captain",
        morale=80.0,
        morale_state="confident",
        nemesis_profile=voss_nem,
    )
    assert isinstance(enemy, Enemy)
    assert EnemyCombatant.from_dict(enemy.to_dict()) == enemy

    # 7. Faction (GDD Section 8 & Section 13)
    guard_faction = Faction(
        id="city_guard",
        name="City Guard",
        leader_id="npc_commander_vael",
        wealth=70.0,
        influence=65.0,
        military_strength=85.0,
        stability=60.0,
        territories=["barracks", "high_quarter"],
        members=["npc_voss", "npc_merek"],
        goals=[{"type": "maintain_authority", "district": "lowtown"}],
        relations={"lowtown_syndicate": -75.0, "noble_houses": 45.0},
        power=75.0,
        public_legitimacy=55.0,
        goal_summary="Maintain authority",
        methods=["arrests", "patrols", "force"],
    )
    assert Faction.from_dict(guard_faction.to_dict()) == guard_faction

    # 8. District influence normalization (GDD Section 8 Lowtown exact percentages)
    lowtown = District(
        id="lowtown",
        name="Lowtown",
        characteristics="Poor, crowded, criminal activity",
        major_conflict="Gang warfare",
        faction_influence={
            "lowtown_syndicate": 48.0,
            "city_guard": 22.0,
            "merchant_consortium": 12.0,
            "iron_workers_union": 10.0,
            "independent": 8.0,
        },
    )
    norm = lowtown.normalize_influence()
    assert round(sum(norm.values()), 4) == 100.0
    assert norm["lowtown_syndicate"] == 48.0

    # Unnormalized weights scale cleanly to 100.0%
    unbalanced = District(
        id="harbor",
        name="Harbor",
        faction_influence={"merchant_consortium": 30.0, "lowtown_syndicate": 20.0},
    )
    norm2 = unbalanced.normalize_influence()
    assert round(sum(norm2.values()), 4) == 100.0
    assert norm2["merchant_consortium"] == 60.0
    assert norm2["lowtown_syndicate"] == 40.0

    # 9. Item, InventoryEntry, Quest, Rumor
    sword = Item(
        id="longsword",
        name="Longsword",
        item_type="weapon",
        damage=18.0,
        damage_type="cutting",
        penetration=6.0,
    )
    assert Item.from_dict(sword.to_dict()) == sword

    inv = InventoryEntry(character_id="player", item_id="longsword", quantity=1, equipped=True, slot="main_hand")
    assert InventoryEntry.from_dict(inv.to_dict()) == inv

    quest = Quest(
        id="quest_blood_in_lowtown",
        title="Blood in Lowtown",
        status="active",
        objectives=[{"id": "inspect_murder", "done": False}],
        conditions={"voss_alive": True},
        involved_characters=["player", "comp_sera", "npc_voss"],
        involved_factions=["city_guard", "lowtown_syndicate"],
        consequences=[{"type": "faction_shift"}],
        quest_type="authored",
    )
    assert Quest.from_dict(quest.to_dict()) == quest

    rumor = Rumor(
        id="rumor_00492",
        subject="player",
        claim="Rowan murdered a City Guard officer.",
        origin="npc_0091",
        truth=False,
        reach={"lowtown": 35.0, "harbor": 12.0, "high_quarter": 3.0},
        confidence=47.0,
    )
    assert Rumor.from_dict(rumor.to_dict()) == rumor


# ==============================================================================
# F6 & F7: SQLite 15-Table Schema, Migrations, SaveManager, Snapshots & Chronicle
# ==============================================================================


def _build_populated_test_world() -> World:
    """Create a rich World populating all 15 SQLite tables for persistence verification."""
    world = World(seed=DEFAULT_WORLD_SEED)
    world.clock.advance(180)  # Year 1, Day 1, 11:00
    world.rng.randint("combat", 1, 100)
    world.rng.randint("faction", 1, 100)

    # District & Locations
    lowtown = District(
        id="lowtown",
        name="Lowtown",
        characteristics="Poor, crowded, criminal activity",
        major_conflict="Gang warfare",
        population=12500,
        wealth=22.0,
        security=25.0,
        unrest=78.0,
        faction_influence={
            "lowtown_syndicate": 48.0,
            "city_guard": 22.0,
            "merchant_consortium": 12.0,
            "iron_workers_union": 10.0,
            "independent": 8.0,
        },
        food_supply=55.0,
        employment=45.0,
        crime=85.0,
        public_opinion=32.0,
        infrastructure_condition=40.0,
    )
    world.add_district(lowtown)
    world.add_location(
        Location(
            id="lowtown_market",
            name="Lowtown Market",
            district_id="lowtown",
            description="Crowded stalls under leaky tarps.",
            connected_locations=["lowtown_docks"],
            terrain_features=["cover", "narrow_passage"],
            npcs_present=["npc_voss", "comp_sera"],
        )
    )

    # Factions
    world.add_faction(
        Faction(
            id="city_guard",
            name="City Guard",
            leader_id="npc_voss",
            wealth=65.0,
            influence=55.0,
            military_strength=80.0,
            stability=60.0,
            territories=["barracks"],
            members=["npc_voss"],
            goals=[{"type": "patrol_lowtown"}],
            relations={"lowtown_syndicate": -70.0},
            power=72.0,
            public_legitimacy=50.0,
            goal_summary="Maintain authority",
            methods=["arrests", "patrols", "force"],
            hierarchy={"captain": ["npc_voss"]},
        )
    )
    world.add_faction(
        Faction(
            id="lowtown_syndicate",
            name="Lowtown Syndicate",
            leader_id="npc_ren",
            wealth=60.0,
            influence=70.0,
            military_strength=50.0,
            stability=65.0,
            territories=["lowtown"],
            members=["comp_sera"],
            goals=[{"type": "control_underworld"}],
            relations={"city_guard": -70.0},
            power=64.0,
            public_legitimacy=30.0,
            goal_summary="Control the underworld",
            methods=["smuggling", "extortion"],
        )
    )

    # Characters (Player, Companion Sera, Nemesis Captain Voss)
    player_body = create_humanoid_body("player")
    player = Character(
        id="player",
        name="Rowan",
        age=27,
        faction_id=None,
        attributes={"strength": 14, "dexterity": 14, "intelligence": 13},
        skills={"swordsmanship": 60.0, "negotiation": 50.0},
        personality={"courage": 70.0, "compassion": 60.0},
        needs={"hunger": 15.0, "fatigue": 20.0},
        body=player_body,
        location_id="lowtown_market",
        is_player=True,
    )
    world.add_character(player)

    sera_body = create_humanoid_body("comp_sera")
    sera = Character(
        id="comp_sera",
        name="Sera",
        age=24,
        faction_id="lowtown_syndicate",
        body=sera_body,
        memories=[
            Memory(
                id="mem_sera_1",
                event_type="PRISON_RESCUE",
                participants=["player", "comp_sera"],
                description="Player rescued Sera from prison.",
                location_id="lowtown_market",
                importance=0.9,
                emotional_valence=0.8,
                confidence=1.0,
                created_at=60,
                emotion="Gratitude",
            )
        ],
        relationships={
            "player": Relationship(
                source_id="comp_sera",
                target_id="player",
                trust=70.0,
                respect=85.0,
                affection=45.0,
                resentment=10.0,
                fear=0.0,
                shared_memories=["mem_sera_1"],
                dependency=30.0,
                relationship_state="Loyal associate",
                friendship_score=50.0,
                rivalry_score=15.0,
            )
        },
        location_id="lowtown_market",
        is_companion=True,
    )
    world.add_character(sera)
    world.add_companion(CompanionProfile.from_dict(CANONICAL_COMPANIONS["comp_sera"]))

    voss_body = create_humanoid_body("npc_voss")
    voss_body["left_leg"].integrity = 40.0
    voss_body["left_leg"].functional = False
    voss_body["left_leg"].injuries.append(
        Injury(
            id="inj_voss_leg",
            injury_type="compound_fracture",
            severity=0.85,
            pain=60.0,
            bleeding=15.0,
            infection_risk=0.25,
            recovery_progress=0.1,
            permanent=False,
            created_at=120,
            cause_description="Struck by Rowan's warhammer",
            body_part_id="left_leg",
            part_key="left_leg",
            character_id="npc_voss",
        )
    )
    voss = Character(
        id="npc_voss",
        name="Captain Garrick Voss",
        age=38,
        faction_id="city_guard",
        rank="captain",
        body=voss_body,
        location_id="lowtown_market",
        is_nemesis=True,
    )
    world.add_character(voss)
    world.add_nemesis(
        NemesisProfile(
            character_id="npc_voss",
            player_hostility=75.0,
            player_respect=40.0,
            encounter_count=1,
            known_player_tactics=["heavy_weapons"],
            grudges=["Broken left leg in Lowtown"],
            career_history=[{"year": 1, "rank": "captain"}],
            last_encounter_date=120,
            current_ambition="Become Commander of the City Guard",
            special_traits=["disciplined"],
            strengths=["Shield defense", "Heavy armor"],
            weaknesses=["Fire", "Poor ranged defense"],
            rank="captain",
            faction_id="city_guard",
            status="active",
        )
    )

    # Items & Inventory
    world.add_item(
        Item(
            id="warhammer",
            name="Iron Warhammer",
            item_type="weapon",
            weight=4.5,
            value=45.0,
            damage=22.0,
            damage_type="blunt",
            penetration=12.0,
        )
    )
    world.add_item(
        Item(
            id="chainmail_hauberk",
            name="Chainmail Hauberk",
            item_type="armor",
            armor_class="chainmail",
            armor_protection=14.0,
            covered_parts=["torso", "left_arm", "right_arm"],
            protection={"cutting": 16.0, "piercing": 10.0, "blunt": 6.0},
            weaknesses=["blunt"],
        )
    )
    world.add_inventory_entry(
        InventoryEntry(character_id="player", item_id="warhammer", quantity=1, equipped=True, slot="main_hand")
    )
    world.add_inventory_entry(
        InventoryEntry(character_id="player", item_id="chainmail_hauberk", quantity=1, equipped=True, slot="torso")
    )

    # Quest & Rumor
    world.add_quest(
        Quest(
            id="quest_blood_in_lowtown",
            title="Blood in Lowtown",
            status="active",
            objectives=[{"id": "confront_voss", "completed": True}],
            conditions={"merchant_dead": True},
            involved_characters=["player", "comp_sera", "npc_voss"],
            involved_factions=["city_guard", "lowtown_syndicate"],
            consequences=[{"type": "voss_injured"}],
            quest_type="authored",
            description="Investigate the murdered merchant in Lowtown.",
            selected_approach="investigate_independently",
        )
    )
    world.add_rumor(
        Rumor(
            id="rumor_00492",
            subject="player",
            claim="Rowan shattered Captain Voss's leg in Lowtown Market.",
            origin="comp_sera",
            truth=True,
            reach={"lowtown": 45.0, "barracks": 25.0},
            confidence=80.0,
        )
    )

    # Event on EventBus
    ev = GameEvent(
        id="event_001",
        event_type=EVENT_LIMB_INJURED,
        timestamp=120,
        source_id="player",
        target_ids=["npc_voss"],
        location_id="lowtown_market",
        data={
            "body_part": "left_leg",
            "injury": "compound_fracture",
            "weapon": "warhammer",
        },
        importance=0.85,
    )
    world.event_bus.emit(ev, priority=EventPriority.CRITICAL)
    return world


def test_database_15_required_tables_and_migrations() -> None:
    db = Database(":memory:")
    assert db.verify_required_tables() is True
    existing_tables = set(db.list_tables())
    for required in REQUIRED_TABLES:
        assert required in existing_tables, f"Missing required SQLite table: {required}"

    mgr = MigrationManager(db)
    assert mgr.get_current_version() == CURRENT_SCHEMA_VERSION
    validation = mgr.validate_schema()
    assert validation["valid"] is True
    assert validation["missing_tables"] == []
    assert validation["fk_violations"] == []

    # Test forward migration v1 -> v2 and idempotency
    mgr.register_migration(
        1,
        2,
        lambda conn: conn.execute("ALTER TABLE world_state ADD COLUMN test_migration_flag INTEGER DEFAULT 0;"),
        description="Add test_migration_flag to world_state",
    )
    assert mgr.migrate(target_version=2) == 2
    assert mgr.get_current_version() == 2
    assert mgr.migrate(target_version=2) == 2  # idempotent

    # Attempting to migrate down / load newer save version raises NewerSaveVersionError
    with pytest.raises(NewerSaveVersionError):
        mgr.migrate(target_version=1)

    db.close()


def test_save_manager_full_15_table_roundtrip_and_file_backup(tmp_path: Path) -> None:
    db_file = tmp_path / "veyr_test.db"
    save_mgr = SaveManager(db_file)
    world = _build_populated_test_world()

    # Verify entity alias lookups on World before save
    assert world.find_character_by_name_or_alias("sera") == world.characters["comp_sera"]
    assert world.find_character_by_name_or_alias("captain voss") == world.characters["npc_voss"]
    assert world.find_faction_by_name_or_alias("city guard") == world.factions["city_guard"]
    assert world.find_location_or_district("lowtown market") == world.locations["lowtown_market"]

    # Save game
    save_mgr.save_game(world, slot="default")

    # Verify all 15 required SQLite tables contain >= 1 row
    counts = save_mgr.db.table_row_counts()
    for tbl_name in REQUIRED_TABLES:
        assert counts[tbl_name] >= 1, f"Expected table '{tbl_name}' to have rows, got {counts[tbl_name]}"

    # Save a second time to trigger .bak file creation
    save_mgr.save_game(world, slot="default")
    assert Path(f"{db_file}.bak").exists()

    # Load game from relational tables
    loaded = save_mgr.load_game(slot="default")
    assert loaded.seed == world.seed
    assert loaded.clock == world.clock
    assert set(loaded.characters.keys()) == {"player", "comp_sera", "npc_voss"}
    assert loaded.characters["npc_voss"].body["left_leg"].functional is False
    assert loaded.characters["npc_voss"].body["left_leg"].injuries[0].injury_type == "compound_fracture"
    assert loaded.characters["comp_sera"].memories[0].emotion == "Gratitude"
    assert loaded.characters["comp_sera"].relationships["player"].trust == 70.0
    assert loaded.companions["comp_sera"].friendship == 50.0
    assert loaded.nemesis_profiles["npc_voss"].player_hostility == 75.0
    assert loaded.districts["lowtown"].faction_influence["lowtown_syndicate"] == 48.0
    assert loaded.factions["city_guard"].relations["lowtown_syndicate"] == -70.0
    assert len(loaded.get_inventory("player")) == 2
    assert loaded.quests["quest_blood_in_lowtown"].selected_approach == "investigate_independently"
    assert loaded.rumors["rumor_00492"].confidence == 80.0

    # Verify RNG state continues identically after load
    assert loaded.rng.randint("combat", 1, 100000) == world.rng.randint("combat", 1, 100000)
    assert loaded.rng.randint("faction", 1, 100000) == world.rng.randint("faction", 1, 100000)

    save_mgr.db.close()


def test_save_manager_multi_slot_and_append_only_event_history() -> None:
    save_mgr = SaveManager(":memory:")
    world = _build_populated_test_world()

    # Hook EventBus persistence listener to SaveManager.append_event
    world.event_bus.register_persistence_listener(save_mgr.append_event)

    save_mgr.save_game(world, slot="slot_a")

    # Advance world and emit new events in slot_b
    world.clock.advance_days(5)
    world.districts["lowtown"].unrest = 92.0
    ev2 = world.event_bus.create_event(
        event_type=EVENT_NEMESIS_CREATED,
        timestamp=world.clock.timestamp,
        source_id="player",
        target_ids=["npc_voss"],
        location_id="lowtown_market",
        data={"rank": "captain"},
        importance=0.9,
        priority=EventPriority.CRITICAL,
    )
    world.event_bus.emit(ev2)
    save_mgr.save_game(world, slot="slot_b")

    # Append-only event history preserves both events across saves
    history = save_mgr.get_event_history(min_importance=0.5)
    assert len(history) == 2
    assert [e.event_type for e in history] == [EVENT_LIMB_INJURED, EVENT_NEMESIS_CREATED]
    assert len(save_mgr.get_event_history(character_id="npc_voss")) == 2
    assert len(save_mgr.get_event_history(event_type=EVENT_NEMESIS_CREATED)) == 1

    # Loading slot_a restores slot_a's unrest and timestamp while keeping event history
    loaded_a = save_mgr.load_game(slot="slot_a")
    assert loaded_a.districts["lowtown"].unrest == 78.0
    assert loaded_a.clock.timestamp == 180

    # Loading slot_b restores slot_b's unrest
    loaded_b = save_mgr.load_game(slot="slot_b")
    assert loaded_b.districts["lowtown"].unrest == 92.0

    with pytest.raises(SaveNotFoundError):
        save_mgr.load_game(slot="nonexistent_slot")


def test_save_manager_snapshots_and_corruption_detection() -> None:
    save_mgr = SaveManager(":memory:")
    world = _build_populated_test_world()

    snap_id = save_mgr.create_snapshot(world, label="before_voss_promotion")
    snaps = save_mgr.list_snapshots()
    assert len(snaps) == 1
    assert snaps[0]["snapshot_id"] == snap_id
    assert snaps[0]["label"] == "before_voss_promotion"

    # Mutate world state significantly
    world.clock.advance_years(2)
    world.characters["npc_voss"].status = "dead"
    save_mgr.save_game(world, slot="default")

    # Restore snapshot -> rolls back state to Year 1 with Voss alive
    restored = save_mgr.restore_snapshot(snap_id)
    assert restored.clock.year == 1
    assert restored.characters["npc_voss"].status == "alive"

    # Tamper with snapshot payload in SQLite -> raises SaveCorruptedError
    with save_mgr.db.transaction() as conn:
        conn.execute(
            "UPDATE snapshots SET payload_json = '{\"corrupted\": true}' WHERE snapshot_id = ?;",
            (snap_id,),
        )
    with pytest.raises(SaveCorruptedError):
        save_mgr.restore_snapshot(snap_id)


def test_chronicle_generator_multi_year_narrative() -> None:
    save_mgr = SaveManager(":memory:")
    world = _build_populated_test_world()

    # Year 2 (Act I): Rival promoted & Nemesis adapted
    world.clock.advance_years(1)
    save_mgr.append_event(
        GameEvent(
            id="event_y2_promote",
            event_type=EVENT_RIVAL_PROMOTED,
            timestamp=world.clock.timestamp,
            source_id="city_guard",
            target_ids=["npc_voss"],
            location_id="lowtown",
            data={"faction_id": "city_guard", "new_rank": "commander", "reason": "ruthless crackdown"},
            importance=0.85,
        )
    )
    save_mgr.append_event(
        GameEvent(
            id="event_y2_adapt",
            event_type=EVENT_NEMESIS_ADAPTED,
            timestamp=world.clock.timestamp + 60,
            source_id="player",
            target_ids=["npc_voss"],
            location_id="lowtown",
            data={"tactic": "heavy_weapons"},
            importance=0.75,
        )
    )

    # Year 5 (Act II): Faction influence shift & Quest completion
    world.clock.advance_years(3)
    save_mgr.append_event(
        GameEvent(
            id="event_y5_faction",
            event_type=EVENT_DISTRICT_INFLUENCE_CHANGED,
            timestamp=world.clock.timestamp,
            source_id="lowtown_syndicate",
            target_ids=["lowtown"],
            location_id="lowtown",
            data={"faction_id": "lowtown_syndicate", "action": "seize_docks", "influence_pct": 62.0},
            importance=0.9,
        )
    )
    save_mgr.append_event(
        GameEvent(
            id="event_y5_quest",
            event_type=EVENT_QUEST_COMPLETED,
            timestamp=world.clock.timestamp + 120,
            source_id="player",
            target_ids=["quest_blood_in_lowtown"],
            location_id="lowtown",
            data={"title": "Blood in Lowtown", "status": "completed", "approach": "investigate_independently"},
            importance=0.95,
        )
    )

    chronicle = save_mgr.generate_chronicle(world=world, min_importance=0.5)
    assert len(chronicle) == 5
    years_present = {entry["year"] for entry in chronicle}
    acts_present = {entry["act"] for entry in chronicle}
    assert years_present == {1, 2, 5}
    assert ACT_PROLOGUE in acts_present
    assert ACT_I in acts_present
    assert ACT_II in acts_present

    formatted = save_mgr.format_chronicle_text(world=world, min_importance=0.5)
    assert "=== THE CHRONICLE OF VEYR ===" in formatted
    assert "## Year 1 — Prologue" in formatted
    assert "## Year 2 — Act I" in formatted
    assert "## Year 5 — Act II" in formatted
    assert "Captain Garrick Voss" in formatted
    assert "compound fracture" in formatted
    assert "Lowtown Syndicate" in formatted
