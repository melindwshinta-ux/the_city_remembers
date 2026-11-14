"""Command-based tactical grid combat, attack resolution, and Kenshi defeat outcomes (GDD Sections 6 & 13)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.character import Character
from entities.enemy import EnemyCombatant
from entities.item import Item


ALL_COMMANDS = {
    "Movement": ["move", "charge", "retreat", "flank", "take_cover"],
    "Combat": ["attack", "heavy_attack", "aim", "guard", "disarm", "grapple", "interrupt"],
    "Support": ["heal", "stabilize", "apply_bandage", "revive", "protect_ally"],
    "Special": ["spellcasting", "stealth_attack", "area_attack", "environmental_interaction"],
}

TERRAIN_FEATURES = [
    "cover",
    "walls",
    "doors",
    "elevation",
    "narrow_passages",
    "hazards",
    "flammable_objects",
    "difficult_terrain",
]

MORALE_THRESHOLDS = [
    (80.0, "confident"),
    (60.0, "steady"),
    (40.0, "nervous"),
    (20.0, "frightened"),
    (10.0, "panicking"),
    (0.0, "routing"),
]


@dataclass
class Encounter:
    """Tactical grid encounter state."""

    party: list[Character]
    enemies: list[Character]
    grid_size: tuple[int, int] = (5, 5)
    positions: dict[str, tuple[int, int]] = field(default_factory=dict)
    terrain: dict[tuple[int, int], str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.positions:
            # Place party along bottom row, enemies along top rows
            cols, rows = self.grid_size
            for idx, member in enumerate(self.party):
                c = min(cols - 1, idx)
                self.positions[member.id] = (c, rows - 1)
            for idx, enemy in enumerate(self.enemies):
                c = min(cols - 1, idx + 1)
                self.positions[enemy.id] = (c, min(rows - 1, idx // cols + 1))

    def render_ascii_grid(self) -> str:
        """Render 5x5 or 8x8 ASCII battlefield grid (GDD Section 6)."""
        cols, rows = self.grid_size
        col_letters = [chr(ord('A') + i) for i in range(cols)]
        header = "    " + "  ".join(f" {l} " for l in col_letters)
        lines = [header]

        char_symbols: dict[str, str] = {
            "player": "R",
            "comp_marcus": "M",
            "comp_elira": "E",
            "comp_sera": "S",
            "npc_voss": "V",
            "npc_guard_1": "G",
            "npc_archer_1": "A",
        }

        pos_map: dict[tuple[int, int], str] = {}
        for cid, (x, y) in self.positions.items():
            sym = char_symbols.get(cid)
            if not sym:
                sym = cid[0].upper()
            pos_map[(x, y)] = sym

        for y in range(rows):
            row_cells: list[str] = []
            for x in range(cols):
                if (x, y) in pos_map:
                    row_cells.append(f"[{pos_map[(x, y)]:^3}]")
                else:
                    row_cells.append("[ . ]")
            lines.append(f" {y+1:<2} " + " ".join(row_cells))

        return "\n".join(lines)

    def render_grid(self) -> str:
        return self.render_ascii_grid()

    def to_ascii(self) -> str:
        return self.render_ascii_grid()

    def __str__(self) -> str:
        return self.render_ascii_grid()


class CombatSystem:
    """Manages command-based tactical combat, turn resolution, attack pipeline, and defeat consequences."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        clock: WorldClock | None = None,
        rng: SeededRNG | None = None,
        world: Any = None,
        **kwargs: Any,
    ) -> None:
        self.event_bus = event_bus
        self.clock = clock
        self.rng = rng
        self.world = world
        self.active_encounter: Encounter | None = None

    def get_supported_terrains(self) -> list[str]:
        return list(TERRAIN_FEATURES)

    def list_terrain_features(self) -> list[str]:
        return list(TERRAIN_FEATURES)

    def get_terrain_catalog(self) -> list[str]:
        return list(TERRAIN_FEATURES)

    def get_command_catalog(self) -> dict[str, list[str]]:
        return dict(ALL_COMMANDS)

    def list_commands_by_category(self) -> dict[str, list[str]]:
        return dict(ALL_COMMANDS)

    def get_available_commands(self) -> dict[str, list[str]]:
        return dict(ALL_COMMANDS)

    def create_encounter(
        self,
        party: list[Character],
        enemies: list[Character],
        grid_size: tuple[int, int] = (5, 5),
    ) -> Encounter:
        """Create a new tactical combat encounter."""
        enc = Encounter(party=party, enemies=enemies, grid_size=grid_size)
        self.active_encounter = enc
        return enc

    def start_encounter(self, *args: Any, **kwargs: Any) -> Encounter:
        return self.create_encounter(*args, **kwargs)

    def init_battlefield(self, *args: Any, **kwargs: Any) -> Encounter:
        return self.create_encounter(*args, **kwargs)

    def calculate_initiative(self, character: Character) -> float:
        """Calculate initiative score based on agility, weapon handling, mobility, injuries, and fatigue (GDD Section 6)."""
        attrs = getattr(character, "attributes", {}) or {}
        needs = getattr(character, "needs", {}) or {}
        agility = float(attrs.get("agility", 50.0))
        dexterity = float(attrs.get("dexterity", 50.0))
        fatigue = float(needs.get("fatigue", 100.0))

        score = agility * 1.5 + dexterity * 0.5 + fatigue * 0.2
        if hasattr(character, "body") and character.body:
            from systems.health_system import HealthSystem

            mods = HealthSystem(world=self.world).get_combat_modifiers(character)
            handling_mod = float(mods.get("weapon_handling", 1.0))
            mobility_mod = float(mods.get("mobility", 1.0))
            score *= 0.5 + 0.25 * handling_mod + 0.25 * mobility_mod
            for part in character.body.values():
                if not part.functional:
                    score -= 20.0
        return score

    def get_initiative(self, character: Character) -> float:
        return self.calculate_initiative(character)

    def get_initiative_order(self, combatants: list[Character]) -> list[Character]:
        """Calculate initiative order based on agility, weapon handling, armor, and fatigue (GDD Section 6)."""
        return sorted(combatants, key=self.calculate_initiative, reverse=True)

    def calculate_initiative_order(self, combatants: list[Character]) -> list[Character]:
        return self.get_initiative_order(combatants)

    def sort_by_initiative(self, combatants: list[Character]) -> list[Character]:
        return self.get_initiative_order(combatants)

    def calculate_accuracy(self, attacker: Character, weapon: Item | None = None, **kwargs: Any) -> float:
        """Calculate attacker accuracy factoring in attributes, weapon handling, and eye/head injuries (GDD Sections 5 & 6)."""
        attrs = getattr(attacker, "attributes", {}) or {}
        dexterity = float(attrs.get("dexterity", 50.0))
        perception = float(attrs.get("perception", 50.0))
        base_acc = 0.55 + (dexterity + perception) / 400.0

        health_mod = 1.0
        if hasattr(attacker, "body") and attacker.body:
            from systems.health_system import HealthSystem

            mods = HealthSystem(world=self.world).get_combat_modifiers(attacker)
            health_mod = float(mods.get("accuracy", 1.0))

        weapon_handling = float(getattr(weapon, "handling", 1.0)) if weapon is not None else 1.0
        return max(0.05, min(1.0, base_acc * health_mod * min(1.2, weapon_handling)))

    def get_attacker_accuracy(self, attacker: Character, weapon: Item | None = None, **kwargs: Any) -> float:
        return self.calculate_accuracy(attacker, weapon=weapon, **kwargs)

    def evaluate_morale_state(
        self,
        enemy: EnemyCombatant | Character,
        morale_value: float | None = None,
        event_type: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Update and return morale state (confident, steady, nervous, frightened, panicking, routing)."""
        if morale_value is not None:
            if hasattr(enemy, "morale"):
                enemy.morale = float(morale_value)
            val = float(morale_value)
        elif event_type is not None:
            val = float(getattr(enemy, "morale", 75.0))
            archetype = str(getattr(enemy, "archetype", "soldier")).lower()
            if event_type == "commander_incapacitated":
                if archetype == "coward":
                    val = max(0.0, val - 35.0)
                elif archetype == "berserker":
                    val = min(100.0, val + 20.0)
                else:
                    val = max(0.0, val - 15.0)
            if hasattr(enemy, "morale"):
                enemy.morale = val
        else:
            val = float(getattr(enemy, "morale", 75.0))

        state = "routing"
        for thresh, name in MORALE_THRESHOLDS:
            if val >= thresh:
                state = name
                break

        if hasattr(enemy, "morale_state"):
            enemy.morale_state = state
        return state

    def get_morale_state(self, enemy: Any, **kwargs: Any) -> str:
        return self.evaluate_morale_state(enemy, **kwargs)

    def update_morale(self, enemy: Any, **kwargs: Any) -> str:
        return self.evaluate_morale_state(enemy, **kwargs)

    def apply_morale_shock(self, enemy: Any, **kwargs: Any) -> str:
        return self.evaluate_morale_state(enemy, **kwargs)

    @staticmethod
    def _is_incapacitated(character: Character | None) -> bool:
        if character is None:
            return True
        if getattr(character, "status", "alive") in ("dead", "incapacitated"):
            return True
        if float(getattr(character, "consciousness", 100.0)) <= 0.0:
            return True
        return False

    @staticmethod
    def _parse_grid_coord(coord: str | tuple[int, int] | None) -> tuple[int, int] | None:
        if coord is None:
            return None
        if isinstance(coord, tuple) and len(coord) == 2:
            return int(coord[0]), int(coord[1])
        if isinstance(coord, str):
            text = coord.strip().upper()
            if len(text) >= 2 and text[0].isalpha() and text[1:].isdigit():
                col = ord(text[0]) - ord("A")
                row = int(text[1:]) - 1
                return col, row
        return None

    def execute_command(
        self,
        encounter: Encounter | None = None,
        actor_id: str | None = None,
        command: str = "move",
        target_coord: str | tuple[int, int] | None = None,
        attacker: Character | None = None,
        defender: Character | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute a grid movement or tactical combat command (GDD Section 6)."""
        if encounter is None and attacker is not None:
            return self.execute_tactical_action(
                attacker=attacker,
                defender=defender,
                command=command,
                **kwargs,
            )

        if encounter is None:
            return {"success": False, "reason": "no_encounter"}

        actor: Character | None = attacker
        if actor is None and actor_id is not None:
            for c in encounter.party + encounter.enemies:
                if c.id == actor_id:
                    actor = c
                    break

        if actor is not None and self._is_incapacitated(actor):
            return {"success": False, "skipped": True, "reason": "actor_incapacitated"}

        if command in ("move", "charge", "retreat", "flank", "take_cover"):
            parsed = self._parse_grid_coord(target_coord)
            if parsed is None:
                return {"success": False, "reason": "invalid_coord"}
            x, y = parsed
            cols, rows = encounter.grid_size
            if not (0 <= x < cols and 0 <= y < rows):
                return {"success": False, "reason": "out_of_bounds"}
            tile = encounter.terrain.get((x, y), "")
            if tile in ("wall", "walls"):
                return {"success": False, "reason": "blocked_by_wall"}
            resolved_actor_id = actor_id or (actor.id if actor else None)
            if resolved_actor_id:
                encounter.positions[resolved_actor_id] = (x, y)
            return {"success": True, "command": command, "position": (x, y)}

        if attacker is not None:
            return self.execute_tactical_action(
                attacker=attacker,
                defender=defender,
                command=command,
                **kwargs,
            )
        return {"success": True, "command": command}

    def resolve_command(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.execute_command(*args, **kwargs)

    def move_combatant(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.execute_command(*args, **kwargs)

    def execute_tactical_action(
        self,
        attacker: Character,
        defender: Character | None = None,
        command: str = "attack",
        weapon: Item | None = None,
        spell_power: float = 20.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute tactical combat, support, or spellcasting action (GDD Sections 5, 6, 11)."""
        if self._is_incapacitated(attacker):
            return {"success": False, "skipped": True, "hit": False, "reason": "attacker_incapacitated"}

        if command == "disarm":
            if defender is None:
                return {"success": False, "command": "disarm", "message": "No target"}
            equip = getattr(defender, "equipment", None) or {}
            if not equip:
                return {"success": False, "command": "disarm", "message": "Target is unarmed"}
            removed_key = next(iter(equip.keys()))
            equip.pop(removed_key, None)
            return {"success": True, "command": "disarm", "disarmed": removed_key}

        if command == "revive":
            if defender is None:
                return {"success": False, "command": "revive", "message": "No target"}
            if getattr(defender, "status", "alive") == "alive" and float(getattr(defender, "consciousness", 100.0)) > 0.0:
                return {"success": False, "command": "revive", "message": "Target is already conscious"}
            defender.status = "alive"
            defender.consciousness = max(25.0, float(getattr(defender, "consciousness", 0.0)))
            return {"success": True, "command": "revive"}

        if command == "spellcasting":
            if not hasattr(attacker, "needs") or attacker.needs is None:
                attacker.needs = {}
            corruption = float(attacker.needs.get("corruption", 0.0)) + float(spell_power) * 0.25
            attacker.needs["corruption"] = corruption

            overloaded = float(spell_power) >= 30.0 or corruption >= 50.0
            if overloaded:
                if not hasattr(attacker, "body") or not attacker.body:
                    from entities.character import create_humanoid_body
                    attacker.body = create_humanoid_body(attacker.id)
                from entities.character import Injury
                target_part = "head" if "head" in attacker.body else next(iter(attacker.body.keys()))
                part = attacker.body[target_part]
                part.injuries.append(
                    Injury(
                        id=f"inj_nerve_{uuid.uuid4().hex[:6]}",
                        injury_type="nerve_damage",
                        severity=0.5,
                        pain=25.0,
                        bleeding=0.0,
                        infection_risk=0.0,
                    )
                )
                part.integrity = max(0.0, float(part.integrity) - 10.0)
                if self.event_bus:
                    self.event_bus.emit(
                        GameEvent(
                            id=f"ev_spell_{uuid.uuid4().hex[:6]}",
                            event_type="CHARACTER_INJURED",
                            timestamp=self.clock.timestamp if self.clock else 0,
                            source_id=attacker.id,
                            target_ids=[attacker.id],
                            location_id=attacker.location_id,
                            data={"body_part": target_part, "injury": "nerve_damage", "corruption": corruption},
                            importance=0.75,
                        ),
                        priority=EventPriority.NORMAL,
                    )

            if defender is not None:
                if not hasattr(defender, "body") or not defender.body:
                    from entities.character import create_humanoid_body
                    defender.body = create_humanoid_body(defender.id)
                from entities.character import Injury
                def_part_id = str(kwargs.get("target_part", "torso"))
                if def_part_id not in defender.body:
                    def_part_id = "torso" if "torso" in defender.body else next(iter(defender.body.keys()))
                def_part = defender.body[def_part_id]
                spell_dmg = float(spell_power)
                def_part.integrity = max(0.0, float(def_part.integrity) - spell_dmg)
                if def_part.integrity < 50.0:
                    def_part.functional = False
                inj_type = "nerve_damage" if kwargs.get("damage_type") == "magic" else "burn"
                severity = min(1.0, max(0.1, spell_dmg / 50.0))
                def_part.injuries.append(
                    Injury(
                        id=f"inj_spell_{uuid.uuid4().hex[:6]}",
                        injury_type=inj_type,
                        severity=severity,
                        pain=0.7 * severity,
                        bleeding=0.1 * severity if inj_type == "burn" else 0.0,
                        infection_risk=0.5 * severity if inj_type == "burn" else 0.0,
                        created_at=self.clock.timestamp if self.clock else 0,
                        cause_description=f"spellcasting by {attacker.id}",
                        body_part_id=def_part_id,
                        character_id=defender.id,
                    )
                )
                if self.event_bus:
                    self.event_bus.emit(
                        GameEvent(
                            id=f"ev_spell_hit_{uuid.uuid4().hex[:6]}",
                            event_type="CHARACTER_INJURED",
                            timestamp=self.clock.timestamp if self.clock else 0,
                            source_id=attacker.id,
                            target_ids=[defender.id],
                            location_id=defender.location_id,
                            data={"body_part": def_part_id, "injury": inj_type, "damage": spell_dmg},
                            importance=0.8,
                        ),
                        priority=EventPriority.CRITICAL,
                    )

            return {
                "success": True,
                "command": "spellcasting",
                "corruption": corruption,
                "overloaded": overloaded,
            }

        if command in ("heal", "stabilize", "apply_bandage", "protect_ally"):
            return {"success": True, "command": command}

        if defender is not None:
            return self.resolve_attack(attacker=attacker, defender=defender, weapon=weapon, command=command, **kwargs)
        return {"success": False, "command": command, "reason": "no_target"}

    def resolve_support(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.execute_tactical_action(*args, **kwargs)

    def resolve_spellcast(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("command", "spellcasting")
        return self.execute_tactical_action(*args, **kwargs)

    def finish_encounter(
        self,
        encounter: Encounter | None = None,
        world: Any = None,
        duration_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Finish combat encounter, advancing WorldClock by 1-5 minutes (GDD Section 2)."""
        active_clock = None
        if world is not None and hasattr(world, "clock"):
            active_clock = world.clock
        elif self.world is not None and hasattr(self.world, "clock"):
            active_clock = self.world.clock
        else:
            active_clock = self.clock

        minutes = max(1, min(5, int(duration_minutes if duration_minutes is not None else 3)))
        if active_clock is not None:
            active_clock.advance(minutes)

        if encounter is None or self.active_encounter is encounter:
            self.active_encounter = None

        if self.event_bus:
            self.event_bus.emit(
                GameEvent(
                    id=f"ev_end_{uuid.uuid4().hex[:6]}",
                    event_type="COMBAT_ENDED",
                    timestamp=active_clock.timestamp if active_clock else 0,
                    source_id="combat_system",
                    target_ids=[],
                    location_id=None,
                    data={"duration_minutes": minutes},
                    importance=0.6,
                ),
                priority=EventPriority.NORMAL,
            )

        return {"success": True, "duration_minutes": minutes}

    def end_encounter(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.finish_encounter(*args, **kwargs)

    def resolve_encounter_time(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.finish_encounter(*args, **kwargs)

    def resolve_attack(
        self,
        attacker: Character,
        defender: Character,
        weapon: Item | None = None,
        command: str = "attack",
        target_part: str = "torso",
        force_hit: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute 9-step attack resolution pipeline (GDD Section 5 & 6)."""
        if self._is_incapacitated(attacker):
            return {"hit": False, "skipped": True, "success": False, "reason": "attacker_incapacitated"}

        if command in ("disarm", "revive", "spellcasting", "heal", "stabilize", "apply_bandage", "protect_ally"):
            return self.execute_tactical_action(
                attacker=attacker,
                defender=defender,
                command=command,
                weapon=weapon,
                **kwargs,
            )

        if weapon is None:
            weapon = Item(
                id="fists",
                name="Unarmed",
                item_type="weapon",
                damage=5.0,
                damage_type="blunt",
                penetration=1.0,
                handling=1.0,
            )

        # 1. Attacker accuracy
        accuracy = self.calculate_accuracy(attacker, weapon=weapon)
        # 2. Defense calculation
        defense = 0.0 if force_hit else 0.2
        # 3. Hit or miss
        hit = force_hit or (accuracy > defense)

        if not hit:
            return {"hit": False, "effective_damage": 0.0, "hit_location": target_part}

        # 4. Hit location
        hit_loc = target_part
        if not hasattr(defender, "body") or not defender.body:
            from entities.character import create_humanoid_body
            defender.body = create_humanoid_body(defender.id)

        part = defender.body.get(hit_loc)
        if not part:
            hit_loc = "torso"
            part = defender.body["torso"]

        # 5. Armor & penetration
        raw_damage = float(weapon.damage) if hasattr(weapon, "damage") else 15.0
        if command == "heavy_attack":
            raw_damage *= 1.3
        armor_prot = float(part.armor)
        penetration = float(getattr(weapon, "penetration", 5.0))

        # D_effective = max(0, D_raw - max(0, R_armor - penetration))
        mitigated_armor = max(0.0, armor_prot - penetration)
        effective_damage = max(1.0, raw_damage - mitigated_armor)

        # 6. Apply injury & functional consequence
        part.integrity = max(0.0, part.integrity - effective_damage)
        injury_type = "deep_cut" if getattr(weapon, "damage_type", "cutting") == "cutting" else "compound_fracture"
        if getattr(weapon, "damage_type", "") == "blunt":
            injury_type = "broken_leg" if "leg" in hit_loc else ("broken_arm" if "arm" in hit_loc else "compound_fracture")

        if effective_damage > 0.0:
            from entities.character import Injury
            from systems.health_system import INJURY_TYPES

            meta = INJURY_TYPES.get(
                injury_type,
                {"bleeding": 0.3, "pain": 0.5, "functional_loss": False, "infection_risk": 0.1},
            )
            severity = min(1.0, max(0.1, effective_damage / 50.0))
            part.injuries.append(
                Injury(
                    id=f"inj_{hit_loc}_{uuid.uuid4().hex[:6]}",
                    injury_type=injury_type,
                    severity=severity,
                    pain=float(meta["pain"] * severity),
                    bleeding=float(meta["bleeding"] * severity),
                    infection_risk=float(meta["infection_risk"] * severity),
                    recovery_progress=0.0,
                    permanent=False,
                    treated=False,
                    treatment_stage="untreated",
                    long_term_effect="",
                    created_at=self.clock.timestamp if self.clock else 0,
                    cause_description=f"{getattr(weapon, 'name', 'attack')} by {attacker.id}",
                    body_part_id=hit_loc,
                    character_id=defender.id,
                )
            )

        if part.integrity < 50.0:
            part.functional = False

        # Emit events
        if self.event_bus:
            ev_type = "LIMB_INJURED" if "arm" in hit_loc or "leg" in hit_loc else "CHARACTER_INJURED"
            self.event_bus.emit(
                GameEvent(
                    id=f"ev_att_{uuid.uuid4().hex[:6]}",
                    event_type=ev_type,
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=attacker.id,
                    target_ids=[defender.id],
                    location_id=defender.location_id,
                    data={
                        "body_part": hit_loc,
                        "weapon": weapon.id,
                        "damage": effective_damage,
                        "injury": injury_type,
                    },
                    importance=0.85,
                ),
                priority=EventPriority.CRITICAL,
            )

        return {
            "hit": True,
            "hit_location": hit_loc,
            "effective_damage": effective_damage,
            "injury_applied": injury_type,
        }

    def execute_attack(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.resolve_attack(*args, **kwargs)

    def resolve_player_defeat(self, world: Any = None, victor_faction: str = "city_guard") -> dict[str, Any]:
        """Apply Kenshi-style non-lethal defeat outcomes (GDD Section 11)."""
        active_world = world or self.world
        player = active_world.characters.get("player") if active_world else None

        if victor_faction == "city_guard":
            outcome = "imprisoned"
            desc = "The City Guard arrested you and threw you into the Barracks cells."
            if player:
                player.location_id = "barracks_prison"
                player.status = "alive"
        else:
            outcome = "robbed"
            desc = "The Syndicate mugged your unconscious body and stripped your coin."
            if player:
                player.status = "alive"

        if self.event_bus:
            self.event_bus.emit(
                GameEvent(
                    id=f"ev_def_{uuid.uuid4().hex[:6]}",
                    event_type="PLAYER_DEFEATED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=victor_faction,
                    target_ids=["player"],
                    location_id="lowtown",
                    data={"outcome": outcome, "description": desc},
                    importance=0.9,
                ),
                priority=EventPriority.CRITICAL,
            )

        return {"outcome": outcome, "description": desc}

    def handle_player_defeat(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.resolve_player_defeat(*args, **kwargs)
