"""SQLite connection manager and 15-table schema initialization (GDD Section 15)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

REQUIRED_TABLES: tuple[str, ...] = (
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
)

SUPPORT_TABLES: tuple[str, ...] = (
    "companions",
    "save_slots",
    "snapshots",
    "schema_migrations",
)

SCHEMA_DDL: str = """
-- 1. characters (GDD §13 L498-516, §15 L663)
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    age INTEGER NOT NULL DEFAULT 30,
    faction_id TEXT NULL,
    tier INTEGER NOT NULL DEFAULT 1,
    rank TEXT NULL,
    occupation TEXT NOT NULL DEFAULT '',
    attributes_json TEXT NOT NULL DEFAULT '{}',
    skills_json TEXT NOT NULL DEFAULT '{}',
    personality_json TEXT NOT NULL DEFAULT '{}',
    needs_json TEXT NOT NULL DEFAULT '{}',
    ambitions_json TEXT NOT NULL DEFAULT '[]',
    reputation_json TEXT NOT NULL DEFAULT '{}',
    combat_style TEXT NOT NULL DEFAULT '',
    location_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'alive',
    is_player INTEGER NOT NULL DEFAULT 0,
    is_companion INTEGER NOT NULL DEFAULT 0,
    is_nemesis INTEGER NOT NULL DEFAULT 0,
    extra_json TEXT NOT NULL DEFAULT '{}'
);

-- 2. body_parts (GDD §13 L529-536, §15 L664)
CREATE TABLE IF NOT EXISTS body_parts (
    id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    part_key TEXT NOT NULL,
    name TEXT NOT NULL,
    parent_key TEXT NULL,
    region TEXT NOT NULL DEFAULT '',
    integrity REAL NOT NULL DEFAULT 100.0,
    max_integrity REAL NOT NULL DEFAULT 100.0,
    armor REAL NOT NULL DEFAULT 0.0,
    resistance REAL NOT NULL DEFAULT 0.0,
    functional_importance REAL NOT NULL DEFAULT 1.0,
    vital INTEGER NOT NULL DEFAULT 0,
    functional INTEGER NOT NULL DEFAULT 1,
    prosthetic_item_id TEXT NULL,
    children_json TEXT NOT NULL DEFAULT '[]'
);

-- 3. injuries (GDD §13 L519-527, §15 L665)
CREATE TABLE IF NOT EXISTS injuries (
    id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    body_part_id TEXT NOT NULL REFERENCES body_parts(id) ON DELETE CASCADE,
    part_key TEXT NOT NULL DEFAULT '',
    injury_type TEXT NOT NULL,
    severity REAL NOT NULL DEFAULT 1.0,
    pain REAL NOT NULL DEFAULT 0.0,
    bleeding REAL NOT NULL DEFAULT 0.0,
    infection_risk REAL NOT NULL DEFAULT 0.0,
    recovery_progress REAL NOT NULL DEFAULT 0.0,
    permanent INTEGER NOT NULL DEFAULT 0,
    treatment_stage TEXT NOT NULL DEFAULT 'untreated',
    treated INTEGER NOT NULL DEFAULT 0,
    long_term_effect TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL DEFAULT 0,
    cause_description TEXT NOT NULL DEFAULT '',
    complication TEXT NULL
);

-- 4. memories (GDD §13 L539-549, §15 L666)
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    participants_json TEXT NOT NULL DEFAULT '[]',
    description TEXT NOT NULL DEFAULT '',
    location_id TEXT NOT NULL DEFAULT '',
    importance REAL NOT NULL DEFAULT 0.5,
    emotional_valence REAL NOT NULL DEFAULT 0.0,
    emotion TEXT NOT NULL DEFAULT 'neutral',
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at INTEGER NOT NULL DEFAULT 0,
    decay_rate REAL NOT NULL DEFAULT 0.0,
    source_type TEXT NOT NULL DEFAULT 'witnessed'
);

-- 5. relationships (GDD §13 L551-559, §15 L667)
CREATE TABLE IF NOT EXISTS relationships (
    source_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    target_id TEXT NOT NULL,
    trust REAL NOT NULL DEFAULT 0.0,
    respect REAL NOT NULL DEFAULT 0.0,
    affection REAL NOT NULL DEFAULT 0.0,
    resentment REAL NOT NULL DEFAULT 0.0,
    fear REAL NOT NULL DEFAULT 0.0,
    dependency REAL NOT NULL DEFAULT 0.0,
    friendship REAL NOT NULL DEFAULT 0.0,
    rivalry REAL NOT NULL DEFAULT 0.0,
    relationship_state TEXT NOT NULL DEFAULT 'Acquaintance',
    shared_memories_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (source_id, target_id)
);

