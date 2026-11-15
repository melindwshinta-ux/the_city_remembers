"""Unit tests for M1: GameSettings, Difficulty/Background/Keepsake, SaveManager extensions, and gated DebugMode."""

from __future__ import annotations

from pathlib import Path

import pytest

from config import MINUTES_PER_DAY, MINUTES_PER_HOUR, MINUTES_PER_WEEK, MINUTES_PER_YEAR, SAVES_DIR, SETTINGS_PATH
from core.debug_mode import DISABLED_MESSAGE, DebugMode
from core.game import Game
from core.settings import (
    BACKGROUNDS,
    DIFFICULTY_MODIFIERS,
    KEEPSAKES,
    GameSettings,
    apply_new_game_setup,
    get_difficulty_modifiers,
    load_settings,
    save_settings,
)
from persistence.database import Database
from persistence.save_manager import SaveManager, SaveNotFoundError


def _make_isolated_game(tmp_path: Path, seed: int = 482193) -> Game:
    db = Database(tmp_path / "test_save.db")
    sm = SaveManager(db, backup_enabled=False)
    game = Game(seed=seed, db=db, save_manager=sm)
    game.settings = GameSettings()
    return game


# ----------------------------------------------------------------------
# 1. Config & GameSettings
# ----------------------------------------------------------------------


def test_settings_path_in_config() -> None:
    assert SETTINGS_PATH == SAVES_DIR / "settings.json"


