"""Main overview screen (GDD Sections 12 & 16)."""

from __future__ import annotations

from typing import Any
from rich.panel import Panel
from rich.table import Table


def render_main_view(game_session: Any) -> str:
    """Render the primary world overview, player status, and recent events."""
    world = game_session.world
    player = getattr(world, "player", None)
    p_name = player.name if player else "Rowan"
    p_loc = player.location_id if player else "lowtown"

    out = [
        f"=== THE CITY REMEMBERS | VEYR ===",
        f"Year: {world.clock.year} | Act: {world.clock.act} | Time: {world.clock.format_datetime()}",
        f"Protagonist: {p_name} | Location: {p_loc.replace('_', ' ').title()} (Lowtown)",
        f"Party: {', '.join(getattr(world, 'player_party', ['Rowan']))}",
        f"Recent History: {len(getattr(world.event_bus, 'event_history', []))} recorded events.",
    ]
    return "\n".join(out)


def format_main_screen(game_session: Any) -> str:
    return render_main_view(game_session)


def render_screen(game_session: Any) -> str:
    return render_main_view(game_session)
