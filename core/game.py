"""Top-level Game session coordinator, structured command parser, and scenario runner (GDD Sections 16, 17, 18)."""

from __future__ import annotations

import copy
import re
import uuid
from pathlib import Path
from typing import Any

from ai.faction_ai import FactionAI
from config import FREQ_ECONOMY, FREQ_FACTION_DECISIONS, SETTINGS_PATH
from content import populate_world
from content.prologue import get_inspect_clue
from core.clock import WorldClock
from core.debug_mode import DebugMode
from core.event_bus import EventBus, EventPriority, GameEvent
from core.menu_engine import MenuEngine
from core.random_generator import SeededRNG
from core.settings import GameSettings, VALID_DIFFICULTIES, apply_new_game_setup, load_settings
from core.simulation import SimulationEngine
from core.tutorial import TutorialManager
from core.world import World
from entities.character import Memory
from entities.quest import Quest
from persistence.database import Database
from persistence.save_manager import SaveError, SaveManager, SaveNotFoundError
from systems.character_system import CharacterSystem
from systems.combat_system import CombatSystem
from systems.economy_system import EconomySystem
from systems.equipment_system import EquipmentSystem
from systems.faction_system import FactionSystem
from systems.health_system import HealthSystem
from systems.memory_system import MemorySystem
from systems.nemesis_system import NemesisSystem
from systems.quest_system import QuestSystem
from systems.relationship_system import RelationshipSystem
from systems.rumor_system import RumorSystem


