"""Character, Injury, BodyPart, Memory, Relationship dataclasses & 29-part anatomy factory (GDD Sections 4, 5, 13)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Injury:
    """Persistent anatomical wound (GDD Section 5 & Section 13 lines 519-527)."""

    # --- GDD Section 13 exact fields & order ---
    id: str
    injury_type: str
    severity: float = 1.0
    pain: float = 0.0
    bleeding: float = 0.0
    infection_risk: float = 0.0
    recovery_progress: float = 0.0
    permanent: bool = False
    # --- Additional GDD Sec 5 & Sec 15 SQLite fields ---
    treated: bool = False
    treatment_stage: str = "untreated"
    long_term_effect: str = ""
    created_at: int = 0
    cause_description: str = ""
    complication: str | None = None
    body_part_id: str = ""
    part_key: str = ""
    character_id: str = ""

    def __post_init__(self) -> None:
        self.id = str(self.id)
        self.injury_type = str(self.injury_type)
        self.severity = float(self.severity)
        self.pain = float(self.pain)
        self.bleeding = float(self.bleeding)
        self.infection_risk = float(self.infection_risk)
        self.recovery_progress = float(self.recovery_progress)
        self.permanent = bool(self.permanent)
        self.treated = bool(self.treated)
        self.created_at = int(self.created_at)
        if self.treated and self.treatment_stage == "untreated":
            self.treatment_stage = "first_aid"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "injury_type": self.injury_type,
            "severity": float(self.severity),
            "pain": float(self.pain),
            "bleeding": float(self.bleeding),
            "infection_risk": float(self.infection_risk),
            "recovery_progress": float(self.recovery_progress),
            "permanent": bool(self.permanent),
            "treated": bool(self.treated),
            "treatment_stage": self.treatment_stage,
            "long_term_effect": self.long_term_effect,
            "created_at": int(self.created_at),
            "cause_description": self.cause_description,
            "complication": self.complication,
            "body_part_id": self.body_part_id,
            "part_key": self.part_key,
            "character_id": self.character_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Injury:
        return cls(
            id=str(data["id"]),
            injury_type=str(data.get("injury_type", "deep_cut")),
            severity=float(data.get("severity", 1.0)),
            pain=float(data.get("pain", 0.0)),
            bleeding=float(data.get("bleeding", 0.0)),
            infection_risk=float(data.get("infection_risk", 0.0)),
            recovery_progress=float(data.get("recovery_progress", 0.0)),
            permanent=bool(data.get("permanent", False)),
            treated=bool(data.get("treated", False)),
            treatment_stage=str(data.get("treatment_stage", "untreated")),
            long_term_effect=str(data.get("long_term_effect", "")),
            created_at=int(data.get("created_at", 0)),
            cause_description=str(data.get("cause_description", "")),
            complication=data.get("complication"),
            body_part_id=str(data.get("body_part_id", "")),
            part_key=str(data.get("part_key", "")),
            character_id=str(data.get("character_id", "")),
        )


@dataclass
class BodyPart:
    """Hierarchical anatomical body part or organ (GDD Section 5 & Section 13 lines 529-536)."""

    # --- GDD Section 13 exact fields & order ---
    id: str
    name: str
    integrity: float = 100.0
    armor: float = 0.0
    functional: bool = True
    injuries: list[Injury] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    # --- Additional GDD Sec 5 & Sec 15 SQLite fields ---
    vital: bool = False
    prosthetic_id: str | None = None
    max_integrity: float = 100.0
    parent_key: str | None = None
    region: str = ""
    resistance: float = 0.0
    functional_importance: float = 1.0
    part_key: str = ""
    character_id: str = ""

    def __post_init__(self) -> None:
        self.id = str(self.id)
        self.name = str(self.name)
        self.integrity = float(self.integrity)
        self.armor = float(self.armor)
        self.functional = bool(self.functional)
        self.vital = bool(self.vital)
        self.max_integrity = float(self.max_integrity)
        self.resistance = float(self.resistance)
        self.functional_importance = float(self.functional_importance)
        if not self.part_key:
            self.part_key = self.id.split(":")[-1] if ":" in self.id else self.id
        if not self.region:
            self.region = self.parent_key if self.parent_key else self.part_key
        self.injuries = [
            inj if isinstance(inj, Injury) else Injury.from_dict(inj)
            for inj in self.injuries
        ]
        self.children = [str(c) for c in self.children]

    @property
    def prosthetic_item_id(self) -> str | None:
        return self.prosthetic_id

    @prosthetic_item_id.setter
    def prosthetic_item_id(self, value: str | None) -> None:
        self.prosthetic_id = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "integrity": float(self.integrity),
            "armor": float(self.armor),
            "functional": bool(self.functional),
            "injuries": [inj.to_dict() for inj in self.injuries],
            "children": list(self.children),
            "vital": bool(self.vital),
            "prosthetic_id": self.prosthetic_id,
            "max_integrity": float(self.max_integrity),
            "parent_key": self.parent_key,
            "region": self.region,
            "resistance": float(self.resistance),
            "functional_importance": float(self.functional_importance),
            "part_key": self.part_key,
            "character_id": self.character_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BodyPart:
        raw_injuries = data.get("injuries", [])
        injuries = [
            inj if isinstance(inj, Injury) else Injury.from_dict(inj)
            for inj in raw_injuries
        ]
        prosthetic = data.get("prosthetic_id", data.get("prosthetic_item_id"))
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            integrity=float(data.get("integrity", 100.0)),
            armor=float(data.get("armor", 0.0)),
            functional=bool(data.get("functional", True)),
            injuries=injuries,
            children=list(data.get("children", [])),
            vital=bool(data.get("vital", False)),
            prosthetic_id=prosthetic,
            max_integrity=float(data.get("max_integrity", 100.0)),
            parent_key=data.get("parent_key"),
            region=str(data.get("region", "")),
            resistance=float(data.get("resistance", 0.0)),
            functional_importance=float(data.get("functional_importance", 1.0)),
            part_key=str(data.get("part_key", "")),
            character_id=str(data.get("character_id", "")),
        )


HUMANOID_ANATOMY_SPEC: dict[str, dict[str, Any]] = {
    # 7 Top-Level Regions
    "head": {
        "name": "Head",
        "parent_key": None,
        "region": "head",
        "vital": False,
        "functional_importance": 1.0,
        "children": ["skull", "brain", "eyes", "jaw", "ears"],
    },
    "neck": {
        "name": "Neck",
        "parent_key": None,
        "region": "neck",
        "vital": False,
        "functional_importance": 1.0,
        "children": ["throat", "cervical_spine"],
    },
    "torso": {
        "name": "Torso",
        "parent_key": None,
        "region": "torso",
        "vital": False,
        "functional_importance": 1.0,
        "children": ["skin", "ribs", "spine", "heart", "lungs", "stomach", "liver"],
    },
    "left_arm": {
        "name": "Left Arm",
        "parent_key": None,
        "region": "left_arm",
        "vital": False,
        "functional_importance": 0.8,
        "children": ["left_upper_arm", "left_elbow", "left_forearm", "left_hand"],
    },
    "right_arm": {
        "name": "Right Arm",
        "parent_key": None,
        "region": "right_arm",
        "vital": False,
        "functional_importance": 0.8,
        "children": ["right_upper_arm", "right_elbow", "right_forearm", "right_hand"],
    },
    "left_leg": {
        "name": "Left Leg",
        "parent_key": None,
        "region": "left_leg",
        "vital": False,
        "functional_importance": 0.8,
        "children": ["left_thigh", "left_knee", "left_calf", "left_foot"],
    },
    "right_leg": {
        "name": "Right Leg",
        "parent_key": None,
        "region": "right_leg",
        "vital": False,
        "functional_importance": 0.8,
        "children": ["right_thigh", "right_knee", "right_calf", "right_foot"],
    },
    # Head subparts (5)
    "skull": {"name": "Skull", "parent_key": "head", "region": "head", "vital": False, "functional_importance": 0.8, "children": []},
    "brain": {"name": "Brain", "parent_key": "head", "region": "head", "vital": True, "functional_importance": 1.0, "children": []},
    "eyes": {"name": "Eyes", "parent_key": "head", "region": "head", "vital": False, "functional_importance": 0.9, "children": []},
    "jaw": {"name": "Jaw", "parent_key": "head", "region": "head", "vital": False, "functional_importance": 0.5, "children": []},
    "ears": {"name": "Ears", "parent_key": "head", "region": "head", "vital": False, "functional_importance": 0.5, "children": []},
    # Neck subparts (2)
    "throat": {"name": "Throat", "parent_key": "neck", "region": "neck", "vital": True, "functional_importance": 1.0, "children": []},
    "cervical_spine": {"name": "Cervical Spine", "parent_key": "neck", "region": "neck", "vital": True, "functional_importance": 1.0, "children": []},
    # Torso subparts (7)
    "skin": {"name": "Skin", "parent_key": "torso", "region": "torso", "vital": False, "functional_importance": 0.4, "children": []},
    "ribs": {"name": "Ribs", "parent_key": "torso", "region": "torso", "vital": False, "functional_importance": 0.6, "children": []},
    "spine": {"name": "Spine", "parent_key": "torso", "region": "torso", "vital": False, "functional_importance": 0.95, "children": []},
    "heart": {"name": "Heart", "parent_key": "torso", "region": "torso", "vital": True, "functional_importance": 1.0, "children": []},
    "lungs": {"name": "Lungs", "parent_key": "torso", "region": "torso", "vital": True, "functional_importance": 1.0, "children": []},
    "stomach": {"name": "Stomach", "parent_key": "torso", "region": "torso", "vital": False, "functional_importance": 0.7, "children": []},
    "liver": {"name": "Liver", "parent_key": "torso", "region": "torso", "vital": False, "functional_importance": 0.8, "children": []},
    # Left Arm subparts (4)
    "left_upper_arm": {"name": "Left Upper Arm", "parent_key": "left_arm", "region": "left_arm", "vital": False, "functional_importance": 0.7, "children": []},
    "left_elbow": {"name": "Left Elbow", "parent_key": "left_arm", "region": "left_arm", "vital": False, "functional_importance": 0.7, "children": []},
    "left_forearm": {"name": "Left Forearm", "parent_key": "left_arm", "region": "left_arm", "vital": False, "functional_importance": 0.7, "children": []},
    "left_hand": {"name": "Left Hand", "parent_key": "left_arm", "region": "left_arm", "vital": False, "functional_importance": 0.8, "children": []},
    # Right Arm subparts (4)
    "right_upper_arm": {"name": "Right Upper Arm", "parent_key": "right_arm", "region": "right_arm", "vital": False, "functional_importance": 0.7, "children": []},
    "right_elbow": {"name": "Right Elbow", "parent_key": "right_arm", "region": "right_arm", "vital": False, "functional_importance": 0.7, "children": []},
    "right_forearm": {"name": "Right Forearm", "parent_key": "right_arm", "region": "right_arm", "vital": False, "functional_importance": 0.7, "children": []},
    "right_hand": {"name": "Right Hand", "parent_key": "right_arm", "region": "right_arm", "vital": False, "functional_importance": 0.8, "children": []},
    # Left Leg subparts (4)
    "left_thigh": {"name": "Left Thigh", "parent_key": "left_leg", "region": "left_leg", "vital": False, "functional_importance": 0.75, "children": []},
    "left_knee": {"name": "Left Knee", "parent_key": "left_leg", "region": "left_leg", "vital": False, "functional_importance": 0.75, "children": []},
    "left_calf": {"name": "Left Calf", "parent_key": "left_leg", "region": "left_leg", "vital": False, "functional_importance": 0.7, "children": []},
    "left_foot": {"name": "Left Foot", "parent_key": "left_leg", "region": "left_leg", "vital": False, "functional_importance": 0.7, "children": []},
    # Right Leg subparts (4)
    "right_thigh": {"name": "Right Thigh", "parent_key": "right_leg", "region": "right_leg", "vital": False, "functional_importance": 0.75, "children": []},
    "right_knee": {"name": "Right Knee", "parent_key": "right_leg", "region": "right_leg", "vital": False, "functional_importance": 0.75, "children": []},
    "right_calf": {"name": "Right Calf", "parent_key": "right_leg", "region": "right_leg", "vital": False, "functional_importance": 0.7, "children": []},
    "right_foot": {"name": "Right Foot", "parent_key": "right_leg", "region": "right_leg", "vital": False, "functional_importance": 0.7, "children": []},
}


def create_humanoid_body(character_id: str = "") -> dict[str, BodyPart]:
    """Create a fresh 7-region / 29-part humanoid anatomy dictionary (GDD Section 5)."""
    body: dict[str, BodyPart] = {}
    for part_key, spec in HUMANOID_ANATOMY_SPEC.items():
        body[part_key] = BodyPart(
            id=part_key,
            name=spec["name"],
            integrity=100.0,
            armor=0.0,
            functional=True,
            injuries=[],
            children=list(spec["children"]),
            vital=spec["vital"],
            prosthetic_id=None,
            max_integrity=100.0,
            parent_key=spec["parent_key"],
            region=spec["region"],
            resistance=0.0,
            functional_importance=spec["functional_importance"],
            part_key=part_key,
            character_id=character_id,
        )
    return body


@dataclass
class Memory:
    """Episodic or informational character memory (GDD Section 4 & Section 13 lines 539-549)."""

    # --- GDD Section 13 exact fields & order ---
    id: str
    event_type: str
    participants: list[str] = field(default_factory=list)
    description: str = ""
    location_id: str = ""
    importance: float = 0.5
    emotional_valence: float = 0.0
    confidence: float = 1.0
    created_at: int = 0
    decay_rate: float = 0.0
    # --- Additional GDD Sec 4 & Sec 15 SQLite fields ---
    emotion: str = "neutral"
    character_id: str = ""
    source_type: str = "witnessed"

    def __post_init__(self) -> None:
        self.id = str(self.id)
        self.event_type = str(self.event_type)
        self.participants = [str(p) for p in self.participants]
        self.description = str(self.description)
        self.location_id = str(self.location_id)
        self.importance = float(self.importance)
        self.emotional_valence = float(self.emotional_valence)
        self.confidence = float(self.confidence)
        self.created_at = int(self.created_at)
        self.decay_rate = float(self.decay_rate)
        self.emotion = str(self.emotion)

    @property
    def emotion_label(self) -> str:
        return self.emotion

    @emotion_label.setter
    def emotion_label(self, value: str) -> None:
        self.emotion = str(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "participants": list(self.participants),
            "description": self.description,
            "location_id": self.location_id,
            "importance": float(self.importance),
            "emotional_valence": float(self.emotional_valence),
            "confidence": float(self.confidence),
            "created_at": int(self.created_at),
            "decay_rate": float(self.decay_rate),
            "emotion": self.emotion,
            "character_id": self.character_id,
            "source_type": self.source_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Memory:
        emotion_val = data.get("emotion", data.get("emotion_label", "neutral"))
        return cls(
            id=str(data["id"]),
            event_type=str(data.get("event_type", "UNKNOWN")),
            participants=list(data.get("participants", [])),
            description=str(data.get("description", "")),
            location_id=str(data.get("location_id", "")),
            importance=float(data.get("importance", 0.5)),
            emotional_valence=float(data.get("emotional_valence", 0.0)),
            confidence=float(data.get("confidence", 1.0)),
            created_at=int(data.get("created_at", 0)),
            decay_rate=float(data.get("decay_rate", 0.0)),
            emotion=str(emotion_val),
            character_id=str(data.get("character_id", "")),
            source_type=str(data.get("source_type", "witnessed")),
        )


@dataclass
class Relationship:
    """Directed multidimensional relationship between two characters (GDD Section 4 & Section 13 lines 551-559)."""

    # --- GDD Section 13 exact fields & order ---
    source_id: str
    target_id: str
    trust: float = 0.0
    respect: float = 0.0
    affection: float = 0.0
    resentment: float = 0.0
    fear: float = 0.0
    shared_memories: list[str] = field(default_factory=list)
    # --- Additional GDD Sec 4 & Sec 15 SQLite fields ---
    dependency: float = 0.0
    relationship_state: str = "Acquaintance"
    friendship_score: float = 0.0
    rivalry_score: float = 0.0

    def __post_init__(self) -> None:
        self.source_id = str(self.source_id)
        self.target_id = str(self.target_id)
        self.trust = float(self.trust)
        self.respect = float(self.respect)
        self.affection = float(self.affection)
        self.resentment = float(self.resentment)
        self.fear = float(self.fear)
        self.shared_memories = [str(m) for m in self.shared_memories]
        self.dependency = float(self.dependency)
        self.friendship_score = float(self.friendship_score)
        self.rivalry_score = float(self.rivalry_score)

    @property
    def friendship(self) -> float:
        return self.friendship_score

    @friendship.setter
    def friendship(self, value: float) -> None:
        self.friendship_score = float(value)

    @property
    def rivalry(self) -> float:
        return self.rivalry_score

    @rivalry.setter
    def rivalry(self, value: float) -> None:
        self.rivalry_score = float(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "trust": float(self.trust),
            "respect": float(self.respect),
            "affection": float(self.affection),
            "resentment": float(self.resentment),
            "fear": float(self.fear),
            "shared_memories": list(self.shared_memories),
            "dependency": float(self.dependency),
            "relationship_state": self.relationship_state,
            "friendship_score": float(self.friendship_score),
            "rivalry_score": float(self.rivalry_score),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Relationship:
        return cls(
            source_id=str(data["source_id"]),
            target_id=str(data["target_id"]),
            trust=float(data.get("trust", 0.0)),
            respect=float(data.get("respect", 0.0)),
            affection=float(data.get("affection", 0.0)),
            resentment=float(data.get("resentment", 0.0)),
            fear=float(data.get("fear", 0.0)),
            shared_memories=list(data.get("shared_memories", [])),
            dependency=float(data.get("dependency", 0.0)),
            relationship_state=str(data.get("relationship_state", "Acquaintance")),
            friendship_score=float(data.get("friendship_score", data.get("friendship", 0.0))),
            rivalry_score=float(data.get("rivalry_score", data.get("rivalry", 0.0))),
        )


@dataclass
class Character:
    """Core Character entity matching GDD Section 13 (lines 498-516) and Sections 4, 5, 6, 15."""

    # --- GDD Section 13 exact fields & order ---
    id: str
    name: str
    age: int = 30
    faction_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    skills: dict[str, float] = field(default_factory=dict)
    personality: dict[str, float] = field(default_factory=dict)
    needs: dict[str, float] = field(default_factory=dict)
    body: dict[str, BodyPart] = field(default_factory=dict)
    memories: list[Memory] = field(default_factory=list)
    relationships: dict[str, Relationship] = field(default_factory=dict)
    ambitions: list[Any] = field(default_factory=list)
    location_id: str = ""
    status: str = "alive"
    is_player: bool = False
    is_companion: bool = False
    is_nemesis: bool = False
    # --- Additional GDD Sec 4, 5, 6, 10, 15 fields ---
    tier: int = 1
    rank: str | None = None
    occupation: str = ""
    combat_style: str = ""
    reputation: dict[str, Any] = field(default_factory=dict)
    equipment: dict[str, str] = field(default_factory=dict)
    inventory: list[str] = field(default_factory=list)
    consciousness: float = 100.0
    morale: float = 75.0
    nemesis_profile: Any = None

    def __post_init__(self) -> None:
        if not self.id or not str(self.id).strip():
            raise ValueError("Character.id must be a non-empty string")
        self.id = str(self.id)
        self.name = str(self.name)
        self.age = int(self.age)
        self.tier = int(self.tier)
        self.consciousness = float(self.consciousness)
        self.morale = float(self.morale)

        # Normalize body dict values into BodyPart instances
        normalized_body: dict[str, BodyPart] = {}
        for k, v in self.body.items():
            if isinstance(v, BodyPart):
                if not v.character_id:
                    v.character_id = self.id
                normalized_body[str(k)] = v
            elif isinstance(v, dict):
                bp = BodyPart.from_dict(v)
                if not bp.character_id:
                    bp.character_id = self.id
                normalized_body[str(k)] = bp
        self.body = normalized_body

        # Normalize memories list into Memory instances
        normalized_memories: list[Memory] = []
        for m in self.memories:
            if isinstance(m, Memory):
                if not m.character_id:
                    m.character_id = self.id
                normalized_memories.append(m)
            elif isinstance(m, dict):
                mem = Memory.from_dict(m)
                if not mem.character_id:
                    mem.character_id = self.id
                normalized_memories.append(mem)
        self.memories = normalized_memories

        # Normalize relationships into dict[target_id, Relationship]
        normalized_rels: dict[str, Relationship] = {}
        if isinstance(self.relationships, list):
            for r in self.relationships:
                rel = r if isinstance(r, Relationship) else Relationship.from_dict(r)
                normalized_rels[rel.target_id] = rel
        elif isinstance(self.relationships, dict):
            for k, v in self.relationships.items():
                if isinstance(v, Relationship):
                    normalized_rels[str(k)] = v
                elif isinstance(v, dict):
                    rel_dict = dict(v)
                    rel_dict.setdefault("source_id", self.id)
                    rel_dict.setdefault("target_id", str(k))
                    normalized_rels[str(k)] = Relationship.from_dict(rel_dict)
        self.relationships = normalized_rels

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "age": int(self.age),
            "faction_id": self.faction_id,
            "attributes": dict(self.attributes),
            "skills": dict(self.skills),
            "personality": dict(self.personality),
            "needs": dict(self.needs),
            "body": {k: v.to_dict() for k, v in self.body.items()},
            "memories": [m.to_dict() for m in self.memories],
            "relationships": {k: v.to_dict() for k, v in self.relationships.items()},
            "ambitions": list(self.ambitions),
            "location_id": self.location_id,
            "status": self.status,
            "is_player": bool(self.is_player),
            "is_companion": bool(self.is_companion),
            "is_nemesis": bool(self.is_nemesis),
            "tier": int(self.tier),
            "rank": self.rank,
            "occupation": self.occupation,
            "combat_style": self.combat_style,
            "reputation": dict(self.reputation),
            "equipment": dict(self.equipment),
            "inventory": list(self.inventory),
            "consciousness": float(self.consciousness),
            "morale": float(self.morale),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Character:
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            age=int(data.get("age", 30)),
            faction_id=data.get("faction_id"),
            attributes=dict(data.get("attributes", {})),
            skills=dict(data.get("skills", {})),
            personality=dict(data.get("personality", {})),
            needs=dict(data.get("needs", {})),
            body= {
                str(k): (v if isinstance(v, BodyPart) else BodyPart.from_dict(v))
                for k, v in data.get("body", {}).items()
            },
            memories=[
                m if isinstance(m, Memory) else Memory.from_dict(m)
                for m in data.get("memories", [])
            ],
            relationships={
                str(k): (v if isinstance(v, Relationship) else Relationship.from_dict(v))
                for k, v in data.get("relationships", {}).items()
            } if isinstance(data.get("relationships", {}), dict) else {
                (r.target_id if isinstance(r, Relationship) else str(r["target_id"])): (
                    r if isinstance(r, Relationship) else Relationship.from_dict(r)
                )
                for r in data.get("relationships", [])
            },
            ambitions=list(data.get("ambitions", [])),
            location_id=str(data.get("location_id", "")),
            status=str(data.get("status", "alive")),
            is_player=bool(data.get("is_player", False)),
            is_companion=bool(data.get("is_companion", False)),
            is_nemesis=bool(data.get("is_nemesis", False)),
            tier=int(data.get("tier", 1)),
            rank=data.get("rank"),
            occupation=str(data.get("occupation", "")),
            combat_style=str(data.get("combat_style", "")),
            reputation=dict(data.get("reputation", {})),
            equipment=dict(data.get("equipment", {})),
            inventory=list(data.get("inventory", [])),
            consciousness=float(data.get("consciousness", 100.0)),
            morale=float(data.get("morale", 75.0)),
        )
