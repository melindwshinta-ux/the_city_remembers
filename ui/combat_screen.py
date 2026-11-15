"""Tactical combat grid and command display (GDD Section 16)."""

from __future__ import annotations

from typing import Any


def render_combat_view(game_session: Any) -> str:
    """Render tactical battlefield grid, commands, and initiative."""
    combat_sys = getattr(game_session, "combat_system", None)
    enc = getattr(combat_sys, "active_encounter", None)
    if enc is None:
        status_line = "Status: No active combat encounter (Tactical Preview)"
        player = getattr(getattr(game_session, "world", None), "player", None)
        if player is not None:
            from entities.character import Character
            from systems.combat_system import Encounter

            preview = Encounter(
                party=[player],
                enemies=[Character(id="npc_voss", name="Captain Voss", age=38)],
            )
            grid_str = preview.render_ascii_grid()
        else:
            grid_str = "\n".join(" ".join("[ . ]" for _ in range(5)) for _ in range(5))
    else:
        status_line = "Status: Active Combat Encounter"
        grid_str = enc.render_ascii_grid()

    lines = [
        "=== TACTICAL BATTLEFIELD ===",
        status_line,
        grid_str,
        "",
        "Available Command Categories:",
        "  Movement: Move, Charge, Retreat, Flank, Take Cover",
        "  Combat: Attack, Heavy Attack, Aim, Guard, Disarm, Grapple, Interrupt",
        "  Support: Heal, Stabilize, Apply Bandage, Revive, Protect Ally",
        "  Special: Spellcasting, Stealth Attack, Area Attack, Environmental Interaction",
    ]
    return "\n".join(lines)


def format_combat_screen(game_session: Any) -> str:
    return render_combat_view(game_session)


def render_screen(game_session: Any) -> str:
    return render_combat_view(game_session)
