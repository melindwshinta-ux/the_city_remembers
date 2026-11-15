"""Prologue narrative beats, opening stance choices, Mission 1-2 tutorial steps, and inspect clues."""

from __future__ import annotations

from typing import Any

from entities.character import Memory


PROLOGUE_BEATS: list[dict[str, Any]] = [
    {
        "id": "arrival_in_veyr",
        "order": 0,
        "title": "Arrival in Veyr",
        "narrative": (
            "Rain slicks the cobblestones of Lowtown as you step off the river road into Veyr — "
            "a city held together by seven uneasy factions, old debts, and memories that outlive blood. "
            "Ahead, the lanterns of Lowtown Main Thoroughfare flicker beside The Drunken Gull Tavern, "
            "where Marcus and Sera wait with word of fresh trouble."
        ),
        "requires_choice": False,
        "choices": [],
    },
    {
        "id": "blood_in_lowtown_market",
        "order": 1,
        "title": "The Blood in Lowtown Market",
        "narrative": (
            "Before dawn, a Consortium merchant was found slain beside his overturned cart in Cobblestone Market. "
            "Captain Garrick Voss of the City Guard has already cordoned the square and blamed the Lowtown Syndicate, "
            "while Boss Malakor's enforcers watch from the alleyways. Meanwhile, union master Gregor seeks word of his "
            "missing apprentice, Joren. Every move you make will ripple through the city's factions."
        ),
        "requires_choice": False,
        "choices": [],
    },
    {
        "id": "choose_opening_stance",
        "order": 2,
        "title": "Choose Your Opening Stance",
        "narrative": (
            "Before stepping into Lowtown's crossfire, decide how you walked into Veyr. "
            "Your background shapes your starting reputation, coin, companion rapport, and skills."
        ),
        "requires_choice": True,
        "choices": ["watch_investigator", "street_broker", "unbound_drifter"],
    },
]


PROLOGUE_CHOICES: dict[str, dict[str, Any]] = {
    "watch_investigator": {
        "id": "watch_investigator",
        "label": "Watch-Trained Investigator",
        "summary": "Trained in precinct discipline and evidence gathering. Respected by the Guard, distrusted by the Syndicate.",
        "effects_summary": "+15 City Guard rep, -10 Syndicate rep, +5 Public rep, +25 gold, +10 Marcus friendship, +5 Dexterity",
        "faction_rep": {"city_guard": 15.0, "lowtown_syndicate": -10.0},
        "general_public": 5.0,
        "criminal_underworld": 0.0,
        "wealth_delta": 25.0,
        "companion_friendship": {"comp_marcus": 10.0},
        "companion_rivalry": {"comp_sera": 5.0},
        "attribute_bonus": {"dexterity": 5.0},
        "skill_bonus": {},
        "memory": {
            "id": "mem_prologue_watch",
            "event_type": "PROLOGUE_STANCE",
            "description": "Entered Veyr bearing the discipline of a Watch-trained investigator.",
            "emotion": "Resolve",
            "emotional_valence": 0.3,
        },
    },
    "street_broker": {
        "id": "street_broker",
        "label": "Street-Smart Broker",
        "summary": "Raised in back-alley bargains and dead drops. Welcomed by the Syndicate, watched closely by the Guard.",
        "effects_summary": "+15 Syndicate rep, -10 City Guard rep, +15 Underworld rep, +75 gold, +10 Sera friendship, +10 Stealth",
        "faction_rep": {"lowtown_syndicate": 15.0, "city_guard": -10.0},
        "general_public": 0.0,
        "criminal_underworld": 15.0,
        "wealth_delta": 75.0,
        "companion_friendship": {"comp_sera": 10.0},
        "companion_rivalry": {"comp_marcus": 5.0},
        "attribute_bonus": {},
        "skill_bonus": {"stealth": 10.0},
        "memory": {
            "id": "mem_prologue_broker",
            "event_type": "PROLOGUE_STANCE",
            "description": "Entered Veyr with Syndicate contacts and a heavy purse.",
            "emotion": "Cunning",
            "emotional_valence": 0.2,
        },
    },
    "unbound_drifter": {
        "id": "unbound_drifter",
        "label": "Unbound Drifter",
        "summary": "Owed nothing to badge or syndicate. Trusted by ordinary folk and skilled at keeping allies alive.",
        "effects_summary": "+10 Public rep, +40 gold, +10 Elira friendship, +5 Tomas friendship, +10 Medicine",
        "faction_rep": {},
        "general_public": 10.0,
        "criminal_underworld": 0.0,
        "wealth_delta": 40.0,
        "companion_friendship": {"comp_elira": 10.0, "comp_tomas": 5.0},
        "companion_rivalry": {},
        "attribute_bonus": {},
        "skill_bonus": {"medicine": 10.0},
        "memory": {
            "id": "mem_prologue_drifter",
            "event_type": "PROLOGUE_STANCE",
            "description": "Arrived in Veyr unbound to any banner, relying on grit and field medicine.",
            "emotion": "Independence",
            "emotional_valence": 0.25,
        },
    },
}


