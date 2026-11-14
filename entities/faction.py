"""Faction dataclass matching GDD Section 8 and Section 13 (lines 564-575)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Faction:
    """Political/social faction in Veyr (GDD Section 8 & Section 13 lines 564-575)."""

    # --- GDD Section 13 exact fields & order ---
    id: str
    name: str
    leader_id: str | None = None
    wealth: float = 50.0
    influence: float = 50.0
    military_strength: float = 50.0
    stability: float = 50.0
    territories: list[str] = field(default_factory=list)
    members: list[str] = field(default_factory=list)
    goals: list[dict[str, Any]] = field(default_factory=list)
    relations: dict[str, float] = field(default_factory=dict)
    # --- Additional GDD Sec 8 & Sec 15 SQLite fields ---
    power: float = 50.0
    public_legitimacy: float = 50.0
    goal_summary: str = ""
    methods_summary: str = ""
    methods: list[str] = field(default_factory=list)
    hierarchy: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not str(self.id).strip():
            raise ValueError("Faction.id must be a non-empty string")
        self.id = str(self.id)
        self.name = str(self.name)
        self.wealth = float(self.wealth)
        self.influence = float(self.influence)
        self.military_strength = float(self.military_strength)
        self.stability = float(self.stability)
        self.power = float(self.power)
        self.public_legitimacy = float(self.public_legitimacy)
        self.territories = [str(t) for t in self.territories]
        self.members = [str(m) for m in self.members]
        self.goals = [dict(g) if isinstance(g, dict) else {"type": str(g)} for g in self.goals]
        self.relations = {str(k): float(v) for k, v in self.relations.items()}
        self.methods = [str(m) for m in self.methods]
        self.hierarchy = {str(k): [str(x) for x in v] for k, v in self.hierarchy.items()}

    @property
    def primary_goal(self) -> str:
        return self.goal_summary

    @primary_goal.setter
    def primary_goal(self, value: str) -> None:
        self.goal_summary = str(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "leader_id": self.leader_id,
            "wealth": float(self.wealth),
            "influence": float(self.influence),
            "military_strength": float(self.military_strength),
            "stability": float(self.stability),
            "territories": list(self.territories),
            "members": list(self.members),
            "goals": [dict(g) for g in self.goals],
            "relations": dict(self.relations),
            "power": float(self.power),
            "public_legitimacy": float(self.public_legitimacy),
            "goal_summary": self.goal_summary,
            "methods_summary": self.methods_summary,
            "methods": list(self.methods),
            "hierarchy": {k: list(v) for k, v in self.hierarchy.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Faction:
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            leader_id=data.get("leader_id"),
            wealth=float(data.get("wealth", 50.0)),
            influence=float(data.get("influence", 50.0)),
            military_strength=float(data.get("military_strength", 50.0)),
            stability=float(data.get("stability", 50.0)),
            territories=list(data.get("territories", [])),
            members=list(data.get("members", [])),
            goals=list(data.get("goals", [])),
            relations={str(k): float(v) for k, v in data.get("relations", {}).items()},
            power=float(data.get("power", 50.0)),
            public_legitimacy=float(data.get("public_legitimacy", 50.0)),
            goal_summary=str(data.get("goal_summary", data.get("primary_goal", ""))),
            methods_summary=str(data.get("methods_summary", "")),
            methods=list(data.get("methods", [])),
            hierarchy={str(k): list(v) for k, v in data.get("hierarchy", {}).items()},
        )
