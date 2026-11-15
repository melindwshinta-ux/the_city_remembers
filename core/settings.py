"""Global GameSettings persistence, difficulty modifiers, and New Game Setup helpers (GEMINI_PLAN §1.1, §8)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from config import SETTINGS_PATH
from entities.item import InventoryEntry, Item


VALID_DIFFICULTIES: tuple[str, ...] = ("story", "balanced", "gritty", "ironman")
VALID_AUTOSAVE_MODES: tuple[str, ...] = ("daily_and_precombat", "precombat", "off")
VALID_LAYOUT_MODES: tuple[str, ...] = ("auto", "compact", "standard")


@dataclass
class GameSettings:
    """Global player settings persisted to `saves/settings.json`."""

    difficulty: str = "balanced"
    enable_debug_cheat: bool = False
    autosave_mode: str = "daily_and_precombat"
    guided_tutorial_hud: bool = True
    layout_mode: str = "auto"

    def __post_init__(self) -> None:
        diff = str(self.difficulty).strip().lower()
        self.difficulty = diff if diff in VALID_DIFFICULTIES else "balanced"
        self.enable_debug_cheat = bool(self.enable_debug_cheat)
        auto = str(self.autosave_mode).strip().lower()
        self.autosave_mode = auto if auto in VALID_AUTOSAVE_MODES else "daily_and_precombat"
        self.guided_tutorial_hud = bool(self.guided_tutorial_hud)
        layout = str(self.layout_mode).strip().lower()
        self.layout_mode = layout if layout in VALID_LAYOUT_MODES else "auto"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameSettings:
        if not isinstance(data, dict):
            return cls()
        return cls(
            difficulty=data.get("difficulty", "balanced"),
            enable_debug_cheat=bool(data.get("enable_debug_cheat", False)),
            autosave_mode=data.get("autosave_mode", "daily_and_precombat"),
            guided_tutorial_hud=bool(data.get("guided_tutorial_hud", True)),
            layout_mode=data.get("layout_mode", "auto"),
        )


def load_settings(path: Path | str = SETTINGS_PATH) -> GameSettings:
    """Load GameSettings from JSON file, returning safe defaults if missing or invalid."""
    target = Path(path)
    if not target.exists():
        return GameSettings()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return GameSettings.from_dict(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return GameSettings()


def save_settings(settings: GameSettings, path: Path | str = SETTINGS_PATH) -> Path:
    """Persist GameSettings to JSON file and return the written path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(settings.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return target


DIFFICULTY_MODIFIERS: dict[str, dict[str, Any]] = {
    "story": {
        "label": "Story (Forgiving)",
        "skill_bonus": 20.0,
        "incoming_damage_mult": 0.70,
        "healing_mult": 1.50,
        "gold_mult": 1.25,
        "price_mult": 0.90,
        "nemesis_rate_mult": 0.75,
        "infection_risk_mult": 0.50,
        "guard_suspicion_mult": 0.80,
        "organ_trauma_mult": 0.60,
        "ironman": False,
    },
    "balanced": {
        "label": "Balanced (Normal)",
        "skill_bonus": 0.0,
        "incoming_damage_mult": 1.00,
        "healing_mult": 1.00,
        "gold_mult": 1.00,
        "price_mult": 1.00,
        "nemesis_rate_mult": 1.00,
        "infection_risk_mult": 1.00,
        "guard_suspicion_mult": 1.00,
        "organ_trauma_mult": 1.00,
        "ironman": False,
    },
    "gritty": {
        "label": "Gritty (Hard)",
        "skill_bonus": -10.0,
        "incoming_damage_mult": 1.25,
        "healing_mult": 0.80,
        "gold_mult": 0.90,
        "price_mult": 1.20,
        "nemesis_rate_mult": 1.35,
        "infection_risk_mult": 1.25,
        "guard_suspicion_mult": 1.25,
        "organ_trauma_mult": 1.15,
        "ironman": False,
    },
    "ironman": {
        "label": "Ironman Veyr (Brutal)",
        "skill_bonus": -10.0,
        "incoming_damage_mult": 1.25,
        "healing_mult": 0.80,
        "gold_mult": 0.90,
        "price_mult": 1.20,
        "nemesis_rate_mult": 1.35,
        "infection_risk_mult": 1.35,
        "guard_suspicion_mult": 1.25,
        "organ_trauma_mult": 1.50,
        "ironman": True,
    },
}


def get_difficulty_modifiers(difficulty: str) -> dict[str, Any]:
    """Return a copy of the modifier dictionary for `difficulty` (defaults to balanced)."""
    key = str(difficulty).strip().lower()
    return dict(DIFFICULTY_MODIFIERS.get(key, DIFFICULTY_MODIFIERS["balanced"]))


BACKGROUNDS: dict[str, dict[str, Any]] = {
    "watch_veteran": {
        "name": "Discharged Watch Veteran",
        "epithet": "Ex-Watchman",
        "skills": {"swordsmanship": 12.0, "discipline": 15.0},
        "attributes": {},
        "faction_rep": {"city_guard": 15.0},
        "items": [],
    },
    "dockside_smuggler": {
        "name": "Dockside Smuggler",
        "epithet": "Dockside Smuggler",
        "skills": {"stealth": 15.0, "deception": 15.0},
        "attributes": {},
        "faction_rep": {"lowtown_syndicate": 15.0},
        "items": [],
    },
    "noble_scion": {
        "name": "Disgraced Noble Scion",
        "epithet": "Disgraced Scion",
        "skills": {"persuasion": 15.0, "leadership": 15.0},
        "attributes": {},
        "faction_rep": {"noble_houses": 15.0},
        "items": [],
    },
    "field_chirurgeon": {
        "name": "Field Chirurgeon",
        "epithet": "Field Chirurgeon",
        "skills": {"medicine": 20.0},
        "attributes": {"intelligence": 15},
        "faction_rep": {},
        "items": [
            {
                "id": "surgeons_kit",
                "name": "Surgeon's Kit",
                "item_type": "medicine",
                "value": 45.0,
                "properties": {"healing_bonus": 20, "supports_surgery": True},
            }
        ],
    },
}


KEEPSAKES: dict[str, dict[str, Any]] = {
    "coin_purse": {
        "name": "Heavy Coin Purse",
        "gold_bonus": 100.0,
        "faction_rep": {},
        "items": [],
        "equip_weapon": False,
    },
    "steel_longsword": {
        "name": "Fine Steel Longsword",
        "gold_bonus": 0.0,
        "faction_rep": {},
        "items": [
            {
                "id": "fine_steel_longsword",
                "name": "Fine Steel Longsword",
                "item_type": "weapon",
                "damage": 25.0,
                "damage_type": "cutting",
                "penetration": 9.0,
                "handling": 1.1,
                "value": 75.0,
            }
        ],
        "equip_weapon": True,
    },
    "guild_seal": {
        "name": "Forged Guild Seal",
        "gold_bonus": 0.0,
        "faction_rep": {"merchant_consortium": 15.0, "city_guard": 10.0},
        "items": [
            {
                "id": "forged_guild_seal",
                "name": "Forged Guild Seal",
                "item_type": "misc",
                "value": 30.0,
                "properties": {"social_leverage": True},
            }
        ],
        "equip_weapon": False,
    },
    "chirurgeon_satchel": {
        "name": "Chirurgeon's Satchel",
        "gold_bonus": 0.0,
        "faction_rep": {},
        "items": [
            {
                "id": "linen_bandage",
                "name": "Clean Linen Bandages",
                "item_type": "medicine",
                "value": 12.0,
                "properties": {"stops_bleeding": True, "quantity": 3},
                "quantity": 3,
            },
            {
                "id": "healing_tonic",
                "name": "Herbal Healing Tonic",
                "item_type": "consumable",
                "value": 20.0,
                "properties": {"restore_consciousness": 25.0},
                "quantity": 2,
            },
        ],
        "equip_weapon": False,
    },
}


def _grant_item_to_player(world: Any, item_spec: dict[str, Any], equip_weapon: bool = False) -> None:
    item_id = str(item_spec["id"])
    qty = int(item_spec.get("quantity", 1))
    if item_id not in world.items:
        world.items[item_id] = Item(
            id=item_id,
            name=str(item_spec["name"]),
            item_type=str(item_spec.get("item_type", "misc")),
            damage=float(item_spec.get("damage", 0.0)),
            damage_type=str(item_spec.get("damage_type", "cutting")),
            penetration=float(item_spec.get("penetration", 0.0)),
            handling=float(item_spec.get("handling", 1.0)),
            value=float(item_spec.get("value", 10.0)),
            properties=dict(item_spec.get("properties", {})),
        )

    player = getattr(world, "player", None)
    if player is not None:
        for _ in range(qty):
            if item_id not in player.inventory or qty > 1:
                player.inventory.append(item_id)
        if equip_weapon:
            player.equipment["weapon"] = item_id

        inv_list = world.inventories.setdefault(player.id, [])
        existing = next((e for e in inv_list if e.item_id == item_id), None)
        if existing is not None:
            existing.quantity += qty
            if equip_weapon:
                existing.equipped = True
                existing.slot = "weapon"
        else:
            inv_list.append(
                InventoryEntry(
                    character_id=player.id,
                    item_id=item_id,
                    quantity=qty,
                    equipped=bool(equip_weapon),
                    slot="weapon" if equip_weapon else None,
                )
            )


def apply_new_game_setup(
    world: Any,
    difficulty: str = "balanced",
    background: str = "watch_veteran",
    keepsake: str = "coin_purse",
    skip_prologue: bool = False,
) -> dict[str, Any]:
    """Apply New Game difficulty, background, keepsake, and prologue choice onto `world`."""
    diff_key = str(difficulty or "balanced").strip().lower()
    if diff_key not in DIFFICULTY_MODIFIERS:
        diff_key = "balanced"

    bg_key = str(background or "watch_veteran").strip().lower()
    if bg_key not in BACKGROUNDS:
        bg_key = "watch_veteran"

    ks_key = str(keepsake or "coin_purse").strip().lower()
    if ks_key not in KEEPSAKES:
        ks_key = "coin_purse"

    mods = DIFFICULTY_MODIFIERS[diff_key]
    world.flags["difficulty"] = diff_key
    world.flags["ironman"] = bool(mods["ironman"])
    world.flags["background"] = bg_key
    world.flags["keepsake"] = ks_key

    already_applied = bool(world.flags.get("new_game_setup_applied", False))
    player = getattr(world, "player", None)

    if not already_applied:
        bg_spec = BACKGROUNDS[bg_key]
        ks_spec = KEEPSAKES[ks_key]

        world.flags.setdefault("epithet", bg_spec["epithet"])

        if player is not None:
            for sk, bonus in bg_spec["skills"].items():
                current = float(player.skills.get(sk, 0.0))
                player.skills[sk] = min(100.0, current + float(bonus))
            for attr, bonus in bg_spec["attributes"].items():
                current = float(player.attributes.get(attr, 50.0))
                player.attributes[attr] = min(100.0, current + float(bonus))
            if ks_spec["gold_bonus"]:
                current_gold = float(player.needs.get("wealth", 0.0))
                player.needs["wealth"] = current_gold + float(ks_spec["gold_bonus"])

        fac_rep = world.reputation.setdefault("faction", {})
        for fid, delta in bg_spec["faction_rep"].items():
            fac_rep[fid] = float(fac_rep.get(fid, 0.0)) + float(delta)
        for fid, delta in ks_spec["faction_rep"].items():
            fac_rep[fid] = float(fac_rep.get(fid, 0.0)) + float(delta)

        for item_spec in bg_spec["items"]:
            _grant_item_to_player(world, item_spec, equip_weapon=False)
        for item_spec in ks_spec["items"]:
            _grant_item_to_player(world, item_spec, equip_weapon=bool(ks_spec.get("equip_weapon", False)))

        world.flags["new_game_setup_applied"] = True

    if skip_prologue:
        if hasattr(world, "clock") and hasattr(world.clock, "complete_prologue"):
            world.clock.complete_prologue()
        p_flag = world.flags.get("prologue")
        if isinstance(p_flag, dict):
            p_flag["active"] = False
            p_flag["completed"] = True
            p_flag["skipped"] = True
        else:
            world.flags["prologue"] = {
                "active": False,
                "completed": True,
                "skipped": True,
                "step": 3,
                "choices_made": {},
                "applied_effects": [],
            }

    return {
        "difficulty": diff_key,
        "ironman": bool(mods["ironman"]),
        "background": bg_key,
        "keepsake": ks_key,
        "skip_prologue": bool(skip_prologue),
        "modifiers": dict(mods),
    }
