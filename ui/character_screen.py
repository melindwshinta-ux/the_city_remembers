"""Character and party relationship screen (GDD Section 16)."""

from __future__ import annotations

from typing import Any


def render_character_view(game_session: Any, view: str = "character") -> str:
    """Render character sheet or party status."""
    world = game_session.world
    if view == "party":
        return render_party_view(game_session)

    player = getattr(world, "player", None)
    attrs = getattr(player, "attributes", {}) or {} if player else {}
    attr_str = (
        ", ".join(f"{k.replace('_', ' ').title()} {float(v):.0f}" for k, v in attrs.items())
        if attrs
        else "None recorded"
    )
    pers = getattr(player, "personality", {}) or {} if player else {}
    pers_str = (
        ", ".join(f"{k.replace('_', ' ').title()} {float(v):.0f}" for k, v in pers.items())
        if pers
        else "Neutral"
    )
    skills = getattr(player, "skills", {}) or {} if player else {}
    needs = getattr(player, "needs", {}) or {} if player else {}

    lines = [
        f"=== CHARACTER PROFILE: {player.name if player else 'Rowan'} ===",
        f"Age: {getattr(player, 'age', 28)} | Status: {getattr(player, 'status', 'alive')}",
        f"Attributes: {attr_str}",
        f"Personality: {pers_str}",
    ]
    if skills:
        skill_str = ", ".join(f"{k.replace('_', ' ').title()} {float(v):.0f}" for k, v in skills.items())
        lines.append(f"Skills: {skill_str}")
    if needs:
        lines.append(
            f"Needs: Hunger {float(needs.get('hunger', 90)):.0f}%, Fatigue {float(needs.get('fatigue', 90)):.0f}%, Wealth {float(needs.get('wealth', 0)):.0f}g"
        )
    lines.append(f"Memories Recorded: {len(getattr(player, 'memories', []))}")
    return "\n".join(lines)


def render_party_view(game_session: Any, **kwargs: Any) -> str:
    """Render party members, independent activities, and 6-axis relationships."""
    world = game_session.world
    lines = ["=== PARTY MEMBERS & COMPANION BONDS ==="]
    for cid, comp in getattr(world, "companions", {}).items():
        rel = game_session.relationship_system.get_relationship(cid, "player")
        lines.append(
            f"Companion: {comp.name} ({comp.role}) | Status: {comp.independent_activity}\n"
            f"  Friendship: {comp.friendship:.0f} | Rivalry: {comp.rivalry:.0f}\n"
            f"  Bonds: Trust {rel.trust:.0f} | Respect {rel.respect:.0f} | Affection {rel.affection:.0f} | State: {rel.relationship_state}"
        )
    return "\n".join(lines)


def format_character_screen(game_session: Any) -> str:
    return render_character_view(game_session)


def format_party_screen(game_session: Any) -> str:
    return render_party_view(game_session)


def render_screen(game_session: Any) -> str:
    return render_character_view(game_session)
