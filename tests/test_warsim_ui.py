"""Async Textual pilot tests for M4 Warsim UI: TitleScreen, Action Deck, Combat Clash Viewport, and 80x24 Compact Mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.game import Game
from core.settings import GameSettings, load_settings
from entities.character import Character
from main import CityRemembersApp, create_app
from persistence.database import Database
from persistence.save_manager import SaveManager
from ui.combat_screen import render_combat_view
from ui.title_screen import TitleScreen


@pytest.mark.asyncio
async def test_title_screen_navigation_settings_and_new_game_wizard(tmp_path: Path) -> None:
    """TitleScreen supports 1-5 & 0, Settings cheat persistence, About, Load/Delete, and New Game Wizard."""
    settings_path = tmp_path / "settings.json"
    db_path = tmp_path / "saves.db"
    db = Database(db_path)
    sm = SaveManager(db)

    # 1. Verify Continue disabled when no saves exist, then About & Settings
    results: list[Any] = []

    class _HostApp(CityRemembersApp):
        pass

    app = create_app(game=Game(db=db, save_manager=sm, settings=GameSettings()), show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        ts = TitleScreen(
            settings=GameSettings(),
            save_manager=sm,
            settings_path=settings_path,
            db_path=db_path,
        )
        app.push_screen(ts, callback=results.append)
        await pilot.pause()

        cont_btn = ts.query_one("#title-btn-1")
        assert cont_btn.disabled is True

        # [5] About & Controls Guide -> [0] Back
        await pilot.press("5")
        await pilot.pause()
        assert ts.mode == "about"
        await pilot.press("0")
        await pilot.pause()
        assert ts.mode == "main"

        # [4] Settings -> [2] Toggle Cheat/Debug ON -> [0] Save & Return
        await pilot.press("4")
        await pilot.pause()
        assert ts.mode == "settings"
        await pilot.press("2")
        await pilot.pause()
        assert ts.settings.enable_debug_cheat is True
        await pilot.press("0")
        await pilot.pause()
        assert ts.mode == "main"
        persisted = load_settings(settings_path)
        assert persisted.enable_debug_cheat is True

        # [2] New Game Wizard -> Difficulty [3] Gritty -> BG [2] Smuggler -> KS [1] Coin Purse -> [2] Skip Prologue
        await pilot.press("2")
        await pilot.pause()
        assert ts.mode == "wizard_difficulty"
        await pilot.press("3")
        await pilot.pause()
        assert ts.mode == "wizard_background"
        await pilot.press("2")
        await pilot.pause()
        assert ts.mode == "wizard_keepsake"
        await pilot.press("1")
        await pilot.pause()
        assert ts.mode == "wizard_onboarding"
        await pilot.click("#title-btn-2")
        await pilot.pause()

        assert len(results) == 1
        res = results[0]
        assert res["action"] == "new_game"
        assert res["difficulty"] == "gritty"
        assert res["background"] == "dockside_smuggler"
        assert res["keepsake"] == "coin_purse"
        assert res["skip_prologue"] is True


@pytest.mark.asyncio
async def test_title_screen_load_and_delete_slot_at_80x24(tmp_path: Path) -> None:
    """TitleScreen Load Game lists slots, supports [9] Delete Slot, and fits cleanly at 80x24."""
    settings_path = tmp_path / "settings.json"
    db = Database(tmp_path / "saves.db")
    sm = SaveManager(db)
    g = Game(db=db, save_manager=sm, settings=GameSettings())
    sm.save_game(g.world, slot="slot_alpha")

    results: list[Any] = []
    app = create_app(game=g, show_prologue=False)
    async with app.run_test(size=(80, 24)) as pilot:
        ts = TitleScreen(
            settings=GameSettings(),
            save_manager=sm,
            settings_path=settings_path,
        )
        app.push_screen(ts, callback=results.append)
        await pilot.pause()

        assert ts.has_class("compact")
        cont_btn = ts.query_one("#title-btn-1")
        assert cont_btn.disabled is False

        # Open Load Game [3], toggle delete [9], delete slot [1]
        await pilot.press("3")
        await pilot.pause()
        assert ts.mode == "load_game"
        assert len(sm.list_save_slots()) == 1

        await pilot.press("9")
        await pilot.pause()
        assert ts._delete_mode is True

        await pilot.press("1")
        await pilot.pause()
        assert len(sm.list_save_slots()) == 0

        # [0] Back to main
        await pilot.press("0")
        await pilot.pause()
        assert ts.mode == "main"


@pytest.mark.asyncio
async def test_warsim_mode_zero_typing_navigation_and_gated_debug(tmp_path: Path) -> None:
    """warsim_mode=True hides #command-input, shows #status-banner & #action-deck, and gates [0] Debug Menu."""
    db = Database(tmp_path / "warsim.db")
    sm = SaveManager(db)
    settings = GameSettings(enable_debug_cheat=False)
    game = Game(db=db, save_manager=sm, settings=settings, skip_prologue=True)
    app = create_app(game=game, show_prologue=False, show_title=False, warsim_mode=True)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        assert app.query_one("#command-input").display is False
        assert app.query_one("#status-banner").display is True
        assert app.query_one("#action-deck").display is True
        assert not app.has_class("compact")

        # When debug is OFF, [0] is Pass Time / Rest & City Digest
        btn_0 = app.query_one("#action-0")
        assert "Pass Time" in str(btn_0.label)

        # Navigate to Travel [1], then Back [0]
        await pilot.press("1")
        await pilot.pause()
        assert "Travel" in str(app.query_one("#view-content").content)
        await pilot.click("#action-0")
        await pilot.pause()

        # F3 switches to Character view without breaking Warsim mode
        await pilot.press("f3")
        await pilot.pause()
        assert app.current_view == "character"

        # Enable debug cheat in settings, return to world, press 0 -> Debug Menu -> 1 (+500 Gold)
        game.settings.enable_debug_cheat = True
        app.action_switch_view("world")
        app.refresh_action_deck()
        await pilot.pause()
        assert "Cheat & Debug Menu" in str(app.query_one("#action-0").label)

        gold_before = game.world.player.needs["wealth"]
        await pilot.press("0")
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        assert game.world.player.needs["wealth"] == pytest.approx(gold_before + 500.0)


