"""Interactive Branching Dialogue Engine for Warsim-style NPC conversations (GEMINI_PLAN §3)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.settings import DIFFICULTY_MODIFIERS
from entities.character import Memory

if TYPE_CHECKING:
    from core.game import Game


COMPANION_ACTIONS: dict[str, dict[str, str]] = {
    "comp_sera": {
        "name": "Sera",
        "label": "[Sera] Use underworld cant & street leverage",
        "tag": "Companion: Sera",
    },
    "comp_marcus": {
        "name": "Marcus",
        "label": "[Marcus] Pull Watch rank & authority",
        "tag": "Companion: Marcus",
    },
    "comp_elira": {
        "name": "Elira",
        "label": "[Elira] Sense arcane residue & hidden motives",
        "tag": "Companion: Elira",
    },
    "comp_tomas": {
        "name": "Tomas",
        "label": "[Tomas] Offer Ashen Church counsel & aid",
        "tag": "Companion: Tomas",
    },
}


def _format_bar(value: float, width: int = 10) -> str:
    clamped = max(-100.0, min(100.0, float(value)))
    filled = int(round((abs(clamped) / 100.0) * width))
    fill_char = "#" if clamped >= 0 else "-"
    return f"[{fill_char * filled}{'.' * (width - filled)}] {clamped:+.0f}"


class DialogueEngine:
    """Manages an interactive branching conversation with a single NPC or companion."""

    def __init__(self, game: Game, npc_id: str) -> None:
        self.game = game
        self.npc_id = str(npc_id)
        self.closed: bool = False
        self.enter_combat: bool = False
        self.clash_session: Any = None
        self.last_message: str = ""
        self._event_seq: int = 0

    def _get_npc(self) -> Any:
        return self.game.world.characters.get(self.npc_id)

    def _get_district_id(self) -> str:
        world = self.game.world
        player = world.player
        loc_id = getattr(player, "location_id", "") if player else ""
        loc = world.locations.get(loc_id)
        if loc is not None and getattr(loc, "district_id", None):
            return str(loc.district_id)
        return "lowtown"

    def _get_difficulty_mods(self) -> dict[str, Any]:
        world = self.game.world
        diff = str(
            world.flags.get("difficulty")
            or getattr(getattr(self.game, "settings", None), "difficulty", "balanced")
        ).lower()
        return DIFFICULTY_MODIFIERS.get(diff, DIFFICULTY_MODIFIERS["balanced"])

    def _get_persuade_chance(self) -> int:
        world = self.game.world
        if world.flags.get("god_mode"):
            return 100
        player = world.player
        skills = getattr(player, "skills", {}) if player else {}
        attrs = getattr(player, "attributes", {}) if player else {}
        base = float(skills.get("persuasion", 35.0))
        empathy_bonus = float(skills.get("empathy", attrs.get("charisma", 50.0))) * 0.15
        rel = self.game.relationship_system.get_relationship(self.npc_id, "player")
        rel_mod = (float(rel.trust) * 0.2) + (float(rel.affection) * 0.15) - (float(rel.resentment) * 0.25)
        diff_bonus = float(self._get_difficulty_mods().get("skill_bonus", 0.0))
        chance = int(round(base + empathy_bonus + rel_mod + diff_bonus))
        return max(5, min(95, chance))

    def _get_intimidate_chance(self) -> int:
        world = self.game.world
        if world.flags.get("god_mode"):
            return 100
        player = world.player
        skills = getattr(player, "skills", {}) if player else {}
        attrs = getattr(player, "attributes", {}) if player else {}
        base = float(skills.get("intimidation", 30.0))
        str_bonus = float(attrs.get("strength", 50.0)) * 0.2
        crim_rep = float(world.reputation.get("criminal_underworld", 0.0)) * 0.15
        rel = self.game.relationship_system.get_relationship(self.npc_id, "player")
        fear_bonus = float(rel.fear) * 0.2
        diff_bonus = float(self._get_difficulty_mods().get("skill_bonus", 0.0))
        chance = int(round(base + str_bonus + crim_rep + fear_bonus + diff_bonus))
        return max(5, min(95, chance))

    def _get_active_companion_action(self) -> tuple[str | None, dict[str, str] | None]:
        world = self.game.world
        party = list(getattr(world, "player_party", []) or [])
        for cid in ("comp_sera", "comp_marcus", "comp_elira", "comp_tomas"):
            if cid in party and cid != self.npc_id and cid in COMPANION_ACTIONS:
                return cid, COMPANION_ACTIONS[cid]
        for cid in ("comp_sera", "comp_marcus", "comp_elira", "comp_tomas"):
            if cid in party and cid in COMPANION_ACTIONS:
                return cid, COMPANION_ACTIONS[cid]
        return None, None

    def _visible_injuries(self, npc: Any) -> list[str]:
        if npc is None or not hasattr(npc, "body") or not npc.body:
            return []
        wounds: list[str] = []
        for part in npc.body.values():
            if getattr(part, "prosthetic_id", None):
                wounds.append(f"{part.name}: Prosthetic ({part.prosthetic_id})")
            for inj in getattr(part, "injuries", []):
                wounds.append(f"{part.name}: {inj.injury_type.replace('_', ' ')}")
            if not getattr(part, "functional", True) and not getattr(part, "injuries", []):
                wounds.append(f"{part.name}: Impaired")
        return wounds

    def _build_dynamic_greeting(self, npc: Any, rel: Any) -> str:
        world = self.game.world
        base = self.game.get_dialogue(self.npc_id)
        extras: list[str] = []

        epithet = world.flags.get("epithet")
        if epithet:
            extras.append(f"(They eye you knowingly, mindful of your reputation as '{epithet}'.)")

        injuries = self._visible_injuries(npc)
        if injuries and self.npc_id != "npc_voss":
            extras.append(f"(Visible wound: {injuries[0]}.)")

        # React to recent memories involving player
        if npc is not None and getattr(npc, "memories", None):
            recent = npc.memories[-1]
            desc = getattr(recent, "description", "")
            if desc:
                extras.append(f"[Memory: {desc}]")

        # React to active rumors about this NPC
        for rumor in getattr(world, "rumors", {}).values():
            if getattr(rumor, "subject", None) == self.npc_id:
                extras.append(f"[Rumor: \"{rumor.claim}\"]")
                break

        if not extras:
            return base
        return f"{base}\n" + " ".join(extras)

    def get_view(self) -> dict[str, Any]:
        """Return structured dialogue header, 6-axis bars, greeting, and [1]-[8], [0] options."""
        world = self.game.world
        npc = self._get_npc()
        name = getattr(npc, "name", self.npc_id) if npc else self.npc_id
        rank = str(getattr(npc, "rank", "") or ("Companion" if npc and getattr(npc, "is_companion", False) else "Citizen")).title()
        fac_id = getattr(npc, "faction_id", None) if npc else None
        faction_name = world.factions[fac_id].name if fac_id and fac_id in world.factions else "Independent"
        injuries = self._visible_injuries(npc)

        rel = self.game.relationship_system.get_relationship(self.npc_id, "player")
        axes = {
            "trust": float(rel.trust),
            "respect": float(rel.respect),
            "affection": float(rel.affection),
            "resentment": float(rel.resentment),
            "fear": float(rel.fear),
            "dependency": float(rel.dependency),
        }
        bars = {k: _format_bar(v) for k, v in axes.items()}

        player_gold = float(getattr(world.player, "needs", {}).get("wealth", 0.0)) if world.player else 0.0
        persuade_pct = self._get_persuade_chance()
        intimidate_pct = self._get_intimidate_chance()
        comp_id, comp_meta = self._get_active_companion_action()

        in_party = self.npc_id in (world.player_party or [])
        is_companion = self.npc_id in world.companions
        favor_tag = "Dismiss" if (is_companion and in_party) else ("Recruit" if is_companion else "Trade/Favor")

        options: list[dict[str, Any]] = [
            {
                "key": "1",
                "label": "Ask about local rumors & city news",
                "tags": ["15m", "+Intel"],
                "enabled": True,
            },
            {
                "key": "2",
                "label": "Discuss Mission / Quest Business",
                "tags": ["Quest"],
                "enabled": True,
            },
            {
                "key": "3",
                "label": f"[Persuade {persuade_pct}%] Build Rapport / Reason with them",
                "tags": [f"Persuade {persuade_pct}%", "+Trust/+Affection"],
                "enabled": True,
            },
            {
                "key": "4",
                "label": f"[Intimidate {intimidate_pct}%] Threaten / Demand Compliance",
                "tags": [f"Intimidate {intimidate_pct}%", "+Fear, Risk: Resentment"],
                "enabled": True,
            },
            {
                "key": "5",
                "label": "[Cost: 25g] Offer Gift or Bribe",
                "tags": ["Cost: 25g", "+Trust/+Affection"] if player_gold >= 25.0 else ["Locked: Requires 25 Gold"],
                "enabled": player_gold >= 25.0,
            },
            {
                "key": "6",
                "label": comp_meta["label"] if comp_meta else "[Companion Action] (No companion in party)",
                "tags": [comp_meta["tag"]] if comp_meta else ["Locked: Requires Companion"],
                "enabled": comp_id is not None,
            },
            {
                "key": "7",
                "label": "Call in a Favor / Special Interaction",
                "tags": [favor_tag],
                "enabled": True,
            },
            {
                "key": "8",
                "label": "Provoke / Attack",
                "tags": ["Combat"],
                "enabled": True,
            },
            {
                "key": "0",
                "label": "Leave Conversation",
                "tags": ["Back"],
                "enabled": True,
            },
        ]

        greeting = self._build_dynamic_greeting(npc, rel)
        return {
            "npc_id": self.npc_id,
            "name": name,
            "title_rank": rank,
            "faction": faction_name,
            "visible_injuries": injuries,
            "relationship_state": rel.relationship_state,
            "axes": axes,
            "bars": bars,
            "greeting": greeting,
            "last_message": self.last_message,
            "closed": self.closed,
            "enter_combat": self.enter_combat,
            "options": options,
        }

    def choose(self, key: str | int) -> dict[str, Any]:
        """Execute a numbered dialogue choice [1]-[8] or [0] deterministically."""
        choice = str(key).strip()
        world = self.game.world
        npc = self._get_npc()
        if npc is None:
            self.closed = True
            msg = f"Character '{self.npc_id}' is no longer present."
            self.last_message = msg
            return {
                "success": False,
                "message": msg,
                "closed": True,
                "enter_combat": False,
                "view": self.get_view(),
            }

        success = True
        msg = ""

        if choice == "0":
            self.closed = True
            msg = f"You conclude your conversation with {npc.name}."

        elif choice == "1":
            district_id = self._get_district_id()
            rumors = [
                r for r in getattr(world, "rumors", {}).values()
                if district_id in getattr(r, "reach", {}) or getattr(r, "subject", "") == self.npc_id
            ]
            if not rumors:
                rumors = list(getattr(world, "rumors", {}).values())
            if rumors:
                r = rumors[0]
                claim = getattr(r, "claim", "Strange movements around the docks.")
                msg = f"{npc.name} lowers their voice: \"{claim}\""
            else:
                msg = f"{npc.name} shares word from {district_id.replace('_', ' ').title()}: \"Watch the Watchpost patrols—tensions with the Syndicate are boiling over.\""

            if world.player is not None:
                self._event_seq += 1
                mem_id = f"mem_dlg_rumor_{self.npc_id}_{world.clock.timestamp}_{self._event_seq}"
                world.player.memories.append(
                    Memory(
                        id=mem_id,
                        event_type="RUMOR_HEARD",
                        participants=["player", self.npc_id],
                        description=msg,
                        location_id=getattr(world.player, "location_id", district_id),
                        importance=0.5,
                        emotional_valence=0.0,
                        confidence=0.8,
                        created_at=int(world.clock.timestamp),
                        emotion="curiosity",
                        character_id=world.player.id,
                        source_type="told_by_other",
                    )
                )

        elif choice == "2":
            msg = self._handle_quest_discussion(npc)

        elif choice == "3":
            chance = self._get_persuade_chance()
            roll = 0.0 if world.flags.get("god_mode") else world.rng.random("dialogue")
            rel = self.game.relationship_system.get_relationship(self.npc_id, "player")
            if roll < (chance / 100.0):
                self.game.relationship_system.set_relationship(
                    self.npc_id,
                    "player",
                    trust=rel.trust + 12.0,
                    affection=rel.affection + 10.0,
                )
                msg = f"Persuasion succeeded ({chance}%): {npc.name} warms to your reasoning (+12 Trust, +10 Affection)."
            else:
                success = False
                self.game.relationship_system.set_relationship(
                    self.npc_id,
                    "player",
                    trust=rel.trust - 2.0,
                    resentment=rel.resentment + 5.0,
                )
                msg = f"Persuasion failed ({chance}%): {npc.name} remains unconvinced (+5 Resentment)."

        elif choice == "4":
            chance = self._get_intimidate_chance()
            roll = 0.0 if world.flags.get("god_mode") else world.rng.random("dialogue")
            rel = self.game.relationship_system.get_relationship(self.npc_id, "player")
            if roll < (chance / 100.0):
                coin = world.rng.randint("dialogue", 10, 25)
                if world.player is not None:
                    world.player.needs["wealth"] = float(world.player.needs.get("wealth", 0.0)) + coin
                self.game.relationship_system.set_relationship(
                    self.npc_id,
                    "player",
                    fear=rel.fear + 15.0,
                    resentment=rel.resentment + 5.0,
                )
                world.flags.setdefault("intimidated_npcs", {})[self.npc_id] = True
                msg = f"Intimidation succeeded ({chance}%): {npc.name} flinches and hands over {coin}g (+15 Fear)."
            else:
                success = False
                self.game.relationship_system.set_relationship(
                    self.npc_id,
                    "player",
                    trust=rel.trust - 10.0,
                    resentment=rel.resentment + 15.0,
                )
                if self.npc_id in world.nemesis_profiles:
                    world.nemesis_profiles[self.npc_id].player_hostility = min(
                        100.0,
                        float(world.nemesis_profiles[self.npc_id].player_hostility) + 10.0,
                    )
                msg = f"Intimidation failed ({chance}%): {npc.name} bristles at your threat (+15 Resentment, -10 Trust)."

        elif choice == "5":
            res = self.game.relationship_system.give_gift(world, "player", self.npc_id, gold_cost=25.0)
            if not res.get("success"):
                success = False
                msg = "You lack the 25g required for a gift or bribe."
            else:
                if getattr(npc, "faction_id", None) == "city_guard" and float(world.flags.get("bounty", 0.0)) > 0.0:
                    world.flags["bounty"] = max(0.0, float(world.flags.get("bounty", 0.0)) - 25.0)
                    msg = f"You slip 25g to {npc.name}, easing Guard scrutiny and improving rapport (+Trust, +Affection)."
                else:
                    msg = f"You offer 25g to {npc.name} (+Trust, +Affection, state: {res.get('relationship_state')})."

        elif choice == "6":
            comp_id, comp_meta = self._get_active_companion_action()
            if comp_id is None or comp_meta is None:
                success = False
                msg = "No companion is currently in your party to interject."
            else:
                rel = self.game.relationship_system.get_relationship(self.npc_id, "player")
                if comp_id == "comp_sera":
                    self.game.relationship_system.set_relationship(self.npc_id, "player", trust=rel.trust + 8.0, dependency=rel.dependency + 5.0)
                    world.flags["criminal_contacts_unlocked"] = True
                    msg = f"Sera leans in with Lowtown cant, disarming {npc.name}'s suspicion (+8 Trust, +5 Dependency)."
                elif comp_id == "comp_marcus":
                    self.game.relationship_system.set_relationship(self.npc_id, "player", respect=rel.respect + 12.0)
                    msg = f"Marcus steps forward in Watch bearing, pressing {npc.name} to show deference (+12 Respect)."
                elif comp_id == "comp_elira":
                    self.game.relationship_system.set_relationship(self.npc_id, "player", fear=rel.fear + 6.0, respect=rel.respect + 6.0)
                    world.flags.setdefault("elira_insights", {})[self.npc_id] = True
                    msg = f"Elira traces faint arcane residue around {npc.name}, revealing unspoken motives (+6 Respect, +6 Fear)."
                else:
                    self.game.relationship_system.set_relationship(
                        self.npc_id,
                        "player",
                        resentment=max(0.0, rel.resentment - 10.0),
                        affection=rel.affection + 8.0,
                    )
                    msg = f"Tomas offers calm Ashen Church counsel, soothing tensions with {npc.name} (-10 Resentment, +8 Affection)."

        elif choice == "7":
            if self.npc_id in world.companions:
                if self.npc_id in world.player_party:
                    world.player_party.remove(self.npc_id)
                    world.companions[self.npc_id].in_party = False
                    msg = f"{npc.name} steps back from your active party."
                else:
                    world.player_party.append(self.npc_id)
                    world.companions[self.npc_id].in_party = True
                    msg = f"{npc.name} joins your active party!"
            else:
                rel = self.game.relationship_system.get_relationship(self.npc_id, "player")
                if rel.trust >= 25.0 or rel.respect >= 25.0 or rel.dependency >= 20.0:
                    if world.player is not None:
                        world.player.needs["wealth"] = float(world.player.needs.get("wealth", 0.0)) + 15.0
                    msg = f"{npc.name} honors your standing and provides 15g in quiet support."
                else:
                    success = False
                    msg = f"{npc.name} doesn't trust or respect you enough yet to grant a favor (requires 25 Trust or Respect)."

        elif choice == "8":
            self.enter_combat = True
            self.closed = True
            party = [world.characters[cid] for cid in (world.player_party or ["player"]) if cid in world.characters]
            if not party and world.player is not None:
                party = [world.player]
            victor_fac = getattr(npc, "faction_id", None) or "city_guard"
            self.clash_session = self.game.combat_system.start_clash_session(
                party=party,
                enemies=[npc],
                victor_faction=victor_fac,
                world=world,
            )
            msg = f"You provoke {npc.name}! Combat Clash begins!"

        else:
            success = False
            msg = f"Invalid dialogue choice '{choice}'. Choose [1]-[8] or [0]."

        self.last_message = msg
        return {
            "success": success,
            "message": msg,
            "closed": self.closed,
            "enter_combat": self.enter_combat,
            "clash_session": self.clash_session,
            "view": self.get_view(),
        }

    def _handle_quest_discussion(self, npc: Any) -> str:
        world = self.game.world
        q_blood = world.quests.get("quest_blood_in_lowtown")
        if q_blood and q_blood.status == "active":
            if self.npc_id in ("npc_voss", "npc_merek", "comp_marcus"):
                for obj in q_blood.objectives:
                    if obj.get("id") == "investigate_crime_scene":
                        obj["completed"] = True
                return (
                    f"{npc.name} confirms the slain merchant carried a forged Guard manifest. "
                    "You can now resolve 'Blood in Lowtown' in Quests [7]."
                )
            if self.npc_id in ("npc_boss_malakor", "npc_gang_karn", "npc_thief_ren", "comp_sera"):
                for obj in q_blood.objectives:
                    if obj.get("id") == "investigate_crime_scene":
                        obj["completed"] = True
                return (
                    f"{npc.name} hints that someone inside the Watchpost sold out the merchant's route. "
                    "You can now choose your faction approach in Quests [7]."
                )
            return f"{npc.name} mentions the slain merchant's cart in Cobblestone Market—inspecting it may yield clues."

        active_quests = [q for q in world.quests.values() if getattr(q, "status", "") == "active"]
        if active_quests:
            q = active_quests[0]
            return f"{npc.name} discusses '{q.title}': {q.description}"
        return f"{npc.name} knows of no urgent contracts at the moment."
