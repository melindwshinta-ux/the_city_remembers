# Project: THE CITY REMEMBERS — Prologue, Tutorial & QOL UI/UX

## Architecture
Layered systemic narrative RPG in Python 3.12 + Textual 8.2.8:
- `config.py`: Constants, calendar, acts (`ACT_PROLOGUE`, `ACT_I`–`ACT_III`), action durations, event types.
- `entities/`: Pure dataclasses (`Character`, `CompanionProfile`, `District`, `Location`, `Quest`, `Rumor`, `Item`, `Faction`, `NemesisProfile`).
- `core/`: `World` (with persistent `flags: dict[str, Any]` and `locations`), `WorldClock` (`prologue_completed`, `complete_prologue()`), `EventBus`, `SimulationEngine`, `Game` (command parser, `execute_command`, `get_dialogue`, `resolve_scenario_approach`).
- `systems/` & `ai/`: 11 simulation systems + `FactionAI`.
- `persistence/`: `Database` (15 required SQLite tables, `CURRENT_SCHEMA_VERSION = 1`), `SaveManager` (`world.flags` persisted in `world_state.flags_json -> user_flags` and `payload_json`).
- `content/`: World population (`content/__init__.py`) and new prologue/tutorial content (`content/prologue.py`).
- `ui/` & `main.py`: `CityRemembersApp` (Textual app), 8 view renderers (`ui/*_screen.py`), new `PrologueScreen`, `HelpModal`, `QuitConfirmModal`, Tutorial/Objective HUD, Rich markup & QOL keybindings.

## Code Layout
- `content/__init__.py`, `content/prologue.py` — World population, Location registration, Prologue beats/choices, Mission 1–2 tutorial step definitions.
- `core/game.py`, `core/tutorial.py` — Target resolution fix, `talk`/`inspect`/`choose`/`load` improvements, non-blocking Prologue & Tutorial state machine.
- `main.py`, `ui/*.py` — `CityRemembersApp`, `PrologueScreen`, modals, Tutorial HUD, QOL keybindings/history/markup, bug fixes in `ui/combat_screen.py`, `ui/main_screen.py`, `ui/character_screen.py`, `ui/journal_screen.py`.
- `tests/` — Existing 296 tests preserved; new unit/integration tests (`tests/test_prologue_tutorial.py`, `tests/test_ui_qol.py`) + E2E onboarding/QOL tests (`tests/e2e/test_e2e_onboarding_qol.py`).

