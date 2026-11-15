# TEST_READY — THE CITY REMEMBERS (Prologue, Tutorial & QOL UI/UX)

## Test Runner Command
```bash
/home/antigravity/the_city_remembers/.venv/bin/pytest -v
```

## Latest Full Suite Result
- **Status**: PASS (exit code `0`)
- **Total Tests**: `333 passed` (296 existing + 11 M1 unit/integration + 14 M2 UI/QOL + 12 E2E Tiers 1–4 onboarding/QOL tests)
- **E2E Suite File**: `/home/antigravity/the_city_remembers/tests/e2e/test_e2e_onboarding_qol.py`

## Coverage Summary (Tiers 1–4)

### Tier 1 — Feature Coverage
- `test_t1_prologue_beats_and_all_three_stance_choices`: Verifies all 3 prologue beats (`arrival_in_veyr`, `blood_in_lowtown_market`, `choose_opening_stance`) and deterministic starting effects (wealth, faction reputation, companion friendship, memories, `Act I` transition) for `watch_investigator`, `street_broker`, and `unbound_drifter`.
- `test_t1_tutorial_nine_steps_sequential_completion`: Verifies all 9 Mission 1–2 tutorial steps (`m1_move_market` through `m2_save_game`) advance sequentially to `(9, 9)` completion.
- `test_t1_prologue_screen_interactive_beats_preview_and_skip`: Verifies Textual `PrologueScreen` beat progression, stance preview, completion, and `Esc` skip.
- `test_t1_tutorial_hud_help_quit_history_and_view_shortcuts`: Verifies Tutorial HUD (`Hide`/`Show`, `Next Hint`, `Help`), `HelpModal` (`?`, `F1`, `Esc`, `q`, Close button), `QuitConfirmModal` (`Ctrl+Q`, cancel, confirm), `CommandInput` Up/Down history & draft preservation, and `1`–`8` (blurred) / `F2`–`F9` (anytime) view shortcuts.
- `test_t1_four_ui_bugfixes_verified_opaque_box`: Verifies `combat_screen` non-mutation of `active_encounter`, `main_screen` dynamic district rendering, `character_screen` dynamic attributes/personality rendering, and `journal_screen` player-only inventory rendering.

### Tier 2 — Boundary & Corner Cases
- `test_t2_invalid_prologue_choices_and_replay_idempotency`: Rejects invalid/missing prologue choices without completing prologue; verifies `replay_prologue()` does not double-apply starting bonuses.
- `test_t2_skip_prologue_and_tutorial_zero_time_and_out_of_order`: Verifies skipping prologue/tutorial advances 0 simulation minutes, `save` (`require_current=True`) does not auto-complete earlier steps, and out-of-order `inspect lowtown_alleys` auto-advances superseded steps.
- `test_t2_missing_and_corrupted_save_slots`: Verifies `load` on missing slot and corrupted `save_slots.payload_json` fails gracefully (`success=False`) without crashing `Game`.
- `test_t2_rich_markup_escaping_and_compact_80x24_and_non_blocking_create_app`: Verifies `[red]`/`[/]`/`[bold]` Rich markup characters do not raise `MarkupError`, `(80, 24)` layout fits all widgets cleanly, and `create_app(game=...)` defaults `show_prologue=False` (non-blocking).

### Tier 3 — Cross-Feature Combinations
- `test_t3_prologue_missions_sqlite_roundtrip_and_post_load_ui_refresh`: End-to-end Prologue -> Mission 1 -> Mission 2 -> SQLite save/load into fresh `Game` -> continued Textual UI gameplay & HUD refresh to `(9/9)`.
- `test_t3_pilot_command_submission_hud_and_view_switching`: Async Textual `pilot` command submission updating Tutorial HUD progress, switching views on `open <view>`, and updating `#view-content`.

### Tier 4 — Real-World Application Scenarios
- `test_t4_complete_onboarding_walkthrough_prologue_to_m2_save_and_quit`: Complete player onboarding walkthrough from `PrologueScreen` launch through Mission 1 ("Blood in Lowtown") resolution, Mission 2 ("Missing Apprentice") investigation, health check, rest, SQLite save, `QuitConfirmModal` cancel/confirm, and fresh-session reload verification.

## Feature Checklist
- [x] F-PRO-1: Interactive Prologue Narrative & 3 Stance Choices
- [x] F-PRO-2: Non-Blocking, Skippable & Replayable Prologue (`create_app(game=...)` & `show_prologue`)
- [x] F-TUT-1: Hands-On 9-Step Tutorial State Machine (Missions 1–2)
- [x] F-TUT-2: Off-Rails Resilience, Skip, Reset & SQLite Persistence
- [x] F-UI-1: `PrologueScreen` & Collapsible Tutorial/Objective HUD
- [x] F-UI-2: `HelpModal`, `QuitConfirmModal`, `CommandInput` History & View Shortcuts
- [x] F-UI-3: Rich Markup Escaping, `(80, 24)` Responsive Layout & 4 UI Bugfixes
- [x] F-E2E-1: Opaque-Box E2E Test Suite (Tiers 1–4)