def apply_prologue_choice(world: Any, choice_id: str) -> dict[str, Any]:
    """Apply deterministic starting effects for the chosen prologue stance (idempotent)."""
    if choice_id not in PROLOGUE_CHOICES:
        return {
            "success": False,
            "message": f"Unknown prologue choice '{choice_id}'. Valid choices: {', '.join(PROLOGUE_CHOICES)}.",
        }

    existing = world.flags.get("prologue_choice")
    if existing is not None:
        return {
            "success": True,
            "already_applied": True,
            "choice_id": existing,
            "message": f"Prologue stance '{existing}' already applied.",
        }

    spec = PROLOGUE_CHOICES[choice_id]

    # 1. Reputation deltas
    rep = getattr(world, "reputation", None)
    if isinstance(rep, dict):
        fac_rep = rep.setdefault("faction", {})
        for fid, delta in spec.get("faction_rep", {}).items():
            fac_rep[fid] = float(fac_rep.get(fid, 0.0)) + float(delta)
        if spec.get("general_public"):
            rep["general_public"] = float(rep.get("general_public", 0.0)) + float(spec["general_public"])
        if spec.get("criminal_underworld"):
            rep["criminal_underworld"] = float(rep.get("criminal_underworld", 0.0)) + float(spec["criminal_underworld"])

    # 2. Player wealth, attributes, skills, memory
    player = getattr(world, "player", None)
    if player is not None:
        player.needs["wealth"] = float(player.needs.get("wealth", 0.0)) + float(spec.get("wealth_delta", 0.0))
        for attr, delta in spec.get("attribute_bonus", {}).items():
            player.attributes[attr] = float(player.attributes.get(attr, 50.0)) + float(delta)
        for skill, delta in spec.get("skill_bonus", {}).items():
            player.skills[skill] = float(player.skills.get(skill, 0.0)) + float(delta)

        mem_spec = spec.get("memory")
        if mem_spec and not any(getattr(m, "id", None) == mem_spec["id"] for m in player.memories):
            player.memories.append(
                Memory(
                    id=mem_spec["id"],
                    event_type=mem_spec["event_type"],
                    participants=["player"],
                    description=mem_spec["description"],
                    location_id=player.location_id or "lowtown_street",
                    importance=0.7,
                    emotional_valence=float(mem_spec.get("emotional_valence", 0.0)),
                    confidence=1.0,
                    created_at=int(getattr(world.clock, "total_minutes", 0)),
                    emotion=mem_spec.get("emotion", "neutral"),
                    character_id=player.id,
                    source_type="witnessed",
                )
            )

    # 3. Companion rapport
    companions = getattr(world, "companions", {})
    for cid, delta in spec.get("companion_friendship", {}).items():
        if cid in companions:
            companions[cid].friendship = float(companions[cid].friendship) + float(delta)
    for cid, delta in spec.get("companion_rivalry", {}).items():
        if cid in companions:
            companions[cid].rivalry = float(companions[cid].rivalry) + float(delta)

    # 4. Flags & clock transition
    world.flags["prologue_choice"] = choice_id
    if hasattr(world, "clock") and hasattr(world.clock, "complete_prologue"):
        world.clock.complete_prologue()

    return {
        "success": True,
        "already_applied": False,
        "choice_id": choice_id,
        "label": spec["label"],
        "message": f"Chose '{spec['label']}': {spec['effects_summary']}.",
    }


