"""QOL Textual widgets and modals: CommandInput, HelpModal, QuitConfirmModal."""

from __future__ import annotations

from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class CommandInput(Input):
    """Command input with Up/Down command history and Esc-to-blur."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.history: list[str] = []
        self.history_index: int | None = None
        self._draft: str = ""

    def add_to_history(self, cmd: str) -> None:
        cleaned = cmd.strip()
        if cleaned and (not self.history or self.history[-1] != cleaned):
            self.history.append(cleaned)
        self.history_index = None
        self._draft = ""

    def on_key(self, event: events.Key) -> None:
        if event.key == "up":
            if not self.history:
                return
            if self.history_index is None:
                self._draft = self.value
                self.history_index = len(self.history) - 1
            elif self.history_index > 0:
                self.history_index -= 1
            self.value = self.history[self.history_index]
            self.cursor_position = len(self.value)
            event.stop()
            event.prevent_default()
        elif event.key == "down":
            if self.history_index is None:
                return
            if self.history_index < len(self.history) - 1:
                self.history_index += 1
                self.value = self.history[self.history_index]
            else:
                self.history_index = None
                self.value = self._draft
            self.cursor_position = len(self.value)
            event.stop()
            event.prevent_default()
        elif event.key == "escape":
            self.app.set_focus(None)
            event.stop()
            event.prevent_default()


class HelpModal(ModalScreen[None]):
    """Modal reference for structured commands and keyboard shortcuts."""

    CSS = """
    HelpModal {
        align: center middle;
    }
    #help-dialog {
        width: 90%;
        max-width: 76;
        height: auto;
        max-height: 22;
        overflow-y: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    #help-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #help-body {
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("q", "dismiss_modal", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static("THE CITY REMEMBERS — Command & Shortcut Reference", id="help-title")
            yield Static(
                "Warsim Controls (Zero-Typing Mode):\n"
                "  1-9 / 0 (or click Action) Choose numbered action / Back / Debug\n"
                "  F2-F9 or Alt+1-8          Switch between the 8 information views\n"
                "  ? or F1                   Open this Help dialog\n"
                "  Ctrl+Q or q               Quit game (with confirmation)\n\n"
                "Legacy CLI Commands (when Command Input is visible):\n"
                "  move <location_id>        Travel to a connected location\n"
                "  inspect <target>          Inspect a scene, NPC, or clue\n"
                "  talk <npc>                Speak with a companion or NPC\n"
                "  choose <approach>         Resolve a mission approach (e.g. investigate)\n"
                "  check health              Check wounds, trauma, and stamina\n"
                "  open <view>               Switch view (world, character, health, party, combat, factions, journal, inventory)\n"
                "  rest <hours>h / wait <t>  Rest or pass time\n"
                "  save [slot] / load [slot] Save or load game state\n"
                "  prologue / skip prologue  Replay or skip the arrival prologue\n"
                "  tutorial / tutorial skip  Check, skip, or reset the tutorial",
                id="help-body",
            )
            yield Button("Close", id="btn-help-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-help-close":
            self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)


class QuitConfirmModal(ModalScreen[bool]):
    """Confirmation dialog before exiting the application."""

    CSS = """
    QuitConfirmModal {
        align: center middle;
    }
    #quit-dialog {
        width: 56;
        max-width: 90%;
        height: auto;
        border: solid $error;
        background: $surface;
        padding: 1 2;
    }
    #quit-prompt {
        margin-bottom: 1;
    }
    #quit-actions {
        height: auto;
    }
    #quit-actions Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="quit-dialog"):
            yield Static("Leave Veyr? Unsaved progress will be lost.", id="quit-prompt")
            with Horizontal(id="quit-actions"):
                yield Button("Quit", id="btn-quit-confirm", variant="error")
                yield Button("Cancel", id="btn-quit-cancel", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-quit-confirm":
            self.dismiss(True)
        elif event.button.id == "btn-quit-cancel":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)
