"""District and Location dataclasses for the city of Veyr (GDD Sections 2 & 8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Location:
    """Discrete navigable location within a city district."""

    id: str
    name: str
    district_id: str = "lowtown"
    description: str = ""
    connected_locations: list[str] = field(default_factory=list)
    terrain_features: list[str] = field(default_factory=list)
    npcs_present: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id or not str(self.id).strip():
            raise ValueError("Location.id must be a non-empty string")
        self.id = str(self.id)
        self.name = str(self.name)
        self.district_id = str(self.district_id)
        self.connected_locations = [str(loc) for loc in self.connected_locations]
        self.terrain_features = [str(tf) for tf in self.terrain_features]
        self.npcs_present = [str(npc) for npc in self.npcs_present]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "district_id": self.district_id,
            "description": self.description,
            "connected_locations": list(self.connected_locations),
            "terrain_features": list(self.terrain_features),
            "npcs_present": list(self.npcs_present),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Location:
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            district_id=str(data.get("district_id", "lowtown")),
            description=str(data.get("description", "")),
            connected_locations=list(data.get("connected_locations", [])),
            terrain_features=list(data.get("terrain_features", [])),
            npcs_present=list(data.get("npcs_present", [])),
        )


@dataclass
class District:
    """City district tracking all 10 GDD Section 2 metrics and normalized faction influence."""

    id: str
    name: str
    characteristics: str = ""
    major_conflict: str = ""
    # --- All 10 GDD Section 2 tracked metrics (lines 84-86) ---
    population: int = 5000
    wealth: float = 50.0
    security: float = 50.0
    unrest: float = 20.0
    faction_influence: dict[str, float] = field(default_factory=dict)
    food_supply: float = 80.0
    employment: float = 70.0
    crime: float = 30.0
    public_opinion: float = 50.0
    infrastructure_condition: float = 70.0
    # --- Navigable locations in district ---
    locations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id or not str(self.id).strip():
            raise ValueError("District.id must be a non-empty string")
        self.id = str(self.id)
        self.name = str(self.name)
        self.population = int(self.population)
        self.wealth = float(self.wealth)
        self.security = float(self.security)
        self.unrest = float(self.unrest)
        self.food_supply = float(self.food_supply)
        self.employment = float(self.employment)
        self.crime = float(self.crime)
        self.public_opinion = float(self.public_opinion)
        self.infrastructure_condition = float(self.infrastructure_condition)
        self.faction_influence = {str(k): float(v) for k, v in self.faction_influence.items()}
        self.locations = [
            loc.id if isinstance(loc, Location) else str(loc)
            for loc in self.locations
        ]

    def normalize_influence(self) -> dict[str, float]:
        """Ensure faction_influence percentages are non-negative and sum to 100.0 (GDD Section 8)."""
        if not self.faction_influence:
            return self.faction_influence
        clamped = {k: max(0.0, float(v)) for k, v in self.faction_influence.items()}
        total = sum(clamped.values())
        if total <= 0.0:
            equal_share = round(100.0 / len(clamped), 4)
            normalized = {k: equal_share for k in clamped}
        else:
            scale = 100.0 / total
            normalized = {k: round(v * scale, 4) for k, v in clamped.items()}
        keys = sorted(normalized.keys(), key=lambda k: (-normalized[k], k))
        residual = round(100.0 - sum(normalized.values()), 4)
        normalized[keys[0]] = round(normalized[keys[0]] + residual, 4)
        self.faction_influence = normalized
        return self.faction_influence

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "characteristics": self.characteristics,
            "major_conflict": self.major_conflict,
            "population": int(self.population),
            "wealth": float(self.wealth),
            "security": float(self.security),
            "unrest": float(self.unrest),
            "faction_influence": dict(self.faction_influence),
            "food_supply": float(self.food_supply),
            "employment": float(self.employment),
            "crime": float(self.crime),
            "public_opinion": float(self.public_opinion),
            "infrastructure_condition": float(self.infrastructure_condition),
            "locations": list(self.locations),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> District:
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            characteristics=str(data.get("characteristics", "")),
            major_conflict=str(data.get("major_conflict", "")),
            population=int(data.get("population", 5000)),
            wealth=float(data.get("wealth", 50.0)),
            security=float(data.get("security", 50.0)),
            unrest=float(data.get("unrest", 20.0)),
            faction_influence={str(k): float(v) for k, v in data.get("faction_influence", {}).items()},
            food_supply=float(data.get("food_supply", 80.0)),
            employment=float(data.get("employment", 70.0)),
            crime=float(data.get("crime", 30.0)),
            public_opinion=float(data.get("public_opinion", 50.0)),
            infrastructure_condition=float(data.get("infrastructure_condition", 70.0)),
            locations=list(data.get("locations", [])),
        )
