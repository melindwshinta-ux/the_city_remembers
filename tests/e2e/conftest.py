"""Shared E2E fixtures, lazy module loaders, and contract-enforcing adapters for THE CITY REMEMBERS."""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

# Ensure /home/antigravity/the_city_remembers is on sys.path for all E2E tests
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def require_module(module_name: str) -> Any:
    """Import an application module at test execution time.
    Never skips: raises real ImportError/ModuleNotFoundError if missing.
    """
    return importlib.import_module(module_name)


def require_symbol(module_name: str, *symbol_names: str) -> Any:
    """Import a module and return the first matching symbol from symbol_names.
    Enforces PROJECT.md canonical names first while allowing documented aliases.
    Raises AttributeError if none exist.
    """
    mod = require_module(module_name)
    for name in symbol_names:
        if hasattr(mod, name):
            return getattr(mod, name)
    raise AttributeError(
        f"Module '{module_name}' is missing required symbol(s): {symbol_names}. "
        f"Available attributes: {[a for a in dir(mod) if not a.startswith('_')]}"
    )


def call_method(obj: Any, method_names: str | list[str] | tuple[str, ...], *args: Any, **kwargs: Any) -> Any:
    """Call the first matching method on obj from method_names.
    Tries passing kwargs matching the method signature or all args/kwargs directly.
    Raises AttributeError if none of the method names exist on obj.
    """
    if isinstance(method_names, str):
        names = [method_names]
    else:
        names = list(method_names)

    for name in names:
        if hasattr(obj, name):
            fn = getattr(obj, name)
            if callable(fn):
                try:
                    return fn(*args, **kwargs)
                except TypeError:
                    # Inspect signature to filter or remap kwargs if needed
                    sig = inspect.signature(fn)
                    has_var_kw = any(
                        p.kind == inspect.Parameter.VAR_KEYWORD
                        for p in sig.parameters.values()
                    )
                    if not has_var_kw and kwargs:
                        filtered_kw = {
                            k: v for k, v in kwargs.items() if k in sig.parameters
                        }
                        if filtered_kw != kwargs:
                            return fn(*args, **filtered_kw)
                    raise
    raise AttributeError(
        f"Object of type '{type(obj).__name__}' is missing required method(s): {names}. "
        f"Available methods: {[a for a in dir(obj) if not a.startswith('_')]}"
    )


def instantiate_with_context(cls: type, **available_deps: Any) -> Any:
    """Instantiate a system/engine/AI class by matching its __init__ parameters
    against available context objects (world, event_bus, clock, rng, db, save_manager, etc.),
    falling back to no-arg construction + attribute attachment if __init__ takes no args.
    """
    sig = inspect.signature(cls.__init__)
    kwargs: dict[str, Any] = {}
    aliases = {
        "bus": "event_bus",
        "event_bus": "event_bus",
        "clock": "clock",
        "world_clock": "clock",
        "rng": "rng",
        "random_generator": "rng",
        "seeded_rng": "rng",
        "world": "world",
        "db": "db",
        "database": "db",
        "save_manager": "save_manager",
        "seed": "seed",
        "master_seed": "seed",
        "world_seed": "seed",
        "db_path": "db_path",
        "character_system": "character_system",
        "memory_system": "memory_system",
        "relationship_system": "relationship_system",
        "health_system": "health_system",
        "equipment_system": "equipment_system",
        "combat_system": "combat_system",
        "nemesis_system": "nemesis_system",
        "faction_system": "faction_system",
        "quest_system": "quest_system",
        "rumor_system": "rumor_system",
        "economy_system": "economy_system",
    }
    for param_name, param in list(sig.parameters.items())[1:]:
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        canonical = aliases.get(param_name, param_name)
        if canonical in available_deps and available_deps[canonical] is not None:
            kwargs[param_name] = available_deps[canonical]

    try:
        instance = cls(**kwargs)
    except TypeError:
        instance = cls()

    for attr_name in ("event_bus", "clock", "rng", "world", "db", "save_manager"):
        if attr_name in available_deps and available_deps[attr_name] is not None:
            if not hasattr(instance, attr_name) or getattr(instance, attr_name) is None:
                try:
                    setattr(instance, attr_name, available_deps[attr_name])
                except Exception:
                    pass
    return instance


def get_clock_minutes(clock: Any) -> int:
    """Return total elapsed minutes from WorldClock via canonical or alias property."""
    for attr in ("timestamp", "total_minutes", "elapsed_minutes", "minutes"):
        if hasattr(clock, attr):
            val = getattr(clock, attr)
            if isinstance(val, (int, float)):
                return int(val)
    raise AttributeError(f"WorldClock {clock!r} has no timestamp/total_minutes attribute")


