"""Anatomy, damage, injuries, consciousness, and 5-stage medicine system (GDD Sections 5 & 13)."""

from __future__ import annotations

import uuid
from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.character import BodyPart, Character, Injury, create_humanoid_body


INJURY_TYPES = {
    "deep_cut": {"bleeding": 0.6, "pain": 0.5, "functional_loss": False, "infection_risk": 0.2, "scar": "healed_scar"},
    "laceration": {"bleeding": 0.4, "pain": 0.4, "functional_loss": False, "infection_risk": 0.2, "scar": "scar"},
    "broken_arm": {"bleeding": 0.1, "pain": 0.7, "functional_loss": True, "infection_risk": 0.05, "scar": "chronic_pain"},
    "broken_leg": {"bleeding": 0.1, "pain": 0.7, "functional_loss": True, "infection_risk": 0.05, "scar": "chronic_pain"},
    "compound_fracture": {"bleeding": 0.5, "pain": 0.9, "functional_loss": True, "infection_risk": 0.4, "scar": "improperly_healed_bone"},
    "concussion": {"bleeding": 0.0, "pain": 0.6, "functional_loss": True, "infection_risk": 0.0, "scar": "cognitive_impairment"},
    "eye_injury": {"bleeding": 0.2, "pain": 0.8, "functional_loss": True, "infection_risk": 0.3, "scar": "permanent_blindness"},
    "organ_damage": {"bleeding": 0.5, "pain": 0.8, "functional_loss": True, "infection_risk": 0.3, "scar": "chronic_illness"},
    "internal_bleeding": {"bleeding": 0.7, "pain": 0.6, "functional_loss": False, "infection_risk": 0.1, "scar": "chronic_weakness"},
    "burn": {"bleeding": 0.1, "pain": 0.9, "functional_loss": False, "infection_risk": 0.5, "scar": "burn_scar"},
    "nerve_damage": {"bleeding": 0.0, "pain": 0.7, "functional_loss": True, "infection_risk": 0.0, "scar": "chronic_numbness"},
    "amputation": {"bleeding": 0.9, "pain": 1.0, "functional_loss": True, "infection_risk": 0.4, "scar": "prosthetic_dependency"},
}