TUTORIAL_STEPS: list[dict[str, Any]] = [
    {
        "id": "m1_move_market",
        "mission_id": "quest_blood_in_lowtown",
        "order": 1,
        "title": "Reach Cobblestone Market",
        "instruction": "Travel to Cobblestone Market to examine the merchant murder scene.",
        "hint": "Type 'move lowtown_market' (or 'go lowtown_market').",
        "suggested_commands": ["move lowtown_market"],
        "completion_rule": {"actions": ["move"], "targets": ["lowtown_market"]},
    },
    {
        "id": "m1_inspect_scene",
        "mission_id": "quest_blood_in_lowtown",
        "order": 2,
        "title": "Inspect the Crime Scene",
        "instruction": "Examine Cobblestone Market or Captain Voss for forensic clues.",
        "hint": "Type 'inspect lowtown_market' or 'inspect voss'.",
        "suggested_commands": ["inspect lowtown_market", "inspect voss"],
        "completion_rule": {"actions": ["inspect"], "targets": ["lowtown_market", "npc_voss"]},
    },
    {
        "id": "m1_talk_companions",
        "mission_id": "quest_blood_in_lowtown",
        "order": 3,
        "title": "Consult Your Companions",
        "instruction": "Speak with Sera or Marcus to weigh the Syndicate and Guard perspectives.",
        "hint": "Type 'talk sera' or 'talk marcus'.",
        "suggested_commands": ["talk sera", "talk marcus"],
        "completion_rule": {"actions": ["talk"], "targets": ["comp_sera", "comp_marcus", "npc_voss"]},
    },
    {
        "id": "m1_check_journal_factions",
        "mission_id": "quest_blood_in_lowtown",
        "order": 4,
        "title": "Review Journal & Factions",
        "instruction": "Open your Journal or Factions view to track active leads and political standing.",
        "hint": "Type 'open journal' or 'open factions'.",
        "suggested_commands": ["open journal", "open factions"],
        "completion_rule": {"actions": ["open_journal", "open_factions", "open_faction"], "targets": []},
    },
    {
        "id": "m1_choose_approach",
        "mission_id": "quest_blood_in_lowtown",
        "order": 5,
        "title": "Resolve Blood in Lowtown",
        "instruction": "Decide how to resolve the murder: support the Guard, Syndicate, investigate independently, or exploit both.",
        "hint": "Type 'choose support_city_guard', 'choose support_syndicate', 'choose investigate_independently', or 'choose exploit_situation'.",
        "suggested_commands": [
            "choose support_city_guard",
            "choose support_syndicate",
            "choose investigate_independently",
            "choose exploit_situation",
        ],
        "completion_rule": {"actions": ["choose_approach"], "targets": []},
    },
    {
        "id": "m2_investigate_apprentice",
        "mission_id": "quest_missing_apprentice",
        "order": 6,
        "title": "Track the Missing Apprentice",
        "instruction": "Follow up on Joren's disappearance by inspecting Shadow Alleyways or the Fish Warehouse, or talking to Gregor.",
        "hint": "Type 'inspect lowtown_alleys', 'inspect lowtown_warehouse', or 'talk gregor'.",
        "suggested_commands": ["inspect lowtown_alleys", "inspect lowtown_warehouse", "talk gregor"],
        "completion_rule": {
            "actions": ["inspect", "talk", "move"],
            "targets": ["lowtown_alleys", "lowtown_warehouse", "npc_gregor"],
        },
    },
    {
        "id": "m2_check_health",
        "mission_id": "quest_missing_apprentice",
        "order": 7,
        "title": "Check Party Health",
        "instruction": "Monitor your 29-part anatomical health status before venturing deeper into Veyr.",
        "hint": "Type 'check health' or 'open health'.",
        "suggested_commands": ["check health", "open health"],
        "completion_rule": {"actions": ["check_health", "open_health"], "targets": []},
    },
    {
        "id": "m2_rest_or_wait",
        "mission_id": "quest_missing_apprentice",
        "order": 8,
        "title": "Rest & Advance Simulation",
        "instruction": "Rest or wait to recover fatigue and let the city's factions react.",
        "hint": "Type 'rest 4h' or 'wait 1d'.",
        "suggested_commands": ["rest 4h", "wait 1d"],
        "completion_rule": {"actions": ["rest", "wait"], "targets": []},
    },
    {
        "id": "m2_save_game",
        "mission_id": "quest_missing_apprentice",
        "order": 9,
        "title": "Save Your Progress",
        "instruction": "Persist your world state, relationships, and memories to SQLite.",
        "hint": "Type 'save' (or 'save my_run').",
        "suggested_commands": ["save"],
        "completion_rule": {"actions": ["save"], "targets": [], "require_current": True},
    },
]


