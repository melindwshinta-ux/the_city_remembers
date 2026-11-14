"""Equipment, localized armor coverage, damage types, prosthetics, and crafting (GDD Sections 5, 11, 13)."""

from __future__ import annotations

import uuid
from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.character import Character
from entities.item import Item


CRAFTING_RECIPES = {
    "field_bandage": {
        "name": "Field Bandage",
        "item_type": "medicine",
        "value": 5.0,
        "min_skill": 5.0,
        "cost": 2.0,
        "properties": {"heals_bleeding": True},
    },
    "iron_longsword": {
        "name": "Iron Longsword",
        "item_type": "weapon",
        "damage": 18.0,
        "damage_type": "cutting",
        "penetration": 6.0,
        "handling": 1.0,
        "value": 40.0,
        "min_skill": 20.0,
        "cost": 15.0,
    },
    "iron_mace": {
        "name": "Iron Mace",
        "item_type": "weapon",
        "damage": 16.0,
        "damage_type": "blunt",
        "penetration": 12.0,
        "handling": 0.9,
        "value": 35.0,
        "min_skill": 20.0,
        "cost": 12.0,
    },
    "leather_jerkin": {
        "name": "Leather Jerkin",
        "item_type": "armor",
        "armor_class": "leather",
        "armor_protection": 9.0,
        "covered_parts": ["torso"],
        "weaknesses": ["blunt"],
        "value": 30.0,
        "min_skill": 15.0,
        "cost": 10.0,
    },
}


