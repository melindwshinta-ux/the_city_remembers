"""Tier 4 E2E Real-World Application Scenario & Simulation Tests for THE CITY REMEMBERS.

Covers all 12 mandatory end-to-end scenarios (`test_t4_01` through `test_t4_12`):
- GDD Section 18: All 4 approaches to "Blood in Lowtown" + Post-Quest Systemic Continuation
- GDD Appendix B: 10-Step First Vertical Slice Checklist
- GDD Section 19: All 4 Quantitative Simulation Tests (100-Char Survival, 100-Encounter Nemesis, 10-Year Faction Sim, Event Propagation)
- GDD Section 20: Ultimate 5-Year Unique Chronicle Test
- GDD Section 16: Headless Textual UI Full Walkthrough across all 8 views & 7 screen modules
Zero top-level application imports so `pytest --collect-only` always succeeds with 0 errors.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests.e2e.conftest import (
    call_method,
    get_clock_minutes,
    instantiate_with_context,
    require_module,
    require_symbol,
)


def test_t4_01_blood_in_lowtown_approach_support_city_guard(game_session: Any) -> None:
    """Scenario 1 (GDD §18): Support the City Guard -> gain guard rep, anger Syndicate, discover guard corruption."""
    world = game_session.world
    assert "quest_blood_in_lowtown" in world.quests
    assert "npc_voss" in world.characters
    assert "comp_marcus" in world.characters and "comp_sera" in world.characters

    res = call_method(
        game_session,
        ("resolve_scenario_approach", "complete_blood_in_lowtown", "choose_quest_approach"),
        "support_city_guard",
    )
    assert res["success"] is True

    # 1. Immediate effect: Gain City Guard reputation
    assert world.reputation["faction"].get("city_guard", 0.0) > 0.0
    # 2. Consequence: Anger the Syndicate & normalized Lowtown influence
    assert world.reputation["faction"].get("lowtown_syndicate", 0.0) < 0.0
    assert sum(world.districts["lowtown"].faction_influence.values()) == pytest.approx(100.0)
    # 3. Consequence: Discover corruption inside the guard
    assert "corruption" in str(res).lower() or world.flags.get("discovered_guard_corruption") is True
    # 4. Companion reactions: Marcus approves, Sera disagrees
    assert world.companions["comp_marcus"].friendship > 0.0


def test_t4_02_blood_in_lowtown_approach_support_syndicate(game_session: Any) -> None:
    """Scenario 2 (GDD §18): Support the Syndicate -> gain criminal contacts, anger Voss, expose illegal trade."""
    world = game_session.world
    voss_hostility_before = world.nemesis_profiles["npc_voss"].player_hostility

    res = call_method(
        game_session,
        ("resolve_scenario_approach", "complete_blood_in_lowtown", "choose_quest_approach"),
        "support_syndicate",
    )
    assert res["success"] is True

    # 1. Immediate effect: Gain criminal contacts & Syndicate reputation
    assert world.reputation["faction"].get("lowtown_syndicate", 0.0) > 0.0
    assert world.reputation.get("criminal_underworld", 0.0) > 0.0 or world.flags.get("criminal_contacts_unlocked") is True
    # 2. Consequence: Anger Captain Voss
    assert world.nemesis_profiles["npc_voss"].player_hostility > voss_hostility_before
    # 3. Consequence: Expose illegal trade
    assert "illegal_trade" in str(res).lower() or world.flags.get("exposed_illegal_trade") is True
    # 4. Companion reactions: Sera approves, Marcus disagrees (rivalry rises)
    assert world.companions["comp_sera"].friendship > 0.0
    assert world.companions["comp_marcus"].rivalry > 0.0


def test_t4_03_blood_in_lowtown_approach_investigate_independently(game_session: Any) -> None:
    """Scenario 3 (GDD §18): Investigate independently -> question witnesses, examine evidence, choose whom to expose."""
    world = game_session.world

    # Question witness / talk to Sera and inspect crime scene
    game_session.execute_command("talk sera")
    game_session.execute_command("inspect captain voss")

    res = call_method(
        game_session,
        ("resolve_scenario_approach", "complete_blood_in_lowtown", "choose_quest_approach"),
        "investigate_independently",
        expose_target="both",
    )
    assert res["success"] is True
    assert world.quests["quest_blood_in_lowtown"].status == "completed"
    assert any(e.event_type in ("QUEST_COMPLETED", "RUMOR_SPREAD") for e in world.event_bus.event_history)


def test_t4_04_blood_in_lowtown_approach_exploit_situation(game_session: Any) -> None:
    """Scenario 4 (GDD §18): Exploit the situation -> sell information to both sides, encourage conflict, profit from instability."""
    world = game_session.world
    wealth_before = world.player.needs.get("wealth", 0.0)
    unrest_before = world.districts["lowtown"].unrest

    res = call_method(
        game_session,
        ("resolve_scenario_approach", "complete_blood_in_lowtown", "choose_quest_approach"),
        "exploit_situation",
    )
    assert res["success"] is True
    assert world.player.needs.get("wealth", 0.0) > wealth_before
    assert world.districts["lowtown"].unrest > unrest_before
    assert world.factions["city_guard"].relations.get("lowtown_syndicate", 0.0) < 0.0


def test_t4_05_blood_in_lowtown_post_quest_systemic_continuation(game_session: Any) -> None:
    """Scenario 5 (GDD §18 Lines 767-770): Voss survives with broken arm -> less effective -> rival promoted -> blames player -> Marcus disagrees -> Sera approves -> aggressive patrols & financed private investigation quest."""
    world = game_session.world
    res = call_method(
        game_session,
        ("run_post_quest_continuation", "simulate_blood_in_lowtown_aftermath"),
        voss_injury="broken_arm",
        days=21,
    )
    assert res["success"] is True

    voss = world.characters["npc_voss"]
    voss_prof = world.nemesis_profiles["npc_voss"]

    # 1. Voss survives with a broken arm
    assert voss.status == "alive"
    voss_injuries = [inj.injury_type for bp in voss.body.values() for inj in bp.injuries]
    assert "broken_arm" in voss_injuries or "broken_arm" in voss_prof.grudges

    # 2 & 3. Faction system judges him less effective & promotes his rival
    assert any(e.event_type in ("RIVAL_PROMOTED", "NEMESIS_PROMOTED") for e in world.event_bus.event_history)

    # 4. Voss blames the player
    assert voss_prof.player_hostility > 0.0
    assert len(voss_prof.grudges) >= 1

    # 5. Marcus disagrees & Sera approves with dangerous favors
    assert world.companions["comp_marcus"].rivalry > 0.0
    assert world.companions["comp_sera"].friendship > 0.0

    # 6. Weeks later: aggressive guard patrols & new quest from financed private investigation
    assert len(world.quests) >= 2
    assert any("voss" in q.id.lower() or "investigation" in q.title.lower() or "vendetta" in q.id.lower() for q in world.quests.values())


def test_t4_06_appendix_b_ten_step_vertical_slice_checklist(game_session: Any) -> None:
    """Scenario 6 (GDD Appendix B Lines 869-884): Complete 10-step vertical slice checklist."""
    world = game_session.world

    # Step 1: Walk around Lowtown
    r1 = game_session.execute_command("move lowtown_tavern")
    r1b = game_session.execute_command("move lowtown_street")
    assert r1["success"] is True and r1b["success"] is True

    # Step 2: Talk to NPCs and recruit companions
    r2a = game_session.execute_command("talk sera")
    r2b = game_session.execute_command("talk marcus")
    r2c = game_session.execute_command("recruit elira")
    assert r2a["success"] is True and r2b["success"] is True and r2c["success"] is True

    # Step 3 & 4: Start a fight with Captain Voss & injure him using location-specific damage
    r3 = game_session.execute_command("attack captain voss")
    r4 = game_session.execute_command("aim captain voss left_leg")
    assert r3["success"] is True and r4["success"] is True
    voss = world.characters["npc_voss"]
    assert voss.body["left_leg"].integrity < 100.0 or len(voss.body["left_leg"].injuries) >= 1

    # Step 5: Allow him to escape
    assert voss.status == "alive"

    # Step 6 & 7: Advance time by several days & let the faction simulation run
    t_before_wait = get_clock_minutes(world.clock)
    r6 = game_session.execute_command("wait 5d")
    assert r6["success"] is True
    assert get_clock_minutes(world.clock) - t_before_wait == 5 * 1440
    assert any(e.event_type == "FACTION_ACTION_TAKEN" for e in world.event_bus.event_history)

    # Step 8 & 9: Encounter Voss again & discover how his injuries, memories, and political circumstances changed
    r8 = game_session.execute_command("inspect captain voss")
    assert r8["success"] is True
    assert len(voss.memories) >= 1
    assert world.nemesis_profiles["npc_voss"].encounter_count >= 1

    # Step 10: Save the game and inspect its event history
    r10 = game_session.execute_command("save vertical_slice_slot")
    assert r10["success"] is True
    history = game_session.save_manager.get_event_history()
    assert len(history) >= 5


def test_t4_07_sec19_simulation_test_1_hundred_character_survival() -> None:
    """Scenario 7 (GDD §19 Test 1): Generate 100 characters and simulate needs, health, and daily behavior."""
    sim_mod = require_module("core.simulation")
    res = call_method(
        sim_mod,
        ("run_character_survival_sim", "simulate_character_survival"),
        num_characters=100,
        days=14,
        seed=482193,
    )
    assert res["total_characters"] == 100
    assert res["survival_rate"] >= 0.95
    assert res["injuries_healed_count"] >= 20


def test_t4_08_sec19_simulation_test_2_hundred_encounter_nemesis_generation() -> None:
    """Scenario 8 (GDD §19 Test 2): Simulate 100 encounters; verify selective Nemesis rate, promotions, and 100% fair adaptation."""
    sim_mod = require_module("core.simulation")
    res = call_method(
        sim_mod,
        ("run_nemesis_generation_sim", "simulate_nemesis_generation"),
        num_encounters=100,
        seed=482193,
    )
    assert res["total_encounters"] == 100
    assert 10 <= res["nemeses_created"] <= 60
    assert res["promotions_count"] >= 1
    assert res["unfair_adaptations_count"] == 0


def test_t4_09_sec19_simulation_test_3_ten_year_faction_simulation() -> None:
    """Scenario 9 (GDD §19 Test 3): Simulate 10 years; verify no single faction monopoly, vacancies resolved, and city functional."""
    sim_mod = require_module("core.simulation")
    res = call_method(
        sim_mod,
        ("run_faction_10year_sim", "simulate_factions_ten_years"),
        years=10,
        seed=482193,
    )
    assert res["final_year"] >= 10
    assert res["final_act"] == "Act III"
    assert res["active_factions_count"] >= 3
    assert res["unresolved_vacancies"] == 0
    assert res["city_functional"] is True


def test_t4_10_sec19_simulation_test_4_artificial_event_propagation() -> None:
    """Scenario 10 (GDD §19 Test 4): Emit artificial CHARACTER_DIED event and verify Memory, Leadership, Quests, Nemesis, and History update."""
    sim_mod = require_module("core.simulation")
    res = call_method(
        sim_mod,
        ("run_event_propagation_test", "verify_event_propagation"),
        seed=482193,
    )
    assert res["memory_updated"] is True
    assert res["leadership_updated"] is True
    assert res["quests_updated"] is True
    assert res["nemesis_updated"] is True
    assert res["history_updated"] is True


def test_t4_11_sec20_ultimate_five_year_unique_chronicle_test() -> None:
    """Scenario 11 (GDD §20 Lines 825-826): Play/simulate 5 in-game years; Chronicle tells a story unique to that playthrough."""
    sim_mod = require_module("core.simulation")
    chron_a = call_method(sim_mod, ("run_five_year_chronicle_sim", "simulate_five_year_chronicle"), years=5, seed=482193)
    chron_b = call_method(sim_mod, ("run_five_year_chronicle_sim", "simulate_five_year_chronicle"), years=5, seed=991027)
    chron_a_replay = call_method(sim_mod, ("run_five_year_chronicle_sim", "simulate_five_year_chronicle"), years=5, seed=482193)

    years_a = {entry["year"] for entry in chron_a}
    assert {1, 2, 3, 4, 5}.issubset(years_a)
    assert chron_a != chron_b
    assert chron_a == chron_a_replay


def test_t4_12_textual_ui_headless_pilot_full_walkthrough(game_session: Any) -> None:
    """Scenario 12 (GDD §16): Headless Textual App pilot walkthrough across all 8 views and structured commands."""
    main_mod = require_module("main")
    AppCls = getattr(main_mod, "CityRemembersApp", getattr(main_mod, "VeyrApp", None))
    create_app_fn = getattr(main_mod, "create_app", getattr(main_mod, "build_app", None))

    if AppCls is not None or create_app_fn is not None:
        app = create_app_fn(game=game_session) if create_app_fn is not None else instantiate_with_context(AppCls, game=game_session)
        if hasattr(app, "run_test"):

            async def _walkthrough() -> None:
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    for cmd in (
                        "open world",
                        "open character",
                        "open health",
                        "open party",
                        "open combat",
                        "open factions",
                        "open journal",
                        "open inventory",
                        "talk sera",
                        "inspect captain voss",
                        "check health marcus",
                        "open faction city_guard",
                        "rest 8h",
                        "wait 3d",
                    ):
                        game_session.execute_command(cmd)
                    await pilot.pause()

            asyncio.run(_walkthrough())
            assert get_clock_minutes(game_session.world.clock) >= 4800
            return

    # Fallback if app is driven via UI screen modules + game_session command loop
    for cmd in (
        "open world",
        "open character",
        "open health",
        "open party",
        "open combat",
        "open factions",
        "open journal",
        "open inventory",
        "talk sera",
        "inspect captain voss",
        "check health marcus",
        "open faction city_guard",
        "rest 8h",
        "wait 3d",
    ):
        res = game_session.execute_command(cmd)
        assert res["success"] is True
    assert get_clock_minutes(game_session.world.clock) >= 4800
