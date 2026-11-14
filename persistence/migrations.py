"""Schema versioning and idempotent forward migrations (GDD Section 15)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from persistence.database import REQUIRED_TABLES, SCHEMA_DDL, Database, DatabaseError

CURRENT_SCHEMA_VERSION: int = 1


class MigrationError(DatabaseError):
    """Raised when a schema or payload migration fails."""


class NewerSaveVersionError(MigrationError):
    """Raised when loading a save or database from a newer schema version than supported."""


def _migration_0_to_1(conn: sqlite3.Connection) -> None:
    """Initial baseline schema v1 creating all 15 required tables and support tables."""
    conn.executescript(SCHEMA_DDL)
    conn.execute("PRAGMA foreign_keys = ON;")


def _payload_0_to_1(payload: dict[str, Any]) -> dict[str, Any]:
    """Ensure baseline v1 keys exist on serialized payload dictionary."""
    migrated = dict(payload)
    migrated["schema_version"] = 1
    migrated.setdefault("seed", 482193)
    migrated.setdefault("player_id", "player")
    migrated.setdefault("player_party", [])
    migrated.setdefault("characters", {})
    migrated.setdefault("companions", {})
    migrated.setdefault("nemesis_profiles", {})
    migrated.setdefault("factions", {})
    migrated.setdefault("districts", {})
    migrated.setdefault("locations", {})
    migrated.setdefault("items", {})
    migrated.setdefault("inventories", {})
    migrated.setdefault("quests", {})
    migrated.setdefault("rumors", {})
    migrated.setdefault("economy", {"price_index": 1.0, "wage_index": 1.0, "shortages": [], "trade_volume": 100.0})
    migrated.setdefault("reputation", {})
    migrated.setdefault("chronicle", [])
    migrated.setdefault("flags", {})
    return migrated


class MigrationManager:
    """Manages SQLite schema versioning and step-by-step v -> v+1 migrations."""

    def __init__(self, db: Database) -> None:
        self.db: Database = db
        self._migrations: dict[int, tuple[str, Callable[[sqlite3.Connection], None]]] = {
            0: ("Initial 15-table Veyr simulation schema v1", _migration_0_to_1),
        }
        self._payload_migrations: dict[int, tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]] = {
            0: ("Initial payload schema v1", _payload_0_to_1),
        }

    def get_current_version(self) -> int:
        """Return the current schema version recorded in `schema_migrations` (0 if uninitialized)."""
        tables = set(self.db.list_tables())
        if "schema_migrations" not in tables:
            return 0
        row = self.db.fetchone("SELECT MAX(version) AS max_ver FROM schema_migrations;")
        ver = int(row["max_ver"]) if row and row["max_ver"] is not None else 0
        if "world_state" in tables:
            ws_row = self.db.fetchone("SELECT schema_version FROM world_state WHERE id = 1;")
            if ws_row and ws_row["schema_version"] is not None:
                ver = max(ver, int(ws_row["schema_version"]))
        return ver

    def register_migration(
        self,
        from_version: int,
        to_version: int,
        fn: Callable[[sqlite3.Connection], None],
        description: str = "",
    ) -> None:
        """Register a step-by-step SQL migration function from `from_version` to `from_version + 1`."""
        if to_version != from_version + 1:
            raise MigrationError(
                f"Migrations must increment version by 1 (got {from_version} -> {to_version})"
            )
        self._migrations[int(from_version)] = (
            description or f"Migrate v{from_version} to v{to_version}",
            fn,
        )

    def register_payload_migration(
        self,
        from_version: int,
        to_version: int,
        fn: Callable[[dict[str, Any]], dict[str, Any]],
        description: str = "",
    ) -> None:
        """Register a pure dictionary migration function from `from_version` to `from_version + 1`."""
        if to_version != from_version + 1:
            raise MigrationError(
                f"Payload migrations must increment version by 1 (got {from_version} -> {to_version})"
            )
        self._payload_migrations[int(from_version)] = (
            description or f"Migrate payload v{from_version} to v{to_version}",
            fn,
        )

    def migrate(self, target_version: int = CURRENT_SCHEMA_VERSION) -> int:
        """Upgrade the database schema sequentially up to `target_version`."""
        current = self.get_current_version()
        if current > target_version:
            raise NewerSaveVersionError(
                f"Database schema version {current} is newer than supported version {target_version}"
            )
        while current < target_version:
            if current not in self._migrations:
                raise MigrationError(f"Missing migration step from v{current} to v{current + 1}")
            desc, fn = self._migrations[current]
            next_ver = current + 1
            now_iso = datetime.now(timezone.utc).isoformat()
            with self.db.transaction() as conn:
                fn(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?);",
                    (next_ver, desc, now_iso),
                )
                conn.execute(
                    "UPDATE world_state SET schema_version = ? WHERE id = 1;",
                    (next_ver,),
                )
            current = next_ver
        return current

    def ensure_latest(self) -> int:
        """Ensure the database is migrated to `CURRENT_SCHEMA_VERSION`."""
        return self.migrate(CURRENT_SCHEMA_VERSION)

    def migrate_payload_dict(
        self,
        payload: dict[str, Any],
        target_version: int = CURRENT_SCHEMA_VERSION,
    ) -> dict[str, Any]:
        """Upgrade a serialized save/snapshot dictionary sequentially up to `target_version`."""
        v = int(payload.get("schema_version", payload.get("version", 1)))
        if v > target_version:
            raise NewerSaveVersionError(
                f"Save payload version {v} is newer than supported version {target_version}"
            )
        data = dict(payload)
        while v < target_version:
            if v not in self._payload_migrations:
                raise MigrationError(f"Missing payload migration from v{v} to v{v + 1}")
            _, fn = self._payload_migrations[v]
            data = fn(data)
            v += 1
            data["schema_version"] = v
            data["version"] = v
        data["schema_version"] = v
        return data

    def validate_schema(self) -> dict[str, Any]:
        """Verify all 15 required tables exist and check foreign key integrity."""
        existing = set(self.db.list_tables())
        missing = [t for t in REQUIRED_TABLES if t not in existing]
        fk_rows = self.db.fetchall("PRAGMA foreign_key_check;")
        violations = [dict(r) for r in fk_rows]
        return {
            "valid": len(missing) == 0 and len(violations) == 0,
            "missing_tables": missing,
            "fk_violations": violations,
            "version": self.get_current_version(),
        }