class EquipmentSystem:
    """Manages armor coverage, weapon profiles, prosthetics, and crafting (GDD Sections 5, 11)."""

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
        self._character_gear: dict[str, dict[str, Item]] = {}
        self._active_weapons: dict[str, Item] = {}

    def _has_nonfunctional_arm(self, character: Character) -> bool:
        """Return True if either arm or hand subpart in character.body is non-functional."""
        if not getattr(character, "body", None):
            return False
        for part_id in ("left_arm", "right_arm", "left_hand", "right_hand", "left_forearm", "right_forearm"):
            part = character.body.get(part_id)
            if part is not None and not getattr(part, "functional", True):
                return True
        return False

    def equip_item(self, character: Character, item: Item) -> bool:
        """Equip weapon, armor piece, or prosthetic item onto character."""
        cid = character.id
        if cid not in self._character_gear:
            self._character_gear[cid] = {}

        if item.item_type == "armor":
            if character.body:
                if not item.covered_parts or any(p not in character.body for p in item.covered_parts):
                    return False

            # Remove existing armor on overlapping parts
            for prev_item in list(self._character_gear[cid].values()):
                if prev_item.item_type == "armor" and any(p in prev_item.covered_parts for p in item.covered_parts):
                    self.unequip_item(character, prev_item.id)

            self._character_gear[cid][item.id] = item
            # Update body parts
            if character.body:
                for part_id in item.covered_parts:
                    if part_id in character.body:
                        character.body[part_id].armor = float(item.armor_protection)

        elif item.item_type == "weapon":
            props = getattr(item, "properties", {}) or {}
            if (props.get("two_handed") or props.get("dual_wield")) and self._has_nonfunctional_arm(character):
                return False

            self._character_gear[cid][item.id] = item
            self._active_weapons[cid] = item

        elif item.item_type == "prosthetic":
            return self.fit_prosthetic(character, item)

        return True

    def equip(self, character: Character, item: Item) -> bool:
        return self.equip_item(character, item)

    def unequip_item(self, character: Character, item_id: str) -> Item | None:
        """Unequip item and reset armor on affected body parts."""
        cid = character.id
        gear = self._character_gear.get(cid, {})
        item = gear.pop(item_id, None)
        if not item:
            return None

        if item.item_type == "armor" and character.body:
            for part_id in item.covered_parts:
                if part_id in character.body:
                    # Check if another equipped item covers this part
                    other_armor = 0.0
                    for remaining in gear.values():
                        if remaining.item_type == "armor" and part_id in remaining.covered_parts:
                            other_armor = max(other_armor, float(remaining.armor_protection))
                    character.body[part_id].armor = other_armor

        if self._active_weapons.get(cid) and self._active_weapons[cid].id == item_id:
            del self._active_weapons[cid]

        return item

    def unequip(self, character: Character, item_id: str) -> Item | None:
        return self.unequip_item(character, item_id)

    def fit_prosthetic(
        self,
        character: Character,
        prosthetic_item: Item,
        body_part: str | None = None,
    ) -> bool:
        """Fit prosthetic onto amputated or permanently damaged limb, restoring functional=True (GDD Section 5)."""
        target = body_part
        if not target:
            if prosthetic_item.covered_parts:
                target = prosthetic_item.covered_parts[0]
            elif hasattr(prosthetic_item, "properties") and "target_part" in prosthetic_item.properties:
                target = prosthetic_item.properties["target_part"]
            else:
                target = "left_arm"

        if character.body and target in character.body:
            part = character.body[target]
            has_amputation_or_perm = any(
                getattr(inj, "injury_type", "") == "amputation" or getattr(inj, "permanent", False)
                for inj in getattr(part, "injuries", [])
            )
            needs_prosthetic = (
                not getattr(part, "functional", True)
                or float(getattr(part, "integrity", 100.0)) <= 20.0
                or has_amputation_or_perm
            )
            if not needs_prosthetic:
                return False

            part.functional = True
            part.prosthetic_id = prosthetic_item.id
            part.integrity = 80.0
            if cid := character.id:
                if cid not in self._character_gear:
                    self._character_gear[cid] = {}
                self._character_gear[cid][prosthetic_item.id] = prosthetic_item

            if self.event_bus:
                self.event_bus.emit(
                    GameEvent(
                        id=f"ev_pros_{uuid.uuid4().hex[:6]}",
                        event_type="PROSTHETIC_FITTED",
                        timestamp=self.clock.timestamp if self.clock else 0,
                        source_id=None,
                        target_ids=[character.id],
                        location_id=character.location_id,
                        data={"body_part": target, "prosthetic_id": prosthetic_item.id},
                        importance=0.7,
                    ),
                    priority=EventPriority.NORMAL,
                )
            return True
        return False

    def equip_prosthetic(self, character: Character, prosthetic_item: Item, **kwargs: Any) -> bool:
        return self.fit_prosthetic(character, prosthetic_item, **kwargs)

    def get_active_weapon_profile(self, character: Character) -> Item:
        """Return currently equipped active weapon or default fists, adjusted for arm injuries."""
        cid = character.id
        base_weapon = self._active_weapons.get(cid) or Item(
            id="fists",
            name="Unarmed",
            item_type="weapon",
            damage=5.0,
            damage_type="blunt",
            penetration=1.0,
            handling=1.0,
        )
        if not getattr(character, "body", None):
            return base_weapon

        handling_mult = 1.0
        for part_id in ("left_arm", "right_arm"):
            part = character.body.get(part_id)
            if part is not None:
                if not getattr(part, "functional", True):
                    handling_mult = min(handling_mult, 0.5)
                elif float(getattr(part, "integrity", 100.0)) < 100.0:
                    handling_mult = min(handling_mult, max(0.4, float(part.integrity) / 100.0))

        if handling_mult >= 1.0:
            return base_weapon

        adjusted = Item.from_dict(base_weapon.to_dict())
        adjusted.handling = round(float(base_weapon.handling) * handling_mult, 4)
        return adjusted

    def get_equipped_weapon(self, character: Character) -> Item:
        return self.get_active_weapon_profile(character)

    def get_weapon_stats(self, character: Character) -> Item:
        return self.get_active_weapon_profile(character)

    def calculate_armor_mitigation(
        self,
        armor_item: Item,
        damage_type: str,
        raw_damage: float,
    ) -> dict[str, float]:
        """Calculate damage after armor mitigation and material weaknesses (GDD Section 5)."""
        protection = float(getattr(armor_item, "armor_protection", 0.0))
        weaknesses = getattr(armor_item, "weaknesses", []) or []

        # Check weakness
        multiplier = 1.0
        if damage_type in weaknesses:
            multiplier = 0.5  # armor only half as effective against direct weakness
        elif damage_type == "blunt" and getattr(armor_item, "armor_class", "") in ("chainmail", "plate"):
            multiplier = 0.7  # blunt trauma transfers through metal

        effective_protection = protection * multiplier
        effective_damage = max(0.0, raw_damage - effective_protection)

        return {
            "raw_damage": raw_damage,
            "effective_protection": effective_protection,
            "effective_damage": effective_damage,
        }

    def resolve_armor_damage(self, armor_item: Item, damage_type: str, raw_damage: float) -> dict[str, float]:
        return self.calculate_armor_mitigation(armor_item, damage_type, raw_damage)

    def compute_effective_damage(self, armor_item: Item, damage_type: str, raw_damage: float) -> dict[str, float]:
        return self.calculate_armor_mitigation(armor_item, damage_type, raw_damage)

    def craft_item(self, character: Character, recipe_name: str) -> Item | None:
        """Craft an item from recipe (GDD Section 11)."""
        recipe = CRAFTING_RECIPES.get(recipe_name)
        if not recipe:
            return None

        min_skill = float(recipe.get("min_skill", 0.0))
        cost = float(recipe.get("cost", 0.0))
        char_skill = float(getattr(character, "skills", {}).get("crafting", 0.0))
        char_wealth = float(getattr(character, "needs", {}).get("wealth", 0.0))
        if char_skill < min_skill or char_wealth < cost:
            return None

        if cost > 0.0 and hasattr(character, "needs"):
            character.needs["wealth"] = max(0.0, char_wealth - cost)

        item = Item(
            id=f"crafted_{recipe_name}_{uuid.uuid4().hex[:6]}",
            name=recipe["name"],
            item_type=recipe["item_type"],
            armor_class=recipe.get("armor_class"),
            armor_protection=recipe.get("armor_protection", 0.0),
            damage=recipe.get("damage", 0.0),
            damage_type=recipe.get("damage_type"),
            penetration=recipe.get("penetration", 0.0),
            handling=recipe.get("handling", 1.0),
            covered_parts=recipe.get("covered_parts", []),
            weaknesses=recipe.get("weaknesses", []),
            properties=recipe.get("properties", {}),
            value=recipe.get("value", 10.0),
        )
        return item

    def craft(self, character: Character, recipe_name: str) -> Item | None:
        return self.craft_item(character, recipe_name)