LOCATION_CLUES: dict[str, str] = {
    "lowtown_market": (
        "Clue: Muddy bootprints lead from the overturned merchant cart toward Shadow Alleyways, "
        "and a torn City Guard wax seal lies half-buried beside a spilled spice crate."
    ),
    "lowtown_street": (
        "Clue: Patrol lanterns burn low; street rumors whisper that both Guard patrols and Syndicate runners "
        "crossed the thoroughfare before dawn."
    ),
    "lowtown_tavern": (
        "Clue: At the corner booth, Marcus keeps his hand near his hilt while Sera watches the back exit "
        "and trades coded glances with dockside regulars."
    ),
    "lowtown_watchpost": (
        "Clue: Duty rosters on the notice board show two Guard patrols pulled off the market beat an hour before the murder."
    ),
    "lowtown_docks": (
        "Clue: Unmarked cargo crates stamped with a Consortium cipher sit waiting for a midnight barge."
    ),
    "lowtown_alleys": (
        "Clue: Near the storm drain you spot a frayed leather satchel strap marked with the Iron Workers' Union crest — "
        "likely dropped by Gregor's missing apprentice, Joren."
    ),
    "lowtown_warehouse": (
        "Clue: Heavy boots and fresh sawdust mark the path to Boss Malakor's locked office; muffled voices echo behind the door."
    ),
    "lowtown_safehouse": (
        "Clue: The bolted cellar grate offers a quiet place to rest and tend wounds away from faction patrols."
    ),
    "lowtown_tenements": (
        "Clue: Residents whisper that an Iron Ward apprentice hurried past the stairwells toward the alleys last night."
    ),
}


NPC_CLUES: dict[str, str] = {
    "npc_voss": "Captain Voss's cloak hem is spattered with market mud, and his knuckles are freshly bruised.",
    "npc_merek": "Sergeant Merek nervously checks his ledger, avoiding eye contact whenever the night watch roster is mentioned.",
    "comp_sera": "Sera's eyes dart to every rooftop and alley mouth; she clearly knows more about Syndicate movements than she admits.",
    "comp_marcus": "Marcus's old Watch insignia is scratched out, yet he still stands at parade rest when Guard patrols pass.",
    "comp_elira": "Faint arcane residue clings to Elira's cuffs, hinting at recent ward-breaking.",
    "comp_tomas": "Tomas carries a well-worn satchel of clean linen bandages and temple tinctures.",
    "npc_trader_brant": "Brant's stall sits just twenty paces from the murder; his hands tremble as he packs his scales.",
    "npc_boss_malakor": "Malakor wears a silver signet ring and keeps two armed enforcers within arm's reach.",
    "npc_gang_karn": "Karn's knuckle-wraps are stained dark; he watches the alley entrances like a hound.",
    "npc_thief_ren": "Ren palms a brass lockpick and keeps an escape route toward the rooftops.",
    "npc_gregor": "Master smith Gregor's apron is soot-stained; he clutches a half-forged apprentice's hammer as he asks after Joren.",
}


def get_inspect_clue(target_id: str, world: Any = None) -> str:
    """Return rich contextual inspection text for a location, character, district, faction, or item."""
    if target_id in LOCATION_CLUES:
        loc = world.locations.get(target_id) if world is not None else None
        base = f"{loc.name}: {loc.description}" if loc else target_id
        return f"{base} {LOCATION_CLUES[target_id]}"

    if target_id in NPC_CLUES:
        char = world.characters.get(target_id) if world is not None else None
        prefix = f"{char.name}: " if char else ""
        return f"{prefix}{NPC_CLUES[target_id]}"

    if world is not None:
        if target_id in world.districts:
            d = world.districts[target_id]
            return f"{d.name} — {d.characteristics}. Major conflict: {d.major_conflict} (Security: {d.security:.0f}, Unrest: {d.unrest:.0f})."
        if target_id in world.factions:
            f = world.factions[target_id]
            return f"{f.name} — Wealth: {f.wealth:.0f}, Influence: {f.influence:.0f}, Military: {f.military_strength:.0f}, Stability: {f.stability:.0f}."
        if target_id in world.items:
            it = world.items[target_id]
            return f"{it.name} ({it.item_type}) — Value: {it.value:.0f}."
        if target_id in world.characters:
            c = world.characters[target_id]
            return f"{c.name} — Currently at {c.location_id or 'unknown'}."

    return f"You closely inspect {target_id}."