@pytest.mark.asyncio
async def test_warsim_dialogue_and_combat_clash_viewport_at_80x24(tmp_path: Path) -> None:
    """Interactive Dialogue and Combat Clash Viewport render cleanly and remain clickable at (80, 24)."""
    db = Database(tmp_path / "clash.db")
    sm = SaveManager(db)
    game = Game(db=db, save_manager=sm, skip_prologue=True)

    # Verify render_combat_view(game) preserves preview strings when active_encounter is None
    preview_txt = render_combat_view(game)
    assert "TACTICAL BATTLEFIELD" in preview_txt
    assert "[" in preview_txt and "]" in preview_txt
    assert "Movement" in preview_txt and "Combat" in preview_txt
    assert game.combat_system.active_encounter is None

    app = create_app(game=game, show_prologue=False, show_title=False, warsim_mode=True)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.has_class("compact")

        # Verify Action Deck buttons have positive layout dimensions at 80x24
        btn_1 = app.query_one("#action-1")
        assert btn_1.region.width > 0 and btn_1.region.height > 0

        # [2] Speak with Someone Nearby -> [1] First NPC -> Dialogue Mode
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        assert game.menu_engine.active_dialogue is not None
        view_text = str(app.query_one("#view-content").content)
        assert "Trust" in view_text

        # [8] Provoke / Attack -> Enters Combat Clash Viewport
        await pilot.press("8")
        await pilot.pause()
        assert game.menu_engine.active_clash is not None
        clash_text = str(app.query_one("#view-content").content)
        assert "COMBAT CLASH" in clash_text
        assert "PARTY" in clash_text and "ENEMIES" in clash_text
        assert "Consc:" in clash_text and "Morale" in clash_text

        # Execute [1] Balanced Strike via click
        await pilot.click("#action-1")
        await pilot.pause()
        clash_text_after = str(app.query_one("#view-content").content)
        assert "Combat Log" in clash_text_after or game.menu_engine.active_clash is None