def get_minutes_per_year(clock: Any = None) -> int:
    """Return configured minutes per year (default 518,400 for 360-day year)."""
    try:
        cfg = require_module("config")
        if hasattr(cfg, "MINUTES_PER_YEAR"):
            return int(cfg.MINUTES_PER_YEAR)
        if hasattr(cfg, "DAYS_PER_YEAR"):
            return int(cfg.DAYS_PER_YEAR) * 1440
    except ImportError:
        pass
    if clock is not None:
        for attr in ("MINUTES_PER_YEAR", "minutes_per_year"):
            if hasattr(clock, attr):
                return int(getattr(clock, attr))
        for attr in ("DAYS_PER_YEAR", "days_per_year"):
            if hasattr(clock, attr):
                return int(getattr(clock, attr)) * 1440
    return 360 * 1440


REQUIRED_15_TABLES = {
    "characters",
    "body_parts",
    "injuries",
    "memories",
    "relationships",
    "factions",
    "faction_relations",
    "districts",
    "district_influence",
    "nemesis_profiles",
    "events",
    "quests",
    "items",
    "inventories",
    "world_state",
}

CANONICAL_11_RNG_STREAMS = (
    "combat",
    "world",
    "nemesis",
    "faction",
    "character",
    "health",
    "memory",
    "quest",
    "rumor",
    "economy",
    "ai",
)


class LoaderNamespace:
    """Helper object exposed by mod_loader fixture."""

    require_module = staticmethod(require_module)
    require_symbol = staticmethod(require_symbol)
    call_method = staticmethod(call_method)
    instantiate_with_context = staticmethod(instantiate_with_context)
    get_clock_minutes = staticmethod(get_clock_minutes)
    get_minutes_per_year = staticmethod(get_minutes_per_year)


@pytest.fixture(scope="session")
def mod_loader() -> LoaderNamespace:
    """Session-scoped module & symbol loader fixture."""
    return LoaderNamespace()


@pytest.fixture
def seeded_rng() -> Any:
    """Instantiate SeededRNG with canonical master seed 482193."""
    SeededRNG = require_symbol("core.random_generator", "SeededRNG", "RandomGenerator")
    try:
        rng = SeededRNG(482193)
    except TypeError:
        rng = SeededRNG(master_seed=482193)
    return rng


@pytest.fixture
def world_clock() -> Any:
    """Instantiate a fresh WorldClock at timestamp 0."""
    WorldClock = require_symbol("core.clock", "WorldClock", "Clock")
    return WorldClock()


@pytest.fixture
def event_bus() -> Any:
    """Instantiate EventBus with an attached emitted_log spy list."""
    EventBus = require_symbol("core.event_bus", "EventBus")
    bus = EventBus()
    emitted_log: list[Any] = []

    orig_emit = bus.emit

    def spy_emit(event: Any, *args: Any, **kwargs: Any) -> Any:
        emitted_log.append(event)
        return orig_emit(event, *args, **kwargs)

    bus.emit = spy_emit  # type: ignore[method-assign]
    bus.emitted_log = emitted_log
    return bus


@pytest.fixture
def entity_factory() -> dict[str, Any]:
    """Return a dictionary of all canonical entity classes and factories from entities/."""
    Character = require_symbol("entities.character", "Character")
    Injury = require_symbol("entities.character", "Injury")
    BodyPart = require_symbol("entities.character", "BodyPart")
    Memory = require_symbol("entities.character", "Memory")
    Relationship = require_symbol("entities.character", "Relationship")
    Companion = require_symbol("entities.companion", "CompanionProfile", "Companion")
    NemesisProfile = require_symbol("entities.enemy", "NemesisProfile")
    EnemyCombatant = require_symbol("entities.enemy", "EnemyCombatant", "Enemy")
    Faction = require_symbol("entities.faction", "Faction")
    District = require_symbol("entities.district", "District")
    Location = require_symbol("entities.district", "Location")
    Item = require_symbol("entities.item", "Item")
    Quest = require_symbol("entities.quest", "Quest")
    Rumor = require_symbol("entities.quest", "Rumor")
    GameEvent = require_symbol("core.event_bus", "GameEvent")
    EventPriority = require_symbol("core.event_bus", "EventPriority")

    char_mod = require_module("entities.character")
    create_humanoid_body = getattr(char_mod, "create_humanoid_body", None)
    item_mod = require_module("entities.item")
    InventoryEntry = getattr(item_mod, "InventoryEntry", None)

    return {
        "Character": Character,
        "Injury": Injury,
        "BodyPart": BodyPart,
        "Memory": Memory,
        "Relationship": Relationship,
        "Companion": Companion,
        "CompanionProfile": Companion,
        "NemesisProfile": NemesisProfile,
        "EnemyCombatant": EnemyCombatant,
        "Enemy": EnemyCombatant,
        "Faction": Faction,
        "District": District,
        "Location": Location,
        "Item": Item,
        "InventoryEntry": InventoryEntry,
        "Quest": Quest,
        "Rumor": Rumor,
        "GameEvent": GameEvent,
        "EventPriority": EventPriority,
        "create_humanoid_body": create_humanoid_body,
    }


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Any:
    """Create an isolated SQLite Database in tmp_path and apply migrations."""
    Database = require_symbol("persistence.database", "Database")
    db_file = tmp_path / "test_veyr.db"
    db = Database(db_file)

    try:
        mig_mod = require_module("persistence.migrations")
        if hasattr(mig_mod, "MigrationManager"):
            mgr = mig_mod.MigrationManager(db)
            if hasattr(mgr, "migrate"):
                mgr.migrate()
            elif hasattr(mgr, "ensure_latest"):
                mgr.ensure_latest()
        elif hasattr(mig_mod, "apply_migrations"):
            mig_mod.apply_migrations(db)
    except ImportError:
        pass

    yield db
    if hasattr(db, "close"):
        db.close()


