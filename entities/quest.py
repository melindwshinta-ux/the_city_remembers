"""Quest and Rumor dataclasses (GDD Section 10 & Section 13 line 613)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Quest:
    """Authored, systemic, or hybrid quest model (GDD Section 10 & Section 13 line 613)."""

    id: str
    title: str
    status: str = "available"  # available, active, completed, failed, branched
    objectives: list[dict[str, Any]] = field(default_factory=list)
    conditions: dict[str, Any] = field(default_factory=dict)
    involved_characters: list[str] = field(default_factory=list)
    involved_factions: list[str] = field(default_factory=list)
    consequences: list[dict[str, Any]] | dict[str, Any] = field(default_factory=list)
    quest_type: str = "hybrid"  # authored, systemic, hybrid
    description: str = ""
    selected_approach: str | None = None

    def __post_init__(self) -> None:
        if not self.id or not str(self.id).strip():
            raise ValueError("Quest.id must be a non-empty string")
        self.id = str(self.id)
        self.title = str(self.title)
        self.status = str(self.status)
        self.quest_type = str(self.quest_type)
        self.objectives = [dict(o) if isinstance(o, dict) else {"description": str(o)} for o in self.objectives]
        self.conditions = dict(self.conditions)
        self.involved_characters = [str(c) for c in self.involved_characters]
        self.involved_factions = [str(f) for f in self.involved_factions]
        if isinstance(self.consequences, dict):
            self.consequences = dict(self.consequences)
        else:
            self.consequences = [dict(c) if isinstance(c, dict) else {"effect": str(c)} for c in self.consequences]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.self_title if hasattr(self, "self_title") else self.title,
            "status": self.status,
            "objectives": [dict(o) for o in self.objectives],
            "conditions": dict(self.conditions),
            "involved_characters": list(self.involved_characters),
            "involved_factions": list(self.involved_factions),
            "consequences": dict(self.consequences) if isinstance(self.consequences, dict) else [dict(c) for c in self.consequences],
            "quest_type": self.quest_type,
            "description": self.description,
            "selected_approach": self.selected_approach,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Quest:
        return cls(
            id=str(data["id"]),
            title=str(data.get("title", data["id"])),
            status=str(data.get("status", "available")),
            objectives=list(data.get("objectives", [])),
            conditions=dict(data.get("conditions", {})),
            involved_characters=list(data.get("involved_characters", [])),
            involved_factions=list(data.get("involved_factions", [])),
            consequences=data.get("consequences", []),
            quest_type=str(data.get("quest_type", "hybrid")),
            description=str(data.get("description", "")),
            selected_approach=data.get("selected_approach"),
        )


@dataclass
class Rumor:
    """Social network rumor tracking truth, district reach %, and confidence % (GDD Section 10)."""

    id: str
    subject: str
    claim: str
    origin: str
    truth: bool = False
    reach: dict[str, float] = field(default_factory=dict)  # district_id -> percentage (0-100)
    confidence: float = 50.0  # 0-100%

    def __post_init__(self) -> None:
        if not self.id or not str(self.id).strip():
            raise ValueError("Rumor.id must be a non-empty string")
        self.id = str(self.id)
        self.subject = str(self.subject)
        self.claim = str(self.claim)
        self.origin = str(self.origin)
        self.truth = bool(self.truth)
        self.reach = {str(k): float(v) for k, v in self.reach.items()}
        self.confidence = float(self.confidence)

    @property
    def subject_id(self) -> str:
        return self.subject

    @property
    def origin_id(self) -> str:
        return self.origin

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "claim": self.claim,
            "origin": self.origin,
            "truth": bool(self.truth),
            "reach": dict(self.reach),
            "confidence": float(self.confidence),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rumor:
        return cls(
            id=str(data["id"]),
            subject=str(data.get("subject", data.get("subject_id", ""))),
            claim=str(data.get("claim", "")),
            origin=str(data.get("origin", data.get("origin_id", ""))),
            truth=bool(data.get("truth", False)),
            reach={str(k): float(v) for k, v in data.get("reach", {}).items()},
            confidence=float(data.get("confidence", 50.0)),
        )
