"""Item and InventoryEntry dataclasses for weapons, localized armor, medicine, prosthetics, and consumables."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Item:
    """Equipment, weapon, localized armor, medicine, prosthetic, or consumable definition."""

    id: str
    name: str
    item_type: str = "misc"  # weapon, armor, medicine, prosthetic, consumable, quest_item, misc
    weight: float = 1.0
    value: float = 10.0
    damage: float = 0.0
    damage_type: str = "cutting"  # cutting, piercing, blunt, fire, poison, magic
    penetration: float = 0.0
    handling: float = 1.0
    accuracy_mod: float = 0.0
    armor_class: str | None = None  # padded_cloth, leather, chainmail, scale, plate
    armor_protection: float = 0.0
    covered_parts: list[str] = field(default_factory=list)
    protection: dict[str, float] = field(default_factory=dict)
    weaknesses: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    category: str = ""
    resistance: dict[str, float] = field(default_factory=dict)
    effects: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not str(self.id).strip():
            raise ValueError("Item.id must be a non-empty string")
        self.id = str(self.id)
        self.name = str(self.name)
        if self.category and self.item_type == "misc":
            self.item_type = str(self.category)
        elif not self.category:
            self.category = str(self.item_type)
        self.weight = float(self.weight)
        self.value = float(self.value)
        self.damage = float(self.damage)
        self.penetration = float(self.penetration)
        self.handling = float(self.handling)
        self.accuracy_mod = float(self.accuracy_mod)
        self.armor_protection = float(self.armor_protection)
        self.covered_parts = [str(p) for p in self.covered_parts]
        self.weaknesses = [str(w) for w in self.weaknesses]
        if self.resistance and not self.protection:
            self.protection = {str(k): float(v) for k, v in self.resistance.items()}
        elif self.protection and not self.resistance:
            self.resistance = {str(k): float(v) for k, v in self.protection.items()}
        else:
            self.protection = {str(k): float(v) for k, v in self.protection.items()}
            self.resistance = {str(k): float(v) for k, v in self.resistance.items()}
        if self.effects and not self.properties:
            self.properties = dict(self.effects)
        elif self.properties and not self.effects:
            self.effects = dict(self.properties)
        else:
            self.properties = dict(self.properties)
            self.effects = dict(self.effects)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "item_type": self.item_type,
            "category": self.category,
            "weight": float(self.weight),
            "value": float(self.value),
            "damage": float(self.damage),
            "damage_type": self.damage_type,
            "penetration": float(self.penetration),
            "handling": float(self.handling),
            "accuracy_mod": float(self.accuracy_mod),
            "armor_class": self.armor_class,
            "armor_protection": float(self.armor_protection),
            "covered_parts": list(self.covered_parts),
            "protection": dict(self.protection),
            "resistance": dict(self.resistance),
            "weaknesses": list(self.weaknesses),
            "properties": dict(self.properties),
            "effects": dict(self.effects),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Item:
        item_type = str(data.get("item_type", data.get("category", "misc")))
        protection = dict(data.get("protection", data.get("resistance", {})))
        properties = dict(data.get("properties", data.get("effects", {})))
        raw_ac = data.get("armor_class")
        armor_class = str(raw_ac) if raw_ac else None
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            item_type=item_type,
            weight=float(data.get("weight", 1.0)),
            value=float(data.get("value", 10.0)),
            damage=float(data.get("damage", 0.0)),
            damage_type=str(data.get("damage_type", "cutting")),
            penetration=float(data.get("penetration", 0.0)),
            handling=float(data.get("handling", 1.0)),
            accuracy_mod=float(data.get("accuracy_mod", 0.0)),
            armor_class=armor_class,
            armor_protection=float(data.get("armor_protection", 0.0)),
            covered_parts=list(data.get("covered_parts", [])),
            protection=protection,
            weaknesses=list(data.get("weaknesses", [])),
            properties=properties,
            category=item_type,
            resistance=dict(protection),
            effects=dict(properties),
        )


@dataclass
class InventoryEntry:
    """Character inventory row linking a character to an item definition and quantity."""

    character_id: str
    item_id: str
    quantity: int = 1
    equipped: bool = False
    slot: str | None = None
    id: int | str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.character_id = str(self.character_id)
        self.item_id = str(self.item_id)
        self.quantity = int(self.quantity)
        self.equipped = bool(self.equipped)
        self.metadata = dict(self.metadata)

    @property
    def equipped_slot(self) -> str | None:
        return self.slot

    @equipped_slot.setter
    def equipped_slot(self, value: str | None) -> None:
        self.slot = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "character_id": self.character_id,
            "item_id": self.item_id,
            "quantity": int(self.quantity),
            "equipped": bool(self.equipped),
            "slot": self.slot,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InventoryEntry:
        slot = data.get("slot", data.get("equipped_slot"))
        return cls(
            character_id=str(data["character_id"]),
            item_id=str(data["item_id"]),
            quantity=int(data.get("quantity", 1)),
            equipped=bool(data.get("equipped", False)),
            slot=str(slot) if slot is not None else None,
            id=data.get("id"),
            metadata=dict(data.get("metadata", {})),
        )
