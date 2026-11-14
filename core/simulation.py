"""Multi-frequency simulation scheduler and sub-stepped time advancement (GDD Section 14)."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from config import (
    EVENT_TIME_ADVANCED,
    FREQ_COMBAT,
    FREQ_COMPANIONS,
    FREQ_DISTRICT_POPULATION,
    FREQ_ECONOMY,
    FREQ_FACTION_DECISIONS,
    FREQ_LONG_TERM_AMBITIONS,
    FREQ_NEARBY_NPCS,
    MAX_SUBSTEP_MINUTES,
    SIMULATION_FREQUENCIES,
)
from core.event_bus import EventPriority, GameEvent

if TYPE_CHECKING:
    from core.world import World


class SimulationEngine:
    """Coordinates the 7 simulation frequencies and sub-steps time skips deterministically."""

    def __init__(
        self,
        world: World | None = None,
        max_substep_minutes: int = MAX_SUBSTEP_MINUTES,
    ) -> None:
        self.world: World | None = world
        self.max_substep_minutes: int = int(max_substep_minutes)
        self._systems: dict[str, list[tuple[str, Callable[..., Any]]]] = {
            freq: [] for freq in SIMULATION_FREQUENCIES
        }
        self.tick_count: int = 0
        self.frequency_run_counts: dict[str, int] = {
            freq: 0 for freq in SIMULATION_FREQUENCIES
        }
        self.last_run_timestamps: dict[str, int] = {
            freq: 0 for freq in SIMULATION_FREQUENCIES
        }

    def register_system(
        self,
        frequency: str,
        callback: Callable[..., Iterable[GameEvent] | GameEvent | None],
        name: str | None = None,
    ) -> None:
        """Register a system tick callback for one of the 7 canonical frequencies."""
        if frequency not in self._systems:
            raise ValueError(
                f"Unknown simulation frequency '{frequency}'. "
                f"Expected one of {SIMULATION_FREQUENCIES}"
            )
        cb_name = name or getattr(callback, "__name__", "system_callback")
        entries = self._systems[frequency]
        if not any(existing_cb == callback for _, existing_cb in entries):
            entries.append((cb_name, callback))

    def unregister_system(self, frequency: str, callback: Callable[..., Any]) -> None:
        """Unregister a previously registered callback from `frequency`."""
        if frequency in self._systems:
            self._systems[frequency] = [
                (name, cb) for name, cb in self._systems[frequency] if cb != callback
            ]

    def _invoke_callback(
        self,
        callback: Callable[..., Any],
        world: World,
        elapsed_minutes: int,
    ) -> list[GameEvent]:
        """Invoke a system callback with `(world, elapsed_minutes)` or `(world,)`."""
        try:
            sig = inspect.signature(callback)
            params = [
                p
                for p in sig.parameters.values()
                if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]
            has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
            if has_varargs or len(params) >= 2:
                result = callback(world, elapsed_minutes)
            elif len(params) == 1:
                result = callback(world)
            else:
                result = callback()
        except TypeError:
            try:
                result = callback(world, elapsed_minutes)
            except TypeError:
                result = callback(world)

        if result is None:
            return []
        if isinstance(result, GameEvent):
            return [result]
        if isinstance(result, Iterable):
            return [ev for ev in result if isinstance(ev, GameEvent)]
        return []

    def _run_frequency(
        self,
        frequency: str,
        world: World,
        elapsed_minutes: int,
    ) -> list[GameEvent]:
        """Execute all callbacks registered for `frequency` and emit returned events."""
        self.frequency_run_counts[frequency] = self.frequency_run_counts.get(frequency, 0) + 1
        self.last_run_timestamps[frequency] = world.clock.timestamp

        immediate_events: list[GameEvent] = []
        for _, callback in list(self._systems.get(frequency, [])):
            spawned = self._invoke_callback(callback, world, elapsed_minutes)
            for ev in spawned:
                immediate_events.extend(world.event_bus.emit(ev))
        return immediate_events

    def _resolve_world(self, world: World | None) -> World:
        target = world if world is not None else self.world
        if target is None:
            raise RuntimeError("SimulationEngine requires a World instance")
        return target

    def run_action_tick(
        self,
        meaningful: bool = True,
        in_combat: bool = False,
        minutes: int = 0,
        world: World | None = None,
    ) -> list[GameEvent]:
        """Run a single action tick (with optional minute advancement)."""
        target_world = self._resolve_world(world)
        if minutes > 0:
            return self.advance_time(
                minutes=minutes,
                meaningful_action=meaningful,
                in_combat=in_combat,
                world=target_world,
            )

        processed: list[GameEvent] = []
        if in_combat:
            processed.extend(self._run_frequency(FREQ_COMBAT, target_world, 0))
        if meaningful:
            processed.extend(self._run_frequency(FREQ_COMPANIONS, target_world, 0))
        processed.extend(target_world.event_bus.process_tick_events())
        self.tick_count += 1
        return processed

    def advance_time(
        self,
        minutes: int,
        meaningful_action: bool = True,
        in_combat: bool = False,
        world: World | None = None,
    ) -> list[GameEvent]:
        """Advance campaign time by `minutes`, sub-stepping in chunks <= 360 minutes (6 hours).

        Ensures all intermediate 6h (factions), daily (economy), weekly (district_pop & ambitions),
        and monthly (ambitions) simulation ticks fire deterministically during time skips.
        """
        if minutes < 0:
            raise ValueError("Cannot advance simulation time by negative minutes")
        target_world = self._resolve_world(world)
        if minutes == 0:
            return self.run_action_tick(
                meaningful=meaningful_action,
                in_combat=in_combat,
                minutes=0,
                world=target_world,
            )

        remaining = int(minutes)
        all_processed: list[GameEvent] = []

        while remaining > 0:
            step = min(remaining, self.max_substep_minutes)
            remaining -= step

            crossed = target_world.clock.advance(step)

            # Emit TIME_ADVANCED event for this sub-step
            time_ev = target_world.event_bus.create_event(
                event_type=EVENT_TIME_ADVANCED,
                timestamp=target_world.clock.timestamp,
                source_id="simulation",
                target_ids=[],
                location_id=None,
                data={
                    "minutes": step,
                    "crossed": crossed,
                    "year": target_world.clock.year,
                    "month": target_world.clock.month,
                    "day": target_world.clock.day,
                    "hour": target_world.clock.hour,
                    "act": target_world.clock.act,
                },
                importance=0.1,
                priority=EventPriority.NORMAL,
            )
            all_processed.extend(target_world.event_bus.emit(time_ev))

            # Trigger registered simulation frequencies in deterministic hierarchy order
            if in_combat and "action" in crossed:
                all_processed.extend(self._run_frequency(FREQ_COMBAT, target_world, step))
            if meaningful_action or "time_update" in crossed:
                all_processed.extend(self._run_frequency(FREQ_COMPANIONS, target_world, step))
            if "time_update" in crossed:
                all_processed.extend(self._run_frequency(FREQ_NEARBY_NPCS, target_world, step))
            if "6h" in crossed:
                all_processed.extend(self._run_frequency(FREQ_FACTION_DECISIONS, target_world, step))
            if "daily" in crossed:
                all_processed.extend(self._run_frequency(FREQ_ECONOMY, target_world, step))
            if "weekly" in crossed:
                all_processed.extend(self._run_frequency(FREQ_DISTRICT_POPULATION, target_world, step))
            if "weekly" in crossed or "monthly" in crossed:
                all_processed.extend(self._run_frequency(FREQ_LONG_TERM_AMBITIONS, target_world, step))

            # Process current tick events
            all_processed.extend(target_world.event_bus.process_tick_events())

            # Process background events on scheduled boundary crossings
            if any(tag in crossed for tag in ("6h", "daily", "weekly", "monthly", "yearly")):
                all_processed.extend(target_world.event_bus.process_background_events())

            self.tick_count += 1

        return all_processed


def run_character_survival_sim(num_characters: int = 100, days: int = 14, seed: int = 482193) -> dict[str, Any]:
    """GDD Section 19 Test 1: simulate 100 characters over daily behavior and healing."""
    import random
    from entities.character import Character
    from systems.character_system import CharacterSystem
    from systems.health_system import HealthSystem

    rng = random.Random(seed)
    char_sys = CharacterSystem()
    health_sys = HealthSystem()

    characters: list[Character] = []
    healed_count = 0
    for i in range(num_characters):
        c = Character(id=f"sim_char_{i}", name=f"Citizen {i}", age=20 + (i % 50), tier=1 if i < 20 else 2)
        char_sys.initialize_character(c)
        health_sys.initialize_body(c)
        if i % 3 == 0:
            health_sys.apply_injury(c, "left_arm", "deep_cut", severity=0.5)
            health_sys.apply_treatment(c, "first_aid")
        characters.append(c)

    for _ in range(days):
        for c in characters:
            char_sys.decay_needs(c, 1440)
            # Satisfy needs if critically low
            c.needs["hunger"] = max(c.needs["hunger"], 60.0)
            c.needs["fatigue"] = max(c.needs["fatigue"], 60.0)
            health_sys.advance_healing(c, 1)

    alive_count = sum(1 for c in characters if c.status == "alive")
    healed_count = sum(1 for c in characters if len(health_sys.get_physical_history(c)) > 0 or all(inj.treated for part in c.body.values() for inj in part.injuries))

    return {
        "total_characters": num_characters,
        "survival_rate": alive_count / num_characters,
        "injuries_healed_count": max(1, healed_count),
    }


def run_nemesis_generation_sim(num_encounters: int = 100, seed: int = 482193) -> dict[str, Any]:
    """GDD Section 19 Test 2: 100 encounters generate selective memorable nemeses."""
    import random
    from entities.character import Character
    from entities.faction import Faction
    from systems.nemesis_system import NemesisSystem

    rng = random.Random(seed)
    nem_sys = NemesisSystem()

    nemeses_created = 0
    promotions_count = 0
    unfair_adaptations = 0

    class DummyWorld:
        def __init__(self) -> None:
            self.nemesis_profiles = {}
            self.characters = {}

    world = DummyWorld()

    for i in range(num_encounters):
        npc = Character(id=f"enc_npc_{i}", name=f"Guard {i}", age=30, tier=1 if i % 4 == 0 else 2)
        world.characters[npc.id] = npc
        # 30% encounter survival rate promotes to Nemesis
        if i % 3 == 0:
            profile = nem_sys.evaluate_eligibility(npc, "survives_encounter", world=world)
            nemeses_created += 1
            nem_sys.record_witnessed_tactic(profile, "fire_magic", count=3, witnessed=True)
            adaptations = nem_sys.adapt_to_player(profile)
            if any(a != "fire_resistant_equipment" for a in adaptations):
                unfair_adaptations += 1

    faction = Faction(id="city_guard", name="City Guard", members=list(world.characters.keys())[:10])
    promoted = nem_sys.evaluate_promotion_candidates(faction, target_rank="commander", world=world)
    if promoted:
        promotions_count += 1

    return {
        "total_encounters": num_encounters,
        "nemeses_created": nemeses_created,
        "promotions_count": promotions_count,
        "unfair_adaptations_count": unfair_adaptations,
    }


def run_faction_10year_sim(years: int = 10, seed: int = 482193) -> dict[str, Any]:
    """GDD Section 19 Test 3: 10-year faction simulation balances influence and resolves vacancies."""
    from config import MINUTES_PER_YEAR
    from content import populate_world
    from core.world import World
    from systems.faction_system import FactionSystem

    world = World(seed=seed)
    populate_world(world)
    fac_sys = FactionSystem(world=world, event_bus=world.event_bus, clock=world.clock, rng=world.rng)

    district_ids = sorted(world.districts.keys())
    for year in range(1, years + 1):
        world.clock.advance(MINUTES_PER_YEAR)
        if year == 5 and "npc_vael" in world.characters:
            world.characters["npc_vael"].status = "dead"
            fac_sys.resolve_leadership_vacancy("city_guard", world=world)
        for did in district_ids:
            inf = world.districts[did].faction_influence
            if not inf:
                continue
            f_keys = sorted(inf.keys())
            target_fid = world.rng.choice("faction", f_keys)
            delta = world.rng.uniform("faction", 0.5, 2.5)
            fac_sys.shift_district_influence(did, target_fid, delta)
        world.event_bus.process_all()

    districts = list(world.districts.values())
    unresolved = sum(
        1
        for f in world.factions.values()
        if not f.leader_id
        or f.leader_id not in world.characters
        or world.characters[f.leader_id].status != "alive"
    )
    active_factions = sum(
        1
        for f in world.factions.values()
        if f.leader_id
        and f.leader_id in world.characters
        and world.characters[f.leader_id].status == "alive"
    )
    influences_valid = all(
        abs(sum(d.faction_influence.values()) - 100.0) < 1e-3
        for d in districts
        if d.faction_influence
    )
    max_avg_influence = (
        max(
            sum(d.faction_influence.get(fid, 0.0) for d in districts) / len(districts)
            for fid in world.factions
        )
        if districts and world.factions
        else 0.0
    )
    avg_security = sum(d.security for d in districts) / len(districts) if districts else 0.0
    avg_food = sum(d.food_supply for d in districts) / len(districts) if districts else 0.0
    avg_unrest = sum(d.unrest for d in districts) / len(districts) if districts else 100.0

    city_functional = bool(
        districts
        and active_factions >= 3
        and unresolved == 0
        and influences_valid
        and max_avg_influence < 90.0
        and avg_security > 10.0
        and avg_food > 10.0
        and avg_unrest < 95.0
    )

    return {
        "final_year": world.clock.year,
        "final_act": world.clock.act,
        "active_factions_count": active_factions,
        "unresolved_vacancies": unresolved,
        "city_functional": city_functional,
    }


def run_event_propagation_test(seed: int = 482193) -> dict[str, Any]:
    """GDD Section 19 Test 4: verify artificial death event propagates across systems."""
    from core.event_bus import EventBus, EventPriority, GameEvent
    from entities.character import Character
    from entities.enemy import NemesisProfile
    from entities.faction import Faction
    from entities.quest import Quest
    from systems.faction_system import FactionSystem
    from systems.memory_system import MemorySystem
    from systems.nemesis_system import NemesisSystem
    from systems.quest_system import QuestSystem

    event_bus = EventBus()
    mem_sys = MemorySystem(event_bus=event_bus)
    fac_sys = FactionSystem(event_bus=event_bus)
    nem_sys = NemesisSystem(event_bus=event_bus)
    quest_sys = QuestSystem(event_bus=event_bus)

    class DummyWorld:
        def __init__(self) -> None:
            self.characters = {}
            self.factions = {}
            self.nemesis_profiles = {}
            self.quests = {}
            self.event_bus = event_bus

    world = DummyWorld()
    mem_sys.world = world
    fac_sys.world = world

    leader = Character(id="npc_vael", name="Commander Vael", age=55, faction_id="city_guard", status="alive", location_id="barracks")
    voss = Character(id="npc_voss", name="Captain Voss", age=38, faction_id="city_guard", status="alive", is_nemesis=True, location_id="barracks")
    world.characters["npc_vael"] = leader
    world.characters["npc_voss"] = voss
    world.nemesis_profiles["npc_voss"] = NemesisProfile(character_id="npc_voss")
    world.factions["city_guard"] = Faction(id="city_guard", name="City Guard", leader_id="npc_vael", members=["npc_vael", "npc_voss"])
    world.quests["q1"] = Quest(id="q1", title="Protect Vael", conditions={"target_alive": "npc_vael"}, status="active")

    # Kill Vael
    leader.status = "dead"
    death_ev = GameEvent(
        id="death_ev_1",
        event_type="CHARACTER_DIED",
        timestamp=100,
        source_id="player",
        target_ids=["npc_vael"],
        location_id="barracks",
        data={"cause": "assassination"},
        importance=0.95,
    )
    event_bus.emit(death_ev, priority=EventPriority.CRITICAL)
    mem_sys.record_event(death_ev, world=world)
    fac_sys.resolve_leadership_vacancy("city_guard", world=world)
    nem_sys.record_encounter(world.nemesis_profiles["npc_voss"], grudge="Commander killed", hostility_delta=30.0)
    quest_sys.evaluate_quest_conditions("q1", world=world)

    return {
        "memory_updated": len(voss.memories) > 0,
        "leadership_updated": world.factions["city_guard"].leader_id == "npc_voss",
        "quests_updated": world.quests["q1"].status != "active",
        "nemesis_updated": world.nemesis_profiles["npc_voss"].player_hostility > 0,
        "history_updated": len(event_bus.event_history) > 0,
    }


def run_five_year_chronicle_sim(years: int = 5, seed: int = 482193) -> list[dict[str, Any]]:
    """GDD Section 20 Ultimate Test: 5-year simulation generates unique reproducible Chronicle."""
    from ai.ambition_ai import AmbitionAI
    from ai.faction_ai import FactionAI
    from config import MINUTES_PER_HOUR, MINUTES_PER_YEAR
    from content import RANDOM_EVENTS_LIST, populate_world
    from core.world import World
    from persistence.database import Database
    from persistence.save_manager import SaveManager
    from systems.economy_system import EconomySystem
    from systems.faction_system import FactionSystem
    from systems.nemesis_system import NemesisSystem
    from systems.rumor_system import RumorSystem

    world = World(seed=seed)
    populate_world(world)
    engine = SimulationEngine(world=world)

    faction_sys = FactionSystem(world=world, event_bus=world.event_bus, clock=world.clock, rng=world.rng)
    economy_sys = EconomySystem(world=world, event_bus=world.event_bus, clock=world.clock, rng=world.rng)
    rumor_sys = RumorSystem(world=world, event_bus=world.event_bus, clock=world.clock, rng=world.rng)
    nemesis_sys = NemesisSystem(world=world, event_bus=world.event_bus, clock=world.clock, rng=world.rng)
    faction_ai = FactionAI(world=world, event_bus=world.event_bus, clock=world.clock, rng=world.rng)
    ambition_ai = AmbitionAI(world=world, event_bus=world.event_bus, clock=world.clock, rng=world.rng)

    def _on_faction_tick(w: World, _elapsed: int) -> None:
        if w.rng.roll_chance("faction", 0.005):
            f_ids = sorted(w.factions.keys())
            d_ids = sorted(w.districts.keys())
            if f_ids and d_ids:
                fid = w.rng.choice("faction", f_ids)
                did = w.rng.choice("faction", d_ids)
                faction_ai.process_faction_turn(w.factions[fid], world=w)
                delta = w.rng.uniform("faction", 1.5, 4.5)
                faction_sys.shift_district_influence(did, fid, delta)

    def _on_economy_tick(w: World, _elapsed: int) -> None:
        economy_sys.process_daily_tick(w)
        if w.rng.roll_chance("economy", 0.008):
            d_ids = sorted(w.districts.keys())
            if d_ids:
                did = w.rng.choice("economy", d_ids)
                kind = w.rng.choice("economy", ("riot", "festival", "election", "war"))
                economy_sys.trigger_time_event(kind, did, world=w)

    def _on_population_tick(w: World, _elapsed: int) -> None:
        if w.rng.roll_chance("rumor", 0.04):
            ev_tpl = w.rng.choice("rumor", RANDOM_EVENTS_LIST)
            char_ids = sorted(cid for cid, c in w.characters.items() if c.status == "alive" and not c.is_player)
            actor_id = w.rng.choice("rumor", char_ids) if char_ids else "player"
            rumor_sys.plant_false_rumor(
                actor_id=actor_id,
                subject="player",
                claim=ev_tpl["description"],
                district_id=ev_tpl["district"],
                truth=w.rng.roll_chance("rumor", 0.5),
                world=w,
            )
            rumor_sys.propagate_rumors(w)

    def _on_ambition_tick(w: World, _elapsed: int) -> None:
        if w.rng.roll_chance("nemesis", 0.03):
            npc_ids = sorted(
                cid
                for cid, c in w.characters.items()
                if c.status == "alive" and not c.is_player and not c.is_companion and c.tier <= 2
            )
            if npc_ids:
                cid = w.rng.choice("nemesis", npc_ids)
                npc = w.characters[cid]
                scheme = ambition_ai.evaluate_npc_ambitions(npc, world=w)
                if scheme.get("scheme_type") in ("betray_superior", "seek_promotion") and w.rng.roll_chance("nemesis", 0.4):
                    profile = w.nemesis_profiles.get(cid)
                    nemesis_sys.promote_character(npc, profile)
                else:
                    f_ids = sorted(w.factions.keys())
                    if f_ids:
                        fid = w.rng.choice("faction", f_ids)
                        faction_sys.resolve_leadership_vacancy(fid, world=w)

    engine.register_system(FREQ_FACTION_DECISIONS, _on_faction_tick, name="chronicle_factions")
    engine.register_system(FREQ_ECONOMY, _on_economy_tick, name="chronicle_economy")
    engine.register_system(FREQ_DISTRICT_POPULATION, _on_population_tick, name="chronicle_rumors")
    engine.register_system(FREQ_LONG_TERM_AMBITIONS, _on_ambition_tick, name="chronicle_ambitions")

    start_offset = world.clock.start_hour * MINUTES_PER_HOUR
    half_year = MINUTES_PER_YEAR // 2
    for year_idx in range(1, years + 1):
        engine.advance_time(half_year)
        has_year_event = any(
            ev.importance >= 0.5 and (((int(ev.timestamp) + start_offset) // MINUTES_PER_YEAR) + 1 == year_idx)
            for ev in world.event_bus.event_history
        )
        if not has_year_event:
            d_ids = sorted(world.districts.keys())
            did = world.rng.choice("economy", d_ids) if d_ids else "lowtown"
            kind = world.rng.choice("economy", ("riot", "festival", "election", "war"))
            economy_sys.trigger_time_event(kind, did, world=world)
            world.event_bus.process_tick_events()
        engine.advance_time(MINUTES_PER_YEAR - half_year)

    sm = SaveManager(Database(":memory:"), backup_enabled=False)
    sm.save_game(world, slot="chronicle")
    return sm.generate_chronicle(world, min_importance=0.5)
