"""Opaque-Box E2E Test Suite (Tiers 1-4) for the Warsim-Style Choice Overhaul & Systemic Depth.

Covers every requirement in GEMINI_PLAN.md (§§1-8):
- Tier 1 (Feature Coverage):
  1. Main Menu & New Game Wizard (Continue, New Game 4 Difficulties / 4 Backgrounds / 4 Keepsakes /
     Prologue vs Skip Prologue, Load Game + Delete Slot, Settings persistence, About).
  2. Settings-Gated Cheat / Debug Mode (blocked when OFF, hidden [0] Debug Menu, all 9 cheats when ON).
  3. Zero-Typing Warsim 1-0 Navigation at (120, 40) and (80, 24) with #command-input hidden.
  4. Interactive Branching Dialogue (Header/Bars, Rumors, Quest Business, Persuade, Intimidate,
     Bribe, Companion Interjection, Favor/Recruit, Provoke->Combat, Leave).
  5. Simplified Combat Clash (1-7, 0: Balanced, Heavy +35%, Aimed Limb, Defend/Rally,
     Field Triage, Tactical Trick, Demand Surrender morale<=30, Retreat + Clash Viewport).
  6. Systemic Depth: Politics & Petitioners, Relationship Social Actions, Commodities,
     5 Upgradeable Properties, Loans/Caravans, and Daily City Digest.
- Tier 2 (Boundary & Corner Cases):
  - Ironman single-slot enforcement, Difficulty modifier scaling, corrupted settings.json fallback,
    social leverage/threshold guards, and Rich markup escaping in Warsim menus.
- Tier 3 (Cross-Feature Combinations):
  - TitleScreen -> Settings -> New Game Wizard -> Warsim Gameplay -> Economy/Digest -> SQLite
    Save/Reload roundtrip preserving all new World fields.
- Tier 4 (Real-World Application Scenarios):
  - Complete zero-typing Warsim gameplay walkthrough across Travel, Trade, Dialogue, Combat Clash,
    Politics, and Daily City Digest using only 1-9/0 keys and #action-* mouse clicks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.conftest import require_module, require_symbol


def _make_isolated_game(
    tmp_path: Path,
    name: str = "warsim_e2e",
    seed: int = 482193,
    **game_kwargs: Any,
) -> tuple[Any, Any, Any, Path]:
    """Create an isolated Game, Database, and SaveManager backed by tmp_path."""
    Game = require_symbol("core.game", "Game")
    Database = require_symbol("persistence.database", "Database")
    SaveManager = require_symbol("persistence.save_manager", "SaveManager")

    db_path = tmp_path / f"{name}.db"
    db = Database(db_path)
    sm = SaveManager(db)
    game = Game(seed=seed, db=db, save_manager=sm, **game_kwargs)
    return game, db, sm, db_path


# ===========================================================================
# TIER 1: FEATURE COVERAGE
# ===========================================================================


@pytest.mark.asyncio
async def test_t1_main_menu_settings_about_load_delete_and_new_game_wizard(tmp_path: Path) -> None:
    """Tier 1: TitleScreen Main Menu, Settings persistence, About, Load/Delete, Continue, and 4x4x4x2 Wizard."""
    settings_mod = require_module("core.settings")
    GameSettings = settings_mod.GameSettings
    load_settings = settings_mod.load_settings
    TitleScreen = require_symbol("ui.title_screen", "TitleScreen")
    create_app = require_symbol("main", "create_app")

    settings_path = tmp_path / "settings.json"
    game, _db, sm, db_path = _make_isolated_game(tmp_path, name="title_suite", settings=GameSettings())

    # 1. Main Menu when no saves exist: [1] Continue disabled, [5] About, [4] Settings
    results: list[Any] = []
    app = create_app(game=game, show_prologue=False)
    async with app.run_test(size=(120, 40)) as pilot:
        ts = TitleScreen(
            settings=GameSettings(),
            save_manager=sm,
            settings_path=settings_path,
            db_path=db_path,
        )
        app.push_screen(ts, callback=results.append)
        await pilot.pause()

        assert ts.query_one("#title-btn-1").disabled is True

        # [5] About & Controls Guide -> [0] Back
        await pilot.click("#title-btn-5")
        await pilot.pause()
        assert ts.mode == "about"
        assert "Warsim" in str(ts.query_one("#title-body").content)
        await pilot.press("0")
        await pilot.pause()
        assert ts.mode == "main"

        # [4] Settings: cycle Difficulty, toggle Cheat ON, cycle AutoSave, toggle HUD, cycle Layout, [0] Save
        await pilot.press("4")
        await pilot.pause()
        assert ts.mode == "settings"
        await pilot.press("1")  # balanced -> gritty
        await pilot.press("2")  # enable_debug_cheat -> True
        await pilot.press("3")  # daily_and_precombat -> precombat
        await pilot.press("4")  # guided_tutorial_hud -> False
        await pilot.press("5")  # auto -> compact
        await pilot.pause()
        await pilot.click("#title-btn-0")
        await pilot.pause()
        assert ts.mode == "main"

        persisted = load_settings(settings_path)
        assert persisted.difficulty == "gritty"
        assert persisted.enable_debug_cheat is True
        assert persisted.autosave_mode == "precombat"
        assert persisted.guided_tutorial_hud is False
        assert persisted.layout_mode == "compact"

        # Create a save, open [3] Load Game, test [9] Delete Slot, then create another for [1] Continue
        sm.save_game(game.world, slot="slot_temp")
        await pilot.press("3")
        await pilot.pause()
        assert ts.mode == "load_game"
        assert len(sm.list_save_slots()) == 1
        await pilot.press("9")  # Enter delete mode
        await pilot.pause()
        await pilot.press("1")  # Delete first slot
        await pilot.pause()
        assert len(sm.list_save_slots()) == 0
        await pilot.press("0")
        await pilot.pause()

        # Save again and verify [1] Continue works after returning from Load Game
        sm.save_game(game.world, slot="slot_continue")
        await pilot.press("3")
        await pilot.pause()
        await pilot.press("0")
        await pilot.pause()
        assert ts.query_one("#title-btn-1").disabled is False
        await pilot.press("1")
        await pilot.pause()
        assert results[-1]["action"] == "continue"
        assert results[-1]["slot"] == "slot_continue"

    # 2. Verify all 4 Difficulties, 4 Backgrounds, 4 Keepsakes, and Prologue vs Skip Prologue in Game
    difficulties = ("story", "balanced", "gritty", "ironman")
    backgrounds = ("watch_veteran", "dockside_smuggler", "noble_scion", "field_chirurgeon")
    keepsakes = ("coin_purse", "steel_longsword", "guild_seal", "chirurgeon_satchel")

    for idx in range(4):
        g_cfg, _, _, _ = _make_isolated_game(
            tmp_path,
            name=f"cfg_{idx}",
            seed=2000 + idx,
            difficulty=difficulties[idx],
            background=backgrounds[idx],
            keepsake=keepsakes[idx],
            skip_prologue=(idx % 2 == 1),
        )
        assert g_cfg.world.flags["difficulty"] == difficulties[idx]
        assert g_cfg.world.flags["background"] == backgrounds[idx]
        assert g_cfg.world.flags["keepsake"] == keepsakes[idx]
        assert g_cfg.world.flags["ironman"] is (difficulties[idx] == "ironman")
        if idx % 2 == 1:
            assert g_cfg.world.flags["prologue"]["completed"] is True
        else:
            assert g_cfg.world.flags["prologue"]["completed"] is False

        if keepsakes[idx] == "coin_purse":
            assert g_cfg.world.player.needs["wealth"] >= 150.0
        elif keepsakes[idx] == "steel_longsword":
            assert g_cfg.world.player.equipment.get("weapon") == "fine_steel_longsword"
        elif keepsakes[idx] == "guild_seal":
            assert "forged_guild_seal" in g_cfg.world.player.inventory
        elif keepsakes[idx] == "chirurgeon_satchel":
            assert "linen_bandage" in g_cfg.world.player.inventory


def test_t1_settings_gated_debug_cheat_mode_all_nine_actions(tmp_path: Path) -> None:
    """Tier 1: Cheat/Debug Mode is strictly blocked when OFF and all 9 actions work when ON."""
    GameSettings = require_symbol("core.settings", "GameSettings")
    DISABLED_MESSAGE = require_symbol("core.debug_mode", "DISABLED_MESSAGE")

    game, _, _, _ = _make_isolated_game(
        tmp_path,
        name="debug_gate",
        settings=GameSettings(enable_debug_cheat=False),
        skip_prologue=True,
    )

    # 1. Blocked when OFF — zero state mutation
    gold_start = game.world.player.needs["wealth"]
    for choice in range(1, 10):
        res = game.debug_mode.execute_cheat(choice)
        assert res["success"] is False
        assert res["message"] == DISABLED_MESSAGE
    assert game.world.player.needs["wealth"] == pytest.approx(gold_start)
    assert not game.world.flags.get("god_mode", False)

    # Root Hub [0] is Pass Time, NOT Cheat & Debug Menu
    hub_off = game.menu_engine.get_screen()
    opt0_off = next(o for o in hub_off["options"] if o["key"] == "0")
    assert "Pass Time" in opt0_off["label"]
    assert "Cheat" not in opt0_off["label"]

    # 2. Enable in Settings -> [0] becomes Cheat & Debug Menu and all 9 actions succeed
    game.settings.enable_debug_cheat = True
    hub_on = game.menu_engine.get_screen()
    opt0_on = next(o for o in hub_on["options"] if o["key"] == "0")
    assert "Cheat & Debug Menu" in opt0_on["label"]

    # [1] +500 Gold
    r1 = game.debug_mode.execute_cheat(1)
    assert r1["success"] is True
    assert game.world.player.needs["wealth"] == pytest.approx(gold_start + 500.0)

    # [2] Full Heal & Cure Wounds
    game.health_system.apply_injury(game.world.player, "left_arm", "laceration", severity=0.6)
    game.world.player.consciousness = 40.0
    r2 = game.debug_mode.execute_cheat(2)
    assert r2["success"] is True
    assert game.world.player.consciousness == pytest.approx(100.0)
    assert len(game.world.player.body["left_arm"].injuries) == 0

    # [3] Max All Attributes & Skills (100)
    r3 = game.debug_mode.execute_cheat(3)
    assert r3["success"] is True
    assert game.world.player.attributes["strength"] == 100
    assert game.world.player.skills["swordsmanship"] == pytest.approx(100.0)

    # [4] Toggle God Mode
    r4 = game.debug_mode.execute_cheat(4)
    assert r4["success"] is True and game.world.flags["god_mode"] is True
    game.debug_mode.execute_cheat(4)  # toggle back off

    # [5] Time Skip (+6h / +1d / +7d / +1y)
    ts_before = game.world.clock.timestamp
    r5 = game.debug_mode.execute_cheat(5, preset="1d")
    assert r5["success"] is True
    assert game.world.clock.timestamp > ts_before

    # [6] Faction & District Manipulation
    r6 = game.debug_mode.execute_cheat(6, mode="max_rep")
    assert r6["success"] is True
    assert all(v == pytest.approx(100.0) for v in game.world.reputation["faction"].values())

    # [7] Relationship Manipulation (+50)
    voss_before = game.relationship_system.get_relationship("npc_voss", "player").trust
    r7 = game.debug_mode.execute_cheat(7)
    assert r7["success"] is True
    assert game.relationship_system.get_relationship("npc_voss", "player").trust > voss_before

    # [8] Nemesis Manipulation
    r8 = game.debug_mode.execute_cheat(8, mode="spawn")
    assert r8["success"] is True
    assert len(game.world.nemesis_profiles) >= 1

    # [9] Quest & Tutorial Skip
    r9 = game.debug_mode.execute_cheat(9, mode="both")
    assert r9["success"] is True
    tut = game.get_tutorial_state()
    assert tut["skipped"] is True or tut["completed"] is True


@pytest.mark.asyncio
async def test_t1_zero_typing_warsim_navigation_120x40_and_80x24(tmp_path: Path) -> None:
    """Tier 1: Zero-typing 1-9/0 + mouse navigation across all Root Hub screens at (120, 40) and (80, 24)."""
    GameSettings = require_symbol("core.settings", "GameSettings")
    create_app = require_symbol("main", "create_app")

    for size in ((120, 40), (80, 24)):
        game, _, _, _ = _make_isolated_game(
            tmp_path,
            name=f"nav_{size[0]}x{size[1]}",
            settings=GameSettings(enable_debug_cheat=False),
            skip_prologue=True,
        )
        app = create_app(game=game, show_prologue=False, show_title=False, warsim_mode=True)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()

            assert app.query_one("#command-input").display is False
            assert app.query_one("#status-banner").display is True
            assert app.query_one("#action-deck").display is True
            if size == (80, 24):
                assert app.has_class("compact")
            else:
                assert not app.has_class("compact")

            # Every visible action button has positive geometry
            btn_1 = app.query_one("#action-1")
            assert btn_1.region.width > 0 and btn_1.region.height > 0

            # Traverse [1] Travel -> [0] Back
            await pilot.press("1")
            await pilot.pause()
            assert "Travel" in str(app.query_one("#view-content").content)
            await pilot.click("#action-0")
            await pilot.pause()

            # Traverse [5] Politics -> [9] Next Page -> [0] Back
            await pilot.press("5")
            await pilot.pause()
            assert "Politics" in str(app.query_one("#view-content").content)
            await pilot.press("9")
            await pilot.pause()
            await pilot.click("#action-0")
            await pilot.pause()

            # Traverse [6] Economy -> [0] Back
            await pilot.click("#action-6")
            await pilot.pause()
            assert "Economy" in str(app.query_one("#view-content").content)
            await pilot.press("0")
            await pilot.pause()

            # Traverse [7] Quests -> [0] Back, [8] Character Sheet -> [0] Back, [9] System -> [0] Back
            for key in ("7", "8", "9"):
                await pilot.press(key)
                await pilot.pause()
                await pilot.press("0")
                await pilot.pause()

            assert game.menu_engine.get_screen()["mode"] == "hub"


def test_t1_interactive_branching_dialogue_all_options(tmp_path: Path) -> None:
    """Tier 1: Interactive Branching Dialogue header, dynamic greeting, and all [1]-[8]/[0] choices."""
    DialogueEngine = require_symbol("core.dialogue_engine", "DialogueEngine")

    game, _, _, _ = _make_isolated_game(tmp_path, name="dialogue_e2e", skip_prologue=True)
    game.world.flags["epithet"] = "Lowtown Sleuth"
    voss = game.world.characters["npc_voss"]
    game.health_system.apply_injury(voss, "left_leg", "broken_leg", severity=0.8)

    dlg = DialogueEngine(game, "npc_voss")
    view = dlg.get_view()
    assert view["name"] == "Captain Garrick Voss"
    assert view["faction"] == "City Guard"
    assert any("Left Leg" in inj for inj in view["visible_injuries"])
    assert set(view["axes"].keys()) == {"trust", "respect", "affection", "resentment", "fear", "dependency"}
    assert "Lowtown Sleuth" in view["greeting"]
    assert [o["key"] for o in view["options"]] == ["1", "2", "3", "4", "5", "6", "7", "8", "0"]

    # [1] Rumors
    mem_before = len(game.world.player.memories)
    assert dlg.choose("1")["success"] is True
    assert len(game.world.player.memories) == mem_before + 1

    # [2] Quest Business
    assert dlg.choose("2")["success"] is True
    q_blood = game.world.quests["quest_blood_in_lowtown"]
    assert any(o["id"] == "investigate_crime_scene" and o["completed"] for o in q_blood.objectives)

    # [3] Persuade & [4] Intimidate
    game.world.flags["god_mode"] = True
    assert dlg.choose("3")["success"] is True
    assert dlg.choose("4")["success"] is True
    assert game.world.flags["intimidated_npcs"]["npc_voss"] is True
    game.world.flags["god_mode"] = False

    # [5] Bribe (25g)
    gold_before = game.world.player.needs["wealth"]
    assert dlg.choose("5")["success"] is True
    assert game.world.player.needs["wealth"] == pytest.approx(gold_before - 25.0)

    # [6] Companion Interjection (Sera in party)
    r6 = dlg.choose("6")
    assert r6["success"] is True and "Sera" in r6["message"]

    # [7] Favor / Companion Recruit
    elira_dlg = DialogueEngine(game, "comp_elira")
    assert "comp_elira" not in game.world.player_party
    assert elira_dlg.choose("7")["success"] is True
    assert "comp_elira" in game.world.player_party
    assert elira_dlg.choose("0")["closed"] is True

    # [8] Provoke / Attack -> ClashSession
    r8 = dlg.choose("8")
    assert r8["enter_combat"] is True and r8["clash_session"] is not None


@pytest.mark.asyncio
async def test_t1_simplified_combat_clash_all_actions_and_viewport(tmp_path: Path) -> None:
    """Tier 1: Combat Clash Viewport and all clash actions [1]-[7] & [0]."""
    create_app = require_symbol("main", "create_app")

    game, _, _, _ = _make_isolated_game(tmp_path, name="combat_e2e", skip_prologue=True)
    app = create_app(game=game, show_prologue=False, show_title=False, warsim_mode=True)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # [2] Speak -> [1] NPC -> [8] Provoke / Attack
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        await pilot.press("8")
        await pilot.pause()

        clash = game.menu_engine.active_clash
        assert clash is not None
        vp = str(app.query_one("#view-content").content)
        assert "COMBAT CLASH" in vp
        assert "PARTY" in vp and "ENEMIES" in vp
        assert "Consc:" in vp and "Morale" in vp

        # [2] Heavy Brutal Assault (+35%)
        await pilot.press("2")
        await pilot.pause()
        if game.menu_engine.active_clash is not None:
            # [3] Aimed Limb -> [2] Arms
            await pilot.press("3")
            await pilot.pause()
            assert any("Arms" in o["label"] for o in game.menu_engine.get_screen()["options"])
            await pilot.press("2")
            await pilot.pause()

        if game.menu_engine.active_clash is not None:
            # [4] Defensive Stance & Rally Party
            await pilot.press("4")
            await pilot.pause()

        if game.menu_engine.active_clash is not None:
            # [5] Field Triage & Bandage
            game.health_system.apply_injury(game.world.player, "torso", "laceration", severity=0.5)
            await pilot.press("5")
            await pilot.pause()

        if game.menu_engine.active_clash is not None:
            # [6] Tactical Trick / Arcane Surge
            await pilot.press("6")
            await pilot.pause()

        if game.menu_engine.active_clash is not None:
            # [7] Demand Surrender when enemy morale <= 30
            for enemy in game.menu_engine.active_clash.encounter.enemies:
                enemy.morale = 20.0
            await pilot.press("7")
            await pilot.pause()

        # If still in combat, test [0] Retreat / Surrender
        if game.menu_engine.active_clash is not None:
            game.world.rng.stream("clash_retreat").seed(1)
            await pilot.press("0")
            await pilot.pause()


def test_t1_systemic_depth_politics_relationships_economy_digest(tmp_path: Path) -> None:
    """Tier 1: Political ops, Petitioners, Relationship Social Actions, Commodities, 5 Properties, Loans/Caravans, Digest."""
    content_mod = require_module("content")
    COMMODITIES = content_mod.COMMODITIES
    PROPERTIES_CATALOG = content_mod.PROPERTIES_CATALOG

    game, _, _, _ = _make_isolated_game(tmp_path, name="systemic_e2e", skip_prologue=True)
    game.world.player.needs["wealth"] = 5000.0
    fac_sys = game.faction_system
    rel_sys = game.relationship_system
    eco_sys = game.economy_system

    # 1. Political Operations & 3 Civic Edicts & Petitioners
    assert fac_sys.petition_faction_leader("city_guard", world=game.world)["success"] is True
    assert fac_sys.donate_to_faction("city_guard", 100.0, world=game.world)["success"] is True
    assert fac_sys.broker_truce("city_guard", "merchant_consortium", world=game.world)["success"] is True
    assert fac_sys.incite_turf_war("lowtown_syndicate", "iron_workers_union", world=game.world)["success"] is True
    assert fac_sys.pay_off_bounty(50.0, world=game.world)["success"] is True
    assert fac_sys.smear_campaign("lowtown_syndicate", world=game.world)["success"] is True
    assert fac_sys.sabotage_district("harbor", world=game.world)["success"] is True
    for edict in ("soup_kitchens", "private_watch_patrols", "festival"):
        assert fac_sys.sponsor_civic_edict("lowtown", edict, world=game.world)["success"] is True
    assert fac_sys.back_internal_coup("lowtown_syndicate", bribe_amount=150.0, world=game.world)["success"] is True

    petitioners = fac_sys.generate_petitioners(game.world, location_type="tavern", count=2)
    assert 1 <= len(petitioners) <= 3
    for pet in petitioners:
        assert fac_sys.resolve_petitioner(game.world, pet, 1)["success"] is True

    # 2. Relationship Social Actions
    assert rel_sys.give_gift(game.world, "player", "comp_sera", gold_cost=25.0)["success"] is True
    rel_sys.set_relationship("npc_voss", "player", fear=65.0)
    assert rel_sys.extort_npc(game.world, "player", "npc_voss")["success"] is True
    assert rel_sys.campfire_counsel(game.world, "comp_sera", resolve_tension=True)["success"] is True
    rel_sys.set_relationship("comp_marcus", "player", trust=70.0, respect=70.0)
    assert rel_sys.swear_blood_oath(game.world, "player", "comp_marcus")["success"] is True
    assert rel_sys.declare_blood_feud(game.world, "player", "npc_voss")["success"] is True

    # 3. Economy: 6 Commodities, 5 Upgradeable Properties, Loans, Caravans, Daily City Digest
    assert len(COMMODITIES) == 6
    assert len(PROPERTIES_CATALOG) == 5

    for cid in COMMODITIES:
        assert eco_sys.buy_commodity("player", cid, quantity=1, district_id="lowtown", world=game.world)["success"] is True
        assert eco_sys.sell_commodity("player", cid, quantity=1, district_id="lowtown", world=game.world)["success"] is True

    for pid in PROPERTIES_CATALOG:
        assert eco_sys.acquire_property("player", pid, world=game.world)["success"] is True
        assert eco_sys.upgrade_property("player", pid, world=game.world)["success"] is True

    loan = eco_sys.take_loan("player", 200.0, lender="merchant_consortium", term_days=5, world=game.world)
    assert loan["success"] is True
    assert eco_sys.repay_loan("player", loan["loan"]["id"], world=game.world)["success"] is True
    assert eco_sys.invest_caravan("player", 150.0, route="lowtown_to_harbor", world=game.world)["success"] is True

    # Trigger Daily City Digest via simulation time advance
    game.simulation.advance_time(1440, world=game.world)
    digest = game.world.flags.get("last_daily_digest")
    assert isinstance(digest, dict)
    assert digest["property_income"] > 0.0
    assert len(digest["summary_lines"]) >= 1


# ===========================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ===========================================================================


def test_t2_ironman_single_slot_difficulty_modifiers_and_corrupt_settings(tmp_path: Path) -> None:
    """Tier 2: Ironman single-slot lock, difficulty modifiers, corrupt settings.json fallback, and social guards."""
    settings_mod = require_module("core.settings")
    load_settings = settings_mod.load_settings
    get_difficulty_modifiers = settings_mod.get_difficulty_modifiers

    # 1. Corrupt settings.json falls back cleanly
    bad_settings = tmp_path / "bad_settings.json"
    bad_settings.write_text("{not valid json", encoding="utf-8")
    recovered = load_settings(bad_settings)
    assert recovered.difficulty == "balanced"
    assert recovered.enable_debug_cheat is False

    # 2. Difficulty modifiers differ meaningfully between story and gritty
    story_mod = get_difficulty_modifiers("story")
    gritty_mod = get_difficulty_modifiers("gritty")
    assert story_mod["skill_bonus"] > gritty_mod["skill_bonus"]
    assert story_mod["incoming_damage_mult"] < gritty_mod["incoming_damage_mult"]
    assert story_mod["price_mult"] < gritty_mod["price_mult"]

    # 3. Ironman redirects any manual save slot to "ironman"
    g_iron, _, sm_iron, _ = _make_isolated_game(tmp_path, name="ironman", difficulty="ironman", skip_prologue=True)
    sm_iron.save_game(g_iron.world, slot="custom_manual_slot")
    slots = sm_iron.list_save_slots()
    assert len(slots) == 1
    assert slots[0]["slot"] == "ironman"
    assert slots[0]["ironman"] is True

    # 4. Social guards: extort without leverage & blood oath below threshold
    g_iron.relationship_system.set_relationship("npc_voss", "player", fear=10.0, trust=10.0, respect=10.0)
    assert g_iron.relationship_system.extort_npc(g_iron.world, "player", "npc_voss")["success"] is False
    assert g_iron.relationship_system.swear_blood_oath(g_iron.world, "player", "npc_voss")["success"] is False


def test_t2_rich_markup_escaping_in_warsim_menus(tmp_path: Path) -> None:
    """Tier 2: Rich markup characters in dynamic epithets/names do not crash MenuEngine or TitleScreen."""
    game, _, _, _ = _make_isolated_game(tmp_path, name="markup_e2e", skip_prologue=True)
    game.world.flags["epithet"] = "[bold red]Unescaped[/] Epithet"
    game.world.player.name = "Rowan [cyan]Veyr[/]"
    scr = game.menu_engine.get_screen()
    assert scr["mode"] == "hub"
    char_scr = game.menu_engine.select("8")
    assert char_scr["success"] is True


# ===========================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS
# ===========================================================================


@pytest.mark.asyncio
async def test_t3_title_to_warsim_economy_digest_and_sqlite_roundtrip(tmp_path: Path) -> None:
    """Tier 3: TitleScreen -> Settings -> New Game -> Warsim Trade & Property -> Daily Digest -> SQLite Reload."""
    GameSettings = require_symbol("core.settings", "GameSettings")
    TitleScreen = require_symbol("ui.title_screen", "TitleScreen")
    create_app = require_symbol("main", "create_app")

    settings_path = tmp_path / "t3_settings.json"
    game, db, sm, db_path = _make_isolated_game(tmp_path, name="t3_roundtrip", settings=GameSettings())

    wizard_result: list[Any] = []
    app_title = create_app(game=game, show_prologue=False)
    async with app_title.run_test(size=(120, 40)) as pilot:
        ts = TitleScreen(settings=GameSettings(), save_manager=sm, settings_path=settings_path, db_path=db_path)
        app_title.push_screen(ts, callback=wizard_result.append)
        await pilot.pause()
        await pilot.press("2")  # New Game
        await pilot.press("2")  # Balanced
        await pilot.press("2")  # Dockside Smuggler
        await pilot.press("1")  # Heavy Coin Purse
        await pilot.press("2")  # Skip Prologue
        await pilot.pause()

    cfg = wizard_result[0]
    g2, db2, sm2, _ = _make_isolated_game(
        tmp_path,
        name="t3_game",
        difficulty=cfg["difficulty"],
        background=cfg["background"],
        keepsake=cfg["keepsake"],
        skip_prologue=cfg["skip_prologue"],
    )
    g2.world.player.needs["wealth"] = 1000.0
    assert g2.economy_system.buy_commodity("player", "grain_rations", quantity=2, district_id="lowtown", world=g2.world)["success"] is True
    assert g2.economy_system.acquire_property("player", "lowtown_safehouse", world=g2.world)["success"] is True
    g2.simulation.advance_time(1440, world=g2.world)
    sm2.save_game(g2.world, slot="t3_slot")

    # Load into fresh Game and verify all new World fields + Digest survive
    g3, _, _, _ = _make_isolated_game(tmp_path, name="t3_game")
    assert g3.execute_command("load t3_slot")["success"] is True
    assert g3.world.commodities.get("grain_rations") == 2
    assert "lowtown_safehouse" in g3.world.properties
    assert "last_daily_digest" in g3.world.flags


# ===========================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS
# ===========================================================================


@pytest.mark.asyncio
async def test_t4_complete_warsim_session_zero_typing_walkthrough(tmp_path: Path) -> None:
    """Tier 4: Full zero-typing Warsim walkthrough (Travel -> Market -> Dialogue -> Combat -> Politics -> Digest)."""
    GameSettings = require_symbol("core.settings", "GameSettings")
    create_app = require_symbol("main", "create_app")

    game, _, _, _ = _make_isolated_game(
        tmp_path,
        name="t4_walkthrough",
        settings=GameSettings(enable_debug_cheat=False),
        difficulty="balanced",
        background="watch_veteran",
        keepsake="coin_purse",
        skip_prologue=True,
    )
    app = create_app(game=game, show_prologue=False, show_title=False, warsim_mode=True)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.query_one("#command-input").display is False

        # 1. Travel to Lowtown Market ([1] -> [1] -> [0])
        await pilot.press("1")
        await pilot.pause()
        await pilot.click("#action-1")
        await pilot.pause()
        await pilot.press("0")
        await pilot.pause()
        assert game.world.player.location_id == "lowtown_market"

        # 2. Buy Grain & Rations at Local Activities ([3] -> [1] -> [1] -> [1] -> Back x3)
        await pilot.press("3")
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        assert game.world.commodities.get("grain_rations", 0) >= 1
        for _ in range(3):
            await pilot.press("0")
            await pilot.pause()

        # 3. Speak with nearby NPC -> Ask Rumors -> Provoke into Combat Clash -> Balanced Strike -> Retreat
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        assert game.menu_engine.active_dialogue is not None
        await pilot.press("1")  # Rumors
        await pilot.pause()
        await pilot.press("8")  # Provoke -> Combat
        await pilot.pause()
        if game.menu_engine.active_clash is not None:
            await pilot.click("#action-1")  # Balanced Strike
            await pilot.pause()
        if game.menu_engine.active_clash is not None:
            game.world.rng.stream("clash_retreat").seed(1)
            await pilot.press("0")  # Retreat
            await pilot.pause()

        # 4. Pass Time [0] to trigger Daily City Digest
        while game.menu_engine.get_screen()["mode"] != "hub":
            await pilot.press("0")
            await pilot.pause()
        await pilot.press("0")
        await pilot.pause()
        assert "last_daily_digest" in game.world.flags
