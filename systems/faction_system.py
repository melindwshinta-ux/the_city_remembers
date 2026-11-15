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

    # --- Player-Driven Political Operations (GEMINI_PLAN §5.1) ---

    @staticmethod
    def _spend_player_wealth(active_world: Any, amount: float) -> tuple[bool, float]:
        cost = max(0.0, float(amount))
        if cost == 0.0:
            return True, 0.0
        player = active_world.characters.get("player") if active_world and hasattr(active_world, "characters") else None
        if player is None:
            return False, 0.0
        wealth = float(player.needs.get("wealth", 0.0))
        if wealth < cost:
            return False, wealth
        player.needs["wealth"] = max(0.0, wealth - cost)
        return True, player.needs["wealth"]

    def petition_faction_leader(
        self,
        faction_id: str,
        request_type: str = "support",
        world: Any = None,
    ) -> dict[str, Any]:
        """Petition a faction leader for support, contract, or protection."""
        active_world = world or self.world
        if not active_world:
            return {"success": False, "reason": "no_world"}
        faction = active_world.factions.get(faction_id)
        if not faction:
            return {"success": False, "reason": "faction_not_found", "faction_id": faction_id}

        rep_map = active_world.reputation.setdefault("faction", {})
        standing = float(rep_map.get(faction_id, 0.0))
        if standing < -20.0:
            return {"success": False, "reason": "hostile_standing", "standing": standing}

        player = active_world.characters.get("player")
        grant = 40.0 if request_type == "contract" else 25.0
        if player is not None:
            player.needs["wealth"] = float(player.needs.get("wealth", 0.0)) + grant
        rep_map[faction_id] = min(100.0, standing + 5.0)
        faction.influence = min(100.0, float(faction.influence) + 2.0)

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="FACTION_PETITIONED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id="player",
                    target_ids=[faction_id],
                    location_id=faction.territories[0] if faction.territories else "lowtown",
                    data={"request_type": request_type, "grant": grant},
                    importance=0.6,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

        return {
            "success": True,
            "faction_id": faction_id,
            "leader_id": faction.leader_id,
            "request_type": request_type,
            "gold_granted": grant,
            "faction_reputation": rep_map[faction_id],
        }

    def donate_to_faction(
        self,
        faction_id: str,
        amount: float = 50.0,
        world: Any = None,
    ) -> dict[str, Any]:
        """Donate gold to a faction treasury (+Legitimacy, +Faction Rep)."""
        active_world = world or self.world
        if not active_world:
            return {"success": False, "reason": "no_world"}
        faction = active_world.factions.get(faction_id)
        if not faction:
            return {"success": False, "reason": "faction_not_found", "faction_id": faction_id}

        amt = max(1.0, float(amount))
        ok, rem = self._spend_player_wealth(active_world, amt)
        if not ok:
            return {"success": False, "reason": "insufficient_wealth", "cost": amt, "wealth": rem}

        faction.wealth = min(100.0, float(faction.wealth) + round(amt * 0.2, 2))
        faction.public_legitimacy = min(100.0, float(faction.public_legitimacy) + round(amt * 0.15, 2))
        rep_map = active_world.reputation.setdefault("faction", {})
        rep_map[faction_id] = min(100.0, float(rep_map.get(faction_id, 0.0)) + round(amt * 0.25, 2))

        return {
            "success": True,
            "faction_id": faction_id,
            "donated": amt,
            "public_legitimacy": faction.public_legitimacy,
            "faction_reputation": rep_map[faction_id],
        }

    def broker_truce(
        self,
        faction_a: str,
        faction_b: str,
        cost: float = 50.0,
        world: Any = None,
    ) -> dict[str, Any]:
        """Broker a truce between two factions, improving bidirectional relations."""
        active_world = world or self.world
        if not active_world:
            return {"success": False, "reason": "no_world"}
        if faction_a == faction_b or faction_a not in active_world.factions or faction_b not in active_world.factions:
            return {"success": False, "reason": "invalid_factions"}

        ok, rem = self._spend_player_wealth(active_world, cost)
        if not ok:
            return {"success": False, "reason": "insufficient_wealth", "cost": cost, "wealth": rem}

        rel_ab = self.get_relation(faction_a, faction_b, world=active_world)
        rel_ba = self.get_relation(faction_b, faction_a, world=active_world)
        new_ab = min(100.0, rel_ab + 30.0)
        new_ba = min(100.0, rel_ba + 30.0)
        self.set_relation(faction_a, faction_b, new_ab, world=active_world)
        self.set_relation(faction_b, faction_a, new_ba, world=active_world)

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="TRUCE_BROKERED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id="player",
                    target_ids=[faction_a, faction_b],
                    location_id=None,
                    data={"relation_ab": new_ab, "relation_ba": new_ba},
                    importance=0.75,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

        return {"success": True, "faction_a": faction_a, "faction_b": faction_b, "relation_ab": new_ab, "relation_ba": new_ba}

    def incite_turf_war(
        self,
        faction_a: str,
        faction_b: str,
        district_id: str = "lowtown",
        cost: float = 40.0,
        world: Any = None,
    ) -> dict[str, Any]:
        """Incite a turf war between two factions in a district."""
        active_world = world or self.world
        if not active_world:
            return {"success": False, "reason": "no_world"}
        if faction_a == faction_b or faction_a not in active_world.factions or faction_b not in active_world.factions:
            return {"success": False, "reason": "invalid_factions"}

        ok, rem = self._spend_player_wealth(active_world, cost)
        if not ok:
            return {"success": False, "reason": "insufficient_wealth", "cost": cost, "wealth": rem}

        rel_ab = self.get_relation(faction_a, faction_b, world=active_world)
        rel_ba = self.get_relation(faction_b, faction_a, world=active_world)
        new_ab = max(-100.0, rel_ab - 35.0)
        new_ba = max(-100.0, rel_ba - 35.0)
        self.set_relation(faction_a, faction_b, new_ab, world=active_world)
        self.set_relation(faction_b, faction_a, new_ba, world=active_world)

        district = active_world.districts.get(district_id)
        if district is not None:
            district.unrest = min(100.0, float(district.unrest) + 15.0)
            district.security = max(0.0, float(district.security) - 10.0)

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="POLITICAL_CONFLICT_STARTED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id="player",
                    target_ids=[faction_a, faction_b],
                    location_id=district_id,
                    data={"district_id": district_id, "relation_ab": new_ab, "relation_ba": new_ba},
                    importance=0.85,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

        return {"success": True, "faction_a": faction_a, "faction_b": faction_b, "district_id": district_id, "relation_ab": new_ab}

    def pay_off_bounty(
        self,
        amount: float = 50.0,
        district_id: str | None = None,
        world: Any = None,
    ) -> dict[str, Any]:
        """Pay off City Guard bounty and clear criminal suspicion record."""
        active_world = world or self.world
        if not active_world:
            return {"success": False, "reason": "no_world"}

        ok, rem = self._spend_player_wealth(active_world, amount)
        if not ok:
            return {"success": False, "reason": "insufficient_wealth", "cost": amount, "wealth": rem}

        active_world.flags["bounty"] = 0.0
        active_world.flags["wanted"] = False
        rep_map = active_world.reputation.setdefault("faction", {})
        rep_map["city_guard"] = min(100.0, float(rep_map.get("city_guard", 0.0)) + 10.0)

        return {"success": True, "paid": amount, "bounty": 0.0, "city_guard_reputation": rep_map["city_guard"]}

    def smear_campaign(
        self,
        target_id: str,
        district_id: str = "lowtown",
        cost: float = 30.0,
        world: Any = None,
    ) -> dict[str, Any]:
        """Plant false rumors via RumorSystem to smear a faction or Nemesis officer."""
        from systems.rumor_system import RumorSystem

        active_world = world or self.world
        if not active_world:
            return {"success": False, "reason": "no_world"}

        ok, rem = self._spend_player_wealth(active_world, cost)
        if not ok:
            return {"success": False, "reason": "insufficient_wealth", "cost": cost, "wealth": rem}

        rumor_sys = RumorSystem(
            event_bus=self.event_bus or getattr(active_world, "event_bus", None),
            clock=self.clock or getattr(active_world, "clock", None),
            rng=self.rng or getattr(active_world, "rng", None),
            world=active_world,
        )
        rumor = rumor_sys.plant_false_rumor(
            actor_id="player",
            subject=target_id,
            claim=f"{target_id} is secretly embezzling relief funds and conspiring against {district_id}.",
            district_id=district_id,
            truth=False,
            world=active_world,
        )

        if target_id in active_world.factions:
            fac = active_world.factions[target_id]
            fac.public_legitimacy = max(0.0, float(fac.public_legitimacy) - 10.0)
            self.world = active_world
            self.shift_district_influence(district_id, target_id, -6.0)
        if target_id in active_world.nemesis_profiles:
            prof = active_world.nemesis_profiles[target_id]
            prof.player_respect = max(-100.0, float(prof.player_respect) - 10.0)

        return {"success": True, "target_id": target_id, "district_id": district_id, "rumor_id": rumor.id}

    def sabotage_district(
        self,
        district_id: str,
        target_metric: str = "security",
        cost: float = 35.0,
        world: Any = None,
    ) -> dict[str, Any]:
        """Sabotage district infrastructure and incite unrest."""
        active_world = world or self.world
        if not active_world:
            return {"success": False, "reason": "no_world"}
        district = active_world.districts.get(district_id)
        if not district:
            return {"success": False, "reason": "district_not_found", "district_id": district_id}

        ok, rem = self._spend_player_wealth(active_world, cost)
        if not ok:
            return {"success": False, "reason": "insufficient_wealth", "cost": cost, "wealth": rem}

        district.infrastructure_condition = max(0.0, float(district.infrastructure_condition) - 15.0)
        district.unrest = min(100.0, float(district.unrest) + 15.0)
        if target_metric == "wealth":
            district.wealth = max(0.0, float(district.wealth) - 10.0)
        else:
            district.security = max(0.0, float(district.security) - 12.0)

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="DISTRICT_SABOTAGED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id="player",
                    target_ids=[district_id],
                    location_id=district_id,
                    data={"target_metric": target_metric, "unrest": district.unrest},
                    importance=0.8,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

        return {
            "success": True,
            "district_id": district_id,
            "infrastructure_condition": district.infrastructure_condition,
            "unrest": district.unrest,
            "security": district.security,
        }

    def sponsor_civic_edict(
        self,
        district_id: str,
        edict_type: str,
        cost: float = 60.0,
        world: Any = None,
    ) -> dict[str, Any]:
        """Sponsor a civic edict: soup_kitchens, private_watch_patrols, or festival."""
        active_world = world or self.world
        if not active_world:
            return {"success": False, "reason": "no_world"}
        district = active_world.districts.get(district_id)
        if not district:
            return {"success": False, "reason": "district_not_found", "district_id": district_id}
        if edict_type not in ("soup_kitchens", "private_watch_patrols", "festival"):
            return {"success": False, "reason": "unknown_edict", "edict_type": edict_type}

        ok, rem = self._spend_player_wealth(active_world, cost)
        if not ok:
            return {"success": False, "reason": "insufficient_wealth", "cost": cost, "wealth": rem}

        if edict_type == "soup_kitchens":
            district.food_supply = min(100.0, float(district.food_supply) + 20.0)
            district.public_opinion = min(100.0, float(district.public_opinion) + 15.0)
        elif edict_type == "private_watch_patrols":
            district.security = min(100.0, float(district.security) + 18.0)
            district.crime = max(0.0, float(district.crime) - 15.0)
        elif edict_type == "festival":
            district.unrest = max(0.0, float(district.unrest) - 20.0)
            district.public_opinion = min(100.0, float(district.public_opinion) + 10.0)

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="CIVIC_EDICT_SPONSORED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id="player",
                    target_ids=[district_id],
                    location_id=district_id,
                    data={"edict_type": edict_type},
                    importance=0.7,
                    priority=EventPriority.NORMAL,
                ),
                priority=EventPriority.NORMAL,
            )

        return {
            "success": True,
            "district_id": district_id,
            "edict_type": edict_type,
            "food_supply": district.food_supply,
            "security": district.security,
            "crime": district.crime,
            "unrest": district.unrest,
            "public_opinion": district.public_opinion,
        }

    def back_internal_coup(
        self,
        faction_id: str,
        instigator_id: str | None = None,
        bribe_amount: float = 100.0,
        world: Any = None,
    ) -> dict[str, Any]:
        """Back an internal faction coup leveraging AmbitionAI and NemesisSystem."""
        from ai.ambition_ai import AmbitionAI
        from systems.nemesis_system import NemesisSystem

        active_world = world or self.world
        if not active_world:
            return {"success": False, "reason": "no_world"}
        faction = active_world.factions.get(faction_id)
        if not faction:
            return {"success": False, "reason": "faction_not_found", "faction_id": faction_id}

        ambition_ai = AmbitionAI(world=active_world)
        candidates: list[Character] = []
        for mid in faction.members:
            if mid == faction.leader_id:
                continue
            c = active_world.characters.get(mid)
            if c and getattr(c, "status", "alive") == "alive":
                candidates.append(c)

        if not candidates:
            return {"success": False, "reason": "no_coup_candidates"}

        chosen: Character | None = None
        if instigator_id is not None:
            chosen = next((c for c in candidates if c.id == instigator_id), None)
        if chosen is None:
            # Prefer AmbitionAI betray_superior candidates, else highest ambition
            for cand in candidates:
                res = ambition_ai.evaluate_npc_ambitions(cand, world=active_world)
                if res.get("action") == "betray_superior":
                    chosen = cand
                    break
            if chosen is None:
                chosen = max(candidates, key=lambda c: float(getattr(c, "personality", {}).get("ambition", 50.0)))

        ok, rem = self._spend_player_wealth(active_world, bribe_amount)
        if not ok:
            return {"success": False, "reason": "insufficient_wealth", "cost": bribe_amount, "wealth": rem}

        old_leader_id = faction.leader_id
        faction.leader_id = chosen.id
        faction.stability = max(10.0, float(faction.stability) - 15.0)
        chosen.rank = "commander"

        if chosen.id in active_world.nemesis_profiles:
            nem_sys = NemesisSystem(event_bus=self.event_bus, clock=self.clock, rng=self.rng, world=active_world)
            nem_sys.promote_character(chosen, active_world.nemesis_profiles[chosen.id])

        if self.event_bus:
            self.event_bus.emit(
                self._create_event(
                    event_type="INTERNAL_COUP_EXECUTED",
                    timestamp=self.clock.timestamp if self.clock else 0,
                    source_id="player",
                    target_ids=[faction_id, chosen.id],
                    location_id=faction.territories[0] if faction.territories else "lowtown",
                    data={"old_leader": old_leader_id, "new_leader": chosen.id},
                    importance=0.9,
                    priority=EventPriority.CRITICAL,
                ),
                priority=EventPriority.CRITICAL,
            )

        return {
            "success": True,
            "faction_id": faction_id,
            "old_leader_id": old_leader_id,
            "new_leader_id": chosen.id,
            "stability": faction.stability,
        }

    # --- Procedural Petitioners (GEMINI_PLAN §5.1) ---

    def generate_petitioners(
        self,
        world: Any = None,
        location_type: str = "safehouse",
        count: int | None = None,
    ) -> list[dict[str, Any]]:
        """Generate 1-3 procedural petitioners when resting at a Safehouse or Tavern."""
        active_world = world or self.world
        rng = getattr(active_world, "rng", None) or self.rng
        num = count if count is not None else (rng.randint("petitioner_count", 1, 3) if rng else 2)
        num = max(1, min(3, int(num)))

        templates = [
            {
                "role": "merchant",
                "name": "Peddler Hobb",
                "district_id": "lowtown",
                "request": "Syndicate runners are demanding double protection fees at the market.",
                "choices": [
                    {"idx": 1, "label": "Pay off his debt (20g)", "effect": "pay_debt"},
                    {"idx": 2, "label": "Promise Guard patrol protection", "effect": "boost_security"},
                    {"idx": 3, "label": "Demand a cut of his profits (+15g)", "effect": "extort_cut"},
                    {"idx": 4, "label": "Turn him away", "effect": "dismiss"},
                ],
            },
            {
                "role": "informant",
                "name": "Whispering Pip",
                "district_id": "harbor",
                "request": "I overheard smuggler captains moving untaxed crates under Pier Four tonight.",
                "choices": [
                    {"idx": 1, "label": "Pay 15g for full manifest", "effect": "buy_intel"},
                    {"idx": 2, "label": "Pass tip to City Guard", "effect": "tip_guard"},
                    {"idx": 3, "label": "Alert the Syndicate instead", "effect": "tip_syndicate"},
                    {"idx": 4, "label": "Ignore the rumor", "effect": "dismiss"},
                ],
            },
            {
                "role": "citizen",
                "name": "Widow Mara",
                "district_id": "lowtown",
                "request": "Tenement families are going hungry after the grain cart tax hike.",
                "choices": [
                    {"idx": 1, "label": "Donate 25g for bread", "effect": "charity"},
                    {"idx": 2, "label": "Rally neighbors to petition Watch", "effect": "civic_rally"},
                    {"idx": 3, "label": "Offer work at your properties", "effect": "hire_labor"},
                    {"idx": 4, "label": "Send her away", "effect": "dismiss"},
                ],
            },
            {
                "role": "faction_envoy",
                "name": "Envoy Corin",
                "district_id": "iron_ward",
                "request": "The Union seeks a discreet intermediary for foundry wage talks.",
                "choices": [
                    {"idx": 1, "label": "Mediate fairly (+Union Rep)", "effect": "mediate"},
                    {"idx": 2, "label": "Fund strike relief (30g)", "effect": "fund_strike"},
                    {"idx": 3, "label": "Sabotage talks for Consortium", "effect": "sabotage_talks"},
                    {"idx": 4, "label": "Decline involvement", "effect": "dismiss"},
                ],
            },
        ]

        selected: list[dict[str, Any]] = []
        pool = list(templates)
        for i in range(num):
            idx = rng.randint("pet_tpl", 0, len(pool) - 1) if rng else (i % len(pool))
            tpl = dict(pool.pop(idx))
            tpl["id"] = f"pet_{i + 1}_{rng.randint('pet_id', 100, 999) if rng else (i + 100)}"
            tpl["location_type"] = location_type
            selected.append(tpl)
        return selected

    def resolve_petitioner(
        self,
        world: Any,
        petitioner: dict[str, Any],
        choice_idx: int | str,
    ) -> dict[str, Any]:
        """Resolve a petitioner's request using choice [1]-[4]."""
        active_world = world or self.world
        idx = int(choice_idx)
        choices = petitioner.get("choices", [])
        chosen = next((c for c in choices if int(c.get("idx", 0)) == idx), None)
        if chosen is None:
            return {"success": False, "reason": "invalid_choice", "choice_idx": idx}

        effect = chosen.get("effect", "dismiss")
        district_id = petitioner.get("district_id", "lowtown")
        district = active_world.districts.get(district_id) if active_world and hasattr(active_world, "districts") else None
        rep_map = active_world.reputation.setdefault("faction", {}) if active_world else {}
        player = active_world.characters.get("player") if active_world and hasattr(active_world, "characters") else None

        if effect in ("pay_debt", "buy_intel", "charity", "fund_strike"):
            cost_map = {"pay_debt": 20.0, "buy_intel": 15.0, "charity": 25.0, "fund_strike": 30.0}
            cost = cost_map[effect]
            ok, rem = self._spend_player_wealth(active_world, cost)
            if not ok:
                return {"success": False, "reason": "insufficient_wealth", "cost": cost, "wealth": rem}
            if effect == "charity" and district:
                district.food_supply = min(100.0, float(district.food_supply) + 6.0)
                district.public_opinion = min(100.0, float(district.public_opinion) + 5.0)
            elif effect == "pay_debt" and district:
                district.public_opinion = min(100.0, float(district.public_opinion) + 5.0)
            elif effect == "buy_intel" and active_world:
                active_world.flags["harbor_smuggler_intel"] = True
            elif effect == "fund_strike":
                rep_map["iron_workers_union"] = min(100.0, float(rep_map.get("iron_workers_union", 0.0)) + 10.0)
        elif effect == "extort_cut" and player is not None:
            player.needs["wealth"] = float(player.needs.get("wealth", 0.0)) + 15.0
            if district:
                district.public_opinion = max(0.0, float(district.public_opinion) - 5.0)
        elif effect == "boost_security" and district:
            district.security = min(100.0, float(district.security) + 4.0)
        elif effect == "tip_guard":
            rep_map["city_guard"] = min(100.0, float(rep_map.get("city_guard", 0.0)) + 8.0)
        elif effect == "tip_syndicate":
            rep_map["lowtown_syndicate"] = min(100.0, float(rep_map.get("lowtown_syndicate", 0.0)) + 8.0)
        elif effect == "civic_rally" and district:
            district.unrest = max(0.0, float(district.unrest) - 5.0)
        elif effect == "hire_labor" and district:
            district.employment = min(100.0, float(district.employment) + 4.0)
        elif effect == "mediate":
            rep_map["iron_workers_union"] = min(100.0, float(rep_map.get("iron_workers_union", 0.0)) + 8.0)
        elif effect == "sabotage_talks":
            rep_map["merchant_consortium"] = min(100.0, float(rep_map.get("merchant_consortium", 0.0)) + 8.0)
            if district:
                district.unrest = min(100.0, float(district.unrest) + 8.0)

        return {
            "success": True,
            "petitioner_id": petitioner.get("id"),
            "choice_idx": idx,
            "effect": effect,
            "label": chosen.get("label", ""),
        }


def generate_petitioners(world: Any, location_type: str = "safehouse", count: int | None = None) -> list[dict[str, Any]]:
    return FactionSystem(world=world).generate_petitioners(world=world, location_type=location_type, count=count)


def resolve_petitioner(world: Any, petitioner: dict[str, Any], choice_idx: int | str) -> dict[str, Any]:
    return FactionSystem(world=world).resolve_petitioner(world=world, petitioner=petitioner, choice_idx=choice_idx)
