"""Unit and integration tests for M1: Lowtown locations, Prologue, Tutorial, and Core Game verbs."""

from __future__ import annotations

from pathlib import Path

from content import populate_world
from content.prologue import (
    PROLOGUE_BEATS,
    PROLOGUE_CHOICES,
    TUTORIAL_STEPS,
    apply_prologue_choice,
    get_inspect_clue,
)
from core.game import Game
from core.world import World
from persistence.database import Database
from persistence.save_manager import SaveManager


def _make_game(tmp_path: Path, seed: int = 482193) -> Game:
    db_path = tmp_path / f"test_{seed}.db"
    db = Database(db_path)
    return Game(seed=seed, db=db, save_manager=SaveManager(db))


# ---------------------------------------------------------------------------
# F-CORE-1: Lowtown Locations & Target Resolution
# ---------------------------------------------------------------------------


def test_all_nine_lowtown_locations_registered_with_metadata() -> None:
    world = populate_world(World(seed=101))
    expected_ids = {
        "lowtown_tavern",
        "lowtown_market",
        "lowtown_docks",
        "lowtown_alleys",
        "lowtown_safehouse",
        "lowtown_watchpost",
        "lowtown_warehouse",
        "lowtown_tenements",
        "lowtown_street",
    }
    assert expected_ids.issubset(set(world.locations.keys()))
    assert set(world.districts["lowtown"].locations) >= expected_ids

    for lid in expected_ids:
        loc = world.locations[lid]
        assert loc.description and loc.description != loc.name
        assert len(loc.connected_locations) >= 2
        assert len(loc.terrain_features) >= 2
        # Bidirectional connection check
        for neighbor in loc.connected_locations:
            assert lid in world.locations[neighbor].connected_locations


