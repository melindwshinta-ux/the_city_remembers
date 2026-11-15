"""Interactive Textual PrologueScreen for THE CITY REMEMBERS."""

from __future__ import annotations

from typing import Any

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from content.prologue import PROLOGUE_CHOICES


class PrologueScreen(Screen[dict[str, Any] | None]):
    """Multi-beat interactive arrival story and opening stance selection."""

    CSS = """
    PrologueScreen {
        align: center middle;
    }
    #prologue-container {
        width: 96%;
        max-width: 96;
        height: auto;
        max-height: 90%;
        overflow-y: auto;
        border: solid $accent;
        background: $surface;
        padding: 0 1;
    }
    #prologue-step-header {
        height: auto;
        text-style: bold;
        color: $accent;
        margin-bottom: 0;
    }
    #prologue-narrative {
        height: auto;
        margin-bottom: 0;
    }
    #prologue-choices {
        height: auto;
        margin-bottom: 0;
    }
    #prologue-choices Button {
        width: 100%;
        height: 1;
        border: none;
        padding: 0 1;
        margin-bottom: 0;
    }
    #prologue-choice-preview {
        height: auto;
        border: solid $primary;
        padding: 0 1;
        margin-top: 0;
        margin-bottom: 0;
    }
    #prologue-status {
        height: auto;
        margin-bottom: 0;
    }
    #prologue-actions {
        height: auto;
        margin-top: 0;
        align: left middle;
    }
    #prologue-actions Button {
        height: 1;
        border: none;
        padding: 0 2;
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "skip_prologue", "Skip Prologue"),
    ]

    def __init__(self, game: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.game = game
        self.selected_choice: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="prologue-container"):
            yield Static("", id="prologue-step-header", markup=True)
            yield Static("", id="prologue-narrative", markup=True)
            with Vertical(id="prologue-choices"):
                for cid in ("watch_investigator", "street_broker", "unbound_drifter"):
                    spec = PROLOGUE_CHOICES.get(cid, {})
                    label = spec.get("label", cid)
                    yield Button(label, id=f"choice-{cid}", variant="default")
                yield Static(
                    "Select an opening stance above to preview its starting effects.",
                    id="prologue-choice-preview",
                    markup=True,
                )
            yield Static("", id="prologue-status", markup=True)
            with Horizontal(id="prologue-actions"):
                yield Button("Next ->", id="btn-prologue-next", variant="primary")
                yield Button("Begin Investigation ->", id="btn-prologue-begin", variant="success")
                yield Button("Skip Prologue", id="btn-prologue-skip", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_beat()

    def _refresh_beat(self) -> None:
        state = self.game.get_prologue_state()
        beat = state.get("beat")
        if state.get("completed") or beat is None:
            self.dismiss({"completed": True})
            return

        step_num = int(state.get("step", 0)) + 1
        total_steps = int(state.get("total_steps", 3))
        title = escape(str(beat.get("title", "Prologue")))
        narrative = escape(str(beat.get("narrative", "")))

        self.query_one("#prologue-step-header", Static).update(
            f"[bold cyan]PROLOGUE ({step_num}/{total_steps}) — {title}[/]"
        )
        self.query_one("#prologue-narrative", Static).update(narrative)
        self._set_status("")

        requires_choice = bool(beat.get("requires_choice", False))
        choices_box = self.query_one("#prologue-choices", Vertical)
        btn_next = self.query_one("#btn-prologue-next", Button)
        btn_begin = self.query_one("#btn-prologue-begin", Button)

        choices_box.display = requires_choice
        btn_next.display = not requires_choice
        btn_begin.display = requires_choice

        if requires_choice:
            self._refresh_choice_preview()

    def _set_status(self, message: str) -> None:
        status = self.query_one("#prologue-status", Static)
        status.update(message)
        status.display = bool(message)

    def _refresh_choice_preview(self) -> None:
        for cid in ("watch_investigator", "street_broker", "unbound_drifter"):
            btn = self.query_one(f"#choice-{cid}", Button)
            btn.variant = "primary" if cid == self.selected_choice else "default"

        preview = self.query_one("#prologue-choice-preview", Static)
        if self.selected_choice and self.selected_choice in PROLOGUE_CHOICES:
            spec = PROLOGUE_CHOICES[self.selected_choice]
            label = escape(str(spec.get("label", self.selected_choice)))
            summary = escape(str(spec.get("summary", "")))
            effects = escape(str(spec.get("effects_summary", "")))
            preview.update(
                f"[bold]{label}[/]\n{summary}\n[green]Effects:[/] {effects}"
            )
        else:
            preview.update("Select an opening stance above to preview its starting effects.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("choice-"):
            self.selected_choice = btn_id[len("choice-") :]
            self._set_status("")
            self._refresh_choice_preview()
        elif btn_id == "btn-prologue-next":
            res = self.game.advance_prologue()
            if not res.get("success"):
                self._set_status(
                    f"[bold red]{escape(str(res.get('message', 'Could not advance prologue.')))}[/]"
                )
                return
            self._refresh_beat()
        elif btn_id == "btn-prologue-begin":
            if not self.selected_choice:
                self._set_status(
                    "[bold yellow]Select an opening stance to continue.[/]"
                )
                return
            res = self.game.advance_prologue(choice_id=self.selected_choice)
            if not res.get("success"):
                self._set_status(
                    f"[bold red]{escape(str(res.get('message', 'Could not complete prologue.')))}[/]"
                )
                return
            self.dismiss(
                {
                    "completed": True,
                    "choice_id": self.selected_choice,
                    "message": res.get("message", ""),
                }
            )
        elif btn_id == "btn-prologue-skip":
            self.action_skip_prologue()

    def action_skip_prologue(self) -> None:
        res = self.game.skip_prologue()
        self.dismiss({"skipped": True, "message": res.get("message", "")})
