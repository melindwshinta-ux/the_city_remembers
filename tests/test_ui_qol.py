"""Tests for M2 Textual UI, PrologueScreen, Tutorial HUD, QOL modals/keybindings, and UI bugfixes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from entities.item import InventoryEntry, Item
from main import CityRemembersApp, VIEWS, create_app, main
from persistence.database import Database
from persistence.save_manager import SaveManager
from core.game import Game
from ui.character_screen import render_character_view, render_party_view
from ui.combat_screen import render_combat_view
from ui.journal_screen import render_inventory_view
from ui.main_screen import render_main_view
from ui.modals import CommandInput, HelpModal, QuitConfirmModal
from ui.prologue_screen import PrologueScreen


def _make_game(tmp_path: Path, seed: int = 482193) -> Game:
    db = Database(tmp_path / f"ui_{seed}.db")
    sm = SaveManager(db)
    return Game(seed=seed, db=db, save_manager=sm)


# ---------------------------------------------------------------------------
# Group 1: PrologueScreen
# ---------------------------------------------------------------------------


async def test_prologue_screen_advance_beats_and_select_stance(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, PrologueScreen)
        assert game.get_prologue_state()["step"] == 0

        # Beat 0 -> Beat 1
        await pilot.click("#btn-prologue-next")
        await pilot.pause(0.3)
        assert game.get_prologue_state()["step"] == 1

        # Beat 1 -> Beat 2 (choice beat)
        await pilot.click("#btn-prologue-next")
        await pilot.pause(0.3)
        assert game.get_prologue_state()["step"] == 2

        # Select stance & begin investigation
        await pilot.click("#choice-watch_investigator")
        await pilot.pause(0.1)
        await pilot.click("#btn-prologue-begin")
        await pilot.pause(0.1)

        assert not isinstance(app.screen, PrologueScreen)
        assert game.world.clock.prologue_completed is True
        assert game.world.clock.act == "Act I"
        assert game.world.flags["prologue"]["completed"] is True
        assert game.world.flags["prologue_choice"] == "watch_investigator"
        assert game.world.reputation["faction"]["city_guard"] > 0
        assert app.query_one("#command-input", CommandInput) is not None


async def test_prologue_screen_requires_choice_before_begin(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#btn-prologue-next")
        await pilot.pause(0.3)
        await pilot.click("#btn-prologue-next")
        await pilot.pause(0.3)
        # Click Begin without selecting a stance -> stays on PrologueScreen
        await pilot.click("#btn-prologue-begin")
        await pilot.pause(0.1)
        assert isinstance(app.screen, PrologueScreen)
        assert game.get_prologue_state()["completed"] is False


async def test_prologue_screen_skip_prologue(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, PrologueScreen)
        await pilot.click("#btn-prologue-skip")
        await pilot.pause()

        assert not isinstance(app.screen, PrologueScreen)
        assert game.world.clock.prologue_completed is True
        assert game.world.clock.act == "Act I"
        assert game.world.flags["prologue"]["skipped"] is True
        assert game.world.flags["prologue"]["completed"] is True
        assert app.query_one("#view-content") is not None


# ---------------------------------------------------------------------------
# Group 2: show_prologue Default Gating
# ---------------------------------------------------------------------------


async def test_create_app_default_show_prologue_gating(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app_with_game = create_app(game=game)
    assert app_with_game.show_prologue is False
    async with app_with_game.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert not isinstance(app_with_game.screen, PrologueScreen)
        inp = app_with_game.query_one("#command-input", CommandInput)
        inp.focus()
        await pilot.pause()
        for ch in "rest 8h":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        assert game.world.clock.total_minutes >= 480

    app_interactive = CityRemembersApp()
    assert app_interactive.show_prologue is True
    async with app_interactive.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app_interactive.screen, PrologueScreen)


# ---------------------------------------------------------------------------
# Group 3: Tutorial HUD, Modals, History, Keybindings & Responsive Layout
# ---------------------------------------------------------------------------


async def test_tutorial_hud_updates_toggle_hint_and_skip(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        hud = app.query_one("#tutorial-hud")
        assert hud.display is True

        # Toggle collapse & expand
        await pilot.click("#btn-hud-toggle")
        await pilot.pause()
        assert app.hud_collapsed is True
        assert hud.has_class("collapsed")

        await pilot.click("#btn-hud-next-hint")
        await pilot.pause()
        assert app.hud_collapsed is False
        assert not hud.has_class("collapsed")

        # Execute first tutorial command
        inp = app.query_one("#command-input", CommandInput)
        inp.focus()
        for ch in "move lowtown_market":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()

        assert game.get_tutorial_state()["current_step"] == "m1_inspect_scene"

        # Skip tutorial via HUD button
        await pilot.click("#btn-hud-skip-tutorial")
        await pilot.pause()
        t_state = game.get_tutorial_state()
        assert t_state["skipped"] is True
        assert t_state["enabled"] is False


async def test_help_modal_open_and_esc_close(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # Blur input then press ?
        await pilot.press("escape")
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpModal)

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpModal)

        # F1 also opens HelpModal even when input is focused
        app.query_one("#command-input", CommandInput).focus()
        await pilot.press("f1")
        await pilot.pause()
        assert isinstance(app.screen, HelpModal)


async def test_quit_confirm_modal_cancel_and_confirm(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert isinstance(app.screen, QuitConfirmModal)

        await pilot.click("#btn-quit-cancel")
        await pilot.pause()
        assert not isinstance(app.screen, QuitConfirmModal)
        assert app.is_running is True

        await pilot.press("ctrl+q")
        await pilot.pause()
        assert isinstance(app.screen, QuitConfirmModal)
        await pilot.click("#btn-quit-confirm")
        await pilot.pause()
        assert app.is_running is False


async def test_command_history_up_down_navigation(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        inp = app.query_one("#command-input", CommandInput)
        inp.focus()

        for cmd in ("talk sera", "move lowtown_market"):
            for ch in cmd:
                await pilot.press(ch)
            await pilot.press("enter")
            await pilot.pause()

        await pilot.press("up")
        assert inp.value == "move lowtown_market"
        await pilot.press("up")
        assert inp.value == "talk sera"
        await pilot.press("down")
        assert inp.value == "move lowtown_market"
        await pilot.press("down")
        assert inp.value == ""


async def test_view_switching_keys_no_input_conflict(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        inp = app.query_one("#command-input", CommandInput)
        inp.focus()

        # Pressing '2' while focused types into input, does NOT switch view
        await pilot.press("2")
        await pilot.pause()
        assert inp.value == "2"
        assert app.current_view == "world"

        # Clear, Esc to blur, then '2' switches to character view
        inp.value = ""
        await pilot.press("escape")
        await pilot.press("2")
        await pilot.pause()
        assert app.current_view == "character"

        # Re-focus input, F6 switches to combat without typing into input
        inp.focus()
        await pilot.press("f6")
        await pilot.pause()
        assert app.current_view == "combat"
        assert inp.value == ""


async def test_compact_80x24_terminal_layout(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        for selector in ("#nav-bar", "#tutorial-hud", "#view-content", "#command-log", "#command-input"):
            w = app.query_one(selector)
            assert w.region.width > 0, f"{selector} has zero width at 80x24"
            assert w.region.height > 0, f"{selector} has zero height at 80x24"
        inp = app.query_one("#command-input")
        assert inp.region.bottom <= 24
        assert inp.region.right <= 80

        # All 8 nav buttons must fit within 80 columns and #btn-inventory must be clickable
        for view_id in ("world", "character", "health", "party", "combat", "factions", "journal", "inventory"):
            btn = app.query_one(f"#btn-{view_id}")
            assert btn.region.x >= 0, f"#btn-{view_id} x < 0 at 80x24: {btn.region}"
            assert btn.region.right <= 80, f"#btn-{view_id} clipped at 80x24: {btn.region}"
        await pilot.click("#btn-inventory")
        await pilot.pause()
        assert app.current_view == "inventory"

        # Tutorial HUD title and detail must be visible and unclipped within #tutorial-hud
        hud = app.query_one("#tutorial-hud")
        hud_title = app.query_one("#tutorial-hud-title")
        hud_detail = app.query_one("#tutorial-hud-detail")
        assert hud_title.region.width >= 40, f"#tutorial-hud-title squeezed: {hud_title.region}"
        assert hud_title.region.y >= hud.region.y
        assert hud_detail.region.height > 0
        assert hud_detail.region.bottom <= hud.region.bottom, (
            f"#tutorial-hud-detail clipped: detail={hud_detail.region}, hud={hud.region}"
        )


async def test_prologue_screen_80x24_beat2_clickability(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=True)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, PrologueScreen)

        # Beat 0 -> Beat 1 -> Beat 2
        await pilot.click("#btn-prologue-next")
        await pilot.pause(0.3)
        await pilot.click("#btn-prologue-next")
        await pilot.pause(0.3)
        assert game.get_prologue_state()["step"] == 2

        container = app.screen.query_one("#prologue-container")
        for selector in (
            "#choice-watch_investigator",
            "#choice-street_broker",
            "#choice-unbound_drifter",
            "#prologue-choice-preview",
            "#btn-prologue-begin",
            "#btn-prologue-skip",
        ):
            w = app.screen.query_one(selector)
            assert w.region.y >= container.region.y + 1, f"{selector} overflowed top: {w.region}"
            assert w.region.bottom <= container.region.bottom, f"{selector} overflowed bottom: {w.region}"

        await pilot.click("#choice-street_broker")
        await pilot.pause(0.1)
        await pilot.click("#btn-prologue-begin")
        await pilot.pause(0.1)

        assert not isinstance(app.screen, PrologueScreen)
        assert game.world.clock.prologue_completed is True
        assert game.world.flags["prologue_choice"] == "street_broker"



# ---------------------------------------------------------------------------
# Group 4: Four UI Bugfixes
# ---------------------------------------------------------------------------


async def test_combat_screen_render_does_not_mutate_active_encounter(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    assert game.combat_system.active_encounter is None
    txt = render_combat_view(game)
    assert "TACTICAL BATTLEFIELD" in txt
    assert "[" in txt and "]" in txt
    assert "Movement" in txt and "Combat" in txt
    assert game.combat_system.active_encounter is None

    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#btn-combat")
        await pilot.pause()
        assert game.combat_system.active_encounter is None


def test_main_screen_renders_dynamic_district(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    # Default start in lowtown_street -> Lowtown
    initial_txt = render_main_view(game)
    assert "Lowtown" in initial_txt
    assert "Rowan" in initial_txt

    # Move player to high_quarter -> should NOT hardcode (Lowtown)
    game.world.player.location_id = "high_quarter"
    moved_txt = render_main_view(game)
    assert "(Lowtown)" not in moved_txt
    assert "High Quarter" in moved_txt


def test_character_screen_renders_dynamic_attributes_and_personality(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    game.world.player.attributes["strength"] = 92
    game.world.player.personality["courage"] = 95
    txt = render_character_view(game)
    assert "92" in txt
    assert "95" in txt
    assert "Rowan" in txt


def test_journal_screen_renders_only_player_inventory(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    game.world.inventories.clear()
    empty_txt = render_inventory_view(game)
    assert "Inventory is empty." in empty_txt

    owned = Item(id="item_owned_ledger", name="Coded Watch Ledger", item_type="evidence", value=120.0)
    unowned = Item(id="item_unowned_crown", name="Archon Signet Ring", item_type="relic", value=999.0)
    game.world.add_item(owned)
    game.world.add_item(unowned)
    game.world.add_inventory_entry(
        InventoryEntry(character_id="player", item_id="item_owned_ledger", quantity=1)
    )

    inv_txt = render_inventory_view(game)
    assert "Coded Watch Ledger" in inv_txt
    assert "Archon Signet Ring" not in inv_txt


# ---------------------------------------------------------------------------
# Group 5: Tier 5 Adversarial UI/UX Hardening Tests
# ---------------------------------------------------------------------------


async def test_quit_confirm_and_help_modals_do_not_stack(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        await pilot.press("ctrl+q")
        await pilot.press("ctrl+q")
        await pilot.pause()
        quit_modals = [s for s in app.screen_stack if isinstance(s, QuitConfirmModal)]
        assert len(quit_modals) == 1

        await pilot.click("#btn-quit-cancel")
        await pilot.pause()
        assert not isinstance(app.screen, QuitConfirmModal)

        await pilot.press("question_mark")
        await pilot.press("f1")
        await pilot.pause()
        help_modals = [s for s in app.screen_stack if isinstance(s, HelpModal)]
        assert len(help_modals) == 1

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpModal)


async def test_prologue_replay_via_hud_button_and_command(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    game.execute_command("skip prologue")
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert not isinstance(app.screen, PrologueScreen)

        await pilot.click("#btn-hud-prologue")
        await pilot.pause()
        assert isinstance(app.screen, PrologueScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, PrologueScreen)

        inp = app.query_one("#command-input", CommandInput)
        inp.focus()
        for ch in "prologue":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, PrologueScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, PrologueScreen)

        inp.focus()
        for ch in "replay prologue":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, PrologueScreen)


async def test_prologue_screen_isolates_app_bindings(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, PrologueScreen)
        assert app.current_view == "world"

        for key in ("2", "alt+3", "f6", "q", "question_mark"):
            await pilot.press(key)
        await pilot.pause()

        assert app.current_view == "world"
        assert isinstance(app.screen, PrologueScreen)


async def test_alt_and_function_key_view_bindings_all_eight_views(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        inp = app.query_one("#command-input", CommandInput)
        inp.focus()

        for idx, (view_id, _) in enumerate(VIEWS, start=1):
            await pilot.press(f"alt+{idx}")
            await pilot.pause()
            assert app.current_view == view_id
            assert inp.value == ""

        for idx, (view_id, _) in enumerate(VIEWS, start=2):
            await pilot.press(f"f{idx}")
            await pilot.pause()
            assert app.current_view == view_id
            assert inp.value == ""


async def test_command_input_history_empty_dup_and_whitespace_edge_cases(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        inp = app.query_one("#command-input", CommandInput)
        inp.focus()
        inp.value = "draft"

        await pilot.press("up")
        await pilot.press("down")
        assert inp.value == "draft"

        inp.add_to_history("look")
        inp.add_to_history("  look  ")
        inp.add_to_history("   ")
        assert inp.history == ["look"]


def test_render_main_view_unusual_and_empty_world_states() -> None:
    clock = SimpleNamespace(year=1423, act="ACT_I", format_datetime=lambda: "Day 1, 08:00")
    minimal_world = SimpleNamespace(
        player=None,
        player_party=None,
        locations={},
        districts={},
        characters={},
        companions={},
        quests={},
        event_bus=None,
        clock=clock,
    )
    session = SimpleNamespace(world=minimal_world)
    txt = render_main_view(session)
    assert "THE CITY REMEMBERS" in txt
    assert "Rowan" in txt

    minimal_world.player = SimpleNamespace(id="player", name="Rowan", location_id=None)
    txt2 = render_main_view(session)
    assert "Lowtown" in txt2

    party_txt = render_party_view(session)
    assert "PARTY" in party_txt.upper() or "Rowan" in party_txt


async def test_command_input_exit_and_cli_entry(tmp_path: Path, capsys) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        inp = app.query_one("#command-input", CommandInput)
        inp.focus()
        for ch in "exit":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        assert app.is_running is False

    main(["--cli"])
    out_cli = capsys.readouterr().out
    assert "THE CITY REMEMBERS" in out_cli

    main(["talk", "sera"])
    out_cmd = capsys.readouterr().out
    assert len(out_cmd.strip()) > 0


async def test_quick_actions_mouse_navigation_and_execution(tmp_path: Path) -> None:
    game = _make_game(tmp_path)
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # Quick actions bar should contain clickable buttons including tutorial suggested action and universal actions
        assert len(app._quick_cmd_map) >= 4
        assert any(cmd == "rest 8h" for cmd in app._quick_cmd_map.values())
        assert any(cmd == "save" for cmd in app._quick_cmd_map.values())

        # Click the first quick action button (tutorial suggested command or Go/Talk)
        first_btn_id = "#qa-0"
        first_cmd = app._quick_cmd_map["qa-0"]
        t_before = game.world.clock.timestamp
        await pilot.click(first_btn_id)
        await pilot.pause()

        # Verify command executed without typing
        if first_cmd.startswith(("move ", "talk ", "rest ", "wait ")):
            assert game.world.clock.timestamp >= t_before
        # Verify quick actions refreshed cleanly
        assert len(app._quick_cmd_map) >= 4


