"""Main terminal entry point and Textual application for THE CITY REMEMBERS."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, RichLog, Static

from core.game import Game
from ui.character_screen import render_character_view, render_party_view
from ui.combat_screen import render_combat_view
from ui.faction_screen import render_faction_view
from ui.health_screen import render_health_view
from ui.journal_screen import render_inventory_view, render_journal_view
from ui.main_screen import render_main_view
from ui.map_screen import render_map_view

VIEWS: tuple[tuple[str, str], ...] = (
    ("world", "World"),
    ("character", "Character"),
    ("health", "Health"),
    ("party", "Party"),
    ("combat", "Combat"),
    ("factions", "Factions"),
    ("journal", "Journal"),
    ("inventory", "Inventory"),
)
VIEW_KEYS: frozenset[str] = frozenset(view_id for view_id, _ in VIEWS)


class CityRemembersApp(App[None]):
    """Interactive Textual terminal UI for THE CITY REMEMBERS."""

    TITLE = "THE CITY REMEMBERS — Veyr"
    SUB_TITLE = "Systemic Narrative RPG"

    CSS = """
    #nav-bar {
        height: auto;
        padding: 0 1;
        background: $panel;
    }
    #nav-bar Button {
        margin: 0 1 0 0;
        min-width: 10;
    }
    #main-pane {
        height: 1fr;
        padding: 1;
    }
    #view-content {
        height: 1fr;
        overflow-y: auto;
        border: solid $accent;
        padding: 1;
    }
    #command-log {
        height: 7;
        border: solid $primary;
        padding: 0 1;
        margin-top: 1;
    }
    #command-input {
        dock: bottom;
        margin: 0 1 1 1;
    }
    """

    BINDINGS = [
        Binding("1", "switch_view('world')", "World"),
        Binding("2", "switch_view('character')", "Character"),
        Binding("3", "switch_view('health')", "Health"),
        Binding("4", "switch_view('party')", "Party"),
        Binding("5", "switch_view('combat')", "Combat"),
        Binding("6", "switch_view('factions')", "Factions"),
        Binding("7", "switch_view('journal')", "Journal"),
        Binding("8", "switch_view('inventory')", "Inventory"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, game: Game | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.game: Game = game if game is not None else Game()
        self.current_view: str = "world"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="nav-bar"):
            for view_id, label in VIEWS:
                variant = "primary" if view_id == self.current_view else "default"
                yield Button(label, id=f"btn-{view_id}", variant=variant)
        with Vertical(id="main-pane"):
            yield Static(self.render_active_view(), id="view-content")
            yield RichLog(id="command-log", highlight=True, markup=False)
        yield Input(
            placeholder="Enter command (e.g. 'talk sera', 'open health', 'rest 8h', 'help')...",
            id="command-input",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_view()
        log = self.query_one("#command-log", RichLog)
        log.write("Welcome to Veyr. Type 'help' for available commands.")

    def render_active_view(self, view: str | None = None) -> str:
        target = (view or self.current_view).lower()
        if target == "world":
            return f"{render_main_view(self.game)}\n\n{render_map_view(self.game)}"
        if target == "character":
            return render_character_view(self.game)
        if target == "health":
            return render_health_view(self.game)
        if target == "party":
            return render_party_view(self.game)
        if target == "combat":
            return render_combat_view(self.game)
        if target == "factions":
            return render_faction_view(self.game)
        if target == "journal":
            return render_journal_view(self.game)
        if target == "inventory":
            return render_inventory_view(self.game)
        return render_main_view(self.game)

    def refresh_view(self) -> None:
        content = self.query_one("#view-content", Static)
        content.update(self.render_active_view())
        for view_id, _ in VIEWS:
            btn = self.query_one(f"#btn-{view_id}", Button)
            btn.variant = "primary" if view_id == self.current_view else "default"

    def action_switch_view(self, view: str) -> None:
        if view in VIEW_KEYS:
            self.current_view = view
            self.refresh_view()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("btn-"):
            self.action_switch_view(btn_id[len("btn-") :])

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw_cmd = event.value.strip()
        event.input.value = ""
        if not raw_cmd:
            return
        if raw_cmd.lower() in {"exit", "quit"}:
            self.exit()
            return

        res = self.game.execute_command(raw_cmd)
        action = str(res.get("action", ""))
        if res.get("success") and action.startswith("open_"):
            target_view = action[len("open_") :]
            if target_view == "faction":
                target_view = "factions"
            if target_view in VIEW_KEYS:
                self.current_view = target_view

        log = self.query_one("#command-log", RichLog)
        log.write(f"> {raw_cmd}")
        msg = res.get("message")
        if msg:
            log.write(str(msg))
        self.refresh_view()


def create_app(game: Game | None = None) -> CityRemembersApp:
    """Create and return a configured CityRemembersApp instance."""
    return CityRemembersApp(game=game)


def main(argv: list[str] | None = None) -> None:
    """Launch terminal session for THE CITY REMEMBERS."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="THE CITY REMEMBERS — Systemic narrative RPG in Veyr.",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Print initial world overview in non-interactive CLI mode and exit.",
    )
    parser.add_argument(
        "command",
        nargs="*",
        help="Optional structured command to execute directly (e.g. 'talk sera').",
    )
    args = parser.parse_args(argv)

    if args.command:
        game = Game()
        res = game.execute_command(" ".join(args.command))
        print(res.get("message", "Done."))
    elif args.cli or not sys.stdin.isatty():
        game = Game()
        print(render_main_view(game))
        print("\nType a command (e.g. 'talk sera', 'inspect captain voss', 'rest 8h') or 'exit'.")
    else:
        app = create_app()
        app.run()


if __name__ == "__main__":
    main()

