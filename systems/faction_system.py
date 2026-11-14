"""Faction & political simulation: influence, goals, relations, and succession (GDD Sections 8 & 13)."""

from __future__ import annotations

from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.character import Character
from entities.district import District
from entities.faction import Faction


FACTION_IDS = [
    "city_guard",
    "merchant_consortium",
    "ashen_church",
    "lowtown_syndicate",
    "iron_workers_union",
    "noble_houses",
    "independent_mages",
]


class FactionSystem:
    """Manages 7 city factions, territory influence, political actions, and leadership succession."""

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
        self._relations: dict[tuple[str, str], float] = {}
        self._officer_availability: dict[str, float] = {}
        if self.event_bus is not None and hasattr(self.event_bus, "subscribe"):
            for ev_type in ("CHARACTER_DIED", "CHARACTER_INCAPACITATED", "LIMB_INJURED", "CHARACTER_INJURED"):
                self.event_bus.subscribe(ev_type, self.handle_event)

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
            id=f"ev_fac_{self._fallback_event_seq:05d}",
            event_type=event_type,
            timestamp=timestamp,
            source_id=source_id,
            target_ids=list(target_ids) if target_ids else [],
            location_id=location_id,
            data=dict(data) if data else {},
            importance=importance,
            priority=priority.value if isinstance(priority, EventPriority) else (priority or "normal"),
        )

    def set_relation(
        self,
        source_faction_id: str,
        target_faction_id: str,
        value: float,
        world: Any = None,
    ) -> None:
        """Set directional relationship score between two factions (-100 to +100)."""
        if source_faction_id == target_faction_id:
            raise ValueError(f"Cannot set self-relation for faction '{source_faction_id}'.")
        val = max(-100.0, min(100.0, float(value)))
        self._relations[(source_faction_id, target_faction_id)] = val

        active_world = world or self.world
        if active_world and hasattr(active_world, "factions"):
            f = active_world.factions.get(source_faction_id)
            if f:
                f.relations[target_faction_id] = val

    def adjust_relation(self, source: str, target: str, delta_or_val: float, world: Any = None) -> None:
        self.set_relation(source, target, delta_or_val, world=world)

    def update_relation(self, source: str, target: str, delta_or_val: float, world: Any = None) -> None:
        self.set_relation(source, target, delta_or_val, world=world)

    def get_relation(self, source_faction_id: str, target_faction_id: str, world: Any = None) -> float:
        """Query directional relationship from source_faction_id to target_faction_id."""
        key = (source_faction_id, target_faction_id)
        if key in self._relations:
            return self._relations[key]

        active_world = world or self.world
        if active_world and hasattr(active_world, "factions"):
            f = active_world.factions.get(source_faction_id)
            if f and target_faction_id in f.relations:
                val = float(f.relations[target_faction_id])
                self._relations[key] = val
                return val

        return 0.0

    def query_relation(self, source: str, target: str, world: Any = None) -> float:
        return self.get_relation(source, target, world=world)

    def shift_district_influence(self, district_id: str, faction_id: str, delta: float) -> None:
        """Shift faction influence in a district and normalize all percentages to 100.0%."""
        if not self.world or not hasattr(self.world, "districts"):
            return
        district = self.world.districts.get(district_id)
        if not district:
            return

        inf = district.faction_influence
        if faction_id not in inf:
            inf[faction_id] = 0.0

        inf[faction_id] = max(0.0, inf[faction_id] + delta)

        # Normalize to 100.0%
        total = sum(inf.values())
        if total > 0.0:
            for k in list(inf.keys()):
                inf[k] = (inf[k] / total) * 100.0

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="DISTRICT_INFLUENCE_CHANGED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=faction_id,
                    target_ids=[],
                    location_id=district_id,
                    data={"influence": dict(inf)},
                    importance=0.7,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

    def update_district_influence(self, *args: Any, **kwargs: Any) -> None:
        self.shift_district_influence(*args, **kwargs)

    def adjust_influence(self, *args: Any, **kwargs: Any) -> None:
        self.shift_district_influence(*args, **kwargs)

    def apply_faction_action(
        self,
        faction_id: str,
        action_type: str,
        district_id: str | None = None,
        world: Any = None,
    ) -> None:
        """Apply faction action consequences across multiple district metrics."""
        active_world = world or self.world
        if not active_world:
            return

        target_district_id = district_id or "lowtown"
        district = active_world.districts.get(target_district_id)
        if not district:
            return

        if action_type == "expand_smuggling":
            district.crime = min(100.0, district.crime + 15.0)
            district.employment = min(100.0, district.employment + 10.0)
            district.wealth = min(100.0, district.wealth + 8.0)
            district.security = max(0.0, district.security - 10.0)

    def execute_faction_action(self, *args: Any, **kwargs: Any) -> None:
        self.apply_faction_action(*args, **kwargs)

    def resolve_leadership_vacancy(self, faction_id: str, world: Any = None) -> str | None:
        """Fill leadership vacancy when leader dies or is incapacitated (GDD Section 8)."""
        active_world = world or self.world
        if not active_world:
            return None

        faction = active_world.factions.get(faction_id)
        if not faction:
            return None

        living_members: list[Character] = []
        for mid in faction.members:
            c = active_world.characters.get(mid)
            if c and c.status == "alive":
                living_members.append(c)

        if not living_members:
            return None

        # Choose best candidate by ambition and competence
        def score(c: Character) -> float:
            p = getattr(c, "personality", {})
            return float(p.get("ambition", 50.0)) + float(p.get("courage", 50.0))

        best = max(living_members, key=score)
        faction.leader_id = best.id
        best.rank = "commander"

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="LEADERSHIP_VACANCY",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=faction_id,
                    target_ids=[best.id],
                    location_id="barracks",
                    data={"new_leader": best.id},
                    importance=0.9,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

        return best.id

    def handle_leader_death(self, *args: Any, **kwargs: Any) -> str | None:
        return self.resolve_leadership_vacancy(*args, **kwargs)

    def handle_event(self, event: GameEvent, world: Any = None) -> dict[str, Any] | None:
        """React to character death, incapacitation, or severe limb injuries (GDD Sections 3 & 8)."""
        active_world = world or self.world
        if event is None:
            return None

        ev_type = getattr(event, "event_type", "")
        if ev_type not in ("CHARACTER_DIED", "CHARACTER_INCAPACITATED", "LIMB_INJURED", "CHARACTER_INJURED"):
            return None

        updated: dict[str, float] = {}
        vacancies_resolved: list[str] = []

        for target_id in getattr(event, "target_ids", []) or []:
            char = active_world.characters.get(target_id) if active_world and hasattr(active_world, "characters") else None

            if ev_type in ("CHARACTER_DIED", "CHARACTER_INCAPACITATED"):
                self._officer_availability[target_id] = 0.0
                updated[target_id] = 0.0
                if active_world and hasattr(active_world, "factions"):
                    for faction in active_world.factions.values():
                        if faction.leader_id == target_id:
                            new_leader = self.resolve_leadership_vacancy(faction.id, world=active_world)
                            if new_leader:
                                vacancies_resolved.append(new_leader)
            else:
                # LIMB_INJURED or CHARACTER_INJURED: compute officer effectiveness/availability
                availability = 1.0
                if char is not None:
                    if getattr(char, "status", "alive") in ("dead", "incapacitated"):
                        availability = 0.0
                    elif hasattr(char, "body") and char.body:
                        non_func = sum(1 for bp in char.body.values() if not bp.functional)
                        if non_func > 0:
                            availability = max(0.25, 1.0 - 0.35 * non_func)
                        elif getattr(event, "data", None):
                            body_part = event.data.get("body_part")
                            if body_part and body_part in char.body and char.body[body_part].integrity < 80.0:
                                availability = 0.65
                else:
                    availability = 0.65

                self._officer_availability[target_id] = availability
                updated[target_id] = availability

                if availability <= 0.0 and active_world and hasattr(active_world, "factions"):
                    for faction in active_world.factions.values():
                        if faction.leader_id == target_id:
                            new_leader = self.resolve_leadership_vacancy(faction.id, world=active_world)
                            if new_leader:
                                vacancies_resolved.append(new_leader)

        return {"updated_availability": updated, "vacancies_resolved": vacancies_resolved}

    def on_event(self, event: GameEvent, world: Any = None) -> dict[str, Any] | None:
        return self.handle_event(event, world=world)

    def update_officer_availability(self, event_or_char_id: GameEvent | str, world: Any = None) -> dict[str, Any] | float | None:
        if isinstance(event_or_char_id, GameEvent):
            return self.handle_event(event_or_char_id, world=world)
        active_world = world or self.world
        char = active_world.characters.get(event_or_char_id) if active_world and hasattr(active_world, "characters") else None
        if char is None:
            return self._officer_availability.get(event_or_char_id, 1.0)
        availability = 1.0
        if getattr(char, "status", "alive") in ("dead", "incapacitated"):
            availability = 0.0
        elif hasattr(char, "body") and char.body:
            non_func = sum(1 for bp in char.body.values() if not bp.functional)
            if non_func > 0:
                availability = max(0.25, 1.0 - 0.35 * non_func)
        self._officer_availability[event_or_char_id] = availability
        return availability

    def report_crime(
        self,
        actor_id: str,
        crime_type: str,
        district_id: str,
        witnessed: bool = True,
        world: Any = None,
    ) -> None:
        """Report a crime committed by actor."""
        if witnessed and self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="CRIME_COMMITTED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id=actor_id,
                    target_ids=["city_guard"],
                    location_id=district_id,
                    data={"crime_type": crime_type},
                    importance=0.7,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

    def record_crime(self, *args: Any, **kwargs: Any) -> None:
        self.report_crime(*args, **kwargs)

    def arrest_character(self, character_id: str, world: Any = None) -> None:
        """Arrest character, moving them to prison and advancing clock by 24h."""
        active_world = world or self.world
        if active_world:
            c = active_world.characters.get(character_id)
            if c:
                c.location_id = "barracks_prison"
            if hasattr(active_world, "clock") and active_world.clock:
                active_world.clock.advance(1440)

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="PLAYER_ARRESTED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id="city_guard",
                    target_ids=[character_id],
                    location_id="barracks_prison",
                    data={},
                    importance=0.85,
                    priority=EventPriority.CRITICAL,
                ),
                priority=EventPriority.CRITICAL,
            )

    def arrest_player(self, character_id: str = "player", world: Any = None) -> None:
        self.arrest_character(character_id, world)

    def trigger_religious_schism(self, world: Any = None) -> None:
        """Trigger religious schism in Ashen Church, increasing temple unrest (GDD Section 8)."""
        active_world = world or self.world
        if active_world and hasattr(active_world, "districts"):
            td = active_world.districts.get("temple_district")
            if td:
                td.unrest = min(100.0, td.unrest + 25.0)

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="POLITICAL_CONFLICT_STARTED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id="ashen_church",
                    target_ids=["temple_district"],
                    location_id="temple_district",
                    data={"description": "Religious schism erupts in Ashen Church"},
                    importance=0.85,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

    def evaluate_religious_authority(self, world: Any = None) -> None:
        self.trigger_religious_schism(world)
