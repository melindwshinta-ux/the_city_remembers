"""Opaque-Box E2E Test Suite (Tiers 1-4) for Prologue, Tutorial, Missions 1-2 Onboarding & QOL UI/UX.

Covers:
- Tier 1 (Feature Coverage): Prologue beats & all 3 stance choices, Tutorial 9 steps,
  PrologueScreen, Tutorial HUD, HelpModal, QuitConfirmModal, CommandInput history,
  view shortcuts, and the 4 UI bugfixes.
- Tier 2 (Boundary & Corner Cases): Invalid prologue choices, replay idempotency,
  skip prologue/tutorial, out-of-order tutorial completion, missing/corrupted save slots,
  Rich markup escaping ([red], [/]), (80, 24) compact terminal layout,
  non-blocking create_app(game=...).
- Tier 3 (Cross-Feature Combinations): Prologue -> Mission 1 -> Mission 2 -> SQLite save/load ->
  post-load gameplay & UI refresh; Textual pilot end-to-end command submission + Tutorial HUD +
  view switching.
- Tier 4 (Real-World Application Scenarios): Complete player onboarding walkthrough from
  PrologueScreen launch through Mission 1 ("Blood in Lowtown") resolution and Mission 2
  ("Missing Apprentice") investigation + save + quit confirmation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.conftest import require_module, require_symbol


def _make_isolated_game(tmp_path: Path, name: str = "e2e", seed: int = 482193) -> tuple[Any, Path]:
    """Create an isolated Game instance backed by a dedicated SQLite DB in tmp_path."""
    Game = require_symbol("core.game", "Game")
    Database = require_symbol("persistence.database", "Database")
    SaveManager = require_symbol("persistence.save_manager", "SaveManager")

    db_path = tmp_path / f"{name}.db"
    db = Database(db_path)
    sm = SaveManager(db)
    game = Game(seed=seed, db=db, save_manager=sm)
    return game, db_path


async def _submit_command(pilot: Any, app: Any, cmd: str) -> None:
    """Focus CommandInput, type a command character-by-character, and press Enter."""
    CommandInput = require_symbol("ui.modals", "CommandInput")
    inp = app.query_one("#command-input", CommandInput)
    inp.focus()
    await pilot.pause()
    for ch in cmd:
        await pilot.press(ch)
    await pilot.press("enter")
    await pilot.pause(0.1)


# ===========================================================================
# TIER 1: FEATURE COVERAGE
# ===========================================================================


def test_t1_prologue_beats_and_all_three_stance_choices(tmp_path: Path) -> None:
    """Tier 1: Verify all 3 prologue beats and deterministic effects for all 3 stance choices."""
    prologue_mod = require_module("content.prologue")
    beats = prologue_mod.PROLOGUE_BEATS
    choices = prologue_mod.PROLOGUE_CHOICES

    assert len(beats) == 3
    assert [b["id"] for b in beats] == [
        "arrival_in_veyr",
        "blood_in_lowtown_market",
        "choose_opening_stance",
    ]
    assert set(choices.keys()) == {"watch_investigator", "street_broker", "unbound_drifter"}

    expected_effects = {
        "watch_investigator": {
            "wealth_delta": 25.0,
            "faction_rep": {"city_guard": 15.0, "lowtown_syndicate": -10.0},
            "comp_friendship": ("comp_marcus", 10.0),
            "memory_id": "mem_prologue_watch",
        },
        "street_broker": {
            "wealth_delta": 75.0,
            "faction_rep": {"lowtown_syndicate": 15.0, "city_guard": -10.0},
            "comp_friendship": ("comp_sera", 10.0),
            "memory_id": "mem_prologue_broker",
        },
        "unbound_drifter": {
            "wealth_delta": 40.0,
            "faction_rep": {},
            "comp_friendship": ("comp_elira", 10.0),
            "memory_id": "mem_prologue_drifter",
        },
    }

    for idx, (choice_id, exp) in enumerate(expected_effects.items()):
        game, _ = _make_isolated_game(tmp_path, name=f"stance_{choice_id}", seed=1000 + idx)
        assert game.world.clock.act == "Prologue"
        assert game.world.clock.prologue_completed is False

        s0 = game.get_prologue_state()
        assert s0["active"] is True
        assert s0["completed"] is False
        assert s0["step"] == 0
        assert s0["total_steps"] == 3
        assert s0["beat"]["id"] == "arrival_in_veyr"

        r1 = game.advance_prologue()
        assert r1["success"] is True
        assert r1["state"]["step"] == 1
        assert r1["state"]["beat"]["id"] == "blood_in_lowtown_market"

        r2 = game.advance_prologue()
        assert r2["success"] is True
        assert r2["state"]["step"] == 2
        assert r2["state"]["beat"]["requires_choice"] is True

        wealth_before = float(game.world.player.needs["wealth"])
        guard_before = float(game.world.reputation["faction"].get("city_guard", 0.0))
        synd_before = float(game.world.reputation["faction"].get("lowtown_syndicate", 0.0))
        comp_id, comp_delta = exp["comp_friendship"]
        comp_before = float(game.world.companions[comp_id].friendship)

        r3 = game.advance_prologue(choice_id=choice_id)
        assert r3["success"] is True
        assert r3["state"]["completed"] is True
        assert r3["state"]["active"] is False
        assert game.world.clock.prologue_completed is True
        assert game.world.clock.act == "Act I"
        assert game.world.flags["prologue_choice"] == choice_id
        assert float(game.world.player.needs["wealth"]) == pytest.approx(wealth_before + exp["wealth_delta"])
        assert float(game.world.companions[comp_id].friendship) == pytest.approx(comp_before + comp_delta)
        assert any(m.id == exp["memory_id"] for m in game.world.player.memories)

        if "city_guard" in exp["faction_rep"]:
            assert float(game.world.reputation["faction"]["city_guard"]) == pytest.approx(
                guard_before + exp["faction_rep"]["city_guard"]
            )
        if "lowtown_syndicate" in exp["faction_rep"]:
            assert float(game.world.reputation["faction"]["lowtown_syndicate"]) == pytest.approx(
                synd_before + exp["faction_rep"]["lowtown_syndicate"]
            )


def test_t1_tutorial_nine_steps_sequential_completion(tmp_path: Path) -> None:
    """Tier 1: Verify all 9 Mission 1-2 tutorial steps advance sequentially to completion."""
    prologue_mod = require_module("content.prologue")
    assert len(prologue_mod.TUTORIAL_STEPS) == 9

    game, _ = _make_isolated_game(tmp_path, name="tut_9_steps")
    game.skip_prologue()

    expected_sequence = [
        ("m1_move_market", "move lowtown_market"),
        ("m1_inspect_scene", "inspect lowtown_market"),
        ("m1_talk_companions", "talk sera"),
        ("m1_check_journal_factions", "open journal"),
        ("m1_choose_approach", "choose investigate_independently"),
        ("m2_investigate_apprentice", "inspect lowtown_alleys"),
        ("m2_check_health", "check health"),
        ("m2_rest_or_wait", "rest 4h"),
        ("m2_save_game", "save e2e_tut"),
    ]

    for idx, (step_id, cmd) in enumerate(expected_sequence):
        state = game.get_tutorial_state()
        assert state["enabled"] is True
        assert state["completed"] is False
        assert state["current_step"] == step_id
        assert state["progress"] == (idx, 9)

        res = game.execute_command(cmd)
        assert res["success"] is True, f"Step {step_id} command '{cmd}' failed: {res}"

    final_state = game.get_tutorial_state()
    assert final_state["completed"] is True
    assert final_state["current_step"] is None
    assert final_state["progress"] == (9, 9)


async def test_t1_prologue_screen_interactive_beats_preview_and_skip(tmp_path: Path) -> None:
    """Tier 1: PrologueScreen renders beats, previews stances, completes, and supports Esc skip."""
    create_app = require_symbol("main", "create_app")
    PrologueScreen = require_symbol("ui.prologue_screen", "PrologueScreen")
    Static = require_symbol("textual.widgets", "Static")

    # 1. Interactive completion path
    game1, _ = _make_isolated_game(tmp_path, name="pro_screen_complete")
    app1 = create_app(game=game1, show_prologue=True)
    async with app1.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app1.screen, PrologueScreen)

        await pilot.click("#btn-prologue-next")
        await pilot.pause(0.2)
        await pilot.click("#btn-prologue-next")
        await pilot.pause(0.2)
        assert game1.get_prologue_state()["step"] == 2

        await pilot.click("#choice-street_broker")
        await pilot.pause(0.1)
        preview = app1.screen.query_one("#prologue-choice-preview", Static)
        assert "Street-Smart Broker" in str(preview.content)

        await pilot.click("#btn-prologue-begin")
        await pilot.pause(0.1)
        assert not isinstance(app1.screen, PrologueScreen)
        assert game1.world.flags["prologue_choice"] == "street_broker"
        assert game1.world.clock.act == "Act I"

    # 2. Esc key skips PrologueScreen cleanly
    game2, _ = _make_isolated_game(tmp_path, name="pro_screen_esc")
    app2 = create_app(game=game2, show_prologue=True)
    async with app2.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app2.screen, PrologueScreen)
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert not isinstance(app2.screen, PrologueScreen)
        assert game2.get_prologue_state()["skipped"] is True
        assert game2.world.clock.act == "Act I"


async def test_t1_tutorial_hud_help_quit_history_and_view_shortcuts(tmp_path: Path) -> None:
    """Tier 1: Tutorial HUD controls, HelpModal, QuitConfirmModal, CommandInput history, and view shortcuts."""
    create_app = require_symbol("main", "create_app")
    HelpModal = require_symbol("ui.modals", "HelpModal")
    QuitConfirmModal = require_symbol("ui.modals", "QuitConfirmModal")
    CommandInput = require_symbol("ui.modals", "CommandInput")
    Static = require_symbol("textual.widgets", "Static")

    game, _ = _make_isolated_game(tmp_path, name="qol_features")
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        # Tutorial HUD toggle & Next Hint
        hud_title = app.query_one("#tutorial-hud-title", Static)
        assert "(0/9)" in str(hud_title.content)

        await pilot.click("#btn-hud-toggle")
        await pilot.pause()
        assert app.hud_collapsed is True
        await pilot.click("#btn-hud-next-hint")
        await pilot.pause()
        assert app.hud_collapsed is False

        # HelpModal via HUD button + close via button
        await pilot.click("#btn-hud-help")
        await pilot.pause()
        assert isinstance(app.screen, HelpModal)
        await pilot.click("#btn-help-close")
        await pilot.pause()
        assert not isinstance(app.screen, HelpModal)

        # HelpModal via F1 when input focused + close via Esc
        inp = app.query_one("#command-input", CommandInput)
        inp.focus()
        await pilot.press("f1")
        await pilot.pause()
        assert isinstance(app.screen, HelpModal)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpModal)

        # HelpModal via '?' when input blurred + close via 'q'
        inp.focus()
        await pilot.press("escape")
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpModal)
        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, HelpModal)

        # CommandInput history (Up/Down + draft preservation)
        await _submit_command(pilot, app, "talk sera")
        await _submit_command(pilot, app, "move lowtown_market")
        inp.focus()
        inp.value = "draft_cmd"
        await pilot.press("up")
        assert inp.value == "move lowtown_market"
        await pilot.press("up")
        assert inp.value == "talk sera"
        await pilot.press("down")
        assert inp.value == "move lowtown_market"
        await pilot.press("down")
        assert inp.value == "draft_cmd"
        inp.value = ""

        # View shortcuts: 1-8 when blurred, F2-F9 anytime
        await pilot.press("escape")
        await pilot.press("3")
        await pilot.pause()
        assert app.current_view == "health"

        inp.focus()
        await pilot.press("f7")
        await pilot.pause()
        assert app.current_view == "factions"
        assert inp.value == ""

        await pilot.press("f2")
        await pilot.pause()
        assert app.current_view == "world"

        # QuitConfirmModal: cancel then confirm
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert isinstance(app.screen, QuitConfirmModal)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, QuitConfirmModal)
        assert app.is_running is True

        await pilot.press("ctrl+q")
        await pilot.pause()
        assert isinstance(app.screen, QuitConfirmModal)
        await pilot.click("#btn-quit-confirm")
        await pilot.pause()
        assert app.is_running is False


def test_t1_four_ui_bugfixes_verified_opaque_box(tmp_path: Path) -> None:
    """Tier 1: Verify all 4 UI bugfixes (combat non-mutation, dynamic district, dynamic stats, player inventory)."""
    render_combat_view = require_symbol("ui.combat_screen", "render_combat_view")
    render_main_view = require_symbol("ui.main_screen", "render_main_view")
    render_character_view = require_symbol("ui.character_screen", "render_character_view")
    render_inventory_view = require_symbol("ui.journal_screen", "render_inventory_view")
    Item = require_symbol("entities.item", "Item")
    InventoryEntry = require_symbol("entities.item", "InventoryEntry")

    game, _ = _make_isolated_game(tmp_path, name="ui_bugfixes")

    # 1. Combat screen render does not mutate active_encounter
    assert game.combat_system.active_encounter is None
    combat_txt = render_combat_view(game)
    assert "TACTICAL BATTLEFIELD" in combat_txt
    assert game.combat_system.active_encounter is None

    # 2. Main screen renders dynamic district rather than hardcoded Lowtown
    game.world.player.location_id = "high_quarter"
    main_txt = render_main_view(game)
    assert "(Lowtown)" not in main_txt
    assert "High Quarter" in main_txt

    # 3. Character screen renders dynamic player attributes & personality
    game.world.player.attributes["perception"] = 88.0
    game.world.player.personality["pragmatism"] = 77.0
    char_txt = render_character_view(game)
    assert "88" in char_txt
    assert "77" in char_txt

    # 4. Journal inventory view renders only player inventory entries
    game.world.inventories.clear()
    game.world.add_item(Item(id="item_e2e_owned", name="Guard Seal Fragment", item_type="evidence", value=50.0))
    game.world.add_item(Item(id="item_e2e_other", name="Malakor Ledger", item_type="evidence", value=200.0))
    game.world.add_inventory_entry(InventoryEntry(character_id="player", item_id="item_e2e_owned", quantity=1))
    inv_txt = render_inventory_view(game)
    assert "Guard Seal Fragment" in inv_txt
    assert "Malakor Ledger" not in inv_txt


# ===========================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ===========================================================================


def test_t2_invalid_prologue_choices_and_replay_idempotency(tmp_path: Path) -> None:
    """Tier 2: Invalid prologue choices fail cleanly; replay does not double-apply bonuses."""
    apply_prologue_choice = require_symbol("content.prologue", "apply_prologue_choice")

    game, _ = _make_isolated_game(tmp_path, name="pro_boundary")
    # Advance to choice beat (step 2)
    assert game.advance_prologue()["success"] is True
    assert game.advance_prologue()["success"] is True

    # Missing choice or invalid choice fails without completing
    res_none = game.advance_prologue()
    assert res_none["success"] is False
    res_bad = game.advance_prologue(choice_id="nonexistent_stance")
    assert res_bad["success"] is False
    assert game.get_prologue_state()["completed"] is False

    # Direct apply_prologue_choice rejects invalid choice
    direct_bad = apply_prologue_choice(game.world, "bogus_id")
    assert direct_bad["success"] is False

    # Command interface rejects invalid prologue subcommand
    cmd_bad = game.execute_command("prologue bogus_id")
    assert cmd_bad["success"] is False

    # Complete with watch_investigator
    wealth_start = float(game.world.player.needs["wealth"])
    guard_start = float(game.world.reputation["faction"].get("city_guard", 0.0))
    res_ok = game.advance_prologue(choice_id="watch_investigator")
    assert res_ok["success"] is True
    wealth_after = float(game.world.player.needs["wealth"])
    guard_after = float(game.world.reputation["faction"]["city_guard"])
    assert wealth_after == pytest.approx(wealth_start + 25.0)
    assert guard_after == pytest.approx(guard_start + 15.0)

    # Replay prologue and pick street_broker -> bonuses must NOT stack/double-apply
    replay_res = game.replay_prologue()
    assert replay_res["success"] is True
    assert replay_res["state"]["active"] is True
    assert replay_res["state"]["step"] == 0

    assert game.advance_prologue()["success"] is True
    assert game.advance_prologue()["success"] is True
    replay_choice_res = game.advance_prologue(choice_id="street_broker")
    assert replay_choice_res["success"] is True
    assert float(game.world.player.needs["wealth"]) == pytest.approx(wealth_after)
    assert float(game.world.reputation["faction"]["city_guard"]) == pytest.approx(guard_after)


def test_t2_skip_prologue_and_tutorial_zero_time_and_out_of_order(tmp_path: Path) -> None:
    """Tier 2: Skipping advances 0 minutes; out-of-order tutorial auto-advances; save requires current."""
    game, _ = _make_isolated_game(tmp_path, name="tut_boundary")
    t0 = game.world.clock.total_minutes

    # Skip prologue advances 0 minutes
    assert game.execute_command("skip prologue")["success"] is True
    assert game.world.clock.total_minutes == t0
    assert game.world.clock.prologue_completed is True

    # Saving early (step 0) must NOT auto-complete steps 1-8 (require_current=True)
    assert game.execute_command("save early_slot")["success"] is True
    assert game.get_tutorial_state()["progress"] == (0, 9)
    assert game.get_tutorial_state()["current_step"] == "m1_move_market"

    # Skip tutorial advances 0 minutes and blocks step progression
    t1 = game.world.clock.total_minutes
    assert game.execute_command("tutorial skip")["success"] is True
    assert game.world.clock.total_minutes == t1
    assert game.execute_command("move lowtown_market")["success"] is True
    assert game.get_tutorial_state()["completed_steps"] == []

    # Reset tutorial -> re-enabled at step 1, 0 minutes elapsed
    t2 = game.world.clock.total_minutes
    assert game.execute_command("tutorial reset")["success"] is True
    assert game.world.clock.total_minutes == t2
    assert game.get_tutorial_state()["current_step"] == "m1_move_market"

    # Out-of-order completion: inspecting lowtown_alleys (step 6) auto-completes steps 1..6
    assert game.execute_command("inspect lowtown_alleys")["success"] is True
    t_state = game.get_tutorial_state()
    assert t_state["progress"] == (6, 9)
    assert t_state["current_step"] == "m2_check_health"


def test_t2_missing_and_corrupted_save_slots(tmp_path: Path) -> None:
    """Tier 2: Loading a missing or corrupted save slot fails gracefully without crashing Game."""
    game, _ = _make_isolated_game(tmp_path, name="save_corrupt")

    missing = game.execute_command("load slot_does_not_exist")
    assert missing["success"] is False
    assert "not found" in missing["message"].lower()

    # Save a valid slot, then corrupt its payload_json in save_slots
    assert game.execute_command("save corrupt_slot")["success"] is True
    game.db.execute(
        "UPDATE save_slots SET payload_json = ? WHERE slot = ?",
        ("{not-valid-json", "corrupt_slot"),
    )
    game.db.get_connection().commit()

    # Game.execute_command("load ...") catches SaveError and returns success=False cleanly
    corrupt_res = game.execute_command("load corrupt_slot")
    assert corrupt_res["success"] is False


async def test_t2_rich_markup_escaping_and_compact_80x24_and_non_blocking_create_app(tmp_path: Path) -> None:
    """Tier 2: Rich markup characters don't crash UI; (80, 24) fits cleanly; create_app(game=...) is non-blocking."""
    create_app = require_symbol("main", "create_app")
    PrologueScreen = require_symbol("ui.prologue_screen", "PrologueScreen")

    game, _ = _make_isolated_game(tmp_path, name="markup_80x24")
    # Default create_app(game=...) must NOT block with PrologueScreen
    app = create_app(game=game)
    assert app.show_prologue is False

    # Inject Rich markup-like characters into player name
    game.world.player.name = "Rowan [red]of[/] [bold]Veyr[/]"

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert not isinstance(app.screen, PrologueScreen)

        # Compact 80x24 geometry checks
        for selector in ("#nav-bar", "#tutorial-hud", "#view-content", "#command-log", "#command-input"):
            w = app.query_one(selector)
            assert w.region.width > 0, f"{selector} width <= 0 at 80x24"
            assert w.region.height > 0, f"{selector} height <= 0 at 80x24"
        inp = app.query_one("#command-input")
        assert inp.region.bottom <= 24
        assert inp.region.right <= 80

        # Submit command containing Rich markup tokens -> must not raise MarkupError
        await _submit_command(pilot, app, "load [red]missing[/]")
        await _submit_command(pilot, app, "inspect [/]unknown[bold]")
        assert app.is_running is True