@pytest.fixture
def save_manager(sqlite_db: Any) -> Any:
    """Instantiate SaveManager backed by sqlite_db."""
    SaveManager = require_symbol("persistence.save_manager", "SaveManager")
    return SaveManager(sqlite_db)


@pytest.fixture
def systems_suite(world_clock: Any, seeded_rng: Any, event_bus: Any, sqlite_db: Any, save_manager: Any) -> dict[str, Any]:
    """Instantiate World, SimulationEngine, all 11 systems, and 4 AI modules wired together."""
    World = require_symbol("core.world", "World")
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")

    world = instantiate_with_context(
        World,
        seed=482193,
        clock=world_clock,
        rng=seeded_rng,
        event_bus=event_bus,
    )
    sim = instantiate_with_context(
        SimulationEngine,
        world=world,
        clock=world.clock,
        rng=world.rng,
        event_bus=world.event_bus,
    )

    deps: dict[str, Any] = {
        "world": world,
        "clock": world.clock,
        "rng": world.rng,
        "event_bus": world.event_bus,
        "simulation": sim,
        "db": sqlite_db,
        "save_manager": save_manager,
        "seed": 482193,
    }

    system_specs = [
        ("character_system", "systems.character_system", ("CharacterSystem",)),
        ("memory_system", "systems.memory_system", ("MemorySystem",)),
        ("relationship_system", "systems.relationship_system", ("RelationshipSystem",)),
        ("health_system", "systems.health_system", ("HealthSystem",)),
        ("equipment_system", "systems.equipment_system", ("EquipmentSystem",)),
        ("combat_system", "systems.combat_system", ("CombatSystem",)),
        ("nemesis_system", "systems.nemesis_system", ("NemesisSystem",)),
        ("faction_system", "systems.faction_system", ("FactionSystem",)),
        ("quest_system", "systems.quest_system", ("QuestSystem",)),
        ("rumor_system", "systems.rumor_system", ("RumorSystem",)),
        ("economy_system", "systems.economy_system", ("EconomySystem",)),
        ("character_ai", "ai.character_ai", ("CharacterAI",)),
        ("combat_ai", "ai.combat_ai", ("CombatAI",)),
        ("faction_ai", "ai.faction_ai", ("FactionAI",)),
        ("ambition_ai", "ai.ambition_ai", ("AmbitionAI",)),
    ]

    for key, mod_name, cls_names in system_specs:
        cls = require_symbol(mod_name, *cls_names)
        inst = instantiate_with_context(cls, **deps)
        deps[key] = inst
        setattr(world, key, inst)

    return deps


@pytest.fixture
def populated_world(sqlite_db: Any, save_manager: Any) -> Any:
    """Return a fully populated World loaded with Veyr & Lowtown content (seed=482193)."""
    # Try Game or content loader first
    try:
        Game = require_symbol("core.game", "Game")
        game = instantiate_with_context(
            Game,
            seed=482193,
            db=sqlite_db,
            save_manager=save_manager,
        )
        if hasattr(game, "world") and game.world is not None and len(getattr(game.world, "districts", {})) > 0:
            return game.world
    except ImportError:
        pass

    World = require_symbol("core.world", "World")
    world = instantiate_with_context(World, seed=482193)
    content_mod = require_module("content")
    for loader_name in ("load_all_content", "populate_world", "initialize_world_content", "load_content"):
        if hasattr(content_mod, loader_name):
            fn = getattr(content_mod, loader_name)
            res = fn(world) if len(inspect.signature(fn).parameters) >= 1 else fn()
            if isinstance(res, World):
                return res
            break
    return world


@pytest.fixture
def game_session(tmp_path: Path, sqlite_db: Any, save_manager: Any) -> Any:
    """Instantiate top-level Game session with seed=482193 and isolated SQLite persistence."""
    Game = require_symbol("core.game", "Game")
    game = instantiate_with_context(
        Game,
        seed=482193,
        db=sqlite_db,
        save_manager=save_manager,
        db_path=tmp_path / "game_session.db",
    )
    return game
