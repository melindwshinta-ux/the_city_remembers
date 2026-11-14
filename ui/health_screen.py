"""Health, hierarchical anatomy, injuries, and treatments screen (GDD Section 16)."""

from __future__ import annotations

from typing import Any


def render_health_view(game_session: Any) -> str:
    """Render 7 anatomical regions, parts, integrity, armor, and injuries."""
    world = game_session.world
    player = getattr(world, "player", None)
    lines = [
        f"=== ANATOMY & PHYSICAL HEALTH: {player.name if player else 'Rowan'} ===",
        f"Consciousness: {getattr(player, 'consciousness', 100.0):.0f}% | Overall Status: {getattr(player, 'status', 'alive').upper()}",
        "",
        "Regions:",
        "  Head: Skull, Brain, Eyes, Jaw, Ears",
        "  Neck: Throat, Cervical Spine",
        "  Torso: Ribs, Spine, Heart, Lungs, Stomach, Liver",
        "  Left Arm: Upper Arm, Elbow, Forearm, Hand",
        "  Right Arm: Upper Arm, Elbow, Forearm, Hand",
        "  Left Leg: Thigh, Knee, Calf, Foot",
        "  Right Leg: Thigh, Knee, Calf, Foot",
    ]

    body = getattr(player, "body", None) if player else None
    if isinstance(body, dict) and body:
        lines.append("")
        lines.append("Body Parts & Injuries:")
        for part_id, part in body.items():
            part_name = getattr(part, "name", part_id)
            integrity = float(getattr(part, "integrity", 100.0))
            is_functional = bool(getattr(part, "functional", True))
            func_label = "functional" if is_functional else "non-functional"
            prosthetic_id = getattr(part, "prosthetic_id", None)
            prosthetic_str = f" | Prosthetic: {prosthetic_id}" if prosthetic_id else ""
            injuries = getattr(part, "injuries", []) or []
            if not is_functional or injuries or integrity < 100.0 or prosthetic_id:
                lines.append(
                    f"  {part_name} ({part_id}): {integrity:.0f}% | {func_label}{prosthetic_str}"
                )
                for inj in injuries:
                    inj_type = getattr(inj, "injury_type", "injury")
                    severity = float(getattr(inj, "severity", 0.0))
                    stage = getattr(inj, "treatment_stage", "untreated")
                    perm_str = " [permanent]" if getattr(inj, "permanent", False) else ""
                    lines.append(
                        f"    - {inj_type} (severity: {severity:.2f}, stage: {stage}){perm_str}"
                    )

    lines.extend([
        "",
        "Available Treatments: First Aid, Field Treatment, Surgery, Rehabilitation, Prosthetics",
    ])
    return "\n".join(lines)


def format_health_screen(game_session: Any) -> str:
    return render_health_view(game_session)


def render_screen(game_session: Any) -> str:
    return render_health_view(game_session)
