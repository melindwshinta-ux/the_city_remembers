"""Public exports for the persistence package."""

from __future__ import annotations

from persistence.database import REQUIRED_TABLES, SUPPORT_TABLES, Database, DatabaseError
from persistence.migrations import (
    CURRENT_SCHEMA_VERSION,
    MigrationError,
    MigrationManager,
    NewerSaveVersionError,
)
from persistence.save_manager import (
    SaveCorruptedError,
    SaveError,
    SaveManager,
    SaveNotFoundError,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "Database",
    "DatabaseError",
    "MigrationError",
    "MigrationManager",
    "NewerSaveVersionError",
    "REQUIRED_TABLES",
    "SUPPORT_TABLES",
    "SaveCorruptedError",
    "SaveError",
    "SaveManager",
    "SaveNotFoundError",
]