-- 6. factions (GDD §8 L304-319, §13 L564-575, §15 L668)
CREATE TABLE IF NOT EXISTS factions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    leader_id TEXT NULL,
    power REAL NOT NULL DEFAULT 50.0,
    wealth REAL NOT NULL DEFAULT 50.0,
    influence REAL NOT NULL DEFAULT 50.0,
    military_strength REAL NOT NULL DEFAULT 50.0,
    public_legitimacy REAL NOT NULL DEFAULT 50.0,
    stability REAL NOT NULL DEFAULT 50.0,
    primary_goal TEXT NOT NULL DEFAULT '',
    methods_summary TEXT NOT NULL DEFAULT '',
    methods_json TEXT NOT NULL DEFAULT '[]',
    territories_json TEXT NOT NULL DEFAULT '[]',
    members_json TEXT NOT NULL DEFAULT '[]',
    hierarchy_json TEXT NOT NULL DEFAULT '{}',
    goals_json TEXT NOT NULL DEFAULT '[]',
    relations_json TEXT NOT NULL DEFAULT '{}'
);

-- 7. faction_relations (GDD §8 L314-315, §15 L669)
CREATE TABLE IF NOT EXISTS faction_relations (
    source_faction_id TEXT NOT NULL REFERENCES factions(id) ON DELETE CASCADE,
    target_faction_id TEXT NOT NULL,
    relation_value REAL NOT NULL DEFAULT 0.0,
    relation_state TEXT NOT NULL DEFAULT 'neutral',
    PRIMARY KEY (source_faction_id, target_faction_id)
);

-- 8. districts (GDD §2 L76-86, §15 L670)
CREATE TABLE IF NOT EXISTS districts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    characteristics TEXT NOT NULL DEFAULT '',
    major_conflict TEXT NOT NULL DEFAULT '',
    population INTEGER NOT NULL DEFAULT 5000,
    wealth REAL NOT NULL DEFAULT 50.0,
    security REAL NOT NULL DEFAULT 50.0,
    unrest REAL NOT NULL DEFAULT 20.0,
    food_supply REAL NOT NULL DEFAULT 80.0,
    employment REAL NOT NULL DEFAULT 70.0,
    crime REAL NOT NULL DEFAULT 30.0,
    public_opinion REAL NOT NULL DEFAULT 50.0,
    infrastructure_condition REAL NOT NULL DEFAULT 70.0,
    locations_json TEXT NOT NULL DEFAULT '[]',
    extra_json TEXT NOT NULL DEFAULT '{}'
);

-- 9. district_influence (GDD §8 L322-330, §15 L671)
CREATE TABLE IF NOT EXISTS district_influence (
    district_id TEXT NOT NULL REFERENCES districts(id) ON DELETE CASCADE,
    faction_id TEXT NOT NULL,
    influence_pct REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (district_id, faction_id)
);

-- 10. nemesis_profiles (GDD §7 L270-302, §13 L577-587, §15 L672)
CREATE TABLE IF NOT EXISTS nemesis_profiles (
    character_id TEXT PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
    player_hostility REAL NOT NULL DEFAULT 0.0,
    player_respect REAL NOT NULL DEFAULT 0.0,
    encounter_count INTEGER NOT NULL DEFAULT 0,
    known_player_tactics_json TEXT NOT NULL DEFAULT '[]',
    grudges_json TEXT NOT NULL DEFAULT '[]',
    career_history_json TEXT NOT NULL DEFAULT '[]',
    last_encounter_date INTEGER NOT NULL DEFAULT 0,
    current_ambition TEXT NOT NULL DEFAULT '',
    special_traits_json TEXT NOT NULL DEFAULT '[]',
    strengths_json TEXT NOT NULL DEFAULT '[]',
    weaknesses_json TEXT NOT NULL DEFAULT '[]',
    rank TEXT NOT NULL DEFAULT 'captain',
    faction_id TEXT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    combat_style_json TEXT NOT NULL DEFAULT '[]',
    adapted_countermeasures_json TEXT NOT NULL DEFAULT '[]'
);