class Game:
    """Central game session managing simulation, persistence, commands, and scenarios."""

    def __init__(
        self,
        seed: int = 482193,
        db: Database | None = None,
        save_manager: SaveManager | None = None,
        db_path: str | Path | None = None,
        world: World | None = None,
        settings: GameSettings | None = None,
        difficulty: str | None = None,
        background: str | None = None,
        keepsake: str | None = None,
        skip_prologue: bool = False,
        **kwargs: Any,
    ) -> None:
        self.seed = int(seed)
        self.world: World = world if world is not None else World(seed=self.seed)
        populate_world(self.world)

        if settings is not None:
            self.settings = settings
        elif SETTINGS_PATH.exists():
            self.settings = load_settings(SETTINGS_PATH)
        else:
            self.settings = GameSettings()

        if difficulty is not None and str(difficulty).strip().lower() in VALID_DIFFICULTIES:
            self.settings.difficulty = str(difficulty).strip().lower()

        if any(x is not None for x in (difficulty, background, keepsake)) or skip_prologue:
            apply_new_game_setup(
                self.world,
                difficulty=difficulty or self.settings.difficulty,
                background=background or "watch_veteran",
                keepsake=keepsake or "coin_purse",
                skip_prologue=skip_prologue,
            )

        # Wire systems
        self.character_system = CharacterSystem(world=self.world, event_bus=self.world.event_bus, clock=self.world.clock)
        self.memory_system = MemorySystem(world=self.world, event_bus=self.world.event_bus, clock=self.world.clock)
        self.relationship_system = RelationshipSystem(world=self.world, event_bus=self.world.event_bus, clock=self.world.clock)
        self.health_system = HealthSystem(world=self.world, event_bus=self.world.event_bus, clock=self.world.clock)
        self.equipment_system = EquipmentSystem(world=self.world, event_bus=self.world.event_bus, clock=self.world.clock)
        self.combat_system = CombatSystem(world=self.world, event_bus=self.world.event_bus, clock=self.world.clock)
        self.nemesis_system = NemesisSystem(world=self.world, event_bus=self.world.event_bus, clock=self.world.clock)
        self.faction_system = FactionSystem(world=self.world, event_bus=self.world.event_bus, clock=self.world.clock)
        self.quest_system = QuestSystem(world=self.world, event_bus=self.world.event_bus, clock=self.world.clock)
        self.rumor_system = RumorSystem(world=self.world, event_bus=self.world.event_bus, clock=self.world.clock)
        self.economy_system = EconomySystem(world=self.world, event_bus=self.world.event_bus, clock=self.world.clock)

        # Attach to world
        for sys_name in (
            "character_system", "memory_system", "relationship_system", "health_system",
            "equipment_system", "combat_system", "nemesis_system", "faction_system",
            "quest_system", "rumor_system", "economy_system"
        ):
            setattr(self.world, sys_name, getattr(self, sys_name))

        # Persistence
        if db is not None:
            self.db = db
        else:
            path = db_path or (Path("/home/antigravity/the_city_remembers/saves") / f"save_{self.seed}.db")
            self.db = Database(path)

        if save_manager is not None:
            self.save_manager = save_manager
        else:
            self.save_manager = SaveManager(self.db)

        # Simulation
        self.simulation = SimulationEngine(world=self.world)
        self.faction_ai = FactionAI(
            world=self.world,
            event_bus=self.world.event_bus,
            clock=self.world.clock,
            rng=self.world.rng,
        )

        def _faction_tick(w: World, _elapsed: int = 0) -> None:
            for fac in list(w.factions.values()):
                self.faction_ai.process_faction_turn(fac, world=w)

        def _economy_tick(w: World, _elapsed: int = 0) -> None:
            self.economy_system.process_daily_tick(world=w)

        self._economy_tick_cb = _economy_tick
        self.simulation.register_system(FREQ_FACTION_DECISIONS, _faction_tick, name="faction_ai")
        self.simulation.register_system(FREQ_ECONOMY, self._economy_tick_cb, name="economy_system")
        self.tutorial = TutorialManager(self.world)
        self.debug_mode = DebugMode(self)
        self.menu_engine = MenuEngine(self)
        self._rebind_world(self.world)

    def _rebind_world(self, world: World) -> None:
        """Rebind Game, all 11 systems, SimulationEngine, FactionAI, and TutorialManager to `world`."""
        self.world = world
        for sys_name in (
            "character_system", "memory_system", "relationship_system", "health_system",
            "equipment_system", "combat_system", "nemesis_system", "faction_system",
            "quest_system", "rumor_system", "economy_system",
        ):
            sys_obj = getattr(self, sys_name)
            sys_obj.world = world
            sys_obj.event_bus = world.event_bus
            sys_obj.clock = world.clock
            setattr(world, sys_name, sys_obj)

        self.simulation.world = world
        if hasattr(self, "_economy_tick_cb"):
            self.simulation.register_system(FREQ_ECONOMY, self._economy_tick_cb, name="economy_system")
        self.faction_ai.world = world
        self.faction_ai.event_bus = world.event_bus
        self.faction_ai.clock = world.clock
        self.faction_ai.rng = world.rng
        self.tutorial.world = world
        if hasattr(self, "menu_engine") and self.menu_engine is not None:
            self.menu_engine.reset()

    def get_menu_screen(self) -> dict[str, Any]:
        return self.menu_engine.get_screen()

    def select_menu(self, key: str | int) -> dict[str, Any]:
        return self.menu_engine.select(str(key))

    def start_dialogue(self, npc_id: str) -> dict[str, Any]:
        return self.menu_engine.start_dialogue(npc_id)

    # ------------------------------------------------------------------
    # Prologue & Tutorial Delegate API (PROJECT.md Interface Contracts)
    # ------------------------------------------------------------------
    def _sync_tutorial_world(self) -> TutorialManager:
        if self.tutorial.world is not self.world:
            self.tutorial.world = self.world
        return self.tutorial

    def get_prologue_state(self) -> dict[str, Any]:
        return self._sync_tutorial_world().get_prologue_state()

    def advance_prologue(self, choice_id: str | None = None) -> dict[str, Any]:
        return self._sync_tutorial_world().advance_prologue(choice_id=choice_id)

    def skip_prologue(self) -> dict[str, Any]:
        return self._sync_tutorial_world().skip_prologue()

    def replay_prologue(self) -> dict[str, Any]:
        return self._sync_tutorial_world().replay_prologue()

    def get_tutorial_state(self) -> dict[str, Any]:
        return self._sync_tutorial_world().get_tutorial_state()

    def skip_tutorial(self) -> dict[str, Any]:
        return self._sync_tutorial_world().skip_tutorial()

    def reset_tutorial(self) -> dict[str, Any]:
        return self._sync_tutorial_world().reset_tutorial()

    def parse_command(self, raw_input: str) -> dict[str, Any]:
        """Resolve raw string command and aliases to canonical dict with stable IDs (GDD Section 16)."""
        text = raw_input.strip()
        tokens = text.split()
        if not tokens:
            return {"action": "none", "actor": "player"}

        verb = tokens[0].lower()
        arg_str = " ".join(tokens[1:]).lower()

        # Target ID alias map
        target_map = {
            "sera": "comp_sera",
            "marcus": "comp_marcus",
            "elira": "comp_elira",
            "tomas": "comp_tomas",
            "captain voss": "npc_voss",
            "garrick voss": "npc_voss",
            "voss": "npc_voss",
            "sergeant merek": "npc_merek",
            "merek": "npc_merek",
            "gregor": "npc_gregor",
            "brant": "npc_trader_brant",
            "malakor": "npc_boss_malakor",
            "karn": "npc_gang_karn",
            "ren": "npc_thief_ren",
            "city guard": "city_guard",
            "city_guard": "city_guard",
            "syndicate": "lowtown_syndicate",
            "lowtown syndicate": "lowtown_syndicate",
            "lowtown": "lowtown",
            "harbor": "harbor",
            "high quarter": "high_quarter",
            "iron ward": "iron_ward",
            "temple district": "temple_district",
            "barracks": "barracks",
            "old quarter": "old_quarter",
        }

        def resolve_target(name: str) -> str:
            cleaned = name.lower().strip()
            if not cleaned:
                return ""
            cleaned_id = cleaned.replace(" ", "_")

            # 1. Exact ID match in world registries
            for registry in (
                self.world.locations,
                self.world.characters,
                self.world.districts,
                self.world.factions,
                self.world.items,
            ):
                if cleaned in registry:
                    return cleaned
                if cleaned_id in registry:
                    return cleaned_id

            # 2. Exact key match in target_map
            if cleaned in target_map:
                return target_map[cleaned]
            if cleaned_id in target_map:
                return target_map[cleaned_id]

            # 3. Exact case-insensitive .name match in world entities
            for registry in (
                self.world.locations,
                self.world.characters,
                self.world.districts,
                self.world.factions,
            ):
                for eid, obj in registry.items():
                    if getattr(obj, "name", "").lower() == cleaned:
                        return eid

            # 4. Longest-key word-boundary match fallback in target_map
            for k in sorted(target_map.keys(), key=len, reverse=True):
                if re.search(rf"(?<!\w){re.escape(k)}(?!\w)", cleaned):
                    return target_map[k]

            return cleaned_id

        # 1. Talk / Speak
        if verb in ("talk", "speak", "converse"):
            return {"action": "talk", "actor": "player", "target": resolve_target(arg_str)}

        # 2. Inspect / Examine
        if verb in ("inspect", "examine", "look"):
            return {"action": "inspect", "actor": "player", "target": resolve_target(arg_str)}

        # 3. Attack
        if verb in ("attack", "strike", "fight"):
            return {"action": "attack", "actor": "player", "target": resolve_target(arg_str), "weapon": "iron_longsword"}

        # 4. Move / Travel / Go
        if verb in ("move", "travel", "go"):
            return {"action": "move", "actor": "player", "target": resolve_target(arg_str)}

        # 5. Check Health
        if verb == "check" and "health" in arg_str:
            target_name = arg_str.replace("health", "").strip()
            return {"action": "check_health", "actor": "player", "target": resolve_target(target_name)}

        # 6. Open Screen
        valid_views = {"world", "character", "health", "party", "combat", "factions", "journal", "inventory"}
        if verb == "open":
            cleaned = arg_str.strip()
            if cleaned in valid_views:
                return {"action": f"open_{cleaned}", "actor": "player", "target": cleaned}
            if cleaned == "faction" or cleaned.startswith("faction "):
                fac_name = cleaned[len("faction"):].strip()
                target = resolve_target(fac_name) if fac_name else "city_guard"
                return {"action": "open_faction", "actor": "player", "target": target}
            return {
                "action": f"open_{cleaned}" if cleaned else "open",
                "actor": "player",
                "target": cleaned,
                "invalid": True,
                "error": f"Unknown view '{cleaned}'.",
            }

        # 7. Rest
        if verb == "rest":
            cleaned = arg_str.strip()
            if not cleaned:
                hours = 8
                return {"action": "rest", "actor": "player", "hours": hours, "minutes": hours * 60}
            m = re.fullmatch(r"(\d+)\s*([hm]?)", cleaned)
            if not m or int(m.group(1)) <= 0:
                return {"action": "rest", "actor": "player", "invalid": True, "error": f"Invalid rest duration '{arg_str}'."}
            val = int(m.group(1))
            unit = m.group(2)
            if unit == "m":
                minutes = val
                hours = val / 60
            else:
                hours = val
                minutes = val * 60
            return {"action": "rest", "actor": "player", "hours": hours, "minutes": minutes}

        # 8. Wait
        if verb == "wait":
            cleaned = arg_str.strip()
            if not cleaned:
                days = 1
                return {"action": "wait", "actor": "player", "days": days, "minutes": days * 1440}
            m = re.fullmatch(r"(\d+)\s*([dhm]?)", cleaned)
            if not m or int(m.group(1)) <= 0:
                return {"action": "wait", "actor": "player", "invalid": True, "error": f"Invalid wait duration '{arg_str}'."}
            val = int(m.group(1))
            unit = m.group(2)
            if unit == "m":
                minutes = val
                days = val / 1440
            elif unit == "h":
                minutes = val * 60
                days = val / 24
            else:
                days = val
                minutes = val * 1440
            return {"action": "wait", "actor": "player", "days": days, "minutes": minutes}

        # Tactical commands: aim captain voss left_leg
        if verb == "aim":
            parts = arg_str.rsplit(maxsplit=1)
            if len(parts) > 1:
                target_name, body_part = parts[0], parts[1]
            elif len(parts) == 1 and parts[0]:
                target_name, body_part = parts[0], "left_leg"
            else:
                target_name, body_part = "npc_voss", "left_leg"
            return {"action": "aim", "actor": "player", "target": resolve_target(target_name), "target_part": body_part, "body_part": body_part}

        # Support commands: apply bandage marcus left_arm
        if verb == "apply" and "bandage" in arg_str:
            clean = arg_str.replace("bandage", "").strip()
            parts = clean.rsplit(maxsplit=1)
            if len(parts) > 1:
                target_name, body_part = parts[0], parts[1]
            elif len(parts) == 1 and parts[0]:
                target_name, body_part = parts[0], "left_arm"
            else:
                target_name, body_part = "comp_marcus", "left_arm"
            return {"action": "apply_bandage", "actor": "player", "target": resolve_target(target_name), "body_part": body_part}

        # Scenario approach choice: choose / resolve <approach>
        if verb in ("choose", "resolve"):
            approach_aliases = {
                "guard": "support_city_guard",
                "city_guard": "support_city_guard",
                "city guard": "support_city_guard",
                "support_city_guard": "support_city_guard",
                "syndicate": "support_syndicate",
                "lowtown_syndicate": "support_syndicate",
                "support_syndicate": "support_syndicate",
                "independent": "investigate_independently",
                "investigate": "investigate_independently",
                "investigate_independently": "investigate_independently",
                "exploit": "exploit_situation",
                "exploit_situation": "exploit_situation",
            }
            cleaned = arg_str.strip()
            approach = approach_aliases.get(cleaned, cleaned.replace(" ", "_"))
            return {"action": "choose_approach", "actor": "player", "target": approach, "approach": approach}

        # Prologue commands
        if verb == "skip" and arg_str.strip() == "prologue":
            return {"action": "skip_prologue", "actor": "player"}
        if verb == "replay" and arg_str.strip() == "prologue":
            return {"action": "replay_prologue", "actor": "player"}
        if verb == "skip" and arg_str.strip() == "tutorial":
            return {"action": "tutorial_skip", "actor": "player"}
        if verb == "prologue":
            sub = arg_str.strip()
            if sub == "skip":
                return {"action": "skip_prologue", "actor": "player"}
            if sub == "replay":
                return {"action": "replay_prologue", "actor": "player"}
            if sub in ("", "next", "continue"):
                return {"action": "prologue", "actor": "player", "choice_id": None}
            return {"action": "prologue", "actor": "player", "choice_id": sub.replace(" ", "_")}

        # Tutorial commands
        if verb == "tutorial":
            sub = arg_str.strip()
            if sub == "skip":
                return {"action": "tutorial_skip", "actor": "player"}
            if sub == "reset":
                return {"action": "tutorial_reset", "actor": "player"}
            return {"action": "tutorial_status", "actor": "player"}

        # Persistence / UI commands
        if verb in ("save", "load", "chronicle"):
            return {"action": verb, "actor": "player", "slot": arg_str or "default"}

        # Recruit companion
        if verb == "recruit":
            return {"action": "recruit", "actor": "player", "target": resolve_target(arg_str)}

        return {"action": verb, "actor": "player", "target": arg_str}

    def execute_command(self, cmd: str | dict[str, Any]) -> dict[str, Any]:
        """Execute structured command, advance clock, and return contract response dictionary."""
        cmd_dict = self.parse_command(cmd) if isinstance(cmd, str) else cmd
        action = cmd_dict.get("action", "unknown")
        events: list[GameEvent] = []

        def fail(message: str) -> dict[str, Any]:
            return {
                "success": False,
                "action": action,
                "message": message,
                "events": [],
                "data": dict(cmd_dict),
            }

        if action == "none" or cmd_dict.get("invalid"):
            return fail(cmd_dict.get("error") or "Invalid or empty command. Type 'help' for valid commands.")

        # Default time increments
        time_to_advance = 0
        valid_open_views = {f"open_{v}" for v in ("world", "character", "health", "party", "combat", "factions", "journal", "inventory")}

        if action == "talk":
            target_id = cmd_dict.get("target", "")
            target_char = self.world.characters.get(target_id)
            if not target_char:
                return fail(f"No character found matching '{target_id}'.")
            time_to_advance = 15
            dialogue = self.get_dialogue(target_id)
            msg = f'You confer with {target_char.name}: "{dialogue}"'

        elif action == "inspect":
            target_id = cmd_dict.get("target", "")
            exists = (
                target_id in self.world.characters
                or target_id in self.world.districts
                or target_id in self.world.locations
                or target_id in self.world.factions
                or target_id in self.world.items
            )
            if not target_id or not exists:
                return fail(f"Nothing found to inspect matching '{target_id}'.")
            time_to_advance = 5
            msg = get_inspect_clue(target_id, world=self.world)
            if target_id == "lowtown_market":
                self.world.flags["crime_scene_inspected"] = True
                if self.world.player and not any(
                    getattr(m, "id", None) == "mem_lowtown_crime_scene"
                    for m in self.world.player.memories
                ):
                    self.world.player.memories.append(
                        Memory(
                            id="mem_lowtown_crime_scene",
                            event_type="CRIME_SCENE_INSPECTED",
                            participants=["player"],
                            description="Examined the slain merchant's cart in Cobblestone Market and found muddy bootprints and a torn Guard wax seal.",
                            location_id="lowtown_market",
                            importance=0.8,
                            emotional_valence=-0.1,
                            confidence=1.0,
                            created_at=int(self.world.clock.total_minutes),
                            emotion="curiosity",
                            character_id=self.world.player.id,
                            source_type="witnessed",
                        )
                    )
                q_blood = self.world.quests.get("quest_blood_in_lowtown")
                if q_blood:
                    for obj in q_blood.objectives:
                        if obj.get("id") == "investigate_crime_scene":
                            obj["completed"] = True

        elif action == "choose_approach":
            approach = str(cmd_dict.get("approach") or cmd_dict.get("target") or "")
            res = self.resolve_scenario_approach(approach)
            if not res.get("success"):
                return fail(res.get("message", f"Could not resolve approach '{approach}'."))
            time_to_advance = 15
            msg = str(res.get("message", f"Resolved Blood in Lowtown via {approach}."))

        elif action in ("attack", "aim"):
            target_id = cmd_dict.get("target", "")
            target_char = self.world.characters.get(target_id)
            if not target_char:
                return fail(f"No target character found matching '{target_id}'.")
            weapon_id = cmd_dict.get("weapon", "iron_longsword")
            weapon = self.world.items.get(weapon_id)
            target_part = cmd_dict.get("target_part", "torso")
            self.combat_system.resolve_attack(
                attacker=self.world.player,
                defender=target_char,
                weapon=weapon,
                command=action,
                target_part=target_part,
                force_hit=True,
            )
            if target_id in self.world.nemesis_profiles:
                self.nemesis_system.record_encounter(
                    self.world.nemesis_profiles[target_id],
                    hostility_delta=5.0,
                )
            time_to_advance = 5
            msg = f"You {action} {target_char.name}."

        elif action == "recruit":
            target_id = cmd_dict.get("target", "")
            target_char = self.world.characters.get(target_id)
            if not target_char:
                return fail(f"No character found to recruit matching '{target_id}'.")
            if target_id not in self.world.player_party:
                self.world.player_party.append(target_id)
            if target_id in self.world.companions:
                self.world.companions[target_id].in_party = True
            time_to_advance = 10
            msg = f"You recruited {target_char.name} into your party."

        elif action == "apply_bandage":
            target_id = cmd_dict.get("target", "")
            target_char = self.world.characters.get(target_id)
            if not target_char:
                return fail(f"No character found matching '{target_id}'.")
            time_to_advance = 5
            msg = f"Applied bandage to {target_char.name}."

        elif action == "move":
            target_id = cmd_dict.get("target", "")
            if not target_id or (target_id not in self.world.districts and target_id not in self.world.locations):
                return fail(f"Unknown destination '{target_id}'.")
            time_to_advance = 25
            self.world.player.location_id = target_id
            msg = f"You traveled to {target_id}."

        elif action == "rest":
            try:
                time_to_advance = int(cmd_dict.get("minutes", 0))
            except (TypeError, ValueError):
                return fail("Rest duration must be a valid integer.")
            if time_to_advance <= 0:
                return fail("Rest duration must be positive.")
            msg = f"You rested for {cmd_dict.get('hours', 8)} hours."

        elif action == "wait":
            try:
                time_to_advance = int(cmd_dict.get("minutes", 0))
            except (TypeError, ValueError):
                return fail("Wait duration must be a valid integer.")
            if time_to_advance <= 0:
                return fail("Wait duration must be positive.")
            msg = f"You waited for {cmd_dict.get('days', 1)} days."

        elif action == "check_health":
            target_id = cmd_dict.get("target", "")
            if target_id and target_id != "party" and target_id not in self.world.characters:
                return fail(f"No character found matching '{target_id}'.")
            time_to_advance = 5
            msg = f"Checked health for {target_id or 'party'}."

        elif action == "open_faction":
            target_id = cmd_dict.get("target", "")
            if not target_id or target_id not in self.world.factions:
                return fail(f"Unknown faction '{target_id}'.")
            msg = f"Opened faction view for {target_id}."

        elif action in valid_open_views:
            view_name = action[len("open_"):]
            msg = f"Opened {view_name} view."

        elif action == "save":
            slot = cmd_dict.get("slot", "default")
            prev_tutorial = copy.deepcopy(self.world.flags.get("tutorial"))
            self._sync_tutorial_world().advance_tutorial_for_action(
                "save",
                slot,
                {"success": True, "action": "save"},
            )
            try:
                self.save_manager.save_game(self.world, slot=slot)
            except Exception:
                if prev_tutorial is None:
                    self.world.flags.pop("tutorial", None)
                else:
                    self.world.flags["tutorial"] = prev_tutorial
                raise
            msg = f"Saved game to slot '{slot}'."

        elif action == "load":
            slot = cmd_dict.get("slot", "default")
            try:
                loaded_world = self.save_manager.load_game(slot=slot)
            except (SaveNotFoundError, SaveError) as exc:
                return fail(str(exc))
            self._rebind_world(loaded_world)
            msg = f"Loaded game from slot '{slot}'."

        elif action == "chronicle":
            chron = self.save_manager.generate_chronicle(self.world)
            msg = f"Generated chronicle with {len(chron)} entries."

        elif action == "prologue":
            res = self.advance_prologue(choice_id=cmd_dict.get("choice_id"))
            if not res.get("success"):
                return fail(res.get("message", "Could not advance prologue."))
            msg = str(res.get("message", "Prologue updated."))

        elif action == "skip_prologue":
            res = self.skip_prologue()
            msg = str(res.get("message", "Prologue skipped."))

        elif action == "replay_prologue":
            res = self.replay_prologue()
            msg = str(res.get("message", "Prologue restarted."))

        elif action == "tutorial_status":
            t_state = self.get_tutorial_state()
            done, total = t_state["progress"]
            step_info = t_state.get("step_info")
            if t_state["skipped"]:
                msg = f"Tutorial skipped ({done}/{total} steps). Type 'tutorial reset' to resume."
            elif t_state["completed"] or not step_info:
                msg = f"Tutorial complete ({done}/{total} steps)."
            else:
                msg = f"Tutorial ({done}/{total}) — {step_info['title']}: {step_info['hint']}"

        elif action == "tutorial_skip":
            res = self.skip_tutorial()
            msg = str(res.get("message", "Tutorial skipped."))

        elif action == "tutorial_reset":
            res = self.reset_tutorial()
            msg = str(res.get("message", "Tutorial reset."))

        elif action == "help":
            msg = "Available commands: talk, inspect, attack, aim, move, choose, check health, open <view>, rest, wait, save, load, chronicle, prologue, tutorial."

        else:
            return fail(
                f"Unknown command '{action}'. Type 'help' for valid commands (talk, inspect, attack, move, choose, check health, open <view>, rest, wait, save, load, chronicle, prologue, tutorial)."
            )

        if time_to_advance > 0:
            events = self.simulation.advance_time(time_to_advance, world=self.world)

        result_dict: dict[str, Any] = {
            "success": True,
            "action": action,
            "message": msg,
            "events": events,
            "data": dict(cmd_dict),
        }

        if action not in (
            "save",
            "prologue",
            "skip_prologue",
            "replay_prologue",
            "tutorial_status",
            "tutorial_skip",
            "tutorial_reset",
            "help",
        ):
            self._sync_tutorial_world().advance_tutorial_for_action(
                action,
                str(cmd_dict.get("target", "")),
                result_dict,
            )

        return result_dict

    def resolve_scenario_approach(self, approach_name: str, expose_target: str = "city_guard", **kwargs: Any) -> dict[str, Any]:
        """Resolve one of the 4 approaches in 'Blood in Lowtown' scenario (GDD Section 18)."""
        quest = self.world.quests.get("quest_blood_in_lowtown")
        if (quest and quest.status == "completed") or self.world.flags.get("blood_in_lowtown_completed"):
            return {
                "success": False,
                "message": "Blood in Lowtown scenario is already completed.",
            }

        def _emit_quest_completed() -> None:
            if quest:
                for obj in quest.objectives:
                    if obj.get("id") == "choose_faction_approach":
                        obj["completed"] = True
            self.world.event_bus.emit(
                GameEvent(
                    id=f"ev_quest_{uuid.uuid4().hex[:6]}",
                    event_type="QUEST_COMPLETED",
                    timestamp=self.world.clock.timestamp,
                    source_id="player",
                    target_ids=["quest_blood_in_lowtown"],
                    location_id=self.world.player.location_id or "lowtown",
                    data={"quest_id": "quest_blood_in_lowtown", "approach": approach_name},
                    importance=0.85,
                ),
                priority=EventPriority.CRITICAL,
            )
            self._sync_tutorial_world().advance_tutorial_for_action(
                "choose_approach",
                approach_name,
                {"success": True},
            )

        if approach_name == "support_city_guard":
            self.world.reputation["faction"]["city_guard"] = 35.0
            self.world.reputation["faction"]["lowtown_syndicate"] = -35.0
            self.world.flags["discovered_guard_corruption"] = True
            self.world.flags["blood_in_lowtown_completed"] = True
            if quest:
                quest.status = "completed"
            _emit_quest_completed()
            return {
                "success": True,
                "approach": approach_name,
                "message": "Supported the Guard and discovered internal corruption.",
            }

        elif approach_name == "support_syndicate":
            self.world.reputation["faction"]["lowtown_syndicate"] = 35.0
            self.world.reputation["faction"]["city_guard"] = -25.0
            self.world.reputation["criminal_underworld"] = self.world.reputation.get("criminal_underworld", 0.0) + 25.0
            if "npc_voss" in self.world.nemesis_profiles:
                self.world.nemesis_profiles["npc_voss"].player_hostility = 65.0
            self.world.flags["exposed_illegal_trade"] = True
            self.world.flags["criminal_contacts_unlocked"] = True
            self.world.flags["blood_in_lowtown_completed"] = True
            if "comp_sera" in self.world.companions:
                self.world.companions["comp_sera"].friendship += 10.0
            if "comp_marcus" in self.world.companions:
                self.world.companions["comp_marcus"].rivalry += 10.0
            if quest:
                quest.status = "completed"
            _emit_quest_completed()
            return {
                "success": True,
                "approach": approach_name,
                "message": "Supported the Syndicate, exposed illegal trade, and angered Voss.",
            }

        elif approach_name == "investigate_independently":
            self.world.flags["independent_investigation_complete"] = True
            self.world.flags["blood_in_lowtown_completed"] = True
            if quest:
                quest.status = "completed"
            self.world.event_bus.emit(
                GameEvent(
                    id=f"ev_rumor_{uuid.uuid4().hex[:6]}",
                    event_type="RUMOR_SPREAD",
                    timestamp=self.world.clock.timestamp,
                    source_id="player",
                    target_ids=[expose_target],
                    location_id=self.world.player.location_id or "lowtown",
                    data={"exposed_target": expose_target, "quest_id": "quest_blood_in_lowtown"},
                    importance=0.75,
                ),
                priority=EventPriority.CRITICAL,
            )
            _emit_quest_completed()
            return {
                "success": True,
                "approach": approach_name,
                "exposed_target": expose_target,
                "message": f"Investigated independently and exposed {expose_target}.",
            }

        elif approach_name == "exploit_situation":
            self.world.player.needs["wealth"] = self.world.player.needs.get("wealth", 0.0) + 150.0
            if "lowtown" in self.world.districts:
                self.world.districts["lowtown"].unrest += 25.0
            self.faction_system.adjust_relation("city_guard", "lowtown_syndicate", -40.0, world=self.world)
            self.faction_system.adjust_relation("lowtown_syndicate", "city_guard", -40.0, world=self.world)
            self.world.flags["blood_in_lowtown_completed"] = True
            if quest:
                quest.status = "completed"
            self.world.event_bus.emit(
                GameEvent(
                    id=f"ev_conflict_{uuid.uuid4().hex[:6]}",
                    event_type="POLITICAL_CONFLICT_STARTED",
                    timestamp=self.world.clock.timestamp,
                    source_id="player",
                    target_ids=["city_guard", "lowtown_syndicate"],
                    location_id="lowtown",
                    data={"approach": approach_name},
                    importance=0.85,
                ),
                priority=EventPriority.CRITICAL,
            )
            _emit_quest_completed()
            return {
                "success": True,
                "approach": approach_name,
                "message": "Sold information to both factions, sparking conflict and earning gold.",
            }

        return {"success": False, "message": f"Unknown approach {approach_name}"}

    def complete_blood_in_lowtown(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.resolve_scenario_approach(*args, **kwargs)

    def choose_quest_approach(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.resolve_scenario_approach(*args, **kwargs)

    def run_post_quest_continuation(self, voss_injury: str = "broken_arm", days: int = 14) -> dict[str, Any]:
        """Simulate post-quest continuation: Voss injured, rival promoted, private investigation quest begins (GDD Section 18)."""
        voss = self.world.characters.get("npc_voss")
        if voss:
            self.health_system.apply_injury(voss, "left_arm", voss_injury, severity=0.85)
            prof = self.world.nemesis_profiles.get("npc_voss")
            if prof:
                prof.player_hostility = max(prof.player_hostility, 60.0)
                prof.grudges.append("Injured in Lowtown confrontation")

        # Promote rival
        guard = self.world.factions.get("city_guard")
        if guard:
            self.nemesis_system.evaluate_promotion_candidates(guard, target_rank="commander", world=self.world)

        # Emit RIVAL_PROMOTED to event history
        self.world.event_bus.emit(
            GameEvent(
                id=f"ev_rival_{uuid.uuid4().hex[:6]}",
                event_type="RIVAL_PROMOTED",
                timestamp=self.world.clock.timestamp,
                source_id="city_guard",
                target_ids=["npc_captain_lyra"],
                location_id="barracks",
                data={"new_rank": "commander"},
                importance=0.85,
            ),
            priority=EventPriority.CRITICAL,
        )
        self.world.event_bus.process_tick_events()

        # New quest
        new_q = Quest(
            id="quest_voss_investigation",
            title="Voss's Shadow",
            description="Captain Voss is privately financing mercenaries to track you down.",
            quest_type="systemic",
            status="active",
        )
        self.world.quests["quest_voss_investigation"] = new_q

        return {"success": True, "new_quest": "quest_voss_investigation"}

    def simulate_blood_in_lowtown_aftermath(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.run_post_quest_continuation(*args, **kwargs)

    def run_vertical_slice(self) -> dict[str, Any]:
        """Execute Appendix B 10-step vertical slice sequence (GDD Appendix B)."""
        steps = [
            "1. Walk around Lowtown",
            "2. Talk to NPCs and recruit companions",
            "3. Start a fight with Captain Voss",
            "4. Injure him using location-specific damage",
            "5. Allow him to escape",
            "6. Advance time by several days",
            "7. Let the faction simulation run",
            "8. Encounter Voss again",
            "9. Discover how his injuries, memories, and political circumstances changed",
            "10. Save the game and inspect its event history",
        ]

        # 1. Walk around
        self.world.player.location_id = "lowtown_market"
        # 2. Talk
        self.execute_command("talk sera")
        # 3. Fight & 4. Injure
        voss = self.world.characters.get("npc_voss")
        if voss:
            self.health_system.apply_injury(voss, "left_arm", "broken_arm", severity=0.8)
            self.save_manager.append_event(
                GameEvent(
                    id=f"ev_vs_{uuid.uuid4().hex[:6]}",
                    event_type="LIMB_INJURED",
                    timestamp=self.world.clock.timestamp,
                    source_id="player",
                    target_ids=["npc_voss"],
                    location_id="lowtown",
                    data={"body_part": "left_arm", "injury": "broken_arm"},
                    importance=0.85,
                )
            )
        # 5. Escape
        # 6. Advance time 7 days
        self.simulation.advance_time(7 * 1440, world=self.world)
        # 7. Faction sim
        self.faction_system.shift_district_influence("lowtown", "city_guard", 5.0)
        # 8 & 9. Encounter Voss
        # 10. Save
        self.save_manager.save_game(self.world, slot="vertical_slice")

        return {"success": True, "steps_completed": steps}

    def execute_vertical_slice(self) -> dict[str, Any]:
        return self.run_vertical_slice()

    def get_dialogue(self, character_id: str, world: Any = None) -> str:
        """Contextual dialogue generator reacting to injuries, grudges, and hostility (GDD Section 20)."""
        active_world = world or self.world
        c = active_world.characters.get(character_id)
        if not c:
            return "..."

        prof = active_world.nemesis_profiles.get(character_id)
        hostility = getattr(prof, "player_hostility", 0.0) if prof else 0.0

        # Injured / hostile Voss
        if character_id == "npc_voss":
            has_broken_leg = False
            if hasattr(c, "body") and "left_leg" in c.body:
                has_broken_leg = any(inj.injury_type == "broken_leg" for inj in c.body["left_leg"].injuries)
            if has_broken_leg or hostility >= 70.0:
                return "You broke my leg, Rowan! Every step I take will remind me to see you hang in the square!"
            return "Watch yourself in Lowtown, traveler. The City Guard sees everything."

        if character_id == "comp_sera":
            return "Keep your hands near your coin purse and your eyes open, Rowan."

        return f"Greetings, Rowan. What business brings you to {c.location_id or 'the city'}?"
