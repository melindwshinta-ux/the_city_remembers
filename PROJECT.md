# Project: THE CITY REMEMBERS — Warsim-Style Choice Overhaul & Systemic Depth

## Architecture
Layered systemic narrative RPG in Python 3.12 + Textual 8.2.8, preserving 100% backward compatibility with all 346 existing tests while layering a *Warsim*-style `1`–`9` & `0` zero-typing choice engine, Title Screen, settings-gated Debug Mode, branching Dialogue Engine, streamlined Combat Clash, and deep Political/Relationship/Economic systems:
- `config.py`: Constants, calendar, acts (`ACT_PROLOGUE`, `ACT_I`–`ACT_III`), `SAVES_DIR`, `SETTINGS_PATH`, difficulty presets, action durations, event types.
- `entities/`: Pure dataclasses (`Character`, `CompanionProfile`, `District`, `Location`, `Quest`, `Rumor`, `Item`, `Faction`, `NemesisProfile`, `EnemyCombatant`).
- `core/`: `World` (now also serializing `properties`, `commodities`, `loans`, `caravans`), `WorldClock`, `EventBus`, `SimulationEngine`, `SeededRNG`, `Game` (preserving `parse_command`, `execute_command`, `get_dialogue`, `resolve_scenario_approach`, prologue/tutorial delegates), `TutorialManager`, plus new `core/settings.py`, `core/menu_engine.py`, `core/dialogue_engine.py`, and `core/debug_mode.py`.
- `systems/` & `ai/`: 11 simulation systems + `FactionAI`/`AmbitionAI`/`CombatAI`, extended with Combat Clash (`ClashSession`), Political Operations & Petitioners, Relationship Social Actions, Commodity Market, Income Properties, Loans/Caravans, and Daily City Digest.
- `persistence/`: `Database` (15 required SQLite tables + `save_slots`), `SaveManager` (extended with `list_save_slots`, `delete_save_slot`, `get_most_recent_slot`, `autosave`, and Ironman single-slot enforcement).
- `content/`: World population (`content/__init__.py`), prologue/tutorial (`content/prologue.py`), commodities, properties, and petitioner templates.
- `ui/` & `main.py`: `CityRemembersApp` (`show_title`, `warsim_mode`, `show_prologue`), `TitleScreen` (`ui/title_screen.py`), `PrologueScreen`, `HelpModal`, `QuitConfirmModal`, `#action-deck` (`1`–`9` & `0` buttons + keybindings), `ui/combat_screen.py` Clash Viewport, Top Status Banner, Tutorial HUD, and responsive `(80, 24)` / `(120, 40)` layout.

## Code Layout
- `core/settings.py`, `core/debug_mode.py`, `persistence/save_manager.py`, `config.py` — M1: Settings, Difficulty/Background/Keepsake, Save Slot Browser/Autosave/Ironman, Settings-Gated Debug Mode.
- `systems/combat_system.py`, `systems/faction_system.py`, `systems/relationship_system.py`, `systems/economy_system.py`, `core/world.py`, `content/__init__.py` — M2: Combat Clash, Political Operations & Petitioners, Relationship Social Actions, Commodities/Properties/Loans/Caravans, Daily City Digest.
- `core/menu_engine.py`, `core/dialogue_engine.py`, `core/game.py` — M3: *Warsim* `1`–`0` Hierarchical Menu Engine & Interactive Branching Dialogue Engine.
- `ui/title_screen.py`, `ui/combat_screen.py`, `ui/modals.py`, `main.py` — M4: Title Screen, New Game Wizard, Zero-Typing Action Deck (`1`–`9`, `0` + mouse), Combat Clash Viewport, Responsive `(80, 24)` Compact Mode.
- `tests/` — Existing 346 tests preserved 100%; new unit/integration tests (`tests/test_settings_debug_persistence.py`, `tests/test_systemic_overhaul.py`, `tests/test_menu_dialogue_engine.py`, `tests/test_warsim_ui.py`) + E2E overhaul tests (`tests/e2e/test_e2e_warsim_overhaul.py`).