-- 11. events (GDD §13 L589-612, §15 L673)
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    timestamp INTEGER NOT NULL DEFAULT 0,
    priority TEXT NOT NULL DEFAULT 'normal',
    source_id TEXT NULL,
    target_ids_json TEXT NOT NULL DEFAULT '[]',
    location_id TEXT NULL,
    data_json TEXT NOT NULL DEFAULT '{}',
    importance REAL NOT NULL DEFAULT 0.5
);

-- 12. quests (GDD §10 L363-375, §13 L613-614, §15 L674)
CREATE TABLE IF NOT EXISTS quests (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    quest_type TEXT NOT NULL DEFAULT 'hybrid',
    status TEXT NOT NULL DEFAULT 'available',
    description TEXT NOT NULL DEFAULT '',
    objectives_json TEXT NOT NULL DEFAULT '[]',
    conditions_json TEXT NOT NULL DEFAULT '{}',
    involved_characters_json TEXT NOT NULL DEFAULT '[]',
    involved_factions_json TEXT NOT NULL DEFAULT '[]',
    consequences_json TEXT NOT NULL DEFAULT '[]',
    selected_approach TEXT NULL,
    extra_json TEXT NOT NULL DEFAULT '{}'
);

-- 13. items (GDD §5 L181-228, §15 L675)
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    item_type TEXT NOT NULL DEFAULT 'misc',
    weight REAL NOT NULL DEFAULT 1.0,
    value REAL NOT NULL DEFAULT 10.0,
    damage REAL NOT NULL DEFAULT 0.0,
    damage_type TEXT NOT NULL DEFAULT 'cutting',
    penetration REAL NOT NULL DEFAULT 0.0,
    accuracy_mod REAL NOT NULL DEFAULT 0.0,
    handling REAL NOT NULL DEFAULT 1.0,
    armor_class TEXT NULL,
    armor_protection REAL NOT NULL DEFAULT 0.0,
    covered_parts_json TEXT NOT NULL DEFAULT '[]',
    protection_json TEXT NOT NULL DEFAULT '{}',
    weaknesses_json TEXT NOT NULL DEFAULT '[]',
    properties_json TEXT NOT NULL DEFAULT '{}'
);

-- 14. inventories (GDD §15 L676)
CREATE TABLE IF NOT EXISTS inventories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 1,
    equipped INTEGER NOT NULL DEFAULT 0,
    slot TEXT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- 15. world_state (GDD §2 L89-99, §14 L656-658, §15 L677)
CREATE TABLE IF NOT EXISTS world_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    active_slot TEXT NOT NULL DEFAULT 'default',
    world_seed INTEGER NOT NULL DEFAULT 482193,
    current_timestamp INTEGER NOT NULL DEFAULT 0,
    current_year INTEGER NOT NULL DEFAULT 1,
    current_day INTEGER NOT NULL DEFAULT 1,
    current_hour INTEGER NOT NULL DEFAULT 8,
    current_minute INTEGER NOT NULL DEFAULT 0,
    current_act TEXT NOT NULL DEFAULT 'Prologue',
    clock_json TEXT NOT NULL DEFAULT '{}',
    rng_state_json TEXT NOT NULL DEFAULT '{}',
    player_party_json TEXT NOT NULL DEFAULT '[]',
    rumors_json TEXT NOT NULL DEFAULT '[]',
    economy_json TEXT NOT NULL DEFAULT '{}',
    reputation_json TEXT NOT NULL DEFAULT '{}',
    chronicle_json TEXT NOT NULL DEFAULT '[]',
    flags_json TEXT NOT NULL DEFAULT '{}',
    schema_version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT ''
);

-- Support Table A: companions
CREATE TABLE IF NOT EXISTS companions (
    character_id TEXT PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    archetype_title TEXT NOT NULL DEFAULT '',
    personal_conflict TEXT NOT NULL DEFAULT '',
    friendship REAL NOT NULL DEFAULT 0.0,
    rivalry REAL NOT NULL DEFAULT 0.0,
    approval REAL NOT NULL DEFAULT 0.0,
    loyalty_conditions_json TEXT NOT NULL DEFAULT '[]',
    breaking_points_json TEXT NOT NULL DEFAULT '[]',
    personal_quest_id TEXT NULL,
    faction_opinions_json TEXT NOT NULL DEFAULT '{}',
    in_party INTEGER NOT NULL DEFAULT 1,
    independent_activity TEXT NOT NULL DEFAULT '',
    extra_json TEXT NOT NULL DEFAULT '{}'
);

