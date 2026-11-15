"""Atmospheric Warsim-style Title Screen, New Game Wizard, Save Browser & Settings (GEMINI_PLAN §1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from config import SAVES_DIR, SETTINGS_PATH
from core.settings import (
    BACKGROUNDS,
    DIFFICULTY_MODIFIERS,
    KEEPSAKES,
    VALID_AUTOSAVE_MODES,
    VALID_DIFFICULTIES,
    VALID_LAYOUT_MODES,
    GameSettings,
    load_settings,
    save_settings,
)
from persistence.database import Database
from persistence.save_manager import SaveManager

TITLE_ASCII = (
    "[bold gold1]╔══════════════════════════════════════════════════════════╗\n"
    "║              THE CITY REMEMBERS — VEYR                   ║\n"
    "║      A Systemic Narrative RPG of Memory & Consequence    ║\n"
    "╚══════════════════════════════════════════════════════════╝[/]"
)

TITLE_ASCII_COMPACT = "[bold gold1]═══ THE CITY REMEMBERS — VEYR ═══[/]"


class TitleScreen(Screen[dict[str, Any] | None]):
    """Main Menu, New Game Setup Wizard, Save Slot Browser, Settings, and About."""

    CSS = """
    TitleScreen {
        align: center middle;
    }
    #title-container {
        width: 96%;
        max-width: 96;
        height: auto;
        max-height: 95%;
        overflow-y: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    TitleScreen.compact #title-container {
        width: 100%;
        max-height: 100%;
        padding: 0 1;
    }
    #title-banner {
        height: auto;
        text-align: center;
        margin-bottom: 1;
    }
    TitleScreen.compact #title-banner {
        margin-bottom: 0;
    }
    #title-header {
        height: auto;
        text-style: bold;
        color: $accent;
        margin-bottom: 0;
    }
    #title-body {
        height: auto;
        margin-bottom: 1;
    }
    TitleScreen.compact #title-body {
        margin-bottom: 0;
    }
    #title-options {
        height: auto;
    }
    #title-options Button {
        width: 100%;
        height: 1;
        border: none;
        padding: 0 1;
        margin-bottom: 0;
        content-align: left middle;
    }
    #title-status {
        height: auto;
        margin-top: 1;
        color: $warning;
    }
    """

    BINDINGS = [
        Binding("1", "choose('1')", "1", show=False),
        Binding("2", "choose('2')", "2", show=False),
        Binding("3", "choose('3')", "3", show=False),
        Binding("4", "choose('4')", "4", show=False),
        Binding("5", "choose('5')", "5", show=False),
        Binding("6", "choose('6')", "6", show=False),
        Binding("7", "choose('7')", "7", show=False),
        Binding("8", "choose('8')", "8", show=False),
        Binding("9", "choose('9')", "9", show=False),
        Binding("0", "choose('0')", "0/Back", show=False),
        Binding("escape", "choose('0')", "Back", show=False),
    ]

    def __init__(
        self,
        settings: GameSettings | None = None,
        save_manager: SaveManager | None = None,
        settings_path: Path | str = SETTINGS_PATH,
        db_path: Path | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.settings_path = Path(settings_path)
        self.settings: GameSettings = settings if settings is not None else load_settings(self.settings_path)
        self._save_manager = save_manager
        self._db_path = Path(db_path) if db_path is not None else None
        self.mode: str = "main"
        self.status_message: str = ""
        self._delete_mode: bool = False
        self._wizard_difficulty: str = self.settings.difficulty
        self._wizard_background: str = "watch_veteran"
        self._wizard_keepsake: str = "coin_purse"
        self._current_options: list[dict[str, Any]] = []

    def _get_save_manager(self) -> SaveManager:
        if self._save_manager is not None:
            return self._save_manager
        app_game = getattr(self.app, "game", None)
        if app_game is not None and getattr(app_game, "save_manager", None) is not None and self._db_path is None:
            self._save_manager = app_game.save_manager
            return self._save_manager
        target_db = self._db_path or (SAVES_DIR / "save_482193.db")
        self._save_manager = SaveManager(Database(target_db))
        return self._save_manager

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="title-container"):
            yield Static(TITLE_ASCII, id="title-banner", markup=True)
            yield Static("", id="title-header", markup=True)
            yield Static("", id="title-body", markup=True)
            with Vertical(id="title-options"):
                for key in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"):
                    btn = Button("", id=f"title-btn-{key}", variant="default")
                    btn.display = False
                    yield btn
            yield Static("", id="title-status", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._apply_responsive_class()
        self._render_screen()

    def on_resize(self) -> None:
        self._apply_responsive_class()
        self._render_screen()

    def _apply_responsive_class(self) -> None:
        size = self.size
        compact = self.settings.layout_mode == "compact" or (
            self.settings.layout_mode == "auto" and (size.width <= 85 or size.height <= 26)
        )
        if compact:
            self.add_class("compact")
        else:
            self.remove_class("compact")

    def _build_state(self) -> tuple[str, str, list[dict[str, Any]]]:
        sm = self._get_save_manager()

        if self.mode == "main":
            recent = sm.get_most_recent_slot()
            if recent:
                cont_label = (
                    f"[1] Continue — {recent['character_name']} "
                    f"(Y{recent['year']} D{recent['day']}, {recent['location_name']}, "
                    f"{recent['gold']:.0f}g, {recent['difficulty']})"
                )
                cont_enabled = True
            else:
                cont_label = "[1] Continue (No Save Found)"
                cont_enabled = False
            opts = [
                {"key": "1", "label": cont_label, "enabled": cont_enabled, "action": "continue", "slot": recent["slot"] if recent else ""},
                {"key": "2", "label": "[2] New Game", "enabled": True, "action": "goto", "target": "wizard_difficulty"},
                {"key": "3", "label": "[3] Load Game", "enabled": True, "action": "goto", "target": "load_game"},
                {"key": "4", "label": "[4] Settings", "enabled": True, "action": "goto", "target": "settings"},
                {"key": "5", "label": "[5] About & Controls Guide", "enabled": True, "action": "goto", "target": "about"},
                {"key": "0", "label": "[0] Quit Game", "enabled": True, "action": "quit"},
            ]
            return (
                "MAIN MENU",
                "Play entirely with number keys [1]-[9] & [0] or mouse clicks.",
                opts,
            )

        if self.mode == "wizard_difficulty":
            opts = [
                {"key": "1", "label": "[1] Story (Forgiving) — +20% checks, -30% dmg, +50% heal, +25% gold", "enabled": True, "action": "set_diff", "value": "story"},
                {"key": "2", "label": "[2] Balanced (Normal) — Standard GDD simulation rules", "enabled": True, "action": "set_diff", "value": "balanced"},
                {"key": "3", "label": "[3] Gritty (Hard) — -10% checks, +25% enemy dmg, +20% prices", "enabled": True, "action": "set_diff", "value": "gritty"},
                {"key": "4", "label": "[4] Ironman Veyr (Brutal) — Gritty + single auto-saving slot", "enabled": True, "action": "set_diff", "value": "ironman"},
                {"key": "0", "label": "[0] Back to Main Menu", "enabled": True, "action": "goto", "target": "main"},
            ]
            return ("NEW GAME SETUP (1/4): DIFFICULTY", "Choose how unforgiving Veyr will be.", opts)

        if self.mode == "wizard_background":
            opts = [
                {"key": "1", "label": "[1] Discharged Watch Veteran (+Swordsmanship, +Discipline, +Guard Rep)", "enabled": True, "action": "set_bg", "value": "watch_veteran"},
                {"key": "2", "label": "[2] Dockside Smuggler (+Stealth, +Deception, +Syndicate Rep)", "enabled": True, "action": "set_bg", "value": "dockside_smuggler"},
                {"key": "3", "label": "[3] Disgraced Noble Scion (+Persuasion, +Leadership, +Noble Rep)", "enabled": True, "action": "set_bg", "value": "noble_scion"},
                {"key": "4", "label": "[4] Field Chirurgeon (+Medicine, +Intelligence, Surgeon's Kit)", "enabled": True, "action": "set_bg", "value": "field_chirurgeon"},
                {"key": "0", "label": "[0] Back", "enabled": True, "action": "goto", "target": "wizard_difficulty"},
            ]
            diff_label = DIFFICULTY_MODIFIERS.get(self._wizard_difficulty, {}).get("label", self._wizard_difficulty)
            return ("NEW GAME SETUP (2/4): BACKGROUND", f"Difficulty: {diff_label}", opts)

        if self.mode == "wizard_keepsake":
            opts = [
                {"key": "1", "label": "[1] Heavy Coin Purse (+100 Gold)", "enabled": True, "action": "set_ks", "value": "coin_purse"},
                {"key": "2", "label": "[2] Fine Steel Longsword (Equipped Weapon)", "enabled": True, "action": "set_ks", "value": "steel_longsword"},
                {"key": "3", "label": "[3] Forged Guild Seal (+Merchant & Guard Standing)", "enabled": True, "action": "set_ks", "value": "guild_seal"},
                {"key": "4", "label": "[4] Chirurgeon's Satchel (Bandages & Tonics)", "enabled": True, "action": "set_ks", "value": "chirurgeon_satchel"},
                {"key": "0", "label": "[0] Back", "enabled": True, "action": "goto", "target": "wizard_background"},
            ]
            bg_name = BACKGROUNDS.get(self._wizard_background, {}).get("name", self._wizard_background)
            return ("NEW GAME SETUP (3/4): STARTING KEEPSAKE", f"Background: {bg_name}", opts)

        if self.mode == "wizard_onboarding":
            opts = [
                {"key": "1", "label": "[1] Begin with Interactive Prologue", "enabled": True, "action": "start_new", "skip_prologue": False},
                {"key": "2", "label": "[2] Skip Prologue & Start in Act I (Lowtown)", "enabled": True, "action": "start_new", "skip_prologue": True},
                {"key": "0", "label": "[0] Back", "enabled": True, "action": "goto", "target": "wizard_keepsake"},
            ]
            ks_name = KEEPSAKES.get(self._wizard_keepsake, {}).get("name", self._wizard_keepsake)
            return ("NEW GAME SETUP (4/4): ONBOARDING", f"Keepsake: {ks_name}", opts)

        if self.mode == "load_game":
            slots = sm.list_save_slots()[:8]
            opts = []
            for idx, s in enumerate(slots, 1):
                lbl = (
                    f"[{idx}] {s['slot']} — {s['act']} Y{s['year']}D{s['day']} | "
                    f"{s['location_name']} | {s['gold']:.0f}g | {s['difficulty']}"
                )
                opts.append({"key": str(idx), "label": lbl, "enabled": True, "action": "slot_pick", "slot": s["slot"]})
            if slots:
                del_lbl = "[9] Cancel Delete Mode" if self._delete_mode else "[9] Delete Slot"
                opts.append({"key": "9", "label": del_lbl, "enabled": True, "action": "toggle_delete"})
            opts.append({"key": "0", "label": "[0] Back", "enabled": True, "action": "load_back"})
            body = (
                "[bold red]DELETE MODE: Press [1]-[8] to delete a slot, or [9]/[0] to cancel.[/]"
                if self._delete_mode
                else (f"Found {len(slots)} saved slot(s)." if slots else "No saved games found.")
            )
            return ("LOAD GAME", body, opts)

        if self.mode == "settings":
            s = self.settings
            opts = [
                {"key": "1", "label": f"[1] Difficulty: {s.difficulty.title()}", "enabled": True, "action": "cycle_diff"},
                {"key": "2", "label": f"[2] Enable Cheat / Debug Mode: {'ON' if s.enable_debug_cheat else 'OFF'}", "enabled": True, "action": "toggle_debug"},
                {"key": "3", "label": f"[3] Auto-Save: {s.autosave_mode}", "enabled": True, "action": "cycle_autosave"},
                {"key": "4", "label": f"[4] Guided Tutorial HUD: {'ON' if s.guided_tutorial_hud else 'OFF'}", "enabled": True, "action": "toggle_hud"},
                {"key": "5", "label": f"[5] Layout Mode: {s.layout_mode.title()}", "enabled": True, "action": "cycle_layout"},
                {"key": "0", "label": "[0] Save & Return", "enabled": True, "action": "save_settings"},
            ]
            return ("SETTINGS", f"Persisted to {self.settings_path.name}. Cheat/Debug is strictly gated here.", opts)

        if self.mode == "about":
            body = (
                "THE CITY REMEMBERS — VEYR\n"
                "Inspirations: Warsim, Dragon Age 2, RimWorld, Shadow of Mordor.\n"
                "Controls: Press [1]-[9] & [0] or click any numbered button.\n"
                "In-game: F2-F9 or Alt+1-8 switch information views; ?/F1 opens Help.\n"
                "Simulation: 29-part anatomical health, 6-axis relationships, Nemesis AI, "
                "7-faction politics, dynamic commodities, and seeded determinism."
            )
            opts = [{"key": "0", "label": "[0] Back to Main Menu", "enabled": True, "action": "goto", "target": "main"}]
            return ("ABOUT & CONTROLS GUIDE", body, opts)

        return ("MAIN MENU", "", [])

    def _render_screen(self) -> None:
        banner = self.query_one("#title-banner", Static)
        banner.update(TITLE_ASCII_COMPACT if self.has_class("compact") else TITLE_ASCII)

        header_text, body_text, opts = self._build_state()
        self._current_options = opts

        self.query_one("#title-header", Static).update(f"[bold cyan]{escape(header_text)}[/]")
        self.query_one("#title-body", Static).update(body_text if self.mode == "load_game" and self._delete_mode else escape(body_text))
        self.query_one("#title-status", Static).update(escape(self.status_message))

        opt_map = {o["key"]: o for o in opts}
        for key in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"):
            btn = self.query_one(f"#title-btn-{key}", Button)
            opt = opt_map.get(key)
            if opt is None:
                btn.display = False
            else:
                btn.label = opt["label"]
                btn.disabled = not bool(opt.get("enabled", True))
                btn.variant = "primary" if key == "1" and opt.get("enabled", True) else "default"
                btn.display = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("title-btn-"):
            key = btn_id[len("title-btn-") :]
            self.action_choose(key)

    def action_choose(self, key: str) -> None:
        choice = str(key).strip()
        opt = next((o for o in self._current_options if o["key"] == choice), None)
        if opt is None:
            return
        if not opt.get("enabled", True):
            self.status_message = "Option unavailable."
            self._render_screen()
            return

        act = opt.get("action")
        self.status_message = ""

        if act == "goto":
            self._delete_mode = False
            self.mode = str(opt["target"])
            self._render_screen()
            return

        if act == "quit":
            self.dismiss({"action": "quit"})
            return

        if act == "continue":
            self.dismiss({"action": "continue", "slot": opt["slot"], "settings": self.settings})
            return

        if act == "set_diff":
            self._wizard_difficulty = str(opt["value"])
            self.mode = "wizard_background"
            self._render_screen()
            return

        if act == "set_bg":
            self._wizard_background = str(opt["value"])
            self.mode = "wizard_keepsake"
            self._render_screen()
            return

        if act == "set_ks":
            self._wizard_keepsake = str(opt["value"])
            self.mode = "wizard_onboarding"
            self._render_screen()
            return

        if act == "start_new":
            self.settings.difficulty = self._wizard_difficulty
            save_settings(self.settings, self.settings_path)
            self.dismiss(
                {
                    "action": "new_game",
                    "difficulty": self._wizard_difficulty,
                    "background": self._wizard_background,
                    "keepsake": self._wizard_keepsake,
                    "skip_prologue": bool(opt.get("skip_prologue", False)),
                    "settings": self.settings,
                }
            )
            return

        if act == "toggle_delete":
            self._delete_mode = not self._delete_mode
            self._render_screen()
            return

        if act == "load_back":
            if self._delete_mode:
                self._delete_mode = False
                self._render_screen()
            else:
                self.mode = "main"
                self._render_screen()
            return

        if act == "slot_pick":
            slot = str(opt["slot"])
            if self._delete_mode:
                deleted = self._get_save_manager().delete_save_slot(slot)
                self._delete_mode = False
                self.status_message = f"Deleted slot '{slot}'." if deleted else f"Slot '{slot}' not found."
                self._render_screen()
            else:
                self.dismiss({"action": "load", "slot": slot, "settings": self.settings})
            return

        if act == "cycle_diff":
            idx = VALID_DIFFICULTIES.index(self.settings.difficulty) if self.settings.difficulty in VALID_DIFFICULTIES else 1
            self.settings.difficulty = VALID_DIFFICULTIES[(idx + 1) % len(VALID_DIFFICULTIES)]
            self._render_screen()
            return

        if act == "toggle_debug":
            self.settings.enable_debug_cheat = not self.settings.enable_debug_cheat
            self._render_screen()
            return

        if act == "cycle_autosave":
            idx = VALID_AUTOSAVE_MODES.index(self.settings.autosave_mode) if self.settings.autosave_mode in VALID_AUTOSAVE_MODES else 0
            self.settings.autosave_mode = VALID_AUTOSAVE_MODES[(idx + 1) % len(VALID_AUTOSAVE_MODES)]
            self._render_screen()
            return

        if act == "toggle_hud":
            self.settings.guided_tutorial_hud = not self.settings.guided_tutorial_hud
            self._render_screen()
            return

        if act == "cycle_layout":
            idx = VALID_LAYOUT_MODES.index(self.settings.layout_mode) if self.settings.layout_mode in VALID_LAYOUT_MODES else 0
            self.settings.layout_mode = VALID_LAYOUT_MODES[(idx + 1) % len(VALID_LAYOUT_MODES)]
            self._apply_responsive_class()
            self._render_screen()
            return

        if act == "save_settings":
            save_settings(self.settings, self.settings_path)
            self.mode = "main"
            self.status_message = "Settings saved."
            self._render_screen()
            return
