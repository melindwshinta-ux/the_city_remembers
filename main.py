"""Main terminal entry point and Textual application for THE CITY REMEMBERS."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, HorizontalScroll, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, RichLog, Static

from core.game import Game
from ui.character_screen import render_character_view, render_party_view
from ui.combat_screen import render_combat_view
from ui.faction_screen import render_faction_view
from ui.health_screen import render_health_view
from ui.journal_screen import render_inventory_view, render_journal_view
from ui.main_screen import render_main_view
from ui.map_screen import render_map_view
from ui.modals import CommandInput, HelpModal, QuitConfirmModal
from ui.prologue_screen import PrologueScreen
from ui.title_screen import TitleScreen

VIEWS: tuple[tuple[str, str], ...] = (
    ("world", "1:World"),
    ("character", "2:Char"),
    ("health", "3:Health"),
    ("party", "4:Party"),
    ("combat", "5:Combat"),
    ("factions", "6:Fact"),
    ("journal", "7:Journ"),
    ("inventory", "8:Inv"),
)
VIEW_KEYS: frozenset[str] = frozenset(view_id for view_id, _ in VIEWS)


class CityRemembersApp(App[None]):
    """Interactive Textual terminal UI for THE CITY REMEMBERS."""

    TITLE = "THE CITY REMEMBERS — Veyr"
    SUB_TITLE = "Systemic Narrative RPG"

    CSS = """
    #status-banner {
        height: 1;
        padding: 0 1;
        background: $primary-darken-2;
        color: $text;
    }
    #nav-bar {
        layout: grid;
        grid-size: 4 2;
        grid-gutter: 0 1;
        height: auto;
        padding: 0 1;
        background: $panel;
    }
    #nav-bar Button {
        width: 1fr;
        margin: 0;
        min-width: 0;
        height: 1;
        border: none;
        padding: 0 1;
    }
    #tutorial-hud {
        height: auto;
        max-height: 8;
        padding: 0 1;
        margin: 0 1;
        border: solid $secondary;
        background: $surface;
    }
    #tutorial-hud.collapsed #tutorial-hud-body {
        display: none;
    }
    #tutorial-hud-title {
        width: 100%;
        height: auto;
    }
    #tutorial-hud-bar {
        height: auto;
        align: left middle;
    }
    #tutorial-hud-bar Button {
        min-width: 0;
        height: 1;
        border: none;
        padding: 0 1;
        margin: 0 1 0 0;
    }
    #tutorial-hud-body {
        height: auto;
    }
    #main-pane {
        height: 1fr;
        padding: 0 1;
    }
    #view-content {
        height: 1fr;
        min-height: 4;
        overflow-y: auto;
        border: solid $accent;
        padding: 0 1;
    }
    #command-log {
        height: 5;
        border: solid $primary;
        padding: 0 1;
        margin-top: 0;
    }
    #action-deck {
        layout: grid;
        grid-size: 2 5;
        grid-gutter: 0 1;
        height: auto;
        padding: 0 1;
        margin: 0 1;
        background: $panel;
    }
    #action-deck Button {
        width: 1fr;
        min-width: 0;
        height: 1;
        border: none;
        padding: 0 1;
        margin: 0;
        content-align: left middle;
    }
    #quick-actions {
        height: 1;
        min-height: 1;
        max-height: 2;
        margin: 0 1;
        padding: 0;
        background: $panel;
        scrollbar-size-horizontal: 0;
    }
    #quick-actions Button {
        min-width: 0;
        height: 1;
        border: none;
        padding: 0 1;
        margin: 0 1 0 0;
    }
    #command-input {
        dock: bottom;
        margin: 0 1;
    }
    CityRemembersApp.compact #nav-bar Button {
        padding: 0;
    }
    CityRemembersApp.warsim.compact #tutorial-hud {
        max-height: 4;
    }
    CityRemembersApp.compact #command-log {
        height: 3;
    }
    CityRemembersApp.compact #action-deck {
        padding: 0;
        margin: 0;
    }
    """

    BINDINGS = [
        Binding("1", "number_key('1')", "1", show=False),
        Binding("2", "number_key('2')", "2", show=False),
        Binding("3", "number_key('3')", "3", show=False),
        Binding("4", "number_key('4')", "4", show=False),
        Binding("5", "number_key('5')", "5", show=False),
        Binding("6", "number_key('6')", "6", show=False),
        Binding("7", "number_key('7')", "7", show=False),
        Binding("8", "number_key('8')", "8", show=False),
        Binding("9", "number_key('9')", "9", show=False),
        Binding("0", "number_key('0')", "0", show=False),
        Binding("f2", "switch_view('world')", "World", show=False),
        Binding("f3", "switch_view('character')", "Character", show=False),
        Binding("f4", "switch_view('health')", "Health", show=False),
        Binding("f5", "switch_view('party')", "Party", show=False),
        Binding("f6", "switch_view('combat')", "Combat", show=False),
        Binding("f7", "switch_view('factions')", "Factions", show=False),
        Binding("f8", "switch_view('journal')", "Journal", show=False),
        Binding("f9", "switch_view('inventory')", "Inventory", show=False),
        Binding("alt+1", "switch_view('world')", "World", show=False),
        Binding("alt+2", "switch_view('character')", "Character", show=False),
        Binding("alt+3", "switch_view('health')", "Health", show=False),
        Binding("alt+4", "switch_view('party')", "Party", show=False),
        Binding("alt+5", "switch_view('combat')", "Combat", show=False),
        Binding("alt+6", "switch_view('factions')", "Factions", show=False),
        Binding("alt+7", "switch_view('journal')", "Journal", show=False),
        Binding("alt+8", "switch_view('inventory')", "Inventory", show=False),
        Binding("question_mark", "show_help", "Help"),
        Binding("f1", "show_help", "Help", show=False),
        Binding("ctrl+q", "request_quit", "Quit", priority=True),
        Binding("q", "request_quit", "Quit"),
    ]

    def __init__(
        self,
        game: Game | None = None,
        show_prologue: bool | None = None,
        show_title: bool = False,
        warsim_mode: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.game: Game = game if game is not None else Game()
        self.show_title: bool = bool(show_title)
        self.warsim_mode: bool = bool(warsim_mode)
        self.show_prologue: bool = (
            (game is None and not self.show_title) if show_prologue is None else bool(show_prologue)
        )
        self.current_view: str = "world"
        self.hud_collapsed: bool = False
        self._quick_cmd_map: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        banner = Static("", id="status-banner", markup=True)
        banner.display = self.warsim_mode
        yield banner
        with Horizontal(id="nav-bar"):
            for view_id, label in VIEWS:
                variant = "primary" if view_id == self.current_view else "default"
                yield Button(label, id=f"btn-{view_id}", variant=variant)
        with Vertical(id="tutorial-hud"):
            yield Static("", id="tutorial-hud-title", markup=True)
            with Horizontal(id="tutorial-hud-bar"):
                yield Button("Hide", id="btn-hud-toggle", variant="default")
                yield Button("Next Hint", id="btn-hud-next-hint", variant="default")
                yield Button("Skip Tutorial", id="btn-hud-skip-tutorial", variant="default")
                yield Button("Prologue", id="btn-hud-prologue", variant="default")
                yield Button("Help", id="btn-hud-help", variant="default")
            with Vertical(id="tutorial-hud-body"):
                yield Static("", id="tutorial-hud-detail", markup=True)
        with Vertical(id="main-pane"):
            yield Static(escape(self.render_active_view()), id="view-content", markup=True)
            yield RichLog(id="command-log", highlight=True, markup=True, wrap=True)
        with Vertical(id="action-deck") as deck:
            deck.display = self.warsim_mode
            for key in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"):
                btn = Button("", id=f"action-{key}", variant="default")
                btn.display = False
                yield btn
        with HorizontalScroll(id="quick-actions") as qa:
            qa.display = not self.warsim_mode
            for idx in range(12):
                btn = Button("", id=f"qa-{idx}", variant="default")
                btn.display = False
                yield btn
        cmd_input = CommandInput(
            placeholder="Click Quick Actions above or type command (e.g. 'talk sera', 'help')...",
            id="command-input",
        )
        cmd_input.display = not self.warsim_mode
        yield cmd_input
        yield Footer()

    def on_mount(self) -> None:
        self._apply_responsive_class()
        self.refresh_status_banner()
        self.refresh_view()
        self.refresh_tutorial_hud()
        self.refresh_quick_actions()
        self.refresh_action_deck()
        log = self.query_one("#command-log", RichLog)
        if self.warsim_mode:
            log.write("[bold green]Welcome to Veyr.[/] Press [cyan]1-9[/] or [cyan]0[/] (or click buttons) to play.")
        else:
            log.write("[bold green]Welcome to Veyr.[/] Click quick buttons below or type [cyan]'help'[/] / press [cyan]?[/] / [cyan]F1[/].")
        if self.show_title:
            self.push_screen(
                TitleScreen(settings=self.game.settings, save_manager=self.game.save_manager),
                callback=self._on_title_closed,
            )
        elif self.show_prologue and self.game.get_prologue_state().get("active", False):
            self.push_screen(PrologueScreen(self.game), callback=self._on_prologue_closed)

    def on_resize(self) -> None:
        self._apply_responsive_class()

    def _apply_responsive_class(self) -> None:
        if self.warsim_mode:
            self.add_class("warsim")
        else:
            self.remove_class("warsim")
        layout_mode = getattr(getattr(self.game, "settings", None), "layout_mode", "auto")
        is_compact = layout_mode == "compact" or (
            layout_mode == "auto" and (self.size.width <= 85 or self.size.height <= 26)
        )
        if is_compact:
            self.add_class("compact")
        else:
            self.remove_class("compact")

    def _on_title_closed(self, result: dict[str, Any] | None) -> None:
        if result is None or result.get("action") == "quit":
            self.exit()
            return
        act = result.get("action")
        if act in ("continue", "load"):
            slot = str(result.get("slot", ""))
            res = self.game.execute_command({"action": "load", "actor": "player", "slot": slot})
            self.game.menu_engine.reset()
            log = self.query_one("#command-log", RichLog)
            log.write(f"[green]{escape(str(res.get('message', f'Loaded {slot}.')))}[/]")
        elif act == "new_game":
            self.game = Game(
                settings=result.get("settings", self.game.settings),
                difficulty=result.get("difficulty"),
                background=result.get("background"),
                keepsake=result.get("keepsake"),
                skip_prologue=bool(result.get("skip_prologue", False)),
            )
            if not result.get("skip_prologue", False) and self.game.get_prologue_state().get("active", False):
                self.push_screen(PrologueScreen(self.game), callback=self._on_prologue_closed)

        self._apply_responsive_class()
        self.refresh_status_banner()
        self.refresh_view()
        self.refresh_tutorial_hud()
        self.refresh_quick_actions()
        self.refresh_action_deck()

    def _on_prologue_closed(self, result: dict[str, Any] | None) -> None:
        log = self.query_one("#command-log", RichLog)
        if result and result.get("message"):
            log.write(f"[green]{escape(str(result['message']))}[/]")
        elif result and result.get("skipped"):
            log.write("[yellow]Prologue skipped. Act I begins in Lowtown.[/]")
        self.refresh_status_banner()
        self.refresh_view()
        self.refresh_tutorial_hud()
        self.refresh_quick_actions()
        self.refresh_action_deck()

    def render_active_view(self, view: str | None = None) -> str:
        target = (view or self.current_view).lower()
        if self.warsim_mode and target == "world":
            screen = self.game.menu_engine.get_screen()
            if screen.get("mode") == "combat":
                return render_combat_view(self.game)
            return f"=== {screen['title']} ===\n{screen['subtitle']}\n\n{screen['body']}"
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

    def refresh_status_banner(self) -> None:
        banner = self.query_one("#status-banner", Static)
        banner.display = self.warsim_mode
        if not self.warsim_mode:
            return
        world = self.game.world
        player = getattr(world, "player", None)
        p_loc = (getattr(player, "location_id", None) or "lowtown") if player else "lowtown"
        loc = world.get_location(p_loc) if hasattr(world, "get_location") else world.locations.get(p_loc)
        loc_name = getattr(loc, "name", p_loc) if loc else p_loc
        gold = float(getattr(player, "needs", {}).get("wealth", 0.0)) if player else 0.0
        consc = float(getattr(player, "consciousness", 100.0)) if player else 100.0
        diff = str(getattr(getattr(self.game, "settings", None), "difficulty", "balanced")).title()
        epithet = str(getattr(world, "flags", {}).get("epithet", "Unproven Wanderer"))
        clock = world.clock
        text = (
            f"[bold gold1]{escape(clock.act)}[/] Y{clock.year}D{clock.day} {clock.hour:02d}:{clock.minute:02d} | "
            f"[cyan]{escape(loc_name)}[/] | [yellow]{gold:.0f}g[/] | "
            f"Consc {consc:.0f}% | {escape(diff)} | [italic]{escape(epithet)}[/]"
        )
        banner.update(text)

    def refresh_action_deck(self) -> None:
        deck = self.query_one("#action-deck", Vertical)
        deck.display = self.warsim_mode
        if not self.warsim_mode:
            return
        screen = self.game.menu_engine.get_screen()
        opts = {str(o["key"]): o for o in screen.get("options", [])}
        debug_on = bool(getattr(getattr(self.game, "settings", None), "enable_debug_cheat", False))
        for key in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"):
            btn = self.query_one(f"#action-{key}", Button)
            opt = opts.get(key)
            if opt is None:
                btn.display = False
            else:
                tags = opt.get("tags") or []
                tag_str = f" ({', '.join(tags[:2])})" if tags else ""
                btn.label = f"[{key}] {opt['label']}{tag_str}"
                btn.disabled = not bool(opt.get("enabled", True))
                if key == "1" and opt.get("enabled", True):
                    btn.variant = "primary"
                elif key == "0" and screen.get("mode") == "hub" and debug_on:
                    btn.variant = "warning"
                else:
                    btn.variant = "default"
                btn.display = True

    def refresh_view(self) -> None:
        content = self.query_one("#view-content", Static)
        content.update(escape(self.render_active_view()))
        for view_id, _ in VIEWS:
            btn = self.query_one(f"#btn-{view_id}", Button)
            btn.variant = "primary" if view_id == self.current_view else "default"

    def refresh_tutorial_hud(self) -> None:
        t_state = self.game.get_tutorial_state()
        done, total = t_state.get("progress", (0, 0))
        title_widget = self.query_one("#tutorial-hud-title", Static)
        detail_widget = self.query_one("#tutorial-hud-detail", Static)
        hud_box = self.query_one("#tutorial-hud", Vertical)
        toggle_btn = self.query_one("#btn-hud-toggle", Button)

        if self.warsim_mode and not getattr(getattr(self.game, "settings", None), "guided_tutorial_hud", True):
            hud_box.display = False
            return
        hud_box.display = True

        if self.hud_collapsed:
            hud_box.add_class("collapsed")
            toggle_btn.label = "Show"
        else:
            hud_box.remove_class("collapsed")
            toggle_btn.label = "Hide"

        if t_state.get("skipped"):
            title_widget.update(
                f"[yellow]Objective HUD: Tutorial skipped ({done}/{total})[/]"
            )
            detail_widget.update(
                "Type [cyan]tutorial reset[/] to resume guided Mission 1-2 objectives."
            )
            return

        step_info = t_state.get("step_info")
        if t_state.get("completed") or not step_info:
            title_widget.update(
                f"[bold green]Objective HUD: Tutorial Complete ({done}/{total})[/]"
            )
            detail_widget.update(
                "All onboarding steps complete. Explore Veyr freely or type [cyan]help[/]."
            )
            return

        step_title = escape(str(step_info.get("title", "Next Objective")))
        instruction = escape(str(step_info.get("instruction", "")))
        hint = escape(str(step_info.get("hint", "")))
        suggested = step_info.get("suggested_commands", [])
        sug_str = ", ".join(escape(str(c)) for c in suggested[:3])

        title_widget.update(
            f"[bold cyan]Objective ({done}/{total}): {step_title}[/]"
        )
        detail_lines = [instruction]
        if hint:
            detail_lines.append(f"[dim]Hint:[/] {hint}")
        if sug_str:
            detail_lines.append(f"[dim]Try:[/] [cyan]{sug_str}[/]")
        detail_widget.update("\n".join(detail_lines))

    def _build_quick_actions(self) -> list[tuple[str, str, str]]:
        """Return list of (label, command, variant) for mouse-driven quick actions."""
        actions: list[tuple[str, str, str]] = []
        seen_cmds: set[str] = set()

        def add_action(label: str, cmd: str, variant: str = "default") -> None:
            norm = cmd.strip().lower()
            if norm and norm not in seen_cmds:
                seen_cmds.add(norm)
                actions.append((label, cmd, variant))

        # 1. Active tutorial suggested command
        t_state = self.game.get_tutorial_state()
        if not t_state.get("skipped") and not t_state.get("completed"):
            step_info = t_state.get("step_info") or {}
            suggested = step_info.get("suggested_commands") or []
            if suggested:
                first_cmd = str(suggested[0])
                add_action(f"Do: {first_cmd}", first_cmd, "primary")

        # 2. Active combat quick commands
        if getattr(self.game, "active_encounter", None) is not None:
            add_action("Attack", "attack", "warning")
            add_action("Aim Leg", "aim left_leg", "default")
            add_action("Defend", "defend", "default")
            add_action("First Aid", "first_aid", "default")
            add_action("Retreat", "retreat", "default")

        # 3. Nearby NPCs and connected exits at current location
        world = self.game.world
        player = getattr(world, "player", None)
        p_loc = (getattr(player, "location_id", None) or "lowtown") if player else "lowtown"
        p_id = getattr(player, "id", "player") if player else "player"
        loc = (
            world.get_location(p_loc)
            if hasattr(world, "get_location")
            else getattr(world, "locations", {}).get(p_loc)
        )

        npc_count = 0
        seen_npcs: set[str] = {p_id}
        if loc:
            for nid in getattr(loc, "npcs_present", []):
                if nid in seen_npcs or npc_count >= 4:
                    continue
                seen_npcs.add(nid)
                npc = world.get_character(nid) if hasattr(world, "get_character") else None
                if npc and getattr(npc, "status", "alive") != "dead":
                    add_action(f"Talk: {npc.name}", f"talk {nid}")
                    npc_count += 1
        for cid, char in getattr(world, "characters", {}).items():
            if cid in seen_npcs or npc_count >= 4:
                continue
            if getattr(char, "location_id", None) == p_loc and getattr(char, "status", "alive") != "dead":
                seen_npcs.add(cid)
                add_action(f"Talk: {getattr(char, 'name', cid)}", f"talk {cid}")
                npc_count += 1

        if loc and getattr(loc, "connected_locations", None):
            for eid in list(loc.connected_locations)[:4]:
                dest = world.get_location(eid) if hasattr(world, "get_location") else None
                dest_name = dest.name if dest else str(eid).replace("_", " ").title()
                add_action(f"Go: {dest_name}", f"move {eid}")

        # 4. Universal QOL actions
        add_action("Rest 8h", "rest 8h")
        add_action("Wait 1h", "wait 1h")
        add_action("Save", "save")
        return actions

    def refresh_quick_actions(self) -> None:
        """Update the clickable quick-actions bar for the current game context."""
        actions = self._build_quick_actions()[:12]
        self._quick_cmd_map.clear()
        for idx in range(12):
            btn_id = f"qa-{idx}"
            try:
                btn = self.query_one(f"#{btn_id}", Button)
            except Exception:
                continue
            if idx < len(actions):
                label, cmd, variant = actions[idx]
                self._quick_cmd_map[btn_id] = cmd
                btn.label = label
                btn.variant = variant  # type: ignore[assignment]
                btn.display = True
            else:
                btn.display = False

    def action_number_key(self, key: str) -> None:
        if isinstance(self.screen, (TitleScreen, PrologueScreen, ModalScreen)):
            return
        if self.warsim_mode:
            self._handle_warsim_choice(key)
        elif key in {"1", "2", "3", "4", "5", "6", "7", "8"}:
            view_id = VIEWS[int(key) - 1][0]
            self.action_switch_view(view_id)

    def _handle_warsim_choice(self, key: str) -> None:
        res = self.game.menu_engine.select(key)
        self.current_view = "world"
        msg = res.get("message")
        if msg:
            log = self.query_one("#command-log", RichLog)
            color = "green" if res.get("success", True) else "bold red"
            log.write(f"[{color}]{escape(str(msg))}[/]")
        self._apply_responsive_class()
        self.refresh_status_banner()
        self.refresh_view()
        self.refresh_tutorial_hud()
        self.refresh_action_deck()

    def action_switch_view(self, view: str) -> None:
        if isinstance(self.screen, (TitleScreen, PrologueScreen, ModalScreen)):
            return
        if view in VIEW_KEYS:
            self.current_view = view
            self.refresh_view()

    def action_show_help(self) -> None:
        if isinstance(self.screen, (TitleScreen, PrologueScreen, ModalScreen)):
            return
        self.push_screen(HelpModal())

    def action_request_quit(self) -> None:
        if isinstance(self.screen, (TitleScreen, PrologueScreen, ModalScreen)):
            return
        self.push_screen(QuitConfirmModal(), callback=self._on_quit_confirmed)

    def _on_quit_confirmed(self, confirmed: bool | None) -> None:
        if confirmed:
            self.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("action-"):
            key = btn_id[len("action-") :]
            if self.warsim_mode:
                self._handle_warsim_choice(key)
            return
        if btn_id.startswith("qa-"):
            cmd = self._quick_cmd_map.get(btn_id)
            if cmd:
                self._execute_ui_command(cmd)
            return
        if btn_id == "btn-hud-toggle":
            self.hud_collapsed = not self.hud_collapsed
            self.refresh_tutorial_hud()
            return
        if btn_id == "btn-hud-next-hint":
            self.hud_collapsed = False
            self.refresh_tutorial_hud()
            t_state = self.game.get_tutorial_state()
            step_info = t_state.get("step_info")
            log = self.query_one("#command-log", RichLog)
            if step_info:
                log.write(
                    f"[cyan]Hint ({escape(str(step_info.get('title', 'Objective')))}):[/] "
                    f"{escape(str(step_info.get('hint', '')))}"
                )
            else:
                log.write("[green]All tutorial hints complete![/]")
            return
        if btn_id == "btn-hud-skip-tutorial":
            res = self.game.skip_tutorial()
            self.query_one("#command-log", RichLog).write(
                f"[yellow]{escape(str(res.get('message', 'Tutorial skipped.')))}[/]"
            )
            self.refresh_tutorial_hud()
            self.refresh_quick_actions()
            self.refresh_action_deck()
            return
        if btn_id == "btn-hud-prologue":
            self.game.replay_prologue()
            self.push_screen(PrologueScreen(self.game), callback=self._on_prologue_closed)
            return
        if btn_id == "btn-hud-help":
            self.action_show_help()
            return
        if btn_id.startswith("btn-"):
            self.action_switch_view(btn_id[len("btn-") :])

    def _execute_ui_command(self, raw_cmd: str) -> None:
        """Execute a structured command from either keyboard input or a mouse button."""
        raw_cmd = raw_cmd.strip()
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
        log.write(f"[bold cyan]> {escape(raw_cmd)}[/]")
        msg = res.get("message")
        if msg:
            color = "green" if res.get("success", True) else "bold red"
            log.write(f"[{color}]{escape(str(msg))}[/]")

        if res.get("success") and (
            action == "replay_prologue"
            or (action == "prologue" and self.game.get_prologue_state().get("active", False))
        ):
            self.push_screen(PrologueScreen(self.game), callback=self._on_prologue_closed)
        elif res.get("success") and action == "prologue" and raw_cmd.lower() == "prologue":
            replay_res = self.game.replay_prologue()
            if replay_res.get("message"):
                log.write(f"[green]{escape(str(replay_res['message']))}[/]")
            self.push_screen(PrologueScreen(self.game), callback=self._on_prologue_closed)

        self.refresh_view()
        self.refresh_tutorial_hud()
        self.refresh_quick_actions()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw_cmd = event.value.strip()
        event.input.value = ""
        if not raw_cmd:
            return
        if isinstance(event.input, CommandInput):
            event.input.add_to_history(raw_cmd)
        self._execute_ui_command(raw_cmd)


def create_app(
    game: Game | None = None,
    show_prologue: bool | None = None,
    show_title: bool = False,
    warsim_mode: bool = False,
) -> CityRemembersApp:
    """Create and return a configured CityRemembersApp instance."""
    return CityRemembersApp(
        game=game,
        show_prologue=show_prologue,
        show_title=show_title,
        warsim_mode=warsim_mode,
    )


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
        app = create_app(show_title=True, warsim_mode=True)
        app.run()


if __name__ == "__main__":
    main()

