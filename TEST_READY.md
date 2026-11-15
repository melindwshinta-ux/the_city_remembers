# TEST_READY — THE CITY REMEMBERS (Warsim-Style Choice Overhaul & Systemic Depth)

## Test Runner Command
```bash
/home/antigravity/the_city_remembers/.venv/bin/pytest -q tests/e2e/test_e2e_warsim_overhaul.py
/home/antigravity/the_city_remembers/.venv/bin/pytest -q
```

## Latest Full Suite Result
- **Total Tests**: `388` (`346` baseline + `32` M1–M4 unit/UI tests + `10` new E2E Tiers 1–4 tests)
- **Passing**: `387 passed` (`378/378` existing + `9/10` new E2E)
- **Escalated Implementation Bug (`1 failed`)**:
  - `test_t3_title_to_warsim_economy_digest_and_sqlite_roundtrip` failed at `assert g3.world.commodities.get("grain_rations") == 2` (`{}`).
  - Root cause: `SaveManager.load_game()` (`persistence/save_manager.py`) reconstructs `World` from relational tables and does not restore `commodities`, `properties`, `loans`, or `caravans` (even though `World.to_dict()` / `save_slots.payload_json` serializes them). Escalated to orchestrator for M5 fix.
- **E2E Suite File**: `/home/antigravity/the_city_remembers/tests/e2e/test_e2e_warsim_overhaul.py`

## Coverage Summary (Tiers 1–4)

### Tier 1 — Feature Coverage
- `test_t1_main_menu_settings_about_load_delete_and_new_game_wizard`: Verifies `TitleScreen` (`[1]` Continue disabled/enabled, `[2]` New Game across 4 Difficulties, 4 Backgrounds, 4 Keepsakes, Prologue vs Skip Prologue, `[3]` Load Game + `[9]` Delete Slot, `[4]` Settings persisted to `settings.json`, `[5]` About).
- `test_t1_settings_gated_debug_cheat_mode_all_nine_actions`: Verifies `DebugMode` is blocked with zero state mutation and `[0] Debug & Cheat Menu` is hidden when `enable_debug_cheat=False`, and all 9 cheat actions succeed when enabled.
- `test_t1_zero_typing_warsim_navigation_120x40_and_80x24`: Verifies `warsim_mode=True` hides `#command-input`, shows `#status-banner` & `#action-deck`, and navigates all Root Hub screens + `[9]` pagination using only `1`–`9`/`0` keys and `#action-*` clicks at `(120, 40)` and `(80, 24)`.
- `test_t1_interactive_branching_dialogue_all_options`: Verifies `DialogueEngine` NPC header/6-axis bars, dynamic greeting, and all `[1]`–`[8]`/`[0]` choices (Rumors, Quest Business, Persuade, Intimidate, Bribe, Companion Interjection, Recruit/Favor, Provoke -> Combat, Leave).
- `test_t1_simplified_combat_clash_all_actions_and_viewport`: Verifies Combat Clash Viewport rendering and all `[1]`–`[7]`/`[0]` clash actions (Balanced, Heavy `+35%`, Aimed Limb, Defend/Rally, Field Triage, Tactical Trick, Demand Surrender `morale <= 30`, Retreat).
- `test_t1_systemic_depth_politics_relationships_economy_digest`: Verifies all Political operations, 3 Civic Edicts, Procedural Petitioners, all 5 Relationship Social Actions, 6 Commodities, 5 Upgradeable Properties, Loans, Caravans, and Daily City Digest.

### Tier 2 — Boundary & Corner Cases
- `test_t2_ironman_single_slot_difficulty_modifiers_and_corrupt_settings`: Verifies Ironman single-slot lock, `story` vs `gritty` modifier scaling, corrupted `settings.json` fallback, and social leverage/threshold guards.
- `test_t2_rich_markup_escaping_in_warsim_menus`: Verifies Rich markup characters in dynamic epithets/names do not raise `MarkupError` in `MenuEngine`.

### Tier 3 — Cross-Feature Combinations
- `test_t3_title_to_warsim_economy_digest_and_sqlite_roundtrip`: End-to-end `TitleScreen` -> New Game Wizard -> Economy (`commodities`, `properties`) + Daily City Digest -> SQLite save/reload roundtrip (currently exposes `SaveManager.load_game` omission of `commodities`/`properties`/`loans`/`caravans`).

### Tier 4 — Real-World Application Scenarios
- `test_t4_complete_warsim_session_zero_typing_walkthrough`: Full zero-typing Textual `pilot` walkthrough across Travel, Market Trade, Dialogue, Combat Clash, and Pass Time / Daily City Digest.
