"""Journal, quests, rumors, chronicle, and inventory screen (GDD Section 16)."""

from __future__ import annotations

from typing import Any


def render_journal_view(game_session: Any, view: str = "quests") -> str:
    """Render active quests, rumors, history chronicle, or inventory."""
    if view == "inventory":
        return render_inventory_view(game_session)

    world = game_session.world
    lines = ["=== ADVENTURE JOURNAL & CHRONICLE ===", "Active Quests:"]
    quests = getattr(world, "quests", {})
    if not quests:
        lines.append("  No active quests.")
    else:
        for _qid, q in quests.items():
            lines.append(f"  [{q.status.upper()}] {q.title} - {q.description}")

    lines.append("")
    lines.append("Active City Rumors:")
    rumors = getattr(world, "rumors", {})
    if not rumors:
        lines.append("  No active rumors.")
    else:
        for r in rumors.values():
            lines.append(f"  Subject: {r.subject} | Claim: {r.claim} (Confidence: {r.confidence:.0f}%)")

    return "\n".join(lines)


def render_inventory_view(game_session: Any, **kwargs: Any) -> str:
    """Render character inventory and gear."""
    world = game_session.world
    lines = ["=== INVENTORY & EQUIPMENT ==="]
    player_id = getattr(world, "player_id", "player") or "player"
    entries = (
        world.get_inventory(player_id)
        if hasattr(world, "get_inventory")
        else getattr(world, "inventories", {}).get(player_id, [])
    )
    if not entries:
        lines.append("  Inventory is empty.")
        return "\n".join(lines)

    for entry in entries:
        item_id = getattr(entry, "item_id", str(entry))
        item = (
            world.get_item(item_id)
            if hasattr(world, "get_item")
            else getattr(world, "items", {}).get(item_id)
        )
        name = item.name if item else item_id.replace("_", " ").title()
        item_type = item.item_type if item else "misc"
        value = float(item.value) if item else 0.0
        qty = getattr(entry, "quantity", 1)
        equipped_str = " [Equipped]" if getattr(entry, "equipped", False) else ""
        lines.append(
            f"  {name} ({item_type}) x{qty}{equipped_str} - Value: {value:.0f} gold"
        )
    return "\n".join(lines)


def format_journal_screen(game_session: Any) -> str:
    return render_journal_view(game_session)


def format_inventory_screen(game_session: Any) -> str:
    return render_inventory_view(game_session)


def render_screen(game_session: Any) -> str:
    return render_journal_view(game_session)