# ===========================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS
# ===========================================================================


async def test_t3_prologue_missions_sqlite_roundtrip_and_post_load_ui_refresh(tmp_path: Path) -> None:
    """Tier 3: Prologue -> Mission 1 -> Mission 2 -> SQLite save/load -> post-load gameplay & UI refresh."""
    Game = require_symbol("core.game", "Game")
    Database = require_symbol("persistence.database", "Database")
    SaveManager = require_symbol("persistence.save_manager", "SaveManager")
    create_app = require_symbol("main", "create_app")
    Static = require_symbol("textual.widgets", "Static")

    game1, db_path = _make_isolated_game(tmp_path, name="t3_roundtrip", seed=9911)
    assert game1.advance_prologue()["success"] is True
    assert game1.advance_prologue()["success"] is True
    assert game1.advance_prologue(choice_id="street_broker")["success"] is True

    # Mission 1 steps + start Mission 2
    for cmd in (
        "move lowtown_market",
        "inspect lowtown_market",
        "talk sera",
        "open factions",
        "choose support_syndicate",
        "inspect lowtown_alleys",
    ):
        res = game1.execute_command(cmd)
        assert res["success"] is True, f"Failed: {cmd} -> {res}"

    assert game1.execute_command("save mid_m2")["success"] is True

    # Load into fresh Game instance using same SQLite DB
    db2 = Database(db_path)
    game2 = Game(seed=9911, db=db2, save_manager=SaveManager(db2))
    assert game2.execute_command("load mid_m2")["success"] is True

    assert game2.world.flags["prologue_choice"] == "street_broker"
    assert game2.world.clock.prologue_completed is True
    assert game2.world.quests["quest_blood_in_lowtown"].status == "completed"
    t_state = game2.get_tutorial_state()
    assert t_state["progress"] == (6, 9)
    assert t_state["current_step"] == "m2_check_health"

    # Continue playing in Textual UI after load and verify HUD & view refresh
    app = create_app(game=game2, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        hud_title = app.query_one("#tutorial-hud-title", Static)
        assert "(6/9)" in str(hud_title.content)

        await _submit_command(pilot, app, "check health")
        await _submit_command(pilot, app, "rest 4h")
        await _submit_command(pilot, app, "save post_load_slot")

        assert game2.get_tutorial_state()["completed"] is True
        assert "(9/9)" in str(hud_title.content)


async def test_t3_pilot_command_submission_hud_and_view_switching(tmp_path: Path) -> None:
    """Tier 3: Textual pilot end-to-end command submission updates Tutorial HUD, view, and RichLog."""
    create_app = require_symbol("main", "create_app")
    Static = require_symbol("textual.widgets", "Static")

    game, _ = _make_isolated_game(tmp_path, name="t3_pilot_hud")
    game.skip_prologue()
    app = create_app(game=game, show_prologue=False)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        hud_title = app.query_one("#tutorial-hud-title", Static)
        view_content = app.query_one("#view-content", Static)

        assert "(0/9)" in str(hud_title.content)
        await _submit_command(pilot, app, "move lowtown_market")
        assert "(1/9)" in str(hud_title.content)
        assert "Cobblestone Market" in str(view_content.content)

        await _submit_command(pilot, app, "inspect lowtown_market")
        assert "(2/9)" in str(hud_title.content)

        await _submit_command(pilot, app, "talk marcus")
        assert "(3/9)" in str(hud_title.content)

        await _submit_command(pilot, app, "open journal")
        assert app.current_view == "journal"
        assert "(4/9)" in str(hud_title.content)
        assert "ADVENTURE JOURNAL" in str(view_content.content)


# ===========================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS
# ===========================================================================


async def test_t4_complete_onboarding_walkthrough_prologue_to_m2_save_and_quit(tmp_path: Path) -> None:
    """Tier 4: Full player onboarding from PrologueScreen launch through M1 & M2, save, and quit confirm."""
    Game = require_symbol("core.game", "Game")
    Database = require_symbol("persistence.database", "Database")
    SaveManager = require_symbol("persistence.save_manager", "SaveManager")
    create_app = require_symbol("main", "create_app")
    PrologueScreen = require_symbol("ui.prologue_screen", "PrologueScreen")
    QuitConfirmModal = require_symbol("ui.modals", "QuitConfirmModal")
    Static = require_symbol("textual.widgets", "Static")

    game, db_path = _make_isolated_game(tmp_path, name="t4_onboarding")
    app = create_app(game=game, show_prologue=True)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # 1. PrologueScreen launch & progression
        assert isinstance(app.screen, PrologueScreen)
        await pilot.click("#btn-prologue-next")
        await pilot.pause(0.2)
        await pilot.click("#btn-prologue-next")
        await pilot.pause(0.2)
        await pilot.click("#choice-watch_investigator")
        await pilot.pause(0.1)
        await pilot.click("#btn-prologue-begin")
        await pilot.pause(0.1)

        assert not isinstance(app.screen, PrologueScreen)
        assert game.world.clock.act == "Act I"
        assert game.world.flags["prologue_choice"] == "watch_investigator"

        # 2. Mission 1: Blood in Lowtown
        for cmd in (
            "move lowtown_market",
            "inspect lowtown_market",
            "talk marcus",
            "open factions",
            "choose support_city_guard",
        ):
            await _submit_command(pilot, app, cmd)

        assert game.world.quests["quest_blood_in_lowtown"].status == "completed"
        assert game.world.flags.get("discovered_guard_corruption") is True
        assert game.get_tutorial_state()["progress"] == (5, 9)

        # 3. Mission 2: Missing Apprentice + Health + Rest + Save
        for cmd in (
            "inspect lowtown_alleys",
            "check health",
            "rest 4h",
            "save onboarding_complete",
        ):
            await _submit_command(pilot, app, cmd)

        hud_title = app.query_one("#tutorial-hud-title", Static)
        assert "(9/9)" in str(hud_title.content)
        assert game.get_tutorial_state()["completed"] is True

        # 4. Quit confirmation flow (cancel once, then confirm)
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert isinstance(app.screen, QuitConfirmModal)
        await pilot.click("#btn-quit-cancel")
        await pilot.pause()
        assert app.is_running is True

        await pilot.press("ctrl+q")
        await pilot.pause()
        assert isinstance(app.screen, QuitConfirmModal)
        await pilot.click("#btn-quit-confirm")
        await pilot.pause()
        assert app.is_running is False

    # Verify persisted SQLite save can be loaded in a fresh session
    db_verify = Database(db_path)
    game_verify = Game(seed=482193, db=db_verify, save_manager=SaveManager(db_verify))
    load_res = game_verify.execute_command("load onboarding_complete")
    assert load_res["success"] is True
    assert game_verify.world.flags["prologue_choice"] == "watch_investigator"
    assert game_verify.get_tutorial_state()["completed"] is True
    assert game_verify.world.quests["quest_blood_in_lowtown"].status == "completed"
