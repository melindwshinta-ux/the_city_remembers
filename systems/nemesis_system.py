"""Nemesis system: rivalries, adaptation, promotions, and career progression (GDD Sections 7 & 13)."""

from __future__ import annotations

from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.character import Character
from entities.enemy import NemesisProfile


ELIGIBILITY_TRIGGERS = {
    "survives_encounter",
    "injures_player",
    "escapes_capture",
    "witnesses_major_event",
    "loses_subordinate",
    "gains_power",
    "develops_personal_grievance",
}

TACTIC_ADAPTATIONS = {
    "fire_magic": "fire_resistant_equipment",
    "backstab": "rear_guards_and_tighter_formations",
    "heavy_shield": "armor_piercing_weapons",
    "ambush": "increased_patrols",
    "poison": "antidotes_and_precautions",
    "frequent_retreat": "pursuit_specialists",
}

RANK_ORDER = ["soldier", "sergeant", "lieutenant", "captain", "commander"]


class NemesisSystem:
    """Tracks personal antagonists, adaptations to player tactics, and faction promotions (GDD Section 7)."""

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
        self._tactic_counts: dict[str, dict[str, int]] = {}

    def _create_event(
        self,
        event_type: str,
        timestamp: int,
        source_id: str | None = None,
        target_ids: list[str] | None = None,
        location_id: str | None = None,
        data: dict[str, Any] | None = None,
        importance: float = 0.5,
        priority: EventPriority | str | None = None,
    ) -> GameEvent:
        if self.event_bus is not None and hasattr(self.event_bus, "create_event"):
            return self.event_bus.create_event(
                event_type=event_type,
                timestamp=timestamp,
                source_id=source_id,
                target_ids=target_ids,
                location_id=location_id,
                data=data,
                importance=importance,
                priority=priority,
            )
        self._fallback_event_seq = getattr(self, "_fallback_event_seq", 0) + 1
        return GameEvent(
            id=f"ev_nem_{self._fallback_event_seq:05d}",
            event_type=event_type,
            timestamp=timestamp,
            source_id=source_id,
            target_ids=list(target_ids) if target_ids else [],
            location_id=location_id,
            data=dict(data) if data else {},
            importance=importance,
            priority=priority.value if isinstance(priority, EventPriority) else (priority or "normal"),
        )

    def evaluate_eligibility(self, npc: Character, trigger: str, world: Any = None) -> NemesisProfile | None:
        """Promote an eligible NPC to a Nemesis upon meeting an eligibility trigger."""
        if (
            getattr(npc, "tier", 1) >= 3
            or getattr(npc, "status", "alive") == "dead"
            or getattr(npc, "is_player", False)
            or getattr(npc, "is_companion", False)
        ):
            return None

        active_world = world or self.world
        npc.is_nemesis = True

        profile = None
        if active_world and hasattr(active_world, "nemesis_profiles"):
            profile = active_world.nemesis_profiles.get(npc.id)

        if not profile:
            profile = NemesisProfile(
                character_id=npc.id,
                rank=getattr(npc, "rank", "captain" if "captain" in npc.name.lower() else "soldier"),
                current_ambition="Achieve glory and revenge",
            )
            if active_world and hasattr(active_world, "nemesis_profiles"):
                active_world.nemesis_profiles[npc.id] = profile

        if trigger in ELIGIBILITY_TRIGGERS:
            profile.grudges.append(f"Triggered by {trigger}")

        return profile

    def check_eligibility(self, npc: Character, trigger: str, world: Any = None) -> NemesisProfile | None:
        return self.evaluate_eligibility(npc, trigger, world)

    def promote_to_nemesis(self, npc: Character, trigger: str = "survives_encounter", world: Any = None) -> NemesisProfile | None:
        return self.evaluate_eligibility(npc, trigger, world)

    def promote_character(self, character: Character, profile: NemesisProfile | None = None) -> str:
        """Advance character and nemesis profile rank along RANK_ORDER, clamped at commander."""
        current = getattr(character, "rank", None) or (profile.rank if profile else "soldier")
        idx = RANK_ORDER.index(current) if current in RANK_ORDER else 0
        new_rank = RANK_ORDER[min(len(RANK_ORDER) - 1, idx + 1)]

        character.rank = new_rank
        if profile is not None:
            profile.rank = new_rank

        if self.event_bus and new_rank != current:
            self.event_bus.emit(
                self._create_event(
                    event_type="NEMESIS_PROMOTED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=character.id,
                    target_ids=[character.id],
                    location_id=getattr(character, "location_id", None),
                    data={"old_rank": current, "new_rank": new_rank},
                    importance=0.8,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

        return new_rank

    def advance_rank(self, character: Character, profile: NemesisProfile | None = None) -> str:
        return self.promote_character(character, profile)

    def record_encounter(
        self,
        profile: NemesisProfile,
        grudge: str | None = None,
        hostility_delta: float = 0.0,
    ) -> None:
        """Record an encounter, grudges, and hostility shift."""
        profile.encounter_count += 1
        profile.player_hostility = min(100.0, max(0.0, profile.player_hostility + hostility_delta))
        if grudge:
            profile.grudges.append(grudge)
        if self.clock:
            profile.last_encounter_date = self.clock.timestamp

    def add_grudge(self, profile: NemesisProfile, **kwargs: Any) -> None:
        self.record_encounter(profile, **kwargs)

    def update_nemesis_from_event(self, profile: NemesisProfile, **kwargs: Any) -> None:
        self.record_encounter(profile, **kwargs)

    def record_witnessed_tactic(
        self,
        profile: NemesisProfile,
        tactic: str,
        count: int = 3,
        witnessed: bool = True,
    ) -> None:
        """Record player tactic if witnessed or confirmed, adapting once repetition >= 3 (GDD Section 7)."""
        if witnessed:
            counts = self._tactic_counts.setdefault(profile.character_id, {})
            counts[tactic] = counts.get(tactic, 0) + max(1, int(count))
            if counts[tactic] >= 3 and tactic not in profile.known_player_tactics:
                profile.known_player_tactics.append(tactic)

    def observe_tactic(self, profile: NemesisProfile, **kwargs: Any) -> None:
        self.record_witnessed_tactic(profile, **kwargs)

    def adapt_to_player(self, profile: NemesisProfile) -> list[str]:
        """Generate tactical adaptations from known witnessed player tactics."""
        new_adaptations: list[str] = []
        for tactic in profile.known_player_tactics:
            adaptation = TACTIC_ADAPTATIONS.get(tactic)
            if adaptation:
                if adaptation not in profile.special_traits:
                    profile.special_traits.append(adaptation)
                if not hasattr(profile, "adaptations"):
                    profile.adaptations = []
                if adaptation not in profile.adaptations:
                    profile.adaptations.append(adaptation)
                new_adaptations.append(adaptation)

        if self.event_bus and new_adaptations:
            self.event_bus.emit(
                self._create_event(
                    event_type="NEMESIS_ADAPTED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=profile.character_id,
                    target_ids=["player"],
                    location_id=None,
                    data={"adaptations": new_adaptations},
                    importance=0.8,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

        return new_adaptations

    def evaluate_adaptations(self, profile: NemesisProfile) -> list[str]:
        return self.adapt_to_player(profile)

    def apply_adaptations(self, profile: NemesisProfile) -> list[str]:
        return self.adapt_to_player(profile)

    def evaluate_promotion_candidates(
        self,
        faction: Any,
        target_rank: str = "commander",
        world: Any = None,
    ) -> Any:
        """Evaluate candidates for promotion. Severe injuries reduce viability (GDD Section 7)."""
        active_world = world or self.world
        members = getattr(faction, "members", [])
        candidates: list[Character] = []
        for mid in members:
            c = active_world.characters.get(mid) if active_world else None
            if c and c.status == "alive":
                candidates.append(c)

        if not candidates:
            return None

        def candidate_score(c: Character) -> float:
            score = 50.0
            personality = getattr(c, "personality", {})
            score += float(personality.get("ambition", 50.0)) * 0.4
            score += float(personality.get("loyalty", 50.0)) * 0.4

            # Penalize injuries severely
            if hasattr(c, "body") and c.body:
                for part in c.body.values():
                    if not part.functional:
                        score -= 40.0
                    for inj in part.injuries:
                        if not inj.treated:
                            score -= inj.severity * 25.0
            return score

        best = max(candidates, key=candidate_score)
        best.rank = target_rank

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="RIVAL_PROMOTED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=faction.id,
                    target_ids=[best.id],
                    location_id="barracks",
                    data={"new_rank": target_rank},
                    importance=0.85,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

        return best

    def resolve_promotion(self, *args: Any, **kwargs: Any) -> Any:
        return self.evaluate_promotion_candidates(*args, **kwargs)

    def promote_best_candidate(self, *args: Any, **kwargs: Any) -> Any:
        return self.evaluate_promotion_candidates(*args, **kwargs)

    def resolve_defeat_outcome(
        self,
        character: Character,
        outcome: str,
        world: Any = None,
    ) -> dict[str, Any]:
        """Apply one of 7 defeat/survival outcomes (GDD Section 7)."""
        active_world = world or self.world
        if outcome == "execution":
            character.status = "dead"
        elif outcome == "recruitment":
            character.is_companion = True
            if active_world and hasattr(active_world, "player_party"):
                if character.id not in active_world.player_party:
                    active_world.player_party.append(character.id)
        elif outcome == "capture":
            character.status = "captured"
            character.location_id = "prison"
        elif outcome == "hospitalization":
            character.location_id = "infirmary"
        elif outcome == "permanent_disability":
            if hasattr(character, "body") and "left_arm" in character.body:
                character.body["left_arm"].functional = False

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="NEMESIS_DEFEATED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id="player",
                    target_ids=[character.id],
                    location_id=character.location_id,
                    data={"outcome": outcome},
                    importance=0.8,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

        return {"outcome": outcome, "character_id": character.id}

    def apply_defeat_outcome(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.resolve_defeat_outcome(*args, **kwargs)
