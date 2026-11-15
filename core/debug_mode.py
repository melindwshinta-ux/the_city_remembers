"""Settings-gated Cheat & Debug Mode controller (GEMINI_PLAN §6)."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from config import MINUTES_PER_DAY, MINUTES_PER_HOUR, MINUTES_PER_WEEK, MINUTES_PER_YEAR
from entities.character import Injury, Relationship
from entities.enemy import NemesisProfile


DISABLED_MESSAGE = "Cheat/Debug Mode is disabled. Enable it in Settings first."

TIME_SKIP_PRESETS: dict[str, int] = {
    "6h": 6 * MINUTES_PER_HOUR,
    "1d": MINUTES_PER_DAY,
    "7d": MINUTES_PER_WEEK,
    "1y": MINUTES_PER_YEAR,
}

STANDARD_ATTRIBUTES: tuple[str, ...] = (
    "strength",
    "dexterity",
    "agility",
    "endurance",
    "constitution",
    "intelligence",
    "charisma",
)

STANDARD_SKILLS: tuple[str, ...] = (
    "swordsmanship",
    "heavy_weapons",
    "stealth",
    "medicine",
    "persuasion",
    "intimidation",
    "deception",
    "leadership",
    "discipline",
    "magic",
)

NEMESIS_RANKS: tuple[str, ...] = ("soldier", "sergeant", "lieutenant", "captain", "commander")


def _require_debug_enabled(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    @wraps(fn)
    def wrapper(self: DebugMode, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if not self.is_enabled():
            return {"success": False, "message": DISABLED_MESSAGE}
        return fn(self, *args, **kwargs)

    return wrapper


class DebugMode:
    """Controller for all 9 numbered Cheat/Debug actions, strictly gated by `game.settings.enable_debug_cheat`."""

    def __init__(self, game: Any) -> None:
        self.game = game

    def is_enabled(self) -> bool:
        settings = getattr(self.game, "settings", None)
        return bool(getattr(settings, "enable_debug_cheat", False))

    def get_menu_options(self) -> list[dict[str, Any]]:
        enabled = self.is_enabled()
        return [
            {"key": "1", "label": "+500 Gold (Wealth)", "enabled": enabled},
            {"key": "2", "label": "Full Heal & Cure All Anatomical Wounds (Player & Party)", "enabled": enabled},
            {"key": "3", "label": "Max All Attributes & Skills (100)", "enabled": enabled},
            {"key": "4", "label": "Toggle God Mode (Invulnerable + 100% Skill/Hit)", "enabled": enabled},
            {"key": "5", "label": "Time Skip (+6h / +1d / +7d / +1y)", "enabled": enabled},
            {"key": "6", "label": "Faction & District Manipulation", "enabled": enabled},
            {"key": "7", "label": "Relationship Manipulation (+50 Trust/Respect/Affection)", "enabled": enabled},
            {"key": "8", "label": "Nemesis Manipulation (Spawn / Promote / Injure Voss)", "enabled": enabled},
            {"key": "9", "label": "Quest & Tutorial Skip", "enabled": enabled},
            {"key": "0", "label": "Back to Game", "enabled": True},
        ]

    @_require_debug_enabled
    def execute_cheat(self, choice_num: int, **kwargs: Any) -> dict[str, Any]:
        """Dispatch numbered cheat action `[1]`-`[9]`."""
        choice = int(choice_num)
        if choice == 1:
            return self.add_gold(**kwargs)
        if choice == 2:
            return self.full_heal_party()
        if choice == 3:
            return self.max_attributes_and_skills(**kwargs)
        if choice == 4:
            return self.toggle_god_mode()
        if choice == 5:
            return self.time_skip(**kwargs)
        if choice == 6:
            return self.manipulate_factions_and_districts(**kwargs)
        if choice == 7:
            return self.boost_all_relationships(**kwargs)
        if choice == 8:
            return self.manipulate_nemesis(**kwargs)
        if choice == 9:
            return self.skip_quest_or_tutorial(**kwargs)
        return {"success": False, "message": f"Unknown debug cheat choice: {choice_num}"}

    # ------------------------------------------------------------------
    # [1] +500 Gold
    # ------------------------------------------------------------------
    @_require_debug_enabled
    def add_gold(self, amount: float = 500.0) -> dict[str, Any]:
        world = self.game.world
        player = getattr(world, "player", None)
        if player is None:
            return {"success": False, "message": "No player character found."}
        current = float(player.needs.get("wealth", 0.0))
        new_gold = current + float(amount)
        player.needs["wealth"] = new_gold
        return {
            "success": True,
            "message": f"Added {float(amount):.0f} Gold. Current wealth: {new_gold:.0f}g.",
            "data": {"gold": new_gold},
        }

    # ------------------------------------------------------------------
    # [2] Full Heal & Cure All Anatomical Wounds (Player & Party)
    # ------------------------------------------------------------------
    @_require_debug_enabled
    def full_heal_party(self) -> dict[str, Any]:
        world = self.game.world
        party_ids = list(dict.fromkeys([world.player_id] + list(getattr(world, "player_party", []))))
        healed: list[str] = []
        for cid in party_ids:
            char = world.characters.get(cid)
            if char is None:
                continue
            char.status = "alive"
            char.consciousness = 100.0
            char.morale = 100.0
            for need_key in ("hunger", "fatigue", "safety"):
                if need_key in char.needs:
                    char.needs[need_key] = 100.0
            for part in char.body.values():
                part.integrity = float(part.max_integrity)
                part.functional = True
                part.injuries.clear()
            healed.append(char.id)
        return {
            "success": True,
            "message": f"Fully healed and cured all wounds for {len(healed)} party member(s).",
            "data": {"healed_ids": healed},
        }

    # ------------------------------------------------------------------
    # [3] Max All Attributes & Skills (100)
    # ------------------------------------------------------------------
    @_require_debug_enabled
    def max_attributes_and_skills(self, value: float = 100.0) -> dict[str, Any]:
        world = self.game.world
        player = getattr(world, "player", None)
        if player is None:
            return {"success": False, "message": "No player character found."}
        cap = float(value)
        for attr in set(player.attributes.keys()) | set(STANDARD_ATTRIBUTES):
            player.attributes[attr] = int(cap) if float(cap).is_integer() else cap
        for skill in set(player.skills.keys()) | set(STANDARD_SKILLS):
            player.skills[skill] = cap
        return {
            "success": True,
            "message": f"All player attributes and skills set to {cap:.0f}.",
            "data": {"attributes": dict(player.attributes), "skills": dict(player.skills)},
        }

    # ------------------------------------------------------------------
    # [4] Toggle God Mode
    # ------------------------------------------------------------------
    @_require_debug_enabled
    def toggle_god_mode(self) -> dict[str, Any]:
        world = self.game.world
        new_state = not bool(world.flags.get("god_mode", False))
        world.flags["god_mode"] = new_state
        status_str = "ENABLED" if new_state else "DISABLED"
        return {
            "success": True,
            "message": f"God Mode {status_str} (Invulnerable + 100% Skill/Hit Success).",
            "data": {"god_mode": new_state},
        }

    # ------------------------------------------------------------------
    # [5] Time Skip (+6h / +1d / +7d / +1y)
    # ------------------------------------------------------------------
    @_require_debug_enabled
    def time_skip(self, preset: str = "1d", minutes: int | None = None) -> dict[str, Any]:
        world = self.game.world
        if minutes is not None:
            delta = max(1, int(minutes))
        else:
            key = str(preset).strip().lower()
            if key not in TIME_SKIP_PRESETS:
                return {
                    "success": False,
                    "message": f"Unknown time skip preset '{preset}'. Valid: {', '.join(TIME_SKIP_PRESETS)}",
                }
            delta = TIME_SKIP_PRESETS[key]

        sim = getattr(self.game, "simulation", None)
        if sim is not None and hasattr(sim, "advance_time"):
            sim.advance_time(delta, world=world)
        else:
            world.clock.advance_time(delta)

        return {
            "success": True,
            "message": (
                f"Skipped {delta} minutes. Now Year {world.clock.year}, "
                f"Day {world.clock.day_of_year}, {world.clock.hour:02d}:{world.clock.minute:02d}."
            ),
            "data": {
                "minutes_skipped": delta,
                "timestamp": world.clock.timestamp,
                "year": world.clock.year,
                "day_of_year": world.clock.day_of_year,
            },
        }

    # ------------------------------------------------------------------
    # [6] Faction & District Manipulation
    # ------------------------------------------------------------------
    @_require_debug_enabled
    def manipulate_factions_and_districts(
        self,
        mode: str = "max_rep",
        faction_id: str | None = None,
        district_id: str | None = None,
    ) -> dict[str, Any]:
        world = self.game.world
        op = str(mode).strip().lower()

        if op == "max_rep":
            fac_rep = world.reputation.setdefault("faction", {})
            for fid in world.factions:
                fac_rep[fid] = 100.0
            world.reputation["general_public"] = 100.0
            world.reputation["noble_society"] = 100.0
            return {
                "success": True,
                "message": "Maximized reputation (+100) with all factions and public.",
                "data": {"mode": op, "faction_reputation": dict(fac_rep)},
            }

        target_dist_id = district_id
        if not target_dist_id:
            player = getattr(world, "player", None)
            if player and player.location_id in world.locations:
                target_dist_id = world.locations[player.location_id].district_id
            elif world.districts:
                target_dist_id = next(iter(world.districts))

        district = world.districts.get(target_dist_id) if target_dist_id else None
        if district is None:
            return {"success": False, "message": f"District '{target_dist_id}' not found."}

        if op == "boost_influence":
            target_fac = faction_id or (next(iter(world.factions)) if world.factions else None)
            if not target_fac:
                return {"success": False, "message": "No faction available."}
            current_inf = float(district.faction_influence.get(target_fac, 0.0))
            new_inf = min(100.0, current_inf + 25.0)
            district.faction_influence[target_fac] = new_inf
            return {
                "success": True,
                "message": f"Boosted '{target_fac}' influence in {district.name} to {new_inf:.1f}%.",
                "data": {"mode": op, "district_id": district.id, "faction_id": target_fac, "influence": new_inf},
            }

        if op == "riot":
            district.unrest = 100.0
            district.security = max(0.0, float(district.security) - 30.0)
            return {
                "success": True,
                "message": f"Triggered riot in {district.name} (Unrest 100, Security {district.security:.0f}).",
                "data": {"mode": op, "district_id": district.id, "unrest": district.unrest, "security": district.security},
            }

        if op == "festival":
            district.unrest = 0.0
            district.security = min(100.0, float(district.security) + 20.0)
            district.wealth = min(100.0, float(district.wealth) + 10.0)
            return {
                "success": True,
                "message": f"Triggered festival in {district.name} (Unrest 0, Security {district.security:.0f}).",
                "data": {"mode": op, "district_id": district.id, "unrest": district.unrest, "security": district.security},
            }

        return {"success": False, "message": f"Unknown faction/district mode '{mode}'."}

    # ------------------------------------------------------------------
    # [7] Relationship Manipulation (+50 Trust, Respect & Affection)
    # ------------------------------------------------------------------
    @_require_debug_enabled
    def boost_all_relationships(self, delta: float = 50.0) -> dict[str, Any]:
        world = self.game.world
        rel_sys = getattr(world, "relationship_system", None)
        player_id = world.player_id
        updated = 0

        for cid, char in world.characters.items():
            if cid == player_id or getattr(char, "is_player", False):
                continue

            if rel_sys is not None and hasattr(rel_sys, "get_relationship"):
                rel = rel_sys.get_relationship(cid, player_id)
                rel_sys.set_relationship(
                    cid,
                    player_id,
                    trust=min(100.0, rel.trust + float(delta)),
                    respect=min(100.0, rel.respect + float(delta)),
                    affection=min(100.0, rel.affection + float(delta)),
                )
            else:
                rel = char.relationships.get(player_id) or Relationship(source_id=cid, target_id=player_id)
                rel.trust = min(100.0, rel.trust + float(delta))
                rel.respect = min(100.0, rel.respect + float(delta))
                rel.affection = min(100.0, rel.affection + float(delta))
                char.relationships[player_id] = rel

            comp = world.companions.get(cid)
            if comp is not None:
                comp.friendship = min(100.0, float(comp.friendship) + float(delta))

            updated += 1

        return {
            "success": True,
            "message": f"Boosted Trust, Respect & Affection by +{float(delta):.0f} for {updated} character(s).",
            "data": {"updated_count": updated},
        }

    # ------------------------------------------------------------------
    # [8] Nemesis Manipulation (Spawn / Promote / Injure Voss)
    # ------------------------------------------------------------------
    @_require_debug_enabled
    def manipulate_nemesis(self, mode: str = "promote", target_id: str = "npc_voss") -> dict[str, Any]:
        world = self.game.world
        op = str(mode).strip().lower()
        nem_sys = getattr(world, "nemesis_system", None)

        if op == "spawn":
            candidate = world.characters.get(target_id)
            if (
                candidate is None
                or candidate.is_player
                or candidate.is_companion
                or candidate.is_nemesis
                or candidate.status == "dead"
            ):
                candidate = next(
                    (
                        c
                        for c in world.characters.values()
                        if not c.is_player
                        and not c.is_companion
                        and not c.is_nemesis
                        and c.status == "alive"
                        and getattr(c, "tier", 1) < 3
                    ),
                    None,
                )
            if candidate is None:
                return {"success": False, "message": "No eligible NPC found to spawn as Nemesis."}

            if nem_sys is not None and hasattr(nem_sys, "evaluate_eligibility"):
                profile = nem_sys.evaluate_eligibility(candidate, "gains_power", world=world)
            else:
                candidate.is_nemesis = True
                profile = NemesisProfile(character_id=candidate.id, rank=candidate.rank or "soldier")
                world.nemesis_profiles[candidate.id] = profile
            return {
                "success": True,
                "message": f"Spawned Nemesis: {candidate.name} ({candidate.id}).",
                "data": {"character_id": candidate.id, "rank": profile.rank if profile else candidate.rank},
            }

        if op == "promote":
            npc = world.characters.get(target_id)
            if npc is None:
                return {"success": False, "message": f"Target '{target_id}' not found."}
            profile = world.nemesis_profiles.get(target_id)
            if nem_sys is not None and hasattr(nem_sys, "promote_character"):
                new_rank = nem_sys.promote_character(npc, profile)
            else:
                cur = npc.rank or (profile.rank if profile else "soldier")
                idx = NEMESIS_RANKS.index(cur) if cur in NEMESIS_RANKS else 0
                new_rank = NEMESIS_RANKS[min(len(NEMESIS_RANKS) - 1, idx + 1)]
                npc.rank = new_rank
                if profile is not None:
                    profile.rank = new_rank
            return {
                "success": True,
                "message": f"Promoted {npc.name} to rank '{new_rank}'.",
                "data": {"character_id": npc.id, "rank": new_rank},
            }

        if op == "injure_voss":
            voss_id = target_id if target_id in world.characters else "npc_voss"
            voss = world.characters.get(voss_id)
            if voss is None:
                return {"success": False, "message": f"Target '{voss_id}' not found."}
            health_sys = getattr(world, "health_system", None)
            if health_sys is not None and hasattr(health_sys, "apply_injury"):
                inj = health_sys.apply_injury(
                    voss,
                    "left_leg",
                    "broken_leg",
                    severity=0.8,
                    cause_description="Debug cheat injury",
                )
                inj_id = inj.id
            else:
                part = voss.body.get("left_leg")
                inj_id = "inj_debug_voss_leg"
                if part is not None:
                    part.injuries.append(
                        Injury(
                            id=inj_id,
                            injury_type="broken_leg",
                            severity=0.8,
                            pain=0.56,
                            bleeding=0.08,
                            body_part_id="left_leg",
                            character_id=voss.id,
                        )
                    )
                    part.functional = False
                    part.integrity = max(10.0, part.integrity - 40.0)
            return {
                "success": True,
                "message": f"Inflicted broken left leg on {voss.name}.",
                "data": {"character_id": voss.id, "injury_id": inj_id},
            }

        return {"success": False, "message": f"Unknown nemesis mode '{mode}'."}

    # ------------------------------------------------------------------
    # [9] Quest & Tutorial Skip
    # ------------------------------------------------------------------
    @_require_debug_enabled
    def skip_quest_or_tutorial(self, mode: str = "auto") -> dict[str, Any]:
        world = self.game.world
        op = str(mode).strip().lower()
        actions_taken: list[str] = []

        tut_flag = world.flags.get("tutorial", {})
        tut_pending = not bool(tut_flag.get("completed", False) or tut_flag.get("skipped", False))

        if op in ("tutorial", "both") or (op == "auto" and tut_pending):
            if hasattr(self.game, "skip_tutorial"):
                self.game.skip_tutorial()
            else:
                t = world.flags.setdefault("tutorial", {})
                t["completed"] = True
                t["skipped"] = True
                t["enabled"] = False
            actions_taken.append("tutorial_skipped")

        if op in ("quest", "both") or (op == "auto" and not tut_pending):
            completed_quests: list[str] = []
            for q in world.quests.values():
                if q.status == "active":
                    for obj in q.objectives:
                        if isinstance(obj, dict):
                            obj["completed"] = True
                    q.status = "completed"
                    completed_quests.append(q.id)
            if completed_quests:
                actions_taken.append(f"quests_completed:{','.join(completed_quests)}")

        if not actions_taken:
            actions_taken.append("nothing_pending")

        return {
            "success": True,
            "message": f"Quest/Tutorial skip executed ({', '.join(actions_taken)}).",
            "data": {"actions": actions_taken},
        }