-- Support Table B: save_slots
CREATE TABLE IF NOT EXISTS save_slots (
    slot TEXT PRIMARY KEY,
    world_seed INTEGER NOT NULL,
    current_timestamp INTEGER NOT NULL,
    current_year INTEGER NOT NULL,
    current_act TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Support Table C: snapshots
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    world_seed INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    year INTEGER NOT NULL,
    act TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    checksum TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Support Table D: schema_migrations
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_importance ON events(importance);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_memories_char ON memories(character_id);
CREATE INDEX IF NOT EXISTS idx_injuries_char ON injuries(character_id);
CREATE INDEX IF NOT EXISTS idx_body_parts_char ON body_parts(character_id);
CREATE INDEX IF NOT EXISTS idx_inventories_char ON inventories(character_id);
"""


class DatabaseError(Exception):
    """Raised when a SQLite schema, connection, or transaction error occurs."""


class Database:
    """SQLite database manager supporting `:memory:` and file-backed persistence."""

    def __init__(self, db_path: str | Path = ":memory:", auto_init: bool = True) -> None:
        raw_path = str(db_path)
        self.is_memory: bool = raw_path == ":memory:" or raw_path.startswith("file::memory:")
        self.db_path: Path | str = ":memory:" if self.is_memory else Path(db_path)
        if not self.is_memory and isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn: sqlite3.Connection | None = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        if not self.is_memory:
            self._conn.execute("PRAGMA journal_mode = WAL;")

        if auto_init:
            self.initialize_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Return the active SQLite connection, reopening if necessary."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON;")
            if not self.is_memory:
                self._conn.execute("PRAGMA journal_mode = WAL;")
        return self._conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Execute a block of SQL operations inside an atomic transaction."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except DatabaseError:
            conn.rollback()
            raise
        except sqlite3.Error as exc:
            conn.rollback()
            raise DatabaseError(f"SQLite transaction error: {exc}") from exc
        except Exception:
            conn.rollback()
            raise

    def initialize_schema(self) -> None:
        """Create all 15 required GDD tables, 4 support tables, and indexes."""
        conn = self.get_connection()
        try:
            conn.executescript(SCHEMA_DDL)
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.commit()
            from persistence.migrations import MigrationManager

            MigrationManager(self).ensure_latest()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Failed to initialize database schema: {exc}") from exc

    def execute(self, sql: str, params: tuple[Any, ...] | dict[str, Any] = ()) -> sqlite3.Cursor:
        conn = self.get_connection()
        try:
            return conn.execute(sql, params)
        except sqlite3.Error as exc:
            raise DatabaseError(f"SQLite execute error: {exc}") from exc

    def executemany(
        self,
        sql: str,
        seq_of_params: Iterable[tuple[Any, ...] | dict[str, Any]],
    ) -> sqlite3.Cursor:
        conn = self.get_connection()
        try:
            return conn.executemany(sql, seq_of_params)
        except sqlite3.Error as exc:
            raise DatabaseError(f"SQLite executemany error: {exc}") from exc

    def fetchone(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] = (),
    ) -> sqlite3.Row | None:
        return self.execute(sql, params).fetchone()

    def fetchall(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] = (),
    ) -> list[sqlite3.Row]:
        return list(self.execute(sql, params).fetchall())

    def list_tables(self) -> list[str]:
        """Return list of user table names in the SQLite database."""
        rows = self.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
        )
        return [str(r["name"]) for r in rows]

    def verify_required_tables(self) -> bool:
        """Return True if all 15 required GDD Section 15 tables exist."""
        existing = set(self.list_tables())
        return all(tbl in existing for tbl in REQUIRED_TABLES)

    def table_row_counts(self) -> dict[str, int]:
        """Return row counts for each of the 15 required tables."""
        counts: dict[str, int] = {}
        existing = set(self.list_tables())
        for tbl in REQUIRED_TABLES:
            if tbl in existing:
                row = self.fetchone(f"SELECT COUNT(*) AS cnt FROM {tbl};")
                counts[tbl] = int(row["cnt"]) if row else 0
            else:
                counts[tbl] = 0
        return counts

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