def test_game_settings_defaults_and_persistence(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    default_loaded = load_settings(settings_file)
    assert default_loaded.difficulty == "balanced"
    assert default_loaded.enable_debug_cheat is False
    assert default_loaded.autosave_mode == "daily_and_precombat"
    assert default_loaded.guided_tutorial_hud is True
    assert default_loaded.layout_mode == "auto"

    custom = GameSettings(
        difficulty="gritty",
        enable_debug_cheat=True,
        autosave_mode="precombat",
        guided_tutorial_hud=False,
        layout_mode="compact",
    )
    written = save_settings(custom, settings_file)
    assert written == settings_file
    assert settings_file.exists()

    reloaded = load_settings(settings_file)
    assert reloaded == custom


def test_load_settings_handles_corrupt_json(tmp_path: Path) -> None:
    bad_file = tmp_path / "settings.json"
    bad_file.write_text("{not valid json", encoding="utf-8")
    loaded = load_settings(bad_file)
    assert loaded.difficulty == "balanced"
    assert loaded.enable_debug_cheat is False


def test_difficulty_modifiers_match_plan() -> None:
    assert set(DIFFICULTY_MODIFIERS.keys()) == {"story", "balanced", "gritty", "ironman"}
    for key, mods in DIFFICULTY_MODIFIERS.items():
        for req_key in (
            "skill_bonus",
            "incoming_damage_mult",
            "healing_mult",
            "gold_mult",
            "price_mult",
            "nemesis_rate_mult",
            "infection_risk_mult",
            "guard_suspicion_mult",
            "ironman",
        ):
            assert req_key in mods, f"Missing {req_key} in {key}"
    assert DIFFICULTY_MODIFIERS["story"]["skill_bonus"] > 0
    assert DIFFICULTY_MODIFIERS["story"]["incoming_damage_mult"] < 1.0
    assert DIFFICULTY_MODIFIERS["balanced"]["incoming_damage_mult"] == 1.0
    assert DIFFICULTY_MODIFIERS["gritty"]["ironman"] is False
    assert DIFFICULTY_MODIFIERS["ironman"]["ironman"] is True
    assert get_difficulty_modifiers("unknown")["incoming_damage_mult"] == 1.0


@pytest.mark.parametrize("background", list(BACKGROUNDS.keys()))
def test_new_game_setup_all_backgrounds(tmp_path: Path, background: str) -> None:
    game = _make_isolated_game(tmp_path)
    base_gold = game.world.player.needs["wealth"]
    res = apply_new_game_setup(
        game.world,
        difficulty="balanced",
        background=background,
        keepsake="coin_purse",
        skip_prologue=False,
    )
    assert res["background"] == background
    assert game.world.flags["background"] == background
    assert game.world.flags["difficulty"] == "balanced"
    assert game.world.flags["ironman"] is False
    assert game.world.player.needs["wealth"] == base_gold + 100.0
    if background == "field_chirurgeon":
        assert "surgeons_kit" in game.world.player.inventory


@pytest.mark.parametrize("keepsake", list(KEEPSAKES.keys()))
def test_new_game_setup_all_keepsakes_and_skip_prologue(tmp_path: Path, keepsake: str) -> None:
    game = _make_isolated_game(tmp_path)
    res = apply_new_game_setup(
        game.world,
        difficulty="ironman",
        background="watch_veteran",
        keepsake=keepsake,
        skip_prologue=True,
    )
    assert res["keepsake"] == keepsake
    assert game.world.flags["ironman"] is True
    assert game.world.clock.prologue_completed is True
    assert game.world.flags["prologue"]["completed"] is True

    if keepsake == "steel_longsword":
        assert game.world.player.equipment.get("weapon") == "fine_steel_longsword"
    elif keepsake == "guild_seal":
        assert game.world.reputation["faction"]["merchant_consortium"] >= 15.0
    elif keepsake == "chirurgeon_satchel":
        assert "linen_bandage" in game.world.player.inventory
        assert "healing_tonic" in game.world.player.inventory


# ----------------------------------------------------------------------
# 2. SaveManager Extensions & Ironman
# ----------------------------------------------------------------------


def test_save_manager_list_most_recent_and_delete(tmp_path: Path) -> None:
    game = _make_isolated_game(tmp_path)
    sm = game.save_manager
    assert sm.list_save_slots() == []
    assert sm.get_most_recent_slot() is None

    apply_new_game_setup(game.world, difficulty="gritty", background="dockside_smuggler", keepsake="coin_purse")
    sm.save_game(game.world, slot="slot_one")

    game.world.player.needs["wealth"] += 250.0
    game.simulation.advance_time(120, world=game.world)
    sm.save_game(game.world, slot="slot_two")

    slots = sm.list_save_slots()
    assert len(slots) == 2
    recent = sm.get_most_recent_slot()
    assert recent is not None
    assert recent["slot"] == "slot_two"
    assert recent["character_name"] == "Rowan"
    assert recent["epithet"] == "Dockside Smuggler"
    assert recent["difficulty"] == "gritty"
    assert recent["ironman"] is False
    assert recent["gold"] == pytest.approx(500.0)
    assert recent["location_id"] == "lowtown_street"

    assert sm.delete_save_slot("slot_two") is True
    assert sm.delete_save_slot("nonexistent") is False
    with pytest.raises(SaveNotFoundError):
        sm.load_game("slot_two")
    assert sm.get_most_recent_slot()["slot"] == "slot_one"


def test_save_manager_autosave_and_ironman_single_slot(tmp_path: Path) -> None:
    game = _make_isolated_game(tmp_path)
    sm = game.save_manager

    assert sm.autosave(game.world, reason="daily", autosave_mode="off") is None
    assert sm.autosave(game.world, reason="daily", autosave_mode="precombat") is None
    assert sm.autosave(game.world, reason="precombat", autosave_mode="precombat") == "autosave"
    assert sm.autosave(game.world, reason="daily", autosave_mode="daily_and_precombat") == "autosave"

    # Ironman enforces single 'ironman' slot even on manual save_game calls
    apply_new_game_setup(game.world, difficulty="ironman")
    sm.save_game(game.world, slot="manual_scum_slot")
    slot_names = {s["slot"] for s in sm.list_save_slots()}
    assert "ironman" in slot_names
    assert "manual_scum_slot" not in slot_names
    assert sm.autosave(game.world, reason="daily", autosave_mode="daily_and_precombat") == "ironman"


# ----------------------------------------------------------------------
# 3. DebugMode Strict Gating & All 9 Cheats
# ----------------------------------------------------------------------


def test_debug_mode_strictly_blocked_when_disabled(tmp_path: Path) -> None:
    game = _make_isolated_game(tmp_path)
    dbg = DebugMode(game)
    assert dbg.is_enabled() is False

    gold_before = game.world.player.needs["wealth"]
    ts_before = game.world.clock.timestamp

    for choice_num in range(1, 10):
        res = dbg.execute_cheat(choice_num)
        assert res["success"] is False
        assert res["message"] == DISABLED_MESSAGE

    assert game.world.player.needs["wealth"] == gold_before
    assert game.world.clock.timestamp == ts_before
    assert bool(game.world.flags.get("god_mode", False)) is False


def test_debug_mode_all_nine_cheats_when_enabled(tmp_path: Path) -> None:
    game = _make_isolated_game(tmp_path)
    game.settings.enable_debug_cheat = True
    dbg = DebugMode(game)
    assert dbg.is_enabled() is True

    # [1] +500 Gold
    gold_before = game.world.player.needs["wealth"]
    r1 = dbg.execute_cheat(1)
    assert r1["success"] is True
    assert game.world.player.needs["wealth"] == gold_before + 500.0

    # [2] Full Heal & Cure All Anatomical Wounds
    game.health_system.apply_injury(game.world.player, "left_arm", "broken_arm", severity=0.8)
    game.world.player.consciousness = 40.0
    r2 = dbg.execute_cheat(2)
    assert r2["success"] is True
    assert game.world.player.consciousness == 100.0
    assert game.world.player.body["left_arm"].functional is True
    assert game.world.player.body["left_arm"].injuries == []

    # [3] Max All Attributes & Skills (100)
    r3 = dbg.execute_cheat(3)
    assert r3["success"] is True
    assert game.world.player.attributes["strength"] == 100
    assert game.world.player.skills["persuasion"] == 100.0

    # [4] Toggle God Mode
    r4_on = dbg.execute_cheat(4)
    assert r4_on["success"] is True
    assert game.world.flags["god_mode"] is True
    r4_off = dbg.execute_cheat(4)
    assert r4_off["success"] is True
    assert game.world.flags["god_mode"] is False

    # [5] Time Skip (+6h / +1d / +7d / +1y)
    t0 = game.world.clock.timestamp
    assert dbg.execute_cheat(5, preset="6h")["success"] is True
    assert game.world.clock.timestamp == t0 + 6 * MINUTES_PER_HOUR
    assert dbg.execute_cheat(5, preset="1d")["success"] is True
    assert game.world.clock.timestamp == t0 + 6 * MINUTES_PER_HOUR + MINUTES_PER_DAY
    assert dbg.execute_cheat(5, preset="7d")["success"] is True
    assert game.world.clock.timestamp == t0 + 6 * MINUTES_PER_HOUR + MINUTES_PER_DAY + MINUTES_PER_WEEK
    assert dbg.execute_cheat(5, preset="1y")["success"] is True
    assert game.world.clock.timestamp == t0 + 6 * MINUTES_PER_HOUR + MINUTES_PER_DAY + MINUTES_PER_WEEK + MINUTES_PER_YEAR

    # [6] Faction & District Manipulation
    assert dbg.execute_cheat(6, mode="max_rep")["success"] is True
    assert game.world.reputation["faction"]["city_guard"] == 100.0
    assert dbg.execute_cheat(6, mode="riot", district_id="lowtown")["success"] is True
    assert game.world.districts["lowtown"].unrest == 100.0
    assert dbg.execute_cheat(6, mode="festival", district_id="lowtown")["success"] is True
    assert game.world.districts["lowtown"].unrest == 0.0

    # [7] Relationship Manipulation (+50 Trust/Respect/Affection)
    assert dbg.execute_cheat(7)["success"] is True
    voss_rel = game.relationship_system.get_relationship("npc_voss", "player")
    assert voss_rel.trust >= 50.0
    assert voss_rel.respect >= 50.0
    assert voss_rel.affection >= 50.0

    # [8] Nemesis Manipulation (Spawn / Promote / Injure Voss)
    assert dbg.execute_cheat(8, mode="spawn", target_id="npc_merek")["success"] is True
    assert game.world.characters["npc_merek"].is_nemesis is True
    assert dbg.execute_cheat(8, mode="promote", target_id="npc_voss")["success"] is True
    assert game.world.characters["npc_voss"].rank == "commander"
    assert dbg.execute_cheat(8, mode="injure_voss")["success"] is True
    assert any(inj.injury_type == "broken_leg" for inj in game.world.characters["npc_voss"].body["left_leg"].injuries)

    # [9] Quest & Tutorial Skip
    assert dbg.execute_cheat(9, mode="tutorial")["success"] is True
    assert game.world.flags["tutorial"]["skipped"] is True
    assert dbg.execute_cheat(9, mode="quest")["success"] is True
    assert game.world.quests["quest_blood_in_lowtown"].status == "completed"
