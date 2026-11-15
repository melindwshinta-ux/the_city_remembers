"""Unit & integration tests for M3: Game integration, DialogueEngine, and MenuEngine."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.dialogue_engine import DialogueEngine
from core.game import Game
from core.menu_engine import MenuEngine
from core.settings import GameSettings


def _make_game(tmp_path: Path, **kwargs) -> Game:
    return Game(seed=482193, db_path=tmp_path / "test_m3.db", **kwargs)


def test_game_init_settings_setup_and_daily_digest(tmp_path: Path) -> None:
    g = _make_game(
        tmp_path,
        difficulty="gritty",
        background="field_chirurgeon",
        keepsake="coin_purse",
        skip_prologue=True,
    )
    assert g.settings.difficulty == "gritty"
    assert g.world.flags["difficulty"] == "gritty"
    assert g.world.flags["background"] == "field_chirurgeon"
    assert g.world.flags["keepsake"] == "coin_purse"
    assert g.world.flags["prologue"]["completed"] is True
    assert g.world.player.needs["wealth"] == pytest.approx(250.0)
    assert g.debug_mode is not None
    assert g.menu_engine is not None

    # Advancing 1440 minutes triggers FREQ_ECONOMY -> process_daily_tick -> last_daily_digest
    g.simulation.advance_time(1440, world=g.world)
    digest = g.world.flags.get("last_daily_digest")
    assert isinstance(digest, dict)
    assert digest["day"] >= 1
    assert len(digest["summary_lines"]) >= 1

    # Save, load, and verify _rebind_world keeps economy tick & resets menu
    g.execute_command("save m3_slot")
    res = g.execute_command("load m3_slot")
    assert res["success"] is True
    g.simulation.advance_time(1440, world=g.world)
    assert "last_daily_digest" in g.world.flags


def test_dialogue_engine_view_and_all_choices(tmp_path: Path) -> None:
    g = _make_game(tmp_path)
    g.world.flags["epithet"] = "Lowtown Sleuth"
    g.health_system.apply_injury(g.world.characters["npc_voss"], "left_leg", "broken_leg", severity=0.8)

    dlg = DialogueEngine(g, "npc_voss")
    view = dlg.get_view()
    assert view["name"] == "Captain Garrick Voss"
    assert view["faction"] == "City Guard"
    assert any("Left Leg" in inj for inj in view["visible_injuries"])
    assert set(view["axes"].keys()) == {"trust", "respect", "affection", "resentment", "fear", "dependency"}
    assert "broke my leg" in view["greeting"].lower()
    assert "Lowtown Sleuth" in view["greeting"]
    assert [o["key"] for o in view["options"]] == ["1", "2", "3", "4", "5", "6", "7", "8", "0"]

    # [1] Rumors -> records memory on player
    mem_before = len(g.world.player.memories)
    r1 = dlg.choose("1")
    assert r1["success"] is True
    assert len(g.world.player.memories) == mem_before + 1

    # [2] Quest Business -> completes investigate_crime_scene
    r2 = dlg.choose("2")
    assert r2["success"] is True
    q_blood = g.world.quests["quest_blood_in_lowtown"]
    assert any(o["id"] == "investigate_crime_scene" and o["completed"] for o in q_blood.objectives)

    # [3] Persuade & [4] Intimidate with God Mode 100%
    g.world.flags["god_mode"] = True
    assert "[Persuade 100%]" in dlg.get_view()["options"][2]["label"]
    r3 = dlg.choose("3")
    assert r3["success"] is True
    r4 = dlg.choose("4")
    assert r4["success"] is True
    assert g.world.flags["intimidated_npcs"]["npc_voss"] is True
    g.world.flags["god_mode"] = False

    # [5] Bribe (25g) and locked check when poor
    gold_before = g.world.player.needs["wealth"]
    r5 = dlg.choose("5")
    assert r5["success"] is True
    assert g.world.player.needs["wealth"] == pytest.approx(gold_before - 25.0)

    g.world.player.needs["wealth"] = 5.0
    assert dlg.get_view()["options"][4]["enabled"] is False
    assert "Locked" in dlg.get_view()["options"][4]["tags"][0]

    # [6] Companion Action (Sera is in party)
    r6 = dlg.choose("6")
    assert r6["success"] is True
    assert "Sera" in r6["message"]

    # [7] Companion recruit/dismiss toggle
    comp_dlg = DialogueEngine(g, "comp_elira")
    assert "comp_elira" not in g.world.player_party
    r7 = comp_dlg.choose("7")
    assert r7["success"] is True
    assert "comp_elira" in g.world.player_party

    # [0] Leave Conversation
    r0 = comp_dlg.choose("0")
    assert r0["closed"] is True

    # [8] Provoke / Attack -> ClashSession
    r8 = dlg.choose("8")
    assert r8["enter_combat"] is True
    assert r8["closed"] is True
    assert r8["clash_session"] is not None


def test_menu_engine_root_hub_debug_gating_and_pagination(tmp_path: Path) -> None:
    g = _make_game(tmp_path)
    menu = g.menu_engine

    # Default: enable_debug_cheat is False -> [0] is Pass Time / Rest & City Digest
    hub = menu.get_screen()
    assert hub["mode"] == "hub"
    opt0 = next(o for o in hub["options"] if o["key"] == "0")
    assert "Pass Time" in opt0["label"]

    # Selecting [0] advances 1 day and updates last_daily_digest
    res0 = menu.select("0")
    assert res0["success"] is True
    assert "last_daily_digest" in g.world.flags

    # Enable debug cheat -> [0] becomes Cheat & Debug Menu
    g.settings.enable_debug_cheat = True
    hub2 = menu.get_screen()
    opt0_dbg = next(o for o in hub2["options"] if o["key"] == "0")
    assert "Cheat & Debug Menu" in opt0_dbg["label"]

    menu.select("0")
    assert menu.get_screen()["title"] == "Cheat & Debug Menu"
    gold_before = g.world.player.needs["wealth"]
    menu.select("1")  # +500 Gold
    assert g.world.player.needs["wealth"] == pytest.approx(gold_before + 500.0)
    menu.select("0")  # Back to Root Hub
    assert menu.get_screen()["mode"] == "hub"

    # Pagination test on Politics Menu (11 items -> page 1 has [1]-[8], [9] Next Page, [0] Back)
    menu.select("5")
    pol = menu.get_screen()
    assert any(o["key"] == "9" and "Next Page" in o["label"] for o in pol["options"])
    menu.select("9")
    pol_p2 = menu.get_screen()
    assert "Page 2" in menu.last_message or any(o["key"] == "1" for o in pol_p2["options"])
    menu.select("0")


def test_menu_engine_all_categories_and_combat_clash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.menu_engine.save_settings", lambda s: tmp_path / "settings.json")
    g = _make_game(tmp_path)
    g.world.player.needs["wealth"] = 1000.0
    menu = g.menu_engine

    # [1] Travel & Explore
    menu.select("1")
    assert menu.get_screen()["title"] == "Travel & Explore District"
    menu.select("1")  # Move to first connected location (lowtown_market)
    assert g.world.player.location_id == "lowtown_market"
    menu.select("0")

    # [3] Local Activities (at Market -> Commodity Market)
    menu.select("3")
    menu.select("1")  # Trade District Commodities
    assert "Commodity Market" in menu.get_screen()["title"]
    menu.select("1")  # Grain & Rations
    menu.select("1")  # Buy 1
    assert g.world.commodities.get("grain_rations", 0) >= 1
    menu.select("0")
    menu.select("0")
    menu.select("0")

    # [4] Party, Anatomy & Medicine
    menu.select("4")
    menu.select("1")  # Anatomy detail
    assert "29-Part" in menu.get_screen()["title"]
    menu.select("0")
    menu.select("4")  # Campfire Counsel
    menu.select("1")  # Counsel first companion
    assert menu.last_message.startswith("Counselled")
    menu.select("0")
    menu.select("0")

    # [6] Trade, Property & Economy -> Properties
    menu.select("6")
    menu.select("2")  # Properties
    menu.select("1")  # Buy Lowtown Safehouse
    assert "lowtown_safehouse" in g.world.properties
    menu.select("0")
    menu.select("0")

    # [7] Quests, Rumors & Chronicle
    menu.select("7")
    menu.select("3")  # View Chronicle
    assert "Chronicle" in menu.last_message
    menu.select("0")

    # [8] Character Sheet
    menu.select("8")
    assert menu.get_screen()["title"] == "Character Sheet & Reputation"
    menu.select("0")

    # [9] System & Settings
    menu.select("9")
    menu.select("4")  # Settings
    assert menu.get_screen()["title"] == "Settings"
    menu.select("2")  # Toggle Debug Cheat ON
    assert g.settings.enable_debug_cheat is True
    menu.select("0")
    menu.select("0")

    # [2] Speak with Someone Nearby -> Dialogue -> [8] Attack -> Combat Clash -> [3] Aimed Limb -> [0] Retreat
    menu.select("2")
    assert menu.get_screen()["title"] == "Speak with Someone Nearby"
    menu.select("1")  # Speak with first nearby person
    assert menu.get_screen()["mode"] == "dialogue"
    menu.select("8")  # Provoke / Attack -> Combat Clash
    assert menu.get_screen()["mode"] == "combat"

    # [3] Aimed Limb sub-menu
    menu.select("3")
    aim_scr = menu.get_screen()
    assert any("Head" in o["label"] for o in aim_scr["options"])
    menu.select("2")  # Arms
    assert menu.get_screen()["mode"] in ("combat", "hub")

    # If still in combat, test [4] Defend & [0] Retreat
    if menu.get_screen()["mode"] == "combat":
        menu.select("4")
        if menu.get_screen()["mode"] == "combat":
            g.world.rng.stream("clash_retreat").seed(1)
            menu.select("0")


def test_menu_engine_quick_save_succeeds(tmp_path: Path) -> None:
    g = _make_game(tmp_path)
    menu = g.menu_engine

    # [9] System, Save / Load & Settings -> [1] Quick Save
    menu.select("9")
    assert menu.get_screen()["title"] == "System, Save / Load & Settings"
    res = menu.select("1")
    assert res["success"] is True
    assert menu.last_message == "Game saved."
    slot_names = {s["slot"] for s in g.save_manager.list_save_slots()}
    assert "autosave" in slot_names
    assert "default" in slot_names


def test_menu_engine_repay_defaulted_loan(tmp_path: Path) -> None:
    g = _make_game(tmp_path)
    menu = g.menu_engine

    loan_res = g.economy_system.take_loan("player", 100.0, "merchant_consortium", world=g.world)
    assert loan_res["success"] is True
    loan = g.world.loans[0]
    loan["status"] = "defaulted"
    g.world.player.needs["wealth"] = 500.0

    # [6] Trade, Property & Economy -> [3] Consortium & Syndicate Loans -> [3] Repay defaulted loan
    menu.select("6")
    menu.select("3")
    loan_screen = menu.get_screen()
    assert loan_screen["title"] == "Consortium & Syndicate Finance"
    repay_opt = next((o for o in loan_screen["options"] if loan["id"] in o["label"]), None)
    assert repay_opt is not None
    assert "DEFAULTED" in repay_opt["tags"]
    assert repay_opt["enabled"] is True

    res = menu.select(repay_opt["key"])
    assert res["success"] is True
    assert loan["status"] == "paid"