## Feature Inventory
Every feature from the Survey phase is assigned to a milestone below:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F-PRO-1 | Interactive Prologue Narrative & Choices | Multi-beat arrival in Veyr (`ACT_PROLOGUE`) with 3 meaningful background/stance choices applying deterministic starting effects, synced with `world.clock.complete_prologue()` | M1 | survey_1, survey_2 |
| F-PRO-2 | Non-Blocking, Skippable & Replayable Prologue | `world.flags["prologue"]` persistence, `prologue` / `skip prologue` commands, and `show_prologue` gating on `CityRemembersApp` so `Game()` & `create_app(game=...)` remain non-blocking | M1, M2 | survey_1, survey_2, survey_3 |
| F-TUT-1 | Hands-On Tutorial State Machine (Missions 1–2) | Guided step-by-step onboarding across Mission 1 (`quest_blood_in_lowtown`) & Mission 2 (`quest_missing_apprentice`) covering movement, inspection/clues, dialogue, faction approach, health, rest, save/load | M1 | survey_1, survey_3 |
| F-TUT-2 | Off-Rails Resilience, Skip & Reset | Completing actions out of order auto-advances superseded tutorial steps; `tutorial`, `tutorial skip`, `tutorial reset` commands; idempotent & save/load round-trip safe | M1 | survey_1, survey_3 |
| F-CORE-1 | Lowtown Location Registration & Target Resolution Fix | Register all 9 Lowtown `Location` objects in `world.locations`; fix `Game.resolve_target()` to prefer exact matches before substring fallback | M1 | survey_1 |
| F-CORE-2 | Enriched `talk`, `inspect`, `choose`/`resolve` & Safe `load` | `talk` surfaces `Game.get_dialogue()`; `inspect` reveals clues & updates `investigate_crime_scene`; `choose`/`resolve` invokes `resolve_scenario_approach()`; `load <missing>` catches `SaveNotFoundError` gracefully | M1 | survey_1, survey_2 |
| F-UI-1 | `PrologueScreen` & Collapsible Tutorial/Objective HUD | Interactive Textual `PrologueScreen` on launch (when `show_prologue=True`) + persistent collapsible Tutorial/Objective HUD bar with `Skip Tutorial` / `Next Hint` / `Help` actions | M2 | survey_2 |
| F-UI-2 | QOL Modals, Keybindings & Command History | `HelpModal` (`?`/`F1`), `QuitConfirmModal` (`Ctrl+Q`), `Up`/`Down` command history in `Input`, `Esc` to blur/close modal, `F1`–`F8` view shortcuts alongside `1`–`8` (no input conflict) | M2 | survey_2 |
| F-UI-3 | Rich Markup, Visual Polish & Bug Fixes | Fix `combat_screen` render mutation, `main_screen` hardcoded district, `character_screen` hardcoded stats, `journal_screen` inventory source; enable `markup=True` & color-coded feedback, responsive `(80, 24)` & `(120, 40)` layout | M2 | survey_2 |
| F-E2E-1 | Comprehensive E2E & Adversarial Test Suite | Requirement-driven E2E tests (Tiers 1–4) for Prologue, Tutorial, Missions 1–2 onboarding, and Textual `pilot` QOL, plus Tier 5 adversarial hardening | E2E, M3 | survey_3 |

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Prologue, Tutorial Engine & Content Onboarding | F-PRO-1, F-PRO-2 (core), F-TUT-1, F-TUT-2, F-CORE-1, F-CORE-2 + unit/integration tests | none | DONE (`content/prologue.py`, `core/tutorial.py`, `core/game.py`, `content/__init__.py`, `tests/test_prologue_tutorial.py`; 307/307 tests passing) |
| M2 | Textual UI Prologue Screen, Tutorial HUD & QOL Polish | F-PRO-2 (UI), F-UI-1, F-UI-2, F-UI-3 + async Textual `pilot` tests | M1 | DONE (`main.py`, `ui/*.py`, `tests/test_ui_qol.py`; `(80,24)` & `(120,40)` verified; 334/334 tests passing) |
| E2E | E2E Testing Track (Onboarding & QOL) | Opaque-box E2E test suite (Tiers 1–4) + `TEST_READY.md` | M1 (contracts defined) | DONE (`tests/e2e/test_e2e_onboarding_qol.py` + `TEST_READY.md`; 333/333 tests passing) |
| M3 | Final Milestone: E2E Pass & Tier 5 Adversarial Hardening | Pass 100% of 296 existing + new unit + E2E Tiers 1–4 tests, then Tier 5 adversarial coverage hardening | M1, M2, E2E | IN_PROGRESS (Phase 1 PASS 334/334; Phase 2 Tier 5 starting) |

## Interface Contracts

### `core/tutorial.py` & `core/game.py` ↔ `main.py` / `ui/`
- `Game.get_prologue_state() -> dict`: returns `{"active": bool, "completed": bool, "skipped": bool, "step": int, "total_steps": int, "beat": dict | None, "choices_made": dict}`
- `Game.advance_prologue(choice_id: str | None = None) -> dict`: advances prologue beat or applies choice, returns `{"success": bool, "message": str, "state": dict}`
- `Game.skip_prologue() -> dict`: marks prologue skipped/completed cleanly without blocking gameplay
- `Game.replay_prologue() -> dict`: resets prologue beat to 0 for replay
- `Game.get_tutorial_state() -> dict`: returns `{"enabled": bool, "completed": bool, "skipped": bool, "current_step": str | None, "step_info": dict | None, "completed_steps": list[str], "progress": tuple[int, int]}`
- `Game.skip_tutorial() -> dict`, `Game.reset_tutorial() -> dict`
- `CityRemembersApp(game: Game | None = None, show_prologue: bool | None = None)` and `create_app(game: Game | None = None, show_prologue: bool | None = None) -> CityRemembersApp`
  - When `show_prologue is None`: `True` if `game is None` (interactive launch), `False` if `game is not None` (preserves `test_t4_12`).