## Feature Inventory
Every requirement from `GEMINI_PLAN.md` (§§1–8) is assigned to a milestone below:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F-SET-1 | Settings Persistence & Difficulty Modifiers | `core/settings.py` (`saves/settings.json`), Difficulty (`story`, `balanced`, `gritty`, `ironman`), Auto-Save, Tutorial HUD, Layout Mode, New Game Background & Keepsake | M1 | GEMINI_PLAN §1.1, §8 |
| F-SAV-1 | Save Slot Browser, Continue, Delete & Ironman | `SaveManager.list_save_slots()`, `delete_save_slot()`, `get_most_recent_slot()`, `autosave()`, Ironman single-slot lock | M1 | GEMINI_PLAN §1.1 |
| F-DBG-1 | Settings-Gated Cheat & Debug Mode | `core/debug_mode.py` strictly blocked unless `settings.enable_debug_cheat == True`; 9 numbered cheat actions (`+500g`, Heal, Max Stats, God Mode, Time Skip, Faction/District, Relationship, Nemesis, Quest/Tutorial Skip) | M1 | GEMINI_PLAN §6 |
| F-CMB-1 | Simplified Combat Clash (`1`–`7`, `0`) | `ClashSession` / `resolve_clash_turn` layered on `CombatSystem` (Balanced, Heavy +35%, Aimed Limb `[1]`–`[4]`, Guard/Rally, Triage/Bandage, Tactical/Arcane, Demand Surrender `morale<=30`, Retreat/Surrender) + 5-line log | M2 | GEMINI_PLAN §4 |
| F-POL-1 | Political Intrigue & Petitioners | `FactionSystem` player ops (Petition, Donate, Truce/Turf War, Clear Bounty, Smear, Sabotage, 3 Civic Edicts, Internal Coup via `AmbitionAI`) + procedural Petitioners at Safehouse/Tavern | M2 | GEMINI_PLAN §5.1 |
| F-REL-1 | Relationship Social Depth | `RelationshipSystem` direct actions: `give_gift`, `extort_npc` (`fear>=50` or secret memory), `campfire_counsel`, `swear_blood_oath`, `declare_blood_feud` | M2 | GEMINI_PLAN §5.2 |
| F-ECO-1 | Commodities, Properties, Loans & Daily Digest | `World` serialization for `properties`/`commodities`/`loans`/`caravans`; 6 dynamic commodities; 5 upgradeable income properties; Consortium/Syndicate loans & caravans; Daily City Digest on `FREQ_ECONOMY` | M2 | GEMINI_PLAN §5.3 |
| F-DLG-1 | Interactive Branching Dialogue (`1`–`8`, `0`) | `core/dialogue_engine.py` with NPC header/bars, dynamic greeting, Rumors, Quest Business, Persuade X%, Intimidate X%, Bribe (25g), Companion Interjection, Favor/Trade, Attack, Leave | M3 | GEMINI_PLAN §3 |
| F-MNU-1 | *Warsim* `1`–`0` Hierarchical Menu Engine | `core/menu_engine.py` stack-based navigation across all 9 Root Hub categories + `[0]` Debug/Pass Time, inline odds/costs/consequences/locks, `[9]` pagination | M3 | GEMINI_PLAN §2 |
| F-UI-1 | Title Screen, New Game Wizard & Zero-Typing Action Deck | `ui/title_screen.py` (`1`–`5`, `0` + mouse), `main.py` (`show_title`, `warsim_mode`, `#action-deck`, hidden `#command-input` in normal play), `ui/combat_screen.py` Clash Viewport, responsive `(80, 24)`/`(120, 40)` | M4 | GEMINI_PLAN §1, §4, §7 |
| F-E2E-1 | Comprehensive Overhaul E2E & Tier 5 Hardening | Opaque-box E2E tests (Tiers 1–4) + `TEST_READY.md` + Tier 5 adversarial coverage hardening while keeping all 346 existing tests green | E2E, M5 | GEMINI_PLAN §8 |

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Settings, Save Browser/Ironman & Gated Debug Mode | F-SET-1, F-SAV-1, F-DBG-1 + `tests/test_settings_debug_persistence.py` | none | DONE (Gate PASS: APPROVE + CLEAN, 16/16 new, 362/362 total) |
| M2 | Systemic Depth (Combat Clash, Politics, Relationships, Economy) | F-CMB-1, F-POL-1, F-REL-1, F-ECO-1 + `tests/test_systemic_overhaul.py` | none | DONE (Gate PASS: APPROVE + CLEAN, 8/8 new, 370/370 total) |
| M3 | *Warsim* `1`–`0` Menu Engine & Branching Dialogue | F-DLG-1, F-MNU-1 + `tests/test_menu_dialogue_engine.py` | M1, M2 | DONE (`core/game.py`, `core/dialogue_engine.py`, `core/menu_engine.py`, 4/4 new, 374/374 total) |
| M4 | Textual UI Overhaul (Title Screen, Action Deck, Combat Viewport, 80x24) | F-UI-1 + `tests/test_warsim_ui.py` | M1, M2, M3 | DONE (`ui/title_screen.py`, `ui/combat_screen.py`, `main.py`, 4/4 new, 378/378 total) |
| E2E | E2E Testing Track (Warsim Overhaul & Systemic Depth) | Opaque-box E2E tests (Tiers 1–4) + `TEST_READY.md` | M1, M2, M3 | DONE (`tests/e2e/test_e2e_warsim_overhaul.py`, 10 tests + `TEST_READY.md`) |
| M5 | Final Milestone: 100% E2E Pass & Tier 5 Adversarial Hardening | Pass 100% of 346 existing + new unit + E2E Tiers 1–4 tests + Tier 5 adversarial hardening | M4, E2E | DONE (Gate PASS: Challengers + Final Auditor CLEAN; 390/390 tests passing) |

