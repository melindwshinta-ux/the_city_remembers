"""CompanionProfile / Companion dataclass and canonical companion templates (GDD Section 9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompanionProfile:
    """Companion state and progression tracks (GDD Section 9)."""

    character_id: str
    name: str = ""
    title: str = ""
    role: str = ""
    friendship: float = 0.0
    rivalry: float = 0.0
    approval: float = 0.0
    loyalty_conditions: list[str] = field(default_factory=list)
    breaking_points: list[str] = field(default_factory=list)
    personal_quest_id: str | None = None
    faction_opinions: dict[str, float] = field(default_factory=dict)
    in_party: bool = True
    independent_activity: str = "following_player"
    conflict_description: str = ""

    def __post_init__(self) -> None:
        if not self.character_id or not str(self.character_id).strip():
            raise ValueError("CompanionProfile.character_id must be a non-empty string")
        self.character_id = str(self.character_id)
        self.friendship = float(self.friendship)
        self.rivalry = float(self.rivalry)
        self.approval = float(self.approval)
        self.in_party = bool(self.in_party)
        self.loyalty_conditions = [str(c) for c in self.loyalty_conditions]
        self.breaking_points = [str(b) for b in self.breaking_points]
        self.faction_opinions = {str(k): float(v) for k, v in self.faction_opinions.items()}

    @property
    def id(self) -> str:
        return self.character_id

    @property
    def current_activity(self) -> str:
        return self.independent_activity

    @current_activity.setter
    def current_activity(self, value: str) -> None:
        self.independent_activity = str(value)

    @property
    def archetype_title(self) -> str:
        return self.title

    @archetype_title.setter
    def archetype_title(self, value: str) -> None:
        self.title = str(value)

    @property
    def personal_conflict(self) -> str:
        return self.conflict_description

    @personal_conflict.setter
    def personal_conflict(self, value: str) -> None:
        self.conflict_description = str(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "name": self.name,
            "title": self.title,
            "role": self.role,
            "friendship": float(self.friendship),
            "rivalry": float(self.rivalry),
            "approval": float(self.approval),
            "loyalty_conditions": list(self.loyalty_conditions),
            "breaking_points": list(self.breaking_points),
            "personal_quest_id": self.personal_quest_id,
            "faction_opinions": dict(self.faction_opinions),
            "in_party": bool(self.in_party),
            "independent_activity": self.independent_activity,
            "conflict_description": self.conflict_description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompanionProfile:
        return cls(
            character_id=str(data.get("character_id", data.get("id", ""))),
            name=str(data.get("name", "")),
            title=str(data.get("title", data.get("archetype_title", ""))),
            role=str(data.get("role", "")),
            friendship=float(data.get("friendship", 0.0)),
            rivalry=float(data.get("rivalry", 0.0)),
            approval=float(data.get("approval", 0.0)),
            loyalty_conditions=list(data.get("loyalty_conditions", [])),
            breaking_points=list(data.get("breaking_points", [])),
            personal_quest_id=data.get("personal_quest_id"),
            faction_opinions={str(k): float(v) for k, v in data.get("faction_opinions", {}).items()},
            in_party=bool(data.get("in_party", True)),
            independent_activity=str(
                data.get("independent_activity", data.get("current_activity", "following_player"))
            ),
            conflict_description=str(
                data.get("conflict_description", data.get("personal_conflict", ""))
            ),
        )


Companion = CompanionProfile

# Canonical GDD Section 9 Companions
CANONICAL_COMPANIONS: dict[str, dict[str, Any]] = {
    "comp_marcus": {
        "character_id": "comp_marcus",
        "name": "Marcus",
        "title": "The Veteran",
        "role": "Tank/frontline warrior",
        "friendship": 40.0,
        "rivalry": 10.0,
        "loyalty_conditions": ["uphold_civic_order", "protect_innocents", "fair_trial_for_guards"],
        "breaking_points": ["abandoned_in_combat", "massacre_city_guard"],
        "personal_quest_id": "quest_marcus_badge",
        "faction_opinions": {"city_guard": 55.0, "lowtown_syndicate": -60.0},
        "in_party": True,
        "independent_activity": "patrolling_barracks_perimeter",
        "conflict_description": (
            "Believes order matters more than freedom. Must decide whether to return "
            "to the institution that betrayed him."
        ),
    },
    "comp_elira": {
        "character_id": "comp_elira",
        "name": "Elira",
        "title": "The Heretic",
        "role": "Mage/support",
        "friendship": 25.0,
        "rivalry": 20.0,
        "loyalty_conditions": ["oppose_magical_censorship", "share_arcane_research"],
        "breaking_points": ["surrender_mages_to_church", "destroy_forbidden_archives"],
        "personal_quest_id": "quest_elira_sanctum",
        "faction_opinions": {"independent_mages": 80.0, "ashen_church": -75.0, "city_guard": -25.0},
        "in_party": False,
        "independent_activity": "researching_old_quarter_ruins",
        "conflict_description": (
            "Believes magic should be unrestricted. Her pursuit of freedom risks making "
            "her like the people she hates."
        ),
    },
    "comp_sera": {
        "character_id": "comp_sera",
        "name": "Sera",
        "title": "The Survivor",
        "role": "Rogue/assassin",
        "friendship": 50.0,
        "rivalry": 15.0,
        "loyalty_conditions": ["never_snitch_to_guard", "protect_lowtown_urchins"],
        "breaking_points": ["sell_companion_to_authorities", "betray_lowtown_refugees"],
        "personal_quest_id": "quest_sera_ledger",
        "faction_opinions": {"lowtown_syndicate": 20.0, "city_guard": -65.0, "noble_houses": -70.0},
        "in_party": True,
        "independent_activity": "gathering_lowtown_rumors",
        "conflict_description": (
            "Trust is dangerous. Must choose between escaping her past and controlling it."
        ),
    },
    "comp_tomas": {
        "character_id": "comp_tomas",
        "name": "Tomas",
        "title": "The Believer",
        "role": "Healer/scholar",
        "friendship": 35.0,
        "rivalry": 5.0,
        "loyalty_conditions": ["heal_the_wounded", "expose_church_hypocrisy_peacefully"],
        "breaking_points": ["execute_helpless_prisoners", "burn_temple_infirmary"],
        "personal_quest_id": "quest_tomas_schism",
        "faction_opinions": {"ashen_church": 40.0, "iron_workers_union": 35.0, "lowtown_syndicate": -45.0},
        "in_party": False,
        "independent_activity": "treating_patients_in_clinic",
        "conflict_description": (
            "Faith conflicts with what he witnesses. Must choose between the church and its victims."
        ),
    },
}
