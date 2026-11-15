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
    p_loc = (getattr(player, "location_id", None) or "lowtown") if player else "lowtown"
    p_id = getattr(player, "id", "player") if player else "player"

    loc = (
        world.get_location(p_loc)
        if hasattr(world, "get_location")
        else getattr(world, "locations", {}).get(p_loc)
    )
    dist_id = getattr(loc, "district_id", None) if loc else None
    dist = None
    if hasattr(world, "get_district"):
        dist = world.get_district(dist_id) if dist_id else world.get_district(p_loc)
    else:
        districts = getattr(world, "districts", {})
        dist = districts.get(dist_id) if dist_id else districts.get(p_loc)

    loc_label = loc.name if loc else str(p_loc).replace("_", " ").title()
    dist_label = (
        dist.name
        if dist
        else (dist_id.replace("_", " ").title() if dist_id else "Veyr")
    )

    party_ids = getattr(world, "player_party", None) or ["Rowan"]
    party_names: list[str] = []
    for cid in party_ids:
        char = world.get_character(cid) if hasattr(world, "get_character") else None
        party_names.append(char.name if char else str(cid))

    out = [
        "=== THE CITY REMEMBERS | VEYR ===",
        f"Year: {world.clock.year} | Act: {world.clock.act} | Time: {world.clock.format_datetime()}",
        f"Protagonist: {p_name} | Location: {loc_label} ({dist_label})",
        f"Party: {', '.join(party_names)}",
    ]

    if loc and getattr(loc, "description", ""):
        out.append(f"Description: {loc.description}")

    # Nearby NPCs
    npc_names: list[str] = []
    seen_ids: set[str] = {p_id}
    if loc:
        for nid in getattr(loc, "npcs_present", []):
            if nid in seen_ids:
                continue
            seen_ids.add(nid)
            npc = world.get_character(nid) if hasattr(world, "get_character") else None
            npc_names.append(npc.name if npc else str(nid))
    for cid, char in getattr(world, "characters", {}).items():
        if cid in seen_ids:
            continue
        if getattr(char, "location_id", None) == p_loc:
            seen_ids.add(cid)
            npc_names.append(getattr(char, "name", str(cid)))
    if npc_names:
        out.append(f"Nearby NPCs: {', '.join(npc_names)}")

    # Connected exits
    if loc and getattr(loc, "connected_locations", None):
        exit_labels: list[str] = []
        for eid in loc.connected_locations:
            dest = world.get_location(eid) if hasattr(world, "get_location") else None
            exit_labels.append(f"{dest.name} ({eid})" if dest else str(eid))
        out.append(f"Exits: {', '.join(exit_labels)}")

    # Active quest summary
    active_quests = [
        q for q in getattr(world, "quests", {}).values()
        if str(getattr(q, "status", "")).lower() == "active"
    ]
    if active_quests:
        q_summaries: list[str] = []
        for q in active_quests[:3]:
            objs = getattr(q, "objectives", []) or []
            next_obj = next(
                (
                    o
                    for o in objs
                    if not (
                        o.get("completed", False)
                        if isinstance(o, dict)
                        else getattr(o, "completed", False)
                    )
                ),
                None,
            )
            if next_obj is not None:
                desc = (
                    next_obj.get("description", "")
                    if isinstance(next_obj, dict)
                    else getattr(next_obj, "description", "")
                )
                q_summaries.append(f"{q.title} ({desc})" if desc else q.title)
            else:
                q_summaries.append(q.title)
        out.append(f"Active Quests: {'; '.join(q_summaries)}")

    out.append(f"Recent History: {len(getattr(world.event_bus, 'event_history', []))} recorded events.")
    return "\n".join(out)


def format_main_screen(game_session: Any) -> str:
    return render_main_view(game_session)


def render_screen(game_session: Any) -> str:
    return render_main_view(game_session)
