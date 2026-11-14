"""NemesisProfile and EnemyCombatant / Enemy dataclasses (GDD Sections 6, 7, 13)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NemesisProfile:
    """Nemesis system profile matching GDD Section 13 (lines 577-587) and Section 7."""

    # --- GDD Section 13 exact fields & order ---
    character_id: str
    player_hostility: float = 0.0
    player_respect: float = 0.0
    encounter_count: int = 0
    known_player_tactics: list[str] = field(default_factory=list)
    grudges: list[str] = field(default_factory=list)
    career_history: list[dict[str, Any]] = field(default_factory=list)
    last_encounter_date: int = 0
    current_ambition: str = ""
    special_traits: list[str] = field(default_factory=list)
    # --- Additional GDD Sec 7 & Sec 15 SQLite fields ---
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    rank: str = "captain"
    status: str = "active"
    faction_id: str | None = None
    combat_style: list[str] = field(default_factory=list)
    adaptations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.character_id or not str(self.character_id).strip():
            raise ValueError("NemesisProfile.character_id must be a non-empty string")
        self.character_id = str(self.character_id)
        self.player_hostility = float(self.player_hostility)
        self.player_respect = float(self.player_respect)
        self.encounter_count = int(self.encounter_count)
        self.last_encounter_date = int(self.last_encounter_date)
        self.known_player_tactics = [str(t) for t in self.known_player_tactics]
        self.grudges = [str(g) for g in self.grudges]
        self.special_traits = [str(t) for t in self.special_traits]
        self.strengths = [str(s) for s in self.strengths]
        self.weaknesses = [str(w) for w in self.weaknesses]
        self.combat_style = [str(c) for c in self.combat_style]
        self.adaptations = [str(a) for a in self.adaptations]

    @property
    def id(self) -> str:
        return self.character_id

    @property
    def adapted_countermeasures(self) -> list[str]:
        return self.adaptations

    @adapted_countermeasures.setter
    def adapted_countermeasures(self, value: list[str]) -> None:
        self.adaptations = [str(x) for x in value]

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "player_hostility": float(self.player_hostility),
            "player_respect": float(self.player_respect),
            "encounter_count": int(self.encounter_count),
            "known_player_tactics": list(self.known_player_tactics),
            "grudges": list(self.grudges),
            "career_history": [dict(c) for c in self.career_history],
            "last_encounter_date": int(self.last_encounter_date),
            "current_ambition": self.current_ambition,
            "special_traits": list(self.special_traits),
            "strengths": list(self.strengths),
            "weaknesses": list(self.weaknesses),
            "rank": self.rank,
            "status": self.status,
            "faction_id": self.faction_id,
            "combat_style": list(self.combat_style),
            "adaptations": list(self.adaptations),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NemesisProfile:
        adaptations = data.get("adaptations", data.get("adapted_countermeasures", []))
        return cls(
            character_id=str(data.get("character_id", data.get("id", ""))),
            player_hostility=float(data.get("player_hostility", 0.0)),
            player_respect=float(data.get("player_respect", 0.0)),
            encounter_count=int(data.get("encounter_count", 0)),
            known_player_tactics=list(data.get("known_player_tactics", [])),
            grudges=list(data.get("grudges", [])),
            career_history=list(data.get("career_history", [])),
            last_encounter_date=int(data.get("last_encounter_date", 0)),
            current_ambition=str(data.get("current_ambition", "")),
            special_traits=list(data.get("special_traits", [])),
            strengths=list(data.get("strengths", [])),
            weaknesses=list(data.get("weaknesses", [])),
            rank=str(data.get("rank", "captain")),
            status=str(data.get("status", "active")),
            faction_id=data.get("faction_id"),
            combat_style=list(data.get("combat_style", [])),
            adaptations=list(adaptations),
        )


@dataclass
class EnemyCombatant:
    """Combat-specific enemy metadata (GDD Section 6)."""

    character_id: str
    archetype: str = "opportunist"  # coward, duelist, commander, berserker, assassin, medic, opportunist
    rank: str = "soldier"           # commander, captain, lieutenant, sergeant, soldier
    morale: float = 75.0
    morale_state: str = "steady"    # confident, steady, nervous, frightened, panicking, routing
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    nemesis_profile: NemesisProfile | None = None

    def __post_init__(self) -> None:
        if not self.character_id or not str(self.character_id).strip():
            raise ValueError("EnemyCombatant.character_id must be a non-empty string")
        self.character_id = str(self.character_id)
        self.morale = float(self.morale)
        if isinstance(self.nemesis_profile, dict):
            self.nemesis_profile = NemesisProfile.from_dict(self.nemesis_profile)

    @property
    def id(self) -> str:
        return self.character_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "archetype": self.archetype,
            "rank": self.rank,
            "morale": float(self.morale),
            "morale_state": self.morale_state,
            "strengths": list(self.strengths),
            "weaknesses": list(self.weaknesses),
            "nemesis_profile": self.nemesis_profile.to_dict() if self.nemesis_profile else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnemyCombatant:
        nem_raw = data.get("nemesis_profile")
        nem = (
            nem_raw
            if isinstance(nem_raw, NemesisProfile)
            else (NemesisProfile.from_dict(nem_raw) if isinstance(nem_raw, dict) else None)
        )
        return cls(
            character_id=str(data.get("character_id", data.get("id", ""))),
            archetype=str(data.get("archetype", "opportunist")),
            rank=str(data.get("rank", "soldier")),
            morale=float(data.get("morale", 75.0)),
            morale_state=str(data.get("morale_state", "steady")),
            strengths=list(data.get("strengths", [])),
            weaknesses=list(data.get("weaknesses", [])),
            nemesis_profile=nem,
        )


Enemy = EnemyCombatant
