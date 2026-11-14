"""Journal, quests, rumors, chronicle, and inventory screen (GDD Section 16)."""

from __future__ import annotations

from typing import Any


def render_journal_view(game_session: Any, view: str = "quests") -> str:
    """Render active quests, rumors, history chronicle, or inventory."""
    if view == "inventory":
        return render_inventory_view(game_session)

    world = game_session.world
    lines = ["=== ADVENTURE JOURNAL & CHRONICLE ===", "Active Quests:"]
    for qid, q in getattr(world, "quests", {}).items():
        lines.append(f"  [{q.status.upper()}] {q.title} - {q.description}")

    lines.append("")
    lines.append("Active City Rumors:")
    for r in getattr(world, "rumors", {}).values():
        lines.append(f"  Subject: {r.subject} | Claim: {r.claim} (Confidence: {r.confidence:.0f}%)")

    return "\n".join(lines)


def render_inventory_view(game_session: Any, **kwargs: Any) -> str:
    """Render character inventory and gear."""
    world = game_session.world
    lines = ["=== INVENTORY & EQUIPMENT ==="]
    for iid, item in getattr(world, "items", {}).items():
        lines.append(f"  {item.name} ({item.item_type}) - Value: {item.value} gold")
    return "\n".join(lines)


def format_journal_screen(game_session: Any) -> str:
    return render_journal_view(game_session)


def format_inventory_screen(game_session: Any) -> str:
    return render_inventory_view(game_session)


def render_screen(game_session: Any) -> str:
    return render_journal_view(game_session)
