"""Tactical combat grid and command display (GDD Section 16)."""

from __future__ import annotations

from typing import Any


def _format_combatant_block(char: Any, combat_sys: Any, world: Any, is_enemy: bool = False) -> list[str]:
    """Build compact status lines for a party member or enemy."""
    name = getattr(char, "name", str(getattr(char, "id", "Unknown")))
    consc = float(getattr(char, "consciousness", 100.0))
    status = getattr(char, "status", "alive")

    if is_enemy and combat_sys is not None and hasattr(combat_sys, "evaluate_morale_state"):
        morale_state = combat_sys.evaluate_morale_state(char)
        morale_val = float(getattr(char, "morale", 75.0))
        morale_str = f"Morale {morale_val:.0f} ({morale_state})"
    else:
        morale_val = float(getattr(char, "morale", 85.0))
        morale_str = f"Morale {morale_val:.0f}"

    equip = getattr(char, "equipment", None) or {}
    items = getattr(world, "items", {}) if world is not None else {}
    w_id = equip.get("weapon") or equip.get("main_hand") or equip.get("primary")
    a_id = equip.get("armor") or equip.get("torso") or equip.get("chest")
    w_name = getattr(items.get(w_id), "name", w_id) if w_id else "Unarmed"
    a_name = getattr(items.get(a_id), "name", a_id) if a_id else "No Armor"

    wounds: list[str] = []
    body = getattr(char, "body", None) or {}
    for part_id, part in body.items():
        part_inj = list(getattr(part, "injuries", []) or [])
        bleeding = float(getattr(part, "bleeding_rate", 0.0))
        functional = bool(getattr(part, "functional", True))
        label = str(part_id).replace("_", " ").title()
        if part_inj:
            wounds.append(f"{label}: {', '.join(str(i) for i in part_inj)}")
        elif bleeding > 0.0:
            wounds.append(f"{label}: Bleeding")
        elif not functional:
            wounds.append(f"{label}: Disabled")
    wound_str = "; ".join(wounds[:3]) if wounds else "None"

    return [
        f"{name} [{status}]",
        f"  Consc: {consc:.0f}% | {morale_str}",
        f"  Gear: {w_name} / {a_name}",
        f"  Wounds: {wound_str}",
    ]


def render_combat_view(game_session: Any) -> str:
    """Render tactical battlefield grid (preview) or Warsim/Battle Brothers Clash Viewport."""
    combat_sys = getattr(game_session, "combat_system", None)
    enc = getattr(combat_sys, "active_encounter", None)
    if enc is None:
        status_line = "Status: No active combat encounter (Tactical Preview)"
        player = getattr(getattr(game_session, "world", None), "player", None)
        if player is not None:
            from entities.character import Character
            from systems.combat_system import Encounter

            preview = Encounter(
                party=[player],
                enemies=[Character(id="npc_voss", name="Captain Voss", age=38)],
            )
            grid_str = preview.render_ascii_grid()
        else:
            grid_str = "\n".join(" ".join("[ . ]" for _ in range(5)) for _ in range(5))
        lines = [
            "=== TACTICAL BATTLEFIELD ===",
            status_line,
            grid_str,
            "",
            "Available Command Categories:",
            "  Movement: Move, Charge, Retreat, Flank, Take Cover",
            "  Combat: Attack, Heavy Attack, Aim, Guard, Disarm, Grapple, Interrupt",
            "  Support: Heal, Stabilize, Apply Bandage, Revive, Protect Ally",
            "  Special: Spellcasting, Stealth Attack, Area Attack, Environmental Interaction",
        ]
        return "\n".join(lines)

    world = getattr(game_session, "world", None)
    menu_engine = getattr(game_session, "menu_engine", None)
    clash_session = getattr(menu_engine, "active_clash", None) if menu_engine is not None else None

    party_list = list(getattr(clash_session, "party", None) or getattr(enc, "party", []) or [])
    enemy_list = list(getattr(clash_session, "enemies", None) or getattr(enc, "enemies", []) or [])

    left_lines = ["[ PARTY ]"]
    for member in party_list:
        left_lines.extend(_format_combatant_block(member, combat_sys, world, is_enemy=False))
    right_lines = ["[ ENEMIES ]"]
    for enemy in enemy_list:
        right_lines.extend(_format_combatant_block(enemy, combat_sys, world, is_enemy=True))

    max_rows = max(len(left_lines), len(right_lines))
    side_by_side: list[str] = []
    for idx in range(max_rows):
        l_txt = left_lines[idx] if idx < len(left_lines) else ""
        r_txt = right_lines[idx] if idx < len(right_lines) else ""
        side_by_side.append(f"{l_txt:<38} | {r_txt}")

    round_num = getattr(clash_session, "round_number", 1) if clash_session is not None else 1
    clash_status = getattr(clash_session, "status", "active") if clash_session is not None else "active"

    lines = [
        f"=== COMBAT CLASH (Round {round_num} | {clash_status}) ===",
        *side_by_side,
    ]
    if clash_session is not None and getattr(clash_session, "combat_log", None):
        lines.append("")
        lines.append("Combat Log (Last 5):")
        for entry in list(clash_session.combat_log)[-5:]:
            lines.append(f"  - {entry}")
    else:
        lines.append("")
        lines.append(enc.render_ascii_grid())

    return "\n".join(lines)


def format_combat_screen(game_session: Any) -> str:
    return render_combat_view(game_session)


def render_screen(game_session: Any) -> str:
    return render_combat_view(game_session)
