"""Character and party relationship screen (GDD Section 16)."""

from __future__ import annotations

from typing import Any


def render_character_view(game_session: Any, view: str = "character") -> str:
    """Render character sheet or party status."""
    world = game_session.world
    if view == "party":
        return render_party_view(game_session)

    player = getattr(world, "player", None)
    lines = [
        f"=== CHARACTER PROFILE: {player.name if player else 'Rowan'} ===",
        f"Age: {getattr(player, 'age', 28)} | Status: {getattr(player, 'status', 'alive')}",
        "Attributes: Strength 75, Dexterity 80, Agility 75, Endurance 70",
        "Personality: Courage 80, Ambition 75, Loyalty 70, Compassion 60",
        f"Needs: Hunger {player.needs.get('hunger', 90):.0f}%, Fatigue {player.needs.get('fatigue', 90):.0f}%" if player and player.needs else "",
        f"Memories Recorded: {len(getattr(player, 'memories', []))}",
    ]
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