class HealthSystem:
    """Manages hierarchical humanoid anatomy, localized injuries, pain, consciousness, and medical treatments."""

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

    def get_injury_types(self) -> list[str]:
        return list(INJURY_TYPES.keys())

    def list_injury_types(self) -> list[str]:
        return list(INJURY_TYPES.keys())

    def get_injury_catalog(self) -> list[str]:
        return list(INJURY_TYPES.keys())

    def initialize_body(self, character: Character) -> Character:
        """Initialize humanoid anatomy on character if not already present."""
        if not character.body:
            character.body = create_humanoid_body(character.id)
        if not hasattr(character, "consciousness") or character.consciousness is None:
            character.consciousness = 100.0
        return character

    def ensure_anatomy(self, character: Character) -> Character:
        return self.initialize_body(character)

    def create_body(self, character: Character) -> Character:
        return self.initialize_body(character)

    def apply_injury(
        self,
        character: Character,
        body_part_id: str,
        injury_type: str,
        severity: float = 1.0,
        cause_description: str = "",
        permanent: bool | None = None,
        **kwargs: Any,
    ) -> Injury:
        """Apply a persistent localized injury to a specific body part."""
        self.initialize_body(character)
        part = character.body.get(body_part_id)
        if not part:
            # Fallback to creating part if missing
            part = BodyPart(id=body_part_id, name=body_part_id.replace("_", " ").title())
            character.body[body_part_id] = part

        meta = INJURY_TYPES.get(injury_type, {"bleeding": 0.3, "pain": 0.5, "functional_loss": False, "infection_risk": 0.1, "scar": "scar"})
        is_permanent = bool(permanent) if permanent is not None else (injury_type == "amputation")

        inj = Injury(
            id=f"inj_{body_part_id}_{uuid.uuid4().hex[:6]}",
            injury_type=injury_type,
            severity=float(severity),
            pain=float(meta["pain"] * severity),
            bleeding=float(meta["bleeding"] * severity),
            infection_risk=float(meta["infection_risk"] * severity),
            recovery_progress=0.0,
            permanent=is_permanent,
            treated=False,
            treatment_stage="untreated",
            long_term_effect="",
            created_at=self.clock.timestamp if self.clock else 0,
            cause_description=cause_description,
            body_part_id=body_part_id,
            character_id=character.id,
        )

        part.injuries.append(inj)
        part.integrity = max(0.0, part.integrity - (severity * 50.0))

        if meta["functional_loss"] or part.integrity <= 20.0 or injury_type == "amputation":
            part.functional = False

        if injury_type == "amputation":
            part.integrity = 0.0
            part.functional = False
            for child_id in part.children:
                if child_id in character.body:
                    character.body[child_id].functional = False
                    character.body[child_id].integrity = 0.0

        if self.event_bus:
            ev = GameEvent(
                id=f"ev_inj_{uuid.uuid4().hex[:6]}",
                event_type="LIMB_INJURED" if "arm" in body_part_id or "leg" in body_part_id else "CHARACTER_INJURED",
                timestamp=self.clock.timestamp if self.clock else 0,
                source_id=None,
                target_ids=[character.id],
                location_id=character.location_id,
                data={
                    "body_part": body_part_id,
                    "injury": injury_type,
                    "severity": severity,
                },
                importance=0.8,
            )
            self.event_bus.emit(ev, priority=EventPriority.CRITICAL)

        self.update_health(character, minutes=1)
        return inj

    def apply_damage(
        self,
        character: Character,
        body_part_id: str,
        damage: float,
        damage_type: str = "cutting",
        **kwargs: Any,
    ) -> Injury:
        """Apply damage directly to a body part, checking vital organs and permanent disability rules."""
        self.initialize_body(character)
        part = character.body.get(body_part_id)
        if not part:
            part = BodyPart(id=body_part_id, name=body_part_id.replace("_", " ").title())
            character.body[body_part_id] = part

        damage = float(damage)
        part.integrity = max(0.0, part.integrity - damage)

        # Determine injury type
        if damage <= 5.0:
            # Ordinary minor hit: does not cause permanent disability or loss of function
            inj_type = "laceration" if damage_type == "cutting" else "bruise"
            severity = 0.1
            permanent = False
        elif part.vital and part.integrity <= 0.0:
            inj_type = "organ_damage" if "brain" in body_part_id or "heart" in body_part_id else "broken_neck"
            severity = 1.0
            permanent = True
            part.functional = False
        elif damage_type == "piercing":
            inj_type = "organ_damage" if part.vital else "deep_cut"
            severity = min(1.0, damage / 50.0)
            permanent = False
        elif damage_type == "blunt":
            if "arm" in body_part_id:
                inj_type = "broken_arm"
            elif "leg" in body_part_id:
                inj_type = "broken_leg"
            elif "head" in body_part_id or "skull" in body_part_id or "brain" in body_part_id:
                inj_type = "concussion"
            else:
                inj_type = "internal_bleeding"
            severity = min(1.0, damage / 50.0)
            permanent = False
        elif damage_type == "fire":
            inj_type = "burn"
            severity = min(1.0, damage / 50.0)
            permanent = False
        elif damage_type == "magic":
            inj_type = "nerve_damage"
            severity = min(1.0, damage / 50.0)
            permanent = False
        else:
            inj_type = "deep_cut" if damage >= 15.0 else "laceration"
            severity = min(1.0, damage / 50.0)
            permanent = False

        meta = INJURY_TYPES.get(inj_type, {"bleeding": 0.3, "pain": 0.5, "functional_loss": False, "infection_risk": 0.1, "scar": "scar"})
        inj = Injury(
            id=f"inj_{body_part_id}_{uuid.uuid4().hex[:6]}",
            injury_type=inj_type,
            severity=severity,
            pain=float(meta["pain"] * severity),
            bleeding=float(meta["bleeding"] * severity),
            infection_risk=float(meta["infection_risk"] * severity),
            recovery_progress=0.0,
            permanent=permanent,
            treated=False,
            treatment_stage="untreated",
            long_term_effect="",
            created_at=self.clock.timestamp if self.clock else 0,
            cause_description=f"{damage_type} attack",
            body_part_id=body_part_id,
            character_id=character.id,
        )
        part.injuries.append(inj)

        if damage > 5.0 and (part.integrity <= 20.0 or meta["functional_loss"]):
            part.functional = False

        if part.vital and part.integrity <= 0.0:
            character.consciousness = 0.0
            character.status = "dead"
            if self.event_bus:
                self.event_bus.emit(
                    GameEvent(
                        id=f"ev_death_{uuid.uuid4().hex[:6]}",
                        event_type="CHARACTER_DIED",
                        timestamp=self.clock.timestamp if self.clock else 0,
                        source_id=None,
                        target_ids=[character.id],
                        location_id=character.location_id,
                        data={"cause": f"Destroyed vital organ: {part.name}"},
                        importance=1.0,
                    ),
                    priority=EventPriority.CRITICAL,
                )

        self.update_health(character, minutes=1)
        return inj

    def inflict_damage(self, character: Character, body_part_id: str, damage: float, damage_type: str = "cutting", **kwargs: Any) -> Injury:
        return self.apply_damage(character, body_part_id, damage, damage_type=damage_type, **kwargs)

    def destroy_part(self, character: Character, body_part_id: str, damage: float = 250.0, damage_type: str = "piercing", **kwargs: Any) -> Injury:
        return self.apply_damage(character, body_part_id, damage, damage_type=damage_type, **kwargs)

    def inflict_injury(self, character: Character, body_part_id: str, injury_type: str, severity: float = 1.0, **kwargs: Any) -> Injury:
        return self.apply_injury(character, body_part_id, injury_type, severity=severity, **kwargs)

    def get_combat_modifiers(self, character: Character) -> dict[str, float]:
        """Calculate functional capability penalties from anatomical injuries (GDD Section 5)."""
        self.initialize_body(character)
        weapon_handling = 1.0
        mobility = 1.0
        accuracy = 1.0
        perception = 1.0

        for part_id, part in character.body.items():
            # Arm functional penalty -> weapon handling
            if "arm" in part_id or "hand" in part_id:
                if not part.functional:
                    weapon_handling *= 0.5
                for inj in part.injuries:
                    if inj.injury_type in ("broken_arm", "compound_fracture", "amputation"):
                        weapon_handling *= 0.6

            # Leg functional penalty -> mobility
            if "leg" in part_id or "foot" in part_id or "thigh" in part_id:
                if not part.functional:
                    mobility *= 0.5
                for inj in part.injuries:
                    if inj.injury_type in ("broken_leg", "compound_fracture", "amputation"):
                        mobility *= 0.6

            # Eye / head penalty -> accuracy and perception
            if "eye" in part_id:
                if not part.functional:
                    accuracy *= 0.3
                    perception *= 0.5
                for inj in part.injuries:
                    if inj.injury_type == "eye_injury":
                        accuracy *= 0.5
            if "head" in part_id or "skull" in part_id or "brain" in part_id:
                for inj in part.injuries:
                    if inj.injury_type == "concussion":
                        perception *= 0.6

        return {
            "weapon_handling": max(0.1, min(1.0, weapon_handling)),
            "mobility": max(0.1, min(1.0, mobility)),
            "accuracy": max(0.1, min(1.0, accuracy)),
            "perception": max(0.1, min(1.0, perception)),
        }

    def calculate_penalties(self, character: Character) -> dict[str, float]:
        return self.get_combat_modifiers(character)

    def get_functional_modifiers(self, character: Character) -> dict[str, float]:
        return self.get_combat_modifiers(character)

    def update_health(self, character: Character, minutes: int = 60) -> None:
        """Update bleeding, pain, consciousness, and check incapacitation/death."""
        self.initialize_body(character)

        total_bleeding = 0.0
        total_pain = 0.0

        for part in character.body.values():
            for inj in part.injuries:
                if not inj.treated:
                    total_bleeding += inj.bleeding
                    total_pain += inj.pain
                else:
                    total_pain += inj.pain * 0.3

        # Rate of consciousness loss: bleeding and pain rapidly deplete consciousness
        drop = (total_bleeding * 60.0 + total_pain * 30.0) * (minutes / 60.0)
        current_c = getattr(character, "consciousness", 100.0)
        new_c = max(0.0, current_c - drop)
        character.consciousness = new_c

        # Vital part check
        for part in character.body.values():
            if part.vital and part.integrity <= 0.0:
                character.consciousness = 0.0
                character.status = "dead"
                if self.event_bus:
                    self.event_bus.emit(
                        GameEvent(
                            id=f"ev_death_{uuid.uuid4().hex[:6]}",
                            event_type="CHARACTER_DIED",
                            timestamp=self.clock.timestamp if self.clock else 0,
                            source_id=None,
                            target_ids=[character.id],
                            location_id=character.location_id,
                            data={"cause": f"Destroyed vital organ: {part.name}"},
                            importance=1.0,
                        ),
                        priority=EventPriority.CRITICAL,
                    )
                return

        # Incapacitation check
        if (new_c < 50.0 or total_pain >= 1.5) and character.status == "alive":
            character.status = "incapacitated"
            if self.event_bus:
                self.event_bus.emit(
                    GameEvent(
                        id=f"ev_incap_{uuid.uuid4().hex[:6]}",
                        event_type="CHARACTER_INCAPACITATED",
                        timestamp=self.clock.timestamp if self.clock else 0,
                        source_id=None,
                        target_ids=[character.id],
                        location_id=character.location_id,
                        data={"cause": "Pain and blood loss", "consciousness": new_c},
                        importance=0.9,
                    ),
                    priority=EventPriority.CRITICAL,
                )

    def process_health_tick(self, character: Character, minutes: int = 60) -> None:
        self.update_health(character, minutes)

    def tick_character_health(self, character: Character, minutes: int = 60) -> None:
        self.update_health(character, minutes)

    def apply_treatment(
        self,
        patient: Character,
        stage: str,
        doctor: Character | None = None,
        body_part: str | None = None,
        prosthetic_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Apply one of 5 medical stages (first_aid, field_treatment, surgery, rehabilitation, prosthetics)."""
        self.initialize_body(patient)

        if stage == "first_aid":
            # Stops bleeding
            for part in patient.body.values():
                for inj in part.injuries:
                    inj.bleeding = 0.0
                    inj.treated = True
                    inj.treatment_stage = "first_aid"
            return True

        elif stage == "field_treatment":
            # Stabilize, reduce pain, and lower infection risk (scaled by doctor medicine skill)
            doc_med = 50.0
            if doctor and hasattr(doctor, "skills"):
                doc_med = float(doctor.skills.get("medicine", 50.0))
            risk_mult = max(0.05, min(0.8, 1.0 - (doc_med / 100.0) * 0.9))
            for part in patient.body.values():
                for inj in part.injuries:
                    inj.treated = True
                    inj.pain = max(0.0, inj.pain * 0.4)
                    inj.infection_risk = max(0.0, inj.infection_risk * risk_mult)
                    inj.treatment_stage = "field_treatment"
            return True

        elif stage == "surgery":
            # Repair internal organ damage
            target = body_part or "stomach"
            cleanliness = float(kwargs.get("cleanliness", 1.0))
            doc_med = 50.0
            if doctor and hasattr(doctor, "skills"):
                doc_med = float(doctor.skills.get("medicine", 50.0))
            is_dirty_or_unskilled = cleanliness < 0.3 or doc_med < 25.0

            if target in patient.body:
                part = patient.body[target]
                has_amputation = any(inj.injury_type == "amputation" for inj in part.injuries)
                if not is_dirty_or_unskilled and not has_amputation:
                    part.functional = True
                    part.integrity = max(part.integrity, 60.0)
                for inj in part.injuries:
                    inj.treated = True
                    inj.treatment_stage = "surgery"
                    inj.bleeding = 0.0
                    inj.pain = 0.1
                    if is_dirty_or_unskilled:
                        inj.permanent = True
                        inj.complication = "improperly_set_disability"

            if is_dirty_or_unskilled:
                return {"success": True, "complication": "improperly_set_disability"}
            return True

        elif stage == "rehabilitation":
            # Restore movement & function to limb
            target = body_part or "right_arm"
            if target in patient.body:
                part = patient.body[target]
                part.functional = True
                part.integrity = max(part.integrity, 70.0)
                for inj in part.injuries:
                    inj.treatment_stage = "rehabilitated"
            return True

        elif stage == "prosthetics":
            # Replace amputated limb
            target = body_part or "left_arm"
            if target in patient.body:
                part = patient.body[target]
                part.functional = True
                part.prosthetic_id = prosthetic_id or "iron_prosthetic_arm"
                part.integrity = 80.0
                if self.event_bus:
                    self.event_bus.emit(
                        GameEvent(
                            id=f"ev_pros_{uuid.uuid4().hex[:6]}",
                            event_type="PROSTHETIC_FITTED",
                            timestamp=self.clock.timestamp if self.clock else 0,
                            source_id=doctor.id if doctor else None,
                            target_ids=[patient.id],
                            location_id=patient.location_id,
                            data={"body_part": target, "prosthetic_id": part.prosthetic_id},
                            importance=0.7,
                        ),
                        priority=EventPriority.NORMAL,
                    )
            return True

        return False

    def treat_character(self, patient: Character, **kwargs: Any) -> bool:
        return self.apply_treatment(patient, **kwargs)

    def perform_treatment(self, patient: Character, **kwargs: Any) -> bool:
        return self.apply_treatment(patient, **kwargs)

    def advance_healing(self, character: Character, days: int = 30) -> None:
        """Progress injury recovery, generating scars or chronic conditions."""
        self.initialize_body(character)
        for part in character.body.values():
            for inj in part.injuries:
                inj.recovery_progress = min(1.0, inj.recovery_progress + (days * 0.05))
                if inj.recovery_progress >= 0.8:
                    spec = INJURY_TYPES.get(inj.injury_type, {})
                    inj.long_term_effect = spec.get("scar", "scar")
                    inj.pain = 0.0
                    inj.bleeding = 0.0

    def heal_over_time(self, character: Character, days: int = 30) -> None:
        self.advance_healing(character, days)

    def get_physical_history(self, character: Character) -> list[str]:
        """Return list of scars, chronic conditions, and prosthetics (GDD Section 5)."""
        self.initialize_body(character)
        history: list[str] = []
        for part_id, part in character.body.items():
            if part.prosthetic_id:
                history.append(f"Prosthetic on {part.name}: {part.prosthetic_id}")
            for inj in part.injuries:
                if inj.long_term_effect:
                    history.append(f"{part.name}: {inj.long_term_effect}")
                elif inj.permanent:
                    history.append(f"{part.name}: permanent {inj.injury_type}")
                elif inj.severity >= 0.7:
                    history.append(f"{part.name}: severe scar from {inj.injury_type}")
        return history

    def get_scars_and_conditions(self, character: Character) -> list[str]:
        return self.get_physical_history(character)

    def inspect_health(self, character: Character) -> list[str]:
        return self.get_physical_history(character)

    def process_infection_tick(self, character: Character) -> dict[str, Any]:
        """Check and advance wound infection progression (GDD Section 5 & 11)."""
        self.initialize_body(character)
        infected_parts: list[str] = []
        for part_id, part in character.body.items():
            for inj in part.injuries:
                if inj.infection_risk >= 0.5 and not inj.treated:
                    inj.pain += 0.2
                    inj.bleeding += 0.05
                    infected_parts.append(part_id)

        return {
            "character_id": character.id,
            "infected": len(infected_parts) > 0,
            "infected_parts": infected_parts,
        }

    def check_infection(self, character: Character) -> dict[str, Any]:
        return self.process_infection_tick(character)

    def update_diseases(self, character: Character) -> dict[str, Any]:
        return self.process_infection_tick(character)
