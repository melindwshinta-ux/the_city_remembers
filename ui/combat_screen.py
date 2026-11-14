"""Tactical combat grid and command display (GDD Section 16)."""

from __future__ import annotations

from typing import Any


def render_combat_view(game_session: Any) -> str:
    """Render tactical battlefield grid, commands, and initiative."""
    combat_sys = game_session.combat_system
    enc = getattr(combat_sys, "active_encounter", None)
    if not enc:
        from entities.character import Character
        party = [game_session.world.player]
        enemies = [Character(id="npc_voss", name="Captain Voss", age=38)]
        enc = combat_sys.create_encounter(party, enemies)

    grid_str = enc.render_ascii_grid()
    lines = [
        "=== TACTICAL BATTLEFIELD ===",
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