## Interface Contracts

### `core/settings.py` ↔ `core/game.py`, `ui/title_screen.py`, `main.py`
- `GameSettings`: dataclass with `difficulty` (`"story"|"balanced"|"gritty"|"ironman"`), `enable_debug_cheat: bool = False`, `autosave_mode: str = "daily_and_precombat"`, `guided_tutorial_hud: bool = True`, `layout_mode: str = "auto"`.
- `load_settings(path=SETTINGS_PATH) -> GameSettings`, `save_settings(settings, path=SETTINGS_PATH) -> Path`.
- `DIFFICULTY_MODIFIERS[difficulty]`: dict with `skill_bonus`, `incoming_damage_mult`, `healing_mult`, `gold_mult`, `price_mult`, `nemesis_rate_mult`, `ironman: bool`.
- `Game(seed=..., settings=None, difficulty=None, background=None, keepsake=None, skip_prologue=False, ...)`: attaches `self.settings` and applies background/keepsake/difficulty deterministically via `world.flags`.

### `core/debug_mode.py` ↔ `core/menu_engine.py`
- `DebugMode(game)`: `is_enabled() -> bool` checks `game.settings.enable_debug_cheat`. Every `execute_cheat(choice_num, ...)` returns `{"success": False, "message": "Cheat/Debug Mode is disabled. Enable it in Settings first."}` if disabled.

### `core/menu_engine.py` & `core/dialogue_engine.py` ↔ `main.py`
- `MenuEngine(game)`: `get_screen() -> dict` returning `{"title": str, "subtitle": str, "body": str, "options": list[dict]}` where each option has `key` (`"1"`..`"9"`, `"0"`), `label`, `tags` (odds/cost/consequence/locked), `enabled: bool`. `select(key: str) -> dict` executes the option and updates the menu stack.
- `DialogueEngine(game, npc_id: str)`: `get_view() -> dict` and `choose(key: str) -> dict` for `[1]`–`[8]`, `[0]`.

### `main.py` ↔ Existing Tests & New Overhaul
- `CityRemembersApp(game: Game | None = None, show_prologue: bool | None = None, show_title: bool = False, warsim_mode: bool = False)` and `create_app(...)`:
  - Preserves `create_app(game=game)` non-blocking and `CityRemembersApp()` -> `PrologueScreen` for all 346 existing tests.
  - `main()` launches `create_app(show_title=True, warsim_mode=True)`.
