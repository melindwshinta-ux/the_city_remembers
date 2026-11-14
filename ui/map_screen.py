"""Map and district locations screen (GDD Section 16)."""

from __future__ import annotations

from typing import Any


def render_map_view(game_session: Any) -> str:
    """Render city district map and locations."""
    world = game_session.world
    lines = ["=== DISTRICT MAP OF VEYR ==="]
    for did, dist in getattr(world, "districts", {}).items():
        inf_summary = ", ".join(f"{k}: {v:.0f}%" for k, v in dist.faction_influence.items())
        lines.append(f"[{dist.name}] - Pop: {dist.population:,} | Unrest: {dist.unrest:.0f}% | Security: {dist.security:.0f}%")
        lines.append(f"  Influence: {inf_summary}")
        if dist.locations:
            lines.append(f"  Locations: {', '.join(loc.name if hasattr(loc, 'name') else str(loc) for loc in dist.locations)}")
    return "\n".join(lines)


def format_map_screen(game_session: Any) -> str:
    return render_map_view(game_session)


def render_screen(game_session: Any) -> str:
    return render_map_view(game_session)