def test_resolve_target_prefers_exact_location_over_lowtown_substring(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    assert game.parse_command("move lowtown_market")["target"] == "lowtown_market"
    assert game.parse_command("move lowtown tavern")["target"] == "lowtown_tavern"
    assert game.parse_command("move Cobblestone Market")["target"] == "lowtown_market"
    assert game.parse_command("move lowtown")["target"] == "lowtown"

    res = game.execute_command("move lowtown_market")
    assert res["success"] is True
    assert game.world.player.location_id == "lowtown_market"


# ---------------------------------------------------------------------------
# F-PRO-1 & F-PRO-2: Prologue Beats, Choices, Skip, Replay & Idempotency
# ---------------------------------------------------------------------------


def test_prologue_beats_and_three_choices_apply_deterministic_effects(tmp_path: Path) -> None:
    for choice_id in ("watch_investigator", "street_broker", "unbound_drifter"):
        game = _make_game(tmp_path, seed=hash(choice_id) % 100000)
        assert game.world.clock.act == "Prologue"
        assert game.world.clock.prologue_completed is False

        state0 = game.get_prologue_state()
        assert state0["active"] is True
        assert state0["completed"] is False
        assert state0["step"] == 0
        assert state0["total_steps"] == len(PROLOGUE_BEATS)

        # Advance beat 0 -> 1 -> 2
        assert game.advance_prologue()["success"] is True
        assert game.advance_prologue()["success"] is True

        # Beat 2 requires a valid choice
        bad = game.advance_prologue()
        assert bad["success"] is False

        wealth_before = game.world.player.needs["wealth"]
        res = game.advance_prologue(choice_id=choice_id)
        assert res["success"] is True
        assert res["state"]["completed"] is True
        assert res["state"]["active"] is False
        assert game.world.flags["prologue_choice"] == choice_id
        assert game.world.clock.prologue_completed is True
        assert game.world.clock.act == "Act I"
        assert game.world.player.needs["wealth"] == wealth_before + PROLOGUE_CHOICES[choice_id]["wealth_delta"]


def test_apply_prologue_choice_is_idempotent(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    wealth_before = game.world.player.needs["wealth"]
    first = apply_prologue_choice(game.world, "street_broker")
    assert first["success"] is True
    assert first["already_applied"] is False

    wealth_after_first = game.world.player.needs["wealth"]
    assert wealth_after_first == wealth_before + 75.0

    second = apply_prologue_choice(game.world, "watch_investigator")
    assert second["success"] is True
    assert second["already_applied"] is True
    assert second["choice_id"] == "street_broker"
    assert game.world.player.needs["wealth"] == wealth_after_first


def test_prologue_skip_and_replay_commands_advance_zero_minutes(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    t0 = game.world.clock.total_minutes

    res_skip = game.execute_command("skip prologue")
    assert res_skip["success"] is True
    assert game.world.clock.total_minutes == t0
    assert game.world.clock.prologue_completed is True
    assert game.get_prologue_state()["skipped"] is True

    res_replay = game.execute_command("prologue replay")
    assert res_replay["success"] is True
    assert game.world.clock.total_minutes == t0
    p_state = game.get_prologue_state()
    assert p_state["active"] is True
    assert p_state["completed"] is False
    assert p_state["step"] == 0


# ---------------------------------------------------------------------------
# F-TUT-1 & F-TUT-2: Tutorial State Machine & Out-of-Order Resilience
# ---------------------------------------------------------------------------


def test_tutorial_full_progression_across_missions_1_and_2(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    game.skip_prologue()

    t0 = game.get_tutorial_state()
    assert t0["enabled"] is True
    assert t0["current_step"] == "m1_move_market"
    assert t0["progress"] == (0, len(TUTORIAL_STEPS))

    commands = [
        "move lowtown_market",
        "inspect lowtown_market",
        "talk sera",
        "open journal",
        "choose support_city_guard",
        "inspect lowtown_alleys",
        "check health",
        "rest 4h",
        "save tut_slot",
    ]
    for cmd in commands:
        res = game.execute_command(cmd)
        assert res["success"] is True, f"Failed on {cmd}: {res}"

    t_end = game.get_tutorial_state()
    assert t_end["completed"] is True
    assert t_end["current_step"] is None
    assert t_end["progress"] == (len(TUTORIAL_STEPS), len(TUTORIAL_STEPS))


def test_tutorial_out_of_order_auto_advances_superseded_steps(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    res = game.execute_command("choose syndicate")
    assert res["success"] is True

    t_state = game.get_tutorial_state()
    # All 5 Mission 1 steps should be auto-completed
    assert t_state["progress"][0] == 5
    assert t_state["current_step"] == "m2_investigate_apprentice"


def test_tutorial_skip_and_reset_commands_advance_zero_minutes(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    t0 = game.world.clock.total_minutes

    assert game.execute_command("tutorial")["success"] is True
    assert game.execute_command("tutorial skip")["success"] is True
    assert game.get_tutorial_state()["skipped"] is True
    assert game.get_tutorial_state()["enabled"] is False

    # Actions while skipped do not advance tutorial
    game.execute_command("move lowtown_market")
    assert game.get_tutorial_state()["completed_steps"] == []

    t_before_reset = game.world.clock.total_minutes
    assert game.execute_command("tutorial reset")["success"] is True
    assert game.world.clock.total_minutes == t_before_reset
    assert game.get_tutorial_state()["enabled"] is True
    assert game.get_tutorial_state()["skipped"] is False
    assert game.get_tutorial_state()["current_step"] == "m1_move_market"


# ---------------------------------------------------------------------------
# F-CORE-2: Enriched talk, inspect, choose/resolve, and safe load
# ---------------------------------------------------------------------------


def test_enriched_talk_inspect_choose_and_safe_load(tmp_path: Path) -> None:
    game = _make_game(tmp_path)

    # Enriched talk
    talk_res = game.execute_command("talk sera")
    assert talk_res["success"] is True
    assert game.get_dialogue("comp_sera") in talk_res["message"]

    # Enriched inspect
    inspect_res = game.execute_command("inspect lowtown_market")
    assert inspect_res["success"] is True
    assert get_inspect_clue("lowtown_market", world=game.world) == inspect_res["message"]
    assert game.world.flags.get("crime_scene_inspected") is True
    assert any(m.id == "mem_lowtown_crime_scene" for m in game.world.player.memories)
    q_blood = game.world.quests["quest_blood_in_lowtown"]
    obj_map = {o["id"]: o["completed"] for o in q_blood.objectives}
    assert obj_map["investigate_crime_scene"] is True

    # Choose / resolve
    choose_res = game.execute_command("resolve independent")
    assert choose_res["success"] is True
    assert q_blood.status == "completed"
    obj_map = {o["id"]: o["completed"] for o in q_blood.objectives}
    assert obj_map["choose_faction_approach"] is True

    # Safe load of missing slot
    missing_res = game.execute_command("load nonexistent_slot_xyz")
    assert missing_res["success"] is False
    assert "not found" in missing_res["message"].lower()


# ---------------------------------------------------------------------------
# SQLite Save/Load Round-Trip
# ---------------------------------------------------------------------------


def test_prologue_and_tutorial_round_trip_through_sqlite_save_load(tmp_path: Path) -> None:
    db_path = tmp_path / "roundtrip.db"
    db1 = Database(db_path)
    game1 = Game(seed=777, db=db1, save_manager=SaveManager(db1))

    game1.advance_prologue()  # step 1
    game1.execute_command("move lowtown_market")
    game1.execute_command("inspect lowtown_market")
    save_res = game1.execute_command("save mid_onboarding")
    assert save_res["success"] is True

    # Load into a fresh Game instance sharing the SQLite file
    db2 = Database(db_path)
    game2 = Game(seed=777, db=db2, save_manager=SaveManager(db2))
    load_res = game2.execute_command("load mid_onboarding")
    assert load_res["success"] is True
    assert game2.tutorial.world is game2.world

    p_state = game2.get_prologue_state()
    assert p_state["step"] == 1
    assert p_state["active"] is True

    t_state = game2.get_tutorial_state()
    assert t_state["completed_steps"] == ["m1_move_market", "m1_inspect_scene"]
    assert t_state["current_step"] == "m1_talk_companions"
    assert "lowtown_market" in game2.world.locations


def test_tutorial_completion_on_save_persists_across_load(tmp_path: Path) -> None:
    db_path = tmp_path / "complete_tutorial.db"
    db1 = Database(db_path)
    game1 = Game(seed=482193, db=db1, save_manager=SaveManager(db1))

    assert game1.execute_command("skip prologue")["success"] is True
    for cmd in [
        "move lowtown_market",
        "inspect lowtown_market",
        "talk sera",
        "open journal",
        "choose guard",
        "inspect lowtown_alleys",
        "check health",
        "rest 4h",
        "save",
    ]:
        res = game1.execute_command(cmd)
        assert res["success"] is True, f"Command failed: {cmd} -> {res}"

    state1 = game1.get_tutorial_state()
    assert state1["completed"] is True
    assert state1["progress"] == (9, 9)
    assert state1["current_step"] is None

    db2 = Database(db_path)
    game2 = Game(seed=482193, db=db2, save_manager=SaveManager(db2))
    load_res = game2.execute_command("load")
    assert load_res["success"] is True

    state2 = game2.get_tutorial_state()
    assert state2["completed"] is True
    assert state2["progress"] == (9, 9)
    assert state2["current_step"] is None


# ---------------------------------------------------------------------------
# Tier 5 Adversarial Hardening Tests
# ---------------------------------------------------------------------------


def test_load_rebinds_all_systems_simulation_and_faction_ai(tmp_path: Path) -> None:
    db_path = tmp_path / "rebind.db"
    db1 = Database(db_path)
    game1 = Game(seed=515, db=db1, save_manager=SaveManager(db1))
    game1.execute_command("skip prologue")
    assert game1.execute_command("save s1")["success"] is True

    db2 = Database(db_path)
    game2 = Game(seed=515, db=db2, save_manager=SaveManager(db2))
    pre_load_world = game2.world
    assert game2.execute_command("load s1")["success"] is True
    assert game2.world is not pre_load_world

    for sys_name in (
        "character_system", "memory_system", "relationship_system", "health_system",
        "equipment_system", "combat_system", "nemesis_system", "faction_system",
        "quest_system", "rumor_system", "economy_system",
    ):
        sys_obj = getattr(game2, sys_name)
        assert sys_obj.world is game2.world, f"{sys_name}.world not rebound"
        assert sys_obj.event_bus is game2.world.event_bus, f"{sys_name}.event_bus not rebound"
        assert sys_obj.clock is game2.world.clock, f"{sys_name}.clock not rebound"

    assert game2.simulation.world is game2.world
    assert game2.faction_ai.world is game2.world
    assert game2.faction_ai.event_bus is game2.world.event_bus
    assert game2.faction_ai.clock is game2.world.clock
    assert game2.faction_ai.rng is game2.world.rng
    assert game2.tutorial.world is game2.world

    pre_events = len(pre_load_world.event_bus.event_history)
    pre_mins = pre_load_world.clock.total_minutes
    assert game2.execute_command("attack voss")["success"] is True
    assert len(pre_load_world.event_bus.event_history) == pre_events
    assert len(game2.world.event_bus.event_history) > 0

    game2.simulation.advance_time(60)
    assert pre_load_world.clock.total_minutes == pre_mins
    assert game2.world.clock.total_minutes >= 60


def test_resolve_target_word_boundary_and_single_arg_aim_bandage(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    assert game.parse_command("talk joren")["target"] == "joren"
    assert game.parse_command("inspect apprentice")["target"] == "apprentice"
    assert game.parse_command("move arena")["target"] == "arena"
    assert game.parse_command("talk ren")["target"] == "npc_thief_ren"

    aim_cmd = game.parse_command("aim malakor")
    assert aim_cmd["target"] == "npc_boss_malakor"
    assert aim_cmd["body_part"] == "left_leg"

    bandage_cmd = game.parse_command("apply bandage sera")
    assert bandage_cmd["target"] == "comp_sera"
    assert bandage_cmd["body_part"] == "left_arm"


def test_tutorial_manager_handles_corrupted_or_partial_flags(tmp_path: Path) -> None:
    game = _make_game(tmp_path)

    game.world.flags["prologue"] = {"choices_made": None, "applied_effects": None, "step": -1}
    p_state = game.get_prologue_state()
    assert p_state["step"] >= 0
    assert p_state["choices_made"] == {}

    game.world.flags["prologue"] = {"step": "bad"}
    p_state2 = game.get_prologue_state()
    assert p_state2["step"] == 0

    game.world.flags["tutorial"] = {"completed_steps": None}
    t_state = game.get_tutorial_state()
    assert t_state["completed"] is False
    assert t_state["completed_steps"] == []

    game.world.flags["tutorial"] = {"completed_steps": [f"bogus_{i}" for i in range(9)]}
    t_state2 = game.get_tutorial_state()
    assert t_state2["completed"] is False
    assert t_state2["current_step"] is not None
    assert t_state2["progress"] == (0, len(TUTORIAL_STEPS))


def test_execute_command_dict_invalid_minutes_and_optional_world_lookups(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    res_rest = game.execute_command({"action": "rest", "minutes": "abc"})
    assert res_rest["success"] is False
    res_wait = game.execute_command({"action": "wait", "minutes": None})
    assert res_wait["success"] is False

    game.world.nemesis_profiles.clear()
    assert game.resolve_scenario_approach("support_syndicate")["success"] is True

    game2 = _make_game(tmp_path, seed=482194)
    game2.world.districts.clear()
    assert game2.resolve_scenario_approach("exploit_situation")["success"] is True


