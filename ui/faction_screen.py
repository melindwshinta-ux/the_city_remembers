"""Faction politics, power balance, and Nemesis status screen (GDD Section 16)."""

from __future__ import annotations

from typing import Any


def render_faction_view(game_session: Any) -> str:
    """Render 7 city factions, power balances, and Nemesis profiles."""
    world = game_session.world
    lines = ["=== FACTION POLITICS & NEMESIS DOSSIER ==="]
    for fid, f in getattr(world, "factions", {}).items():
        leader = f.leader_id or "Vacant"
        lines.append(f"[{f.name}] - Power: {f.power:.0f} | Wealth: {f.wealth:.0f} | Leader: {leader}")

    lines.append("")
    lines.append("Nemesis Antagonists:")
    for nid, nem in getattr(world, "nemesis_profiles", {}).items():
        char = world.characters.get(nid)
        name = char.name if char else nid
        lines.append(f"  {name} ({nem.rank.title()}) - Hostility: {nem.player_hostility:.0f}% | Ambition: {nem.current_ambition}")
        if nem.grudges:
            lines.append(f"    Grudges: {', '.join(nem.grudges)}")
        if nem.special_traits:
            lines.append(f"    Adaptations: {', '.join(nem.special_traits)}")

    return "\n".join(lines)


def format_faction_screen(game_session: Any) -> str:
    return render_faction_view(game_session)


def render_screen(game_session: Any) -> str:
    return render_faction_view(game_session)
