"""SaveManager implementing 15-table save/load, append-only event history, snapshots, and Chronicle generator."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
    DEFAULT_START_HOUR,
    DEFAULT_WORLD_SEED,
    MINUTES_PER_DAY,
    MINUTES_PER_HOUR,
    MINUTES_PER_YEAR,
)
from core.clock import WorldClock
from core.event_bus import EventBus, GameEvent
from core.random_generator import SeededRNG
from core.world import World
from entities.character import BodyPart, Character, Injury, Memory, Relationship
from entities.companion import CompanionProfile
from entities.district import District, Location
from entities.enemy import NemesisProfile
from entities.faction import Faction
from entities.item import InventoryEntry, Item
from entities.quest import Quest, Rumor
from persistence.database import Database, DatabaseError
from persistence.migrations import CURRENT_SCHEMA_VERSION, MigrationManager


class SaveError(DatabaseError):
    """Base exception for save and load operations."""


class SaveNotFoundError(SaveError):
    """Raised when a requested save slot or snapshot does not exist."""


class SaveCorruptedError(SaveError):
    """Raised when a save slot or snapshot fails checksum/schema validation and cannot be recovered."""


def _compute_checksum(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _derive_relation_state(value: float) -> str:
    if value >= 50.0:
        return "allied"
    if value >= 20.0:
        return "friendly"
    if value <= -50.0:
        return "hostile"
    if value <= -20.0:
        return "unfriendly"
    return "neutral"


class SaveManager:
    """Manages SQLite persistence across all 15 GDD tables, event logs, snapshots, and chronicles."""

    def __init__(
        self,
        db: Database | str | Path = ":memory:",
        backup_enabled: bool = True,
    ) -> None:
        self.db: Database = db if isinstance(db, Database) else Database(db)
        self.migrations: MigrationManager = MigrationManager(self.db)
        self.backup_enabled: bool = bool(backup_enabled)

    def _validate_world_before_save(self, world: World) -> None:
        if world is None or not isinstance(world, World):
            raise SaveError("Cannot save a null or invalid World instance")
        for collection_name, mapping in (
            ("characters", world.characters),
            ("factions", world.factions),
            ("districts", world.districts),
            ("items", world.items),
            ("quests", world.quests),
        ):
            for key, entity in mapping.items():
                ent_id = getattr(entity, "id", None)
                if not key or not ent_id or not str(ent_id).strip():
                    raise SaveError(f"Invalid empty ID in {collection_name}")

    def _create_file_backup(self) -> None:
        if self.db.is_memory or not self.backup_enabled:
            return
        db_path = Path(self.db.db_path)
        if not db_path.exists():
            return
        bak_path = Path(f"{db_path}.bak")
        bak_conn = sqlite3.connect(str(bak_path))
        try:
            self.db.get_connection().backup(bak_conn)
        finally:
            bak_conn.close()

    def save_game(self, world: World, slot: str = "default") -> None:
        """Persist current `World` state across all 15 SQLite tables and `save_slots`."""
        self._validate_world_before_save(world)
        if bool(world.flags.get("ironman")):
            slot = "ironman"
        self._create_file_backup()
        now_iso = datetime.now(timezone.utc).isoformat()

        payload_dict = world.to_dict()
        payload_dict["schema_version"] = max(int(world.schema_version), CURRENT_SCHEMA_VERSION)
        payload_json = json.dumps(payload_dict, sort_keys=True)
        checksum = _compute_checksum(payload_json)

        with self.db.transaction() as conn:
            self._write_world_to_relational_tables(conn, world, slot=slot, now_iso=now_iso)
            conn.execute(
                """
                INSERT OR REPLACE INTO save_slots (
                    slot, world_seed, current_timestamp, current_year, current_act,
                    schema_version, checksum, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    slot,
                    int(world.seed),
                    int(world.clock.timestamp),
                    int(world.clock.year),
                    str(world.clock.act),
                    int(payload_dict["schema_version"]),
                    checksum,
                    payload_json,
                    now_iso,
                ),
            )

    def _write_world_to_relational_tables(
        self,
        conn: sqlite3.Connection,
        world: World,
        slot: str,
        now_iso: str,
    ) -> None:
        """Populate the 14 current-state tables + companions and append new events to `events`."""
        # Clear current-state tables in child-to-parent order (never clearing events/snapshots/save_slots)
        for table in (
            "injuries",
            "body_parts",
            "memories",
            "relationships",
            "nemesis_profiles",
            "companions",
            "inventories",
            "district_influence",
            "faction_relations",
            "quests",
            "items",
            "districts",
            "factions",
            "characters",
            "world_state",
        ):
            conn.execute(f"DELETE FROM {table};")

        # 1. world_state (Table 15)
        flags_envelope = {
            "user_flags": dict(world.flags),
            "player_id": world.player_id,
            "locations": {lid: loc.to_dict() for lid, loc in sorted(world.locations.items())},
            "properties": {pid: dict(pdata) for pid, pdata in sorted(world.properties.items())},
            "commodities": {str(cid): int(qty) for cid, qty in sorted(world.commodities.items())},
            "loans": [dict(loan) for loan in world.loans],
            "caravans": [dict(caravan) for caravan in world.caravans],
        }
        conn.execute(
            """
            INSERT INTO world_state (
                id, active_slot, world_seed, current_timestamp, current_year,
                current_day, current_hour, current_minute, current_act,
                clock_json, rng_state_json, player_party_json, rumors_json,
                economy_json, reputation_json, chronicle_json, flags_json,
                schema_version, updated_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                slot,
                int(world.seed),
                int(world.clock.timestamp),
                int(world.clock.year),
                int(world.clock.day),
                int(world.clock.hour),
                int(world.clock.minute),
                str(world.clock.act),
                json.dumps(world.clock.to_dict(), sort_keys=True),
                json.dumps(world.rng.get_state(), sort_keys=True),
                json.dumps(list(world.player_party)),
                json.dumps([r.to_dict() for _, r in sorted(world.rumors.items())], sort_keys=True),
                json.dumps(world.economy, sort_keys=True),
                json.dumps(world.reputation, sort_keys=True),
                json.dumps(world.chronicle, sort_keys=True),
                json.dumps(flags_envelope, sort_keys=True),
                int(world.schema_version),
                now_iso,
            ),
        )

        # 2. districts (Table 8) & district_influence (Table 9)
        for did, dist in sorted(world.districts.items()):
            dist_locs = [
                world.locations[lid].to_dict()
                for lid in dist.locations
                if lid in world.locations
            ]
            conn.execute(
                """
                INSERT INTO districts (
                    id, name, characteristics, major_conflict, population,
                    wealth, security, unrest, food_supply, employment,
                    crime, public_opinion, infrastructure_condition,
                    locations_json, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    dist.id,
                    dist.name,
                    dist.characteristics,
                    dist.major_conflict,
                    int(dist.population),
                    float(dist.wealth),
                    float(dist.security),
                    float(dist.unrest),
                    float(dist.food_supply),
                    float(dist.employment),
                    float(dist.crime),
                    float(dist.public_opinion),
                    float(dist.infrastructure_condition),
                    json.dumps(list(dist.locations)),
                    json.dumps({"location_objects": dist_locs}, sort_keys=True),
                ),
            )
            for fac_id, pct in sorted(dist.faction_influence.items()):
                conn.execute(
                    """
                    INSERT INTO district_influence (district_id, faction_id, influence_pct)
                    VALUES (?, ?, ?);
                    """,
                    (dist.id, str(fac_id), float(pct)),
                )

        # 3. factions (Table 6) & faction_relations (Table 7)
        for fid, fac in sorted(world.factions.items()):
            conn.execute(
                """
                INSERT INTO factions (
                    id, name, leader_id, power, wealth, influence,
                    military_strength, public_legitimacy, stability,
                    primary_goal, methods_summary, methods_json,
                    territories_json, members_json, hierarchy_json,
                    goals_json, relations_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    fac.id,
                    fac.name,
                    fac.leader_id,
                    float(fac.power),
                    float(fac.wealth),
                    float(fac.influence),
                    float(fac.military_strength),
                    float(fac.public_legitimacy),
                    float(fac.stability),
                    fac.goal_summary,
                    fac.methods_summary,
                    json.dumps(list(fac.methods)),
                    json.dumps(list(fac.territories)),
                    json.dumps(list(fac.members)),
                    json.dumps(fac.hierarchy, sort_keys=True),
                    json.dumps(fac.goals, sort_keys=True),
                    json.dumps(fac.relations, sort_keys=True),
                ),
            )
            for target_fid, rel_val in sorted(fac.relations.items()):
                val = float(rel_val)
                conn.execute(
                    """
                    INSERT INTO faction_relations (
                        source_faction_id, target_faction_id, relation_value, relation_state
                    ) VALUES (?, ?, ?, ?);
                    """,
                    (fac.id, str(target_fid), val, _derive_relation_state(val)),
                )

        # 4. characters (Table 1), body_parts (Table 2), injuries (Table 3), memories (Table 4), relationships (Table 5)
        saved_char_ids: set[str] = set()
        for cid, char in sorted(world.characters.items()):
            saved_char_ids.add(char.id)
            char_extra = {
                "equipment": dict(char.equipment),
                "inventory": list(char.inventory),
                "consciousness": float(char.consciousness),
                "morale": float(char.morale),
                "rank_is_none": char.rank is None,
            }
            conn.execute(
                """
                INSERT INTO characters (
                    id, name, age, faction_id, tier, rank, occupation,
                    attributes_json, skills_json, personality_json, needs_json,
                    ambitions_json, reputation_json, combat_style, location_id,
                    status, is_player, is_companion, is_nemesis, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    char.id,
                    char.name,
                    int(char.age),
                    char.faction_id,
                    int(char.tier),
                    char.rank,
                    char.occupation,
                    json.dumps(char.attributes, sort_keys=True),
                    json.dumps(char.skills, sort_keys=True),
                    json.dumps(char.personality, sort_keys=True),
                    json.dumps(char.needs, sort_keys=True),
                    json.dumps(char.ambitions),
                    json.dumps(char.reputation, sort_keys=True),
                    char.combat_style,
                    char.location_id,
                    char.status,
                    1 if char.is_player else 0,
                    1 if char.is_companion else 0,
                    1 if char.is_nemesis else 0,
                    json.dumps(char_extra, sort_keys=True),
                ),
            )

            # Body parts & injuries
            for part_key, part in sorted(char.body.items()):
                db_part_id = f"{char.id}:{part_key}"
                conn.execute(
                    """
                    INSERT INTO body_parts (
                        id, character_id, part_key, name, parent_key, region,
                        integrity, max_integrity, armor, resistance,
                        functional_importance, vital, functional,
                        prosthetic_item_id, children_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        db_part_id,
                        char.id,
                        part_key,
                        part.name,
                        part.parent_key,
                        part.region,
                        float(part.integrity),
                        float(part.max_integrity),
                        float(part.armor),
                        float(part.resistance),
                        float(part.functional_importance),
                        1 if part.vital else 0,
                        1 if part.functional else 0,
                        part.prosthetic_id,
                        json.dumps(list(part.children)),
                    ),
                )
                for inj in part.injuries:
                    prefix = f"{char.id}:{part_key}:"
                    db_inj_id = inj.id if inj.id.startswith(prefix) else f"{prefix}{inj.id}"
                    conn.execute(
                        """
                        INSERT INTO injuries (
                            id, character_id, body_part_id, part_key, injury_type,
                            severity, pain, bleeding, infection_risk,
                            recovery_progress, permanent, treatment_stage,
                            treated, long_term_effect, created_at,
                            cause_description, complication
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            db_inj_id,
                            char.id,
                            db_part_id,
                            part_key,
                            inj.injury_type,
                            float(inj.severity),
                            float(inj.pain),
                            float(inj.bleeding),
                            float(inj.infection_risk),
                            float(inj.recovery_progress),
                            1 if inj.permanent else 0,
                            inj.treatment_stage,
                            1 if inj.treated else 0,
                            inj.long_term_effect,
                            int(inj.created_at),
                            inj.cause_description,
                            inj.complication,
                        ),
                    )

            # Memories
            for mem in char.memories:
                mem_prefix = f"{char.id}:"
                db_mem_id = mem.id if mem.id.startswith(mem_prefix) else f"{mem_prefix}{mem.id}"
                conn.execute(
                    """
                    INSERT INTO memories (
                        id, character_id, event_type, participants_json,
                        description, location_id, importance, emotional_valence,
                        emotion, confidence, created_at, decay_rate, source_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        db_mem_id,
                        char.id,
                        mem.event_type,
                        json.dumps(list(mem.participants)),
                        mem.description,
                        mem.location_id,
                        float(mem.importance),
                        float(mem.emotional_valence),
                        mem.emotion,
                        float(mem.confidence),
                        int(mem.created_at),
                        float(mem.decay_rate),
                        mem.source_type,
                    ),
                )

            # Relationships
            for target_id, rel in sorted(char.relationships.items()):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO relationships (
                        source_id, target_id, trust, respect, affection,
                        resentment, fear, dependency, friendship, rivalry,
                        relationship_state, shared_memories_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        char.id,
                        rel.target_id or str(target_id),
                        float(rel.trust),
                        float(rel.respect),
                        float(rel.affection),
                        float(rel.resentment),
                        float(rel.fear),
                        float(rel.dependency),
                        float(rel.friendship_score),
                        float(rel.rivalry_score),
                        rel.relationship_state,
                        json.dumps(list(rel.shared_memories)),
                    ),
                )

        # 5. companions (Support Table A)
        for comp_id, comp in sorted(world.companions.items()):
            if comp.character_id not in saved_char_ids:
                # Ensure FK target exists in characters
                conn.execute(
                    "INSERT INTO characters (id, name, is_companion, extra_json) VALUES (?, ?, 1, ?);",
                    (comp.character_id, comp.name or comp.character_id, json.dumps({"stub": True})),
                )
                saved_char_ids.add(comp.character_id)
            conn.execute(
                """
                INSERT OR REPLACE INTO companions (
                    character_id, name, role, archetype_title, personal_conflict,
                    friendship, rivalry, approval, loyalty_conditions_json,
                    breaking_points_json, personal_quest_id, faction_opinions_json,
                    in_party, independent_activity, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    comp.character_id,
                    comp.name,
                    comp.role,
                    comp.title,
                    comp.conflict_description,
                    float(comp.friendship),
                    float(comp.rivalry),
                    float(comp.approval),
                    json.dumps(list(comp.loyalty_conditions)),
                    json.dumps(list(comp.breaking_points)),
                    comp.personal_quest_id,
                    json.dumps(comp.faction_opinions, sort_keys=True),
                    1 if comp.in_party else 0,
                    comp.independent_activity,
                    "{}",
                ),
            )

        # 6. nemesis_profiles (Table 10)
        all_nemeses: dict[str, NemesisProfile] = dict(world.nemesis_profiles)
        for cid, char in world.characters.items():
            if isinstance(char.nemesis_profile, NemesisProfile) and cid not in all_nemeses:
                all_nemeses[cid] = char.nemesis_profile

        for nid, nem in sorted(all_nemeses.items()):
            if nem.character_id not in saved_char_ids:
                conn.execute(
                    "INSERT INTO characters (id, name, is_nemesis, extra_json) VALUES (?, ?, 1, ?);",
                    (nem.character_id, nem.character_id, json.dumps({"stub": True})),
                )
                saved_char_ids.add(nem.character_id)
            conn.execute(
                """
                INSERT OR REPLACE INTO nemesis_profiles (
                    character_id, player_hostility, player_respect, encounter_count,
                    known_player_tactics_json, grudges_json, career_history_json,
                    last_encounter_date, current_ambition, special_traits_json,
                    strengths_json, weaknesses_json, rank, faction_id, status,
                    combat_style_json, adapted_countermeasures_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    nem.character_id,
                    float(nem.player_hostility),
                    float(nem.player_respect),
                    int(nem.encounter_count),
                    json.dumps(list(nem.known_player_tactics)),
                    json.dumps(list(nem.grudges)),
                    json.dumps(list(nem.career_history)),
                    int(nem.last_encounter_date),
                    nem.current_ambition,
                    json.dumps(list(nem.special_traits)),
                    json.dumps(list(nem.strengths)),
                    json.dumps(list(nem.weaknesses)),
                    nem.rank,
                    nem.faction_id,
                    nem.status,
                    json.dumps(list(nem.combat_style)),
                    json.dumps(list(nem.adaptations)),
                ),
            )

        # 7. items (Table 13) & inventories (Table 14)
        saved_item_ids: set[str] = set()
        for iid, item in sorted(world.items.items()):
            saved_item_ids.add(item.id)
            conn.execute(
                """
                INSERT INTO items (
                    id, name, item_type, weight, value, damage, damage_type,
                    penetration, accuracy_mod, handling, armor_class,
                    armor_protection, covered_parts_json, protection_json,
                    weaknesses_json, properties_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    item.id,
                    item.name,
                    item.item_type,
                    float(item.weight),
                    float(item.value),
                    float(item.damage),
                    item.damage_type,
                    float(item.penetration),
                    float(item.accuracy_mod),
                    float(item.handling),
                    item.armor_class,
                    float(item.armor_protection),
                    json.dumps(list(item.covered_parts)),
                    json.dumps(item.protection, sort_keys=True),
                    json.dumps(list(item.weaknesses)),
                    json.dumps(item.properties, sort_keys=True),
                ),
            )

        for char_id, entries in sorted(world.inventories.items()):
            if char_id not in saved_char_ids:
                conn.execute(
                    "INSERT INTO characters (id, name, extra_json) VALUES (?, ?, ?);",
                    (char_id, char_id, json.dumps({"stub": True})),
                )
                saved_char_ids.add(char_id)
            for entry in entries:
                if entry.item_id not in saved_item_ids:
                    conn.execute(
                        "INSERT INTO items (id, name, item_type) VALUES (?, ?, 'misc');",
                        (entry.item_id, entry.item_id),
                    )
                    saved_item_ids.add(entry.item_id)
                conn.execute(
                    """
                    INSERT INTO inventories (
                        character_id, item_id, quantity, equipped, slot, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        entry.character_id,
                        entry.item_id,
                        int(entry.quantity),
                        1 if entry.equipped else 0,
                        entry.slot,
                        json.dumps(entry.metadata, sort_keys=True),
                    ),
                )

        # 8. quests (Table 12)
        for qid, quest in sorted(world.quests.items()):
            conn.execute(
                """
                INSERT INTO quests (
                    id, title, quest_type, status, description,
                    objectives_json, conditions_json, involved_characters_json,
                    involved_factions_json, consequences_json, selected_approach, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    quest.id,
                    quest.title,
                    quest.quest_type,
                    quest.status,
                    quest.description,
                    json.dumps(quest.objectives, sort_keys=True),
                    json.dumps(quest.conditions, sort_keys=True),
                    json.dumps(list(quest.involved_characters)),
                    json.dumps(list(quest.involved_factions)),
                    json.dumps(quest.consequences, sort_keys=True),
                    quest.selected_approach,
                    "{}",
                ),
            )

        # 9. events (Table 11 — Append-Only Sync)
        for ev in world.event_bus.event_history:
            conn.execute(
                """
                INSERT OR IGNORE INTO events (
                    id, event_type, timestamp, priority, source_id,
                    target_ids_json, location_id, data_json, importance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    ev.id,
                    ev.event_type,
                    int(ev.timestamp),
                    str(ev.priority),
                    ev.source_id,
                    json.dumps(list(ev.target_ids)),
                    ev.location_id,
                    json.dumps(ev.data, sort_keys=True),
                    float(ev.importance),
                ),
            )

    def load_game(self, slot: str = "default") -> World:
        """Load `World` state from SQLite for `slot` (with migration & corruption fallback)."""
        self.migrations.migrate()
        conn = self.db.get_connection()

        ws_row = self.db.fetchone("SELECT * FROM world_state WHERE id = 1;")
        slot_row = self.db.fetchone("SELECT * FROM save_slots WHERE slot = ?;", (slot,))

        if ws_row is None and slot_row is None:
            raise SaveNotFoundError(f"Save slot '{slot}' not found")

        # If loading a slot other than the active relational slot, restore from save_slots first
        if ws_row is None or str(ws_row["active_slot"]) != slot:
            if slot_row is None:
                raise SaveNotFoundError(f"Save slot '{slot}' not found")
            return self._load_from_slot_row(slot_row, sync_tables=True)

        # Active slot matches `slot`: verify slot checksum if present, then reconstruct from relational tables
        if slot_row is not None:
            expected_checksum = str(slot_row["checksum"])
            actual_checksum = _compute_checksum(str(slot_row["payload_json"]))
            if expected_checksum != actual_checksum:
                return self._recover_from_backup_or_snapshot(slot)

        try:
            return self._reconstruct_world_from_tables(conn)
        except Exception as exc:
            if slot_row is not None:
                try:
                    return self._load_from_slot_row(slot_row, sync_tables=True)
                except Exception:
                    pass
            return self._recover_from_backup_or_snapshot(slot, cause=exc)

    def _load_from_slot_row(self, slot_row: sqlite3.Row, sync_tables: bool = False) -> World:
        payload_json = str(slot_row["payload_json"])
        expected_checksum = str(slot_row["checksum"])
        if _compute_checksum(payload_json) != expected_checksum:
            raise SaveCorruptedError(f"Checksum mismatch in save slot '{slot_row['slot']}'")
        try:
            raw_dict = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            raise SaveCorruptedError(f"Invalid JSON in save slot '{slot_row['slot']}'") from exc

        migrated_dict = self.migrations.migrate_payload_dict(raw_dict)
        world = World.from_dict(migrated_dict)
        # Merge full append-only event history from `events` table
        db_events = self.get_event_history()
        existing_ids = {ev.id for ev in world.event_bus.event_history}
        for ev in db_events:
            if ev.id not in existing_ids:
                world.event_bus.event_history.append(ev)
        world.event_bus.event_history.sort(key=lambda e: e.timestamp)

        if sync_tables:
            now_iso = datetime.now(timezone.utc).isoformat()
            with self.db.transaction() as conn:
                self._write_world_to_relational_tables(conn, world, slot=str(slot_row["slot"]), now_iso=now_iso)
        return world

    def _recover_from_backup_or_snapshot(
        self,
        slot: str,
        cause: Exception | None = None,
    ) -> World:
        """Attempt recovery from `.bak` database file or latest valid snapshot."""
        if not self.db.is_memory and isinstance(self.db.db_path, Path):
            bak_path = Path(f"{self.db.db_path}.bak")
            if bak_path.exists():
                try:
                    bak_db = Database(bak_path, auto_init=False)
                    bak_mgr = SaveManager(bak_db, backup_enabled=False)
                    recovered = bak_mgr.load_game(slot=slot)
                    bak_db.close()
                    return recovered
                except Exception:
                    pass

        snapshots = self.list_snapshots()
        for snap in snapshots:
            try:
                return self.restore_snapshot(str(snap["snapshot_id"]))
            except Exception:
                continue

        raise SaveCorruptedError(f"Save slot '{slot}' is corrupted and recovery failed") from cause

    def _reconstruct_world_from_tables(self, conn: sqlite3.Connection) -> World:
        """Reconstruct a complete `World` directly from the 15 SQLite relational tables."""
        ws = conn.execute("SELECT * FROM world_state WHERE id = 1;").fetchone()
        if ws is None:
            raise SaveNotFoundError("world_state table is empty")

        seed = int(ws["world_seed"])
        clock_data = json.loads(ws["clock_json"]) if ws["clock_json"] else {}
        if not clock_data:
            clock_data = {
                "timestamp": int(ws["current_timestamp"]),
                "start_hour": DEFAULT_START_HOUR,
            }
        clock = WorldClock.from_dict(clock_data)

        rng = SeededRNG(seed)
        if ws["rng_state_json"] and ws["rng_state_json"] != "{}":
            rng.set_state(json.loads(ws["rng_state_json"]))

        event_bus = EventBus()
        world = World(seed=seed, clock=clock, rng=rng, event_bus=event_bus)
        world.schema_version = int(ws["schema_version"])
        world.player_party = [str(p) for p in json.loads(ws["player_party_json"] or "[]")]
        world.economy = json.loads(ws["economy_json"] or "{}")
        world.reputation = json.loads(ws["reputation_json"] or "{}")
        world.chronicle = json.loads(ws["chronicle_json"] or "[]")

        flags_raw = json.loads(ws["flags_json"] or "{}")
        if "user_flags" in flags_raw and isinstance(flags_raw["user_flags"], dict):
            world.flags = dict(flags_raw["user_flags"])
            world.player_id = str(flags_raw.get("player_id", "player"))
            for lid, loc_dict in flags_raw.get("locations", {}).items():
                world.locations[str(lid)] = Location.from_dict(loc_dict)
            world.properties = {
                str(pid): dict(pdata)
                for pid, pdata in (flags_raw.get("properties") or {}).items()
            }
            world.commodities = {
                str(cid): int(qty)
                for cid, qty in (flags_raw.get("commodities") or {}).items()
            }
            world.loans = [dict(loan) for loan in (flags_raw.get("loans") or [])]
            world.caravans = [dict(caravan) for caravan in (flags_raw.get("caravans") or [])]
        else:
            world.flags = dict(flags_raw)

        for r_dict in json.loads(ws["rumors_json"] or "[]"):
            rumor = Rumor.from_dict(r_dict)
            world.rumors[rumor.id] = rumor

        # Districts & district_influence
        dist_rows = conn.execute("SELECT * FROM districts ORDER BY id;").fetchall()
        for d_row in dist_rows:
            did = str(d_row["id"])
            inf_rows = conn.execute(
                "SELECT faction_id, influence_pct FROM district_influence WHERE district_id = ? ORDER BY faction_id;",
                (did,),
            ).fetchall()
            influence = {str(ir["faction_id"]): float(ir["influence_pct"]) for ir in inf_rows}
            loc_ids = [str(x) for x in json.loads(d_row["locations_json"] or "[]")]
            dist = District(
                id=did,
                name=str(d_row["name"]),
                characteristics=str(d_row["characteristics"]),
                major_conflict=str(d_row["major_conflict"]),
                population=int(d_row["population"]),
                wealth=float(d_row["wealth"]),
                security=float(d_row["security"]),
                unrest=float(d_row["unrest"]),
                faction_influence=influence,
                food_supply=float(d_row["food_supply"]),
                employment=float(d_row["employment"]),
                crime=float(d_row["crime"]),
                public_opinion=float(d_row["public_opinion"]),
                infrastructure_condition=float(d_row["infrastructure_condition"]),
                locations=loc_ids,
            )
            world.districts[did] = dist
            extra = json.loads(d_row["extra_json"] or "{}")
            for loc_dict in extra.get("location_objects", []):
                loc = Location.from_dict(loc_dict)
                world.locations.setdefault(loc.id, loc)

        # Factions & faction_relations
        fac_rows = conn.execute("SELECT * FROM factions ORDER BY id;").fetchall()
        for f_row in fac_rows:
            fid = str(f_row["id"])
            rel_rows = conn.execute(
                "SELECT target_faction_id, relation_value FROM faction_relations WHERE source_faction_id = ?;",
                (fid,),
            ).fetchall()
            relations = json.loads(f_row["relations_json"] or "{}")
            for rr in rel_rows:
                relations[str(rr["target_faction_id"])] = float(rr["relation_value"])
            fac = Faction(
                id=fid,
                name=str(f_row["name"]),
                leader_id=f_row["leader_id"],
                wealth=float(f_row["wealth"]),
                influence=float(f_row["influence"]),
                military_strength=float(f_row["military_strength"]),
                stability=float(f_row["stability"]),
                territories=json.loads(f_row["territories_json"] or "[]"),
                members=json.loads(f_row["members_json"] or "[]"),
                goals=json.loads(f_row["goals_json"] or "[]"),
                relations=relations,
                power=float(f_row["power"]),
                public_legitimacy=float(f_row["public_legitimacy"]),
                goal_summary=str(f_row["primary_goal"]),
                methods_summary=str(f_row["methods_summary"]),
                methods=json.loads(f_row["methods_json"] or "[]"),
                hierarchy=json.loads(f_row["hierarchy_json"] or "{}"),
            )
            world.factions[fid] = fac

        # Items
        item_rows = conn.execute("SELECT * FROM items ORDER BY id;").fetchall()
        for i_row in item_rows:
            iid = str(i_row["id"])
            protection = json.loads(i_row["protection_json"] or "{}")
            properties = json.loads(i_row["properties_json"] or "{}")
            world.items[iid] = Item(
                id=iid,
                name=str(i_row["name"]),
                item_type=str(i_row["item_type"]),
                weight=float(i_row["weight"]),
                value=float(i_row["value"]),
                damage=float(i_row["damage"]),
                damage_type=str(i_row["damage_type"]),
                penetration=float(i_row["penetration"]),
                handling=float(i_row["handling"]),
                accuracy_mod=float(i_row["accuracy_mod"]),
                armor_class=i_row["armor_class"] if i_row["armor_class"] else None,
                armor_protection=float(i_row["armor_protection"]),
                covered_parts=json.loads(i_row["covered_parts_json"] or "[]"),
                protection=protection,
                weaknesses=json.loads(i_row["weaknesses_json"] or "[]"),
                properties=properties,
            )

        # Characters, body_parts, injuries, memories, relationships
        char_rows = conn.execute("SELECT * FROM characters ORDER BY id;").fetchall()
        for c_row in char_rows:
            extra = json.loads(c_row["extra_json"] or "{}")
            if extra.get("stub"):
                continue
            cid = str(c_row["id"])

            # Load body_parts & injuries for this character
            bp_rows = conn.execute(
                "SELECT * FROM body_parts WHERE character_id = ? ORDER BY id;",
                (cid,),
            ).fetchall()
            body: dict[str, BodyPart] = {}
            for bp_row in bp_rows:
                db_part_id = str(bp_row["id"])
                part_key = str(bp_row["part_key"])
                inj_rows = conn.execute(
                    "SELECT * FROM injuries WHERE body_part_id = ? ORDER BY id;",
                    (db_part_id,),
                ).fetchall()
                injuries: list[Injury] = []
                prefix = f"{cid}:{part_key}:"
                for ir in inj_rows:
                    raw_inj_id = str(ir["id"])
                    orig_inj_id = raw_inj_id[len(prefix) :] if raw_inj_id.startswith(prefix) else raw_inj_id
                    injuries.append(
                        Injury(
                            id=orig_inj_id,
                            injury_type=str(ir["injury_type"]),
                            severity=float(ir["severity"]),
                            pain=float(ir["pain"]),
                            bleeding=float(ir["bleeding"]),
                            infection_risk=float(ir["infection_risk"]),
                            recovery_progress=float(ir["recovery_progress"]),
                            permanent=bool(ir["permanent"]),
                            treated=bool(ir["treated"]),
                            treatment_stage=str(ir["treatment_stage"]),
                            long_term_effect=str(ir["long_term_effect"]),
                            created_at=int(ir["created_at"]),
                            cause_description=str(ir["cause_description"]),
                            complication=ir["complication"],
                            body_part_id=part_key,
                            part_key=part_key,
                            character_id=cid,
                        )
                    )
                body[part_key] = BodyPart(
                    id=part_key,
                    name=str(bp_row["name"]),
                    integrity=float(bp_row["integrity"]),
                    armor=float(bp_row["armor"]),
                    functional=bool(bp_row["functional"]),
                    injuries=injuries,
                    children=json.loads(bp_row["children_json"] or "[]"),
                    vital=bool(bp_row["vital"]),
                    prosthetic_id=bp_row["prosthetic_item_id"],
                    max_integrity=float(bp_row["max_integrity"]),
                    parent_key=bp_row["parent_key"],
                    region=str(bp_row["region"]),
                    resistance=float(bp_row["resistance"]),
                    functional_importance=float(bp_row["functional_importance"]),
                    part_key=part_key,
                    character_id=cid,
                )

            # Load memories for this character
            mem_rows = conn.execute(
                "SELECT * FROM memories WHERE character_id = ? ORDER BY created_at ASC, rowid ASC;",
                (cid,),
            ).fetchall()
            memories: list[Memory] = []
            mem_prefix = f"{cid}:"
            for mr in mem_rows:
                raw_mem_id = str(mr["id"])
                orig_mem_id = raw_mem_id[len(mem_prefix) :] if raw_mem_id.startswith(mem_prefix) else raw_mem_id
                memories.append(
                    Memory(
                        id=orig_mem_id,
                        event_type=str(mr["event_type"]),
                        participants=json.loads(mr["participants_json"] or "[]"),
                        description=str(mr["description"]),
                        location_id=str(mr["location_id"]),
                        importance=float(mr["importance"]),
                        emotional_valence=float(mr["emotional_valence"]),
                        confidence=float(mr["confidence"]),
                        created_at=int(mr["created_at"]),
                        decay_rate=float(mr["decay_rate"]),
                        emotion=str(mr["emotion"]),
                        character_id=cid,
                        source_type=str(mr["source_type"]),
                    )
                )

            # Load relationships for this character
            rel_rows = conn.execute(
                "SELECT * FROM relationships WHERE source_id = ? ORDER BY target_id;",
                (cid,),
            ).fetchall()
            relationships: dict[str, Relationship] = {}
            for rr in rel_rows:
                tid = str(rr["target_id"])
                relationships[tid] = Relationship(
                    source_id=cid,
                    target_id=tid,
                    trust=float(rr["trust"]),
                    respect=float(rr["respect"]),
                    affection=float(rr["affection"]),
                    resentment=float(rr["resentment"]),
                    fear=float(rr["fear"]),
                    shared_memories=json.loads(rr["shared_memories_json"] or "[]"),
                    dependency=float(rr["dependency"]),
                    relationship_state=str(rr["relationship_state"]),
                    friendship_score=float(rr["friendship"]),
                    rivalry_score=float(rr["rivalry"]),
                )

            rank_val = None if extra.get("rank_is_none") else c_row["rank"]
            char = Character(
                id=cid,
                name=str(c_row["name"]),
                age=int(c_row["age"]),
                faction_id=c_row["faction_id"],
                attributes=json.loads(c_row["attributes_json"] or "{}"),
                skills=json.loads(c_row["skills_json"] or "{}"),
                personality=json.loads(c_row["personality_json"] or "{}"),
                needs=json.loads(c_row["needs_json"] or "{}"),
                body=body,
                memories=memories,
                relationships=relationships,
                ambitions=json.loads(c_row["ambitions_json"] or "[]"),
                location_id=str(c_row["location_id"]),
                status=str(c_row["status"]),
                is_player=bool(c_row["is_player"]),
                is_companion=bool(c_row["is_companion"]),
                is_nemesis=bool(c_row["is_nemesis"]),
                tier=int(c_row["tier"]),
                rank=rank_val,
                occupation=str(c_row["occupation"]),
                combat_style=str(c_row["combat_style"]),
                reputation=json.loads(c_row["reputation_json"] or "{}"),
                equipment=dict(extra.get("equipment", {})),
                inventory=list(extra.get("inventory", [])),
                consciousness=float(extra.get("consciousness", 100.0)),
                morale=float(extra.get("morale", 75.0)),
            )
            world.characters[cid] = char
            if char.is_player:
                world.player_id = cid

        # Companions
        comp_rows = conn.execute("SELECT * FROM companions ORDER BY character_id;").fetchall()
        for cr in comp_rows:
            cid = str(cr["character_id"])
            world.companions[cid] = CompanionProfile(
                character_id=cid,
                name=str(cr["name"]),
                title=str(cr["archetype_title"]),
                role=str(cr["role"]),
                friendship=float(cr["friendship"]),
                rivalry=float(cr["rivalry"]),
                approval=float(cr["approval"]),
                loyalty_conditions=json.loads(cr["loyalty_conditions_json"] or "[]"),
                breaking_points=json.loads(cr["breaking_points_json"] or "[]"),
                personal_quest_id=cr["personal_quest_id"],
                faction_opinions=json.loads(cr["faction_opinions_json"] or "{}"),
                in_party=bool(cr["in_party"]),
                independent_activity=str(cr["independent_activity"]),
                conflict_description=str(cr["personal_conflict"]),
            )

        # Nemesis profiles
        nem_rows = conn.execute("SELECT * FROM nemesis_profiles ORDER BY character_id;").fetchall()
        for nr in nem_rows:
            nid = str(nr["character_id"])
            prof = NemesisProfile(
                character_id=nid,
                player_hostility=float(nr["player_hostility"]),
                player_respect=float(nr["player_respect"]),
                encounter_count=int(nr["encounter_count"]),
                known_player_tactics=json.loads(nr["known_player_tactics_json"] or "[]"),
                grudges=json.loads(nr["grudges_json"] or "[]"),
                career_history=json.loads(nr["career_history_json"] or "[]"),
                last_encounter_date=int(nr["last_encounter_date"]),
                current_ambition=str(nr["current_ambition"]),
                special_traits=json.loads(nr["special_traits_json"] or "[]"),
                strengths=json.loads(nr["strengths_json"] or "[]"),
                weaknesses=json.loads(nr["weaknesses_json"] or "[]"),
                rank=str(nr["rank"]),
                status=str(nr["status"]),
                faction_id=nr["faction_id"],
                combat_style=json.loads(nr["combat_style_json"] or "[]"),
                adaptations=json.loads(nr["adapted_countermeasures_json"] or "[]"),
            )
            world.nemesis_profiles[nid] = prof
            if nid in world.characters:
                world.characters[nid].nemesis_profile = prof

        # Inventories
        inv_rows = conn.execute("SELECT * FROM inventories ORDER BY id ASC;").fetchall()
        for ir in inv_rows:
            cid = str(ir["character_id"])
            entry = InventoryEntry(
                id=int(ir["id"]),
                character_id=cid,
                item_id=str(ir["item_id"]),
                quantity=int(ir["quantity"]),
                equipped=bool(ir["equipped"]),
                slot=ir["slot"],
                metadata=json.loads(ir["metadata_json"] or "{}"),
            )
            world.inventories.setdefault(cid, []).append(entry)

        # Quests
        quest_rows = conn.execute("SELECT * FROM quests ORDER BY id;").fetchall()
        for qr in quest_rows:
            qid = str(qr["id"])
            world.quests[qid] = Quest(
                id=qid,
                title=str(qr["title"]),
                status=str(qr["status"]),
                objectives=json.loads(qr["objectives_json"] or "[]"),
                conditions=json.loads(qr["conditions_json"] or "{}"),
                involved_characters=json.loads(qr["involved_characters_json"] or "[]"),
                involved_factions=json.loads(qr["involved_factions_json"] or "[]"),
                consequences=json.loads(qr["consequences_json"] or "[]"),
                quest_type=str(qr["quest_type"]),
                description=str(qr["description"]),
                selected_approach=qr["selected_approach"],
            )

        # Events
        world.event_bus.event_history = self.get_event_history()
        return world

    # --- Event Log Persistence & Querying ---

    def append_event(self, event: GameEvent) -> None:
        """Append a single `GameEvent` to the SQLite `events` history table."""
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events (
                    id, event_type, timestamp, priority, source_id,
                    target_ids_json, location_id, data_json, importance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    event.id,
                    event.event_type,
                    int(event.timestamp),
                    str(event.priority),
                    event.source_id,
                    json.dumps(list(event.target_ids)),
                    event.location_id,
                    json.dumps(event.data, sort_keys=True),
                    float(event.importance),
                ),
            )

    def get_event_history(
        self,
        limit: int | None = None,
        min_importance: float = 0.0,
        event_type: str | None = None,
        character_id: str | None = None,
        location_id: str | None = None,
        since_timestamp: int | None = None,
        until_timestamp: int | None = None,
    ) -> list[GameEvent]:
        """Query the append-only `events` table with optional filters."""
        clauses: list[str] = ["importance >= ?"]
        params: list[Any] = [float(min_importance)]

        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(str(event_type))
        if location_id is not None:
            clauses.append("location_id = ?")
            params.append(str(location_id))
        if since_timestamp is not None:
            clauses.append("timestamp >= ?")
            params.append(int(since_timestamp))
        if until_timestamp is not None:
            clauses.append("timestamp <= ?")
            params.append(int(until_timestamp))

        where_sql = " AND ".join(clauses)
        sql = f"SELECT * FROM events WHERE {where_sql} ORDER BY timestamp ASC, rowid ASC;"
        rows = self.db.fetchall(sql, tuple(params))

        events: list[GameEvent] = []
        for r in rows:
            target_ids = json.loads(r["target_ids_json"] or "[]")
            data_dict = json.loads(r["data_json"] or "{}")
            ev = GameEvent(
                id=str(r["id"]),
                event_type=str(r["event_type"]),
                timestamp=int(r["timestamp"]),
                source_id=r["source_id"],
                target_ids=target_ids,
                location_id=r["location_id"],
                data=data_dict,
                importance=float(r["importance"]),
                priority=str(r["priority"]),
            )
            if character_id is not None:
                participants = data_dict.get("participants", [])
                if (
                    ev.source_id != character_id
                    and character_id not in ev.target_ids
                    and character_id not in participants
                ):
                    continue
            events.append(ev)

        if limit is not None and limit >= 0:
            return events[-limit:] if limit > 0 else []
        return events

    # --- Periodic Snapshots & Rollback Recovery ---

    def create_snapshot(self, world: World, label: str = "checkpoint") -> str:
        """Create a point-in-time recovery snapshot in the `snapshots` table."""
        self._validate_world_before_save(world)
        snapshot_id = f"snap_y{world.clock.year}_t{world.clock.timestamp}_{uuid.uuid4().hex[:8]}"
        payload_dict = world.to_dict()
        payload_dict["schema_version"] = max(int(world.schema_version), CURRENT_SCHEMA_VERSION)
        payload_json = json.dumps(payload_dict, sort_keys=True)
        checksum = _compute_checksum(payload_json)
        now_iso = datetime.now(timezone.utc).isoformat()

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO snapshots (
                    snapshot_id, label, world_seed, timestamp, year, act,
                    schema_version, checksum, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    snapshot_id,
                    str(label),
                    int(world.seed),
                    int(world.clock.timestamp),
                    int(world.clock.year),
                    str(world.clock.act),
                    int(payload_dict["schema_version"]),
                    checksum,
                    payload_json,
                    now_iso,
                ),
            )
        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> World:
        """Restore a `World` from a periodic snapshot and sync the 15 relational tables."""
        row = self.db.fetchone(
            "SELECT * FROM snapshots WHERE snapshot_id = ?;",
            (snapshot_id,),
        )
        if row is None:
            raise SaveNotFoundError(f"Snapshot '{snapshot_id}' not found")

        payload_json = str(row["payload_json"])
        expected_checksum = str(row["checksum"])
        if _compute_checksum(payload_json) != expected_checksum:
            raise SaveCorruptedError(f"Snapshot '{snapshot_id}' checksum mismatch")

        try:
            raw_dict = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            raise SaveCorruptedError(f"Snapshot '{snapshot_id}' contains invalid JSON") from exc

        migrated_dict = self.migrations.migrate_payload_dict(raw_dict)
        world = World.from_dict(migrated_dict)

        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            self._write_world_to_relational_tables(conn, world, slot="default", now_iso=now_iso)
        return world

    def list_snapshots(self) -> list[dict[str, Any]]:
        """Return metadata for all stored snapshots ordered from newest to oldest."""
        rows = self.db.fetchall(
            """
            SELECT snapshot_id, label, world_seed, timestamp, year, act,
                   schema_version, checksum, created_at
            FROM snapshots
            ORDER BY timestamp DESC, created_at DESC;
            """
        )
        return [dict(r) for r in rows]

    # --- In-Game Chronicle Generator (GDD Section 15 & Section 20) ---

    def _resolve_display_names(
        self,
        world: World | None,
    ) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        char_names: dict[str, str] = {"player": "Rowan"}
        faction_names: dict[str, str] = {}
        loc_names: dict[str, str] = {}

        for r in self.db.fetchall("SELECT id, name FROM characters;"):
            char_names[str(r["id"])] = str(r["name"])
        for r in self.db.fetchall("SELECT id, name FROM factions;"):
            faction_names[str(r["id"])] = str(r["name"])
        for r in self.db.fetchall("SELECT id, name FROM districts;"):
            loc_names[str(r["id"])] = str(r["name"])

        if world is not None:
            for cid, c in world.characters.items():
                char_names[cid] = c.name
            for fid, f in world.factions.items():
                faction_names[fid] = f.name
            for did, d in world.districts.items():
                loc_names[did] = d.name
            for lid, loc in world.locations.items():
                loc_names[lid] = loc.name

        return char_names, faction_names, loc_names

    def generate_chronicle(
        self,
        world: World | None = None,
        min_importance: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Generate structured historical Chronicle entries grouped by Year and Act."""
        db_events = self.get_event_history(min_importance=min_importance)
        events_by_id: dict[str, GameEvent] = {ev.id: ev for ev in db_events}
        if world is not None:
            for ev in world.event_bus.event_history:
                if ev.importance >= min_importance and ev.id not in events_by_id:
                    events_by_id[ev.id] = ev

        ordered_events = sorted(events_by_id.values(), key=lambda e: (e.timestamp, e.id))
        char_names, faction_names, loc_names = self._resolve_display_names(world)
        start_hour = world.clock.start_hour if world is not None else DEFAULT_START_HOUR

        entries: list[dict[str, Any]] = []
        for ev in ordered_events:
            cal_mins = int(ev.timestamp) + (start_hour * MINUTES_PER_HOUR)
            year = (cal_mins // MINUTES_PER_YEAR) + 1
            day_of_year = ((cal_mins % MINUTES_PER_YEAR) // MINUTES_PER_DAY) + 1
            act_name = str(
                ev.data.get(
                    "act",
                    WorldClock.get_act_for_year(
                        year,
                        prologue_completed=(day_of_year > 30 or year > 1),
                        day_of_year=day_of_year,
                    ),
                )
            )

            source_name = (
                char_names.get(ev.source_id, faction_names.get(ev.source_id, str(ev.source_id)))
                if ev.source_id
                else "The City"
            )
            target_names = [
                char_names.get(tid, faction_names.get(tid, str(tid)))
                for tid in ev.target_ids
            ]
            target_primary = target_names[0] if target_names else "unknown"
            location_name = (
                loc_names.get(ev.location_id, str(ev.location_id).replace("_", " ").title())
                if ev.location_id
                else "Veyr"
            )

            headline, narrative, causal_note = self._synthesize_event_narrative(
                ev=ev,
                year=year,
                act_name=act_name,
                source_name=source_name,
                target_primary=target_primary,
                target_names=target_names,
                location_name=location_name,
                faction_names=faction_names,
            )

            participants = [p for p in [source_name, *target_names] if p and p != "The City"]
            entries.append(
                {
                    "entry_id": f"chron_{ev.id}",
                    "event_id": ev.id,
                    "event_type": ev.event_type,
                    "timestamp": int(ev.timestamp),
                    "year": year,
                    "day": day_of_year,
                    "act": act_name,
                    "importance": float(ev.importance),
                    "location_id": ev.location_id,
                    "location_name": location_name,
                    "participants": participants,
                    "headline": headline,
                    "narrative": narrative,
                    "causal_note": causal_note,
                }
            )

        if not entries:
            entries.append(
                {
                    "entry_id": "chron_prologue_0",
                    "event_id": "prologue_arrival",
                    "event_type": "PROLOGUE_ARRIVAL",
                    "timestamp": 0,
                    "year": 1,
                    "day": 1,
                    "act": "Prologue",
                    "importance": 1.0,
                    "location_id": "lowtown",
                    "location_name": "Lowtown",
                    "participants": ["Rowan"],
                    "headline": "Arrival in Veyr",
                    "narrative": (
                        "[Year 1, Prologue] Rowan arrived in Lowtown as tensions simmered "
                        "between the City Guard and the Lowtown Syndicate."
                    ),
                    "causal_note": "Campaign beginning in Veyr.",
                }
            )

        if world is not None:
            world.chronicle = list(entries)
        return entries

    def _synthesize_event_narrative(
        self,
        ev: GameEvent,
        year: int,
        act_name: str,
        source_name: str,
        target_primary: str,
        target_names: list[str],
        location_name: str,
        faction_names: dict[str, str],
    ) -> tuple[str, str, str]:
        et = ev.event_type
        d = ev.data
        prefix = f"[Year {year}, {act_name}]"

        if et in ("LIMB_INJURED", "CHARACTER_INJURED"):
            body_part = str(d.get("body_part", "body")).replace("_", " ")
            injury = str(d.get("injury", d.get("injury_type", "wound"))).replace("_", " ")
            weapon = d.get("weapon")
            weapon_clause = f" with a {str(weapon).replace('_', ' ')}" if weapon else ""
            headline = f"{target_primary} Suffered {injury.title()}"
            narrative = (
                f"{prefix} In {location_name}, {source_name} inflicted a {injury} on "
                f"{target_primary}'s {body_part}{weapon_clause}, leaving a lasting mark on their physical history."
            )
            causal_note = f"Physical trauma to {target_primary}'s {body_part} altered combat capability and personal grudges."
            return headline, narrative, causal_note

        if et == "CHARACTER_INCAPACITATED":
            headline = f"{target_primary} Incapacitated in {location_name}"
            narrative = f"{prefix} {target_primary} was incapacitated during combat in {location_name} by {source_name}."
            causal_note = f"Removed {target_primary} from active duty and shifted local balance."
            return headline, narrative, causal_note

        if et == "CHARACTER_DIED":
            cause = str(d.get("cause", f"slain by {source_name}"))
            headline = f"Death of {target_primary}"
            narrative = f"{prefix} {target_primary} fell in {location_name} ({cause}), creating ripple effects across Veyr."
            causal_note = f"Created a permanent vacancy and lasting memories among witnesses."
            return headline, narrative, causal_note

        if et == "NEMESIS_CREATED":
            headline = f"Rise of Nemesis: {target_primary}"
            narrative = (
                f"{prefix} {target_primary} emerged as a sworn Nemesis after surviving an encounter "
                f"with {source_name} in {location_name}."
            )
            causal_note = f"{target_primary} began pursuing personal vengeance and career advancement."
            return headline, narrative, causal_note

        if et in ("NEMESIS_PROMOTED", "RIVAL_PROMOTED"):
            fid = str(d.get("faction_id", ev.source_id or ""))
            fac_name = faction_names.get(fid, fid.replace("_", " ").title() or "their faction")
            new_rank = str(d.get("new_rank", d.get("rank", "higher rank"))).title()
            reason = d.get("reason")
            reason_clause = f" ({reason})" if reason else ""
            headline = f"{target_primary} Promoted to {new_rank}"
            narrative = f"{prefix} Within {fac_name}, {target_primary} rose to the rank of {new_rank}{reason_clause}."
            causal_note = f"Altered command hierarchy within {fac_name}."
            return headline, narrative, causal_note

        if et == "NEMESIS_ADAPTED":
            tactic = str(d.get("tactic", d.get("adaptation", "player tactics"))).replace("_", " ")
            headline = f"{target_primary} Adapted Combat Tactics"
            narrative = (
                f"{prefix} {target_primary} adapted to {source_name}'s combat tactics, "
                f"preparing countermeasures against {tactic}."
            )
            causal_note = f"Future encounters with {target_primary} reflect learned countermeasures."
            return headline, narrative, causal_note

        if et in ("FACTION_ACTION_TAKEN", "DISTRICT_INFLUENCE_CHANGED"):
            fid = str(d.get("faction_id", ev.source_id or ""))
            fac_name = faction_names.get(fid, source_name)
            action_name = str(d.get("action", d.get("goal", "political maneuver"))).replace("_", " ")
            inf_pct = d.get("influence_pct", d.get("new_influence"))
            pct_clause = f", shifting local influence to {inf_pct}%" if inf_pct is not None else ""
            headline = f"{fac_name} Acted in {location_name}"
            narrative = f"{prefix} {fac_name} executed '{action_name}' in {location_name}{pct_clause}."
            causal_note = f"Reshaped district conditions and faction balance in {location_name}."
            return headline, narrative, causal_note

        if et == "LEADERSHIP_VACANCY":
            fid = str(d.get("faction_id", ev.source_id or ""))
            fac_name = faction_names.get(fid, source_name)
            headline = f"Leadership Vacancy in {fac_name}"
            narrative = f"{prefix} A leadership vacancy opened in {fac_name} following the absence of {target_primary}."
            causal_note = f"Triggered succession competition among ambitious officers in {fac_name}."
            return headline, narrative, causal_note

        if et == "POLITICAL_CONFLICT_STARTED":
            headline = f"Political Conflict in {location_name}"
            narrative = f"{prefix} Open political conflict erupted between {source_name} and {target_primary} in {location_name}."
            causal_note = "Escalated city-wide political tensions."
            return headline, narrative, causal_note

        if et in ("COMPANION_APPROVAL_CHANGED", "COMPANION_BREAKING_POINT"):
            change_desc = str(d.get("reason", d.get("state", "personal conviction")))
            headline = f"Companion Shift: {target_primary}"
            narrative = f"{prefix} Companion {target_primary}'s bond shifted ({change_desc}) following decisions in {location_name}."
            causal_note = f"Affected {target_primary}'s loyalty and personal trajectory."
            return headline, narrative, causal_note

        if et in ("RUMOR_SPREAD", "RUMOR_PLANTED"):
            claim = str(d.get("claim", "a controversial act occurred"))
            conf = d.get("confidence", 50)
            headline = f"Rumor Circulated in {location_name}"
            narrative = f"{prefix} Rumors spread through {location_name} claiming that '{claim}' (confidence {conf}%)."
            causal_note = "Shifted public perception and faction reactions."
            return headline, narrative, causal_note

        if et in ("QUEST_COMPLETED", "QUEST_STARTED", "QUEST_UPDATED"):
            q_title = str(d.get("title", target_primary))
            status = str(d.get("status", et.split("_")[-1].lower()))
            approach = d.get("approach")
            app_clause = f" via '{approach}'" if approach else ""
            headline = f"Quest {status.title()}: {q_title}"
            narrative = f"{prefix} Quest '{q_title}' reached state '{status}'{app_clause} in {location_name}."
            causal_note = "Propagated narrative consequences into the city simulation."
            return headline, narrative, causal_note

        if et == "TIME_EVENT_TRIGGERED":
            desc = str(d.get("description", d.get("event_name", "a major civic upheaval")))
            headline = f"City Event in {location_name}"
            narrative = f"{prefix} Veyr experienced a major city event in {location_name}: {desc}."
            causal_note = "Impacted district stability, economy, and population."
            return headline, narrative, causal_note

        custom_desc = d.get("description")
        headline = f"{et.replace('_', ' ').title()} in {location_name}"
        if custom_desc:
            narrative = f"{prefix} {custom_desc}"
        else:
            targets_str = ", ".join(target_names) if target_names else "the city"
            narrative = f"{prefix} {source_name} triggered {et} involving {targets_str} in {location_name}."
        causal_note = f"Recorded in Veyr's historical log (importance {ev.importance:.2f})."
        return headline, narrative, causal_note

    def format_chronicle_text(
        self,
        world: World | None = None,
        min_importance: float = 0.5,
    ) -> str:
        """Render the historical Chronicle as human-readable text grouped by Year and Act."""
        entries = self.generate_chronicle(world=world, min_importance=min_importance)
        seed = world.seed if world is not None else DEFAULT_WORLD_SEED
        current_year = world.clock.year if world is not None else entries[-1]["year"]
        current_act = world.clock.act if world is not None else entries[-1]["act"]

        lines: list[str] = [
            "=== THE CHRONICLE OF VEYR ===",
            f"World Seed: {seed} | Current Timeline: Year {current_year} ({current_act})",
            "",
        ]

        if world is not None and world.districts:
            lines.append("--- Current District Power Balance ---")
            for did, dist in sorted(world.districts.items()):
                if dist.faction_influence:
                    top_fac, top_pct = max(dist.faction_influence.items(), key=lambda kv: kv[1])
                    lines.append(
                        f"  * {dist.name}: Dominant influence '{top_fac}' ({top_pct:.1f}%), "
                        f"Security {dist.security:.0f}, Unrest {dist.unrest:.0f}, Crime {dist.crime:.0f}"
                    )
                else:
                    lines.append(f"  * {dist.name}: Unclaimed")
            lines.append("")

        grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for entry in entries:
            key = (int(entry["year"]), str(entry["act"]))
            grouped.setdefault(key, []).append(entry)

        for (year, act), group_entries in sorted(grouped.items(), key=lambda kv: kv[0][0]):
            lines.append(f"## Year {year} — {act}")
            for item in group_entries:
                lines.append(f"- Day {item['day']}: {item['narrative']}")
                if item.get("causal_note"):
                    lines.append(f"  -> Consequence: {item['causal_note']}")
            lines.append("")

        return "\n".join(lines).strip()

    # ------------------------------------------------------------------
    # Save Slot Browser, Deletion, Most Recent & Autosave (GEMINI_PLAN §1.1)
    # ------------------------------------------------------------------

    def list_save_slots(self) -> list[dict[str, Any]]:
        """Return metadata dicts for all saved slots ordered most-recent first."""
        rows = self.db.fetchall(
            """
            SELECT slot, world_seed, save_slots."current_timestamp" AS world_ts,
                   current_year, current_act, payload_json, created_at
            FROM save_slots
            ORDER BY created_at DESC, rowid DESC;
            """
        )
        slots: list[dict[str, Any]] = []
        for row in rows:
            slot_name = str(row["slot"])
            try:
                current_ts = int(row["world_ts"] or 0)
            except (TypeError, ValueError):
                current_ts = 0
            current_year = int(row["current_year"] or 1)
            current_act = str(row["current_act"] or "Prologue")
            created_at = str(row["created_at"] or "")

            char_name = "Rowan"
            epithet = ""
            day = ((current_ts + DEFAULT_START_HOUR * MINUTES_PER_HOUR) % MINUTES_PER_YEAR) // MINUTES_PER_DAY + 1
            location_id = ""
            location_name = ""
            gold = 0.0
            difficulty = "balanced"
            ironman = False

            try:
                payload = json.loads(str(row["payload_json"]))
                if isinstance(payload, dict):
                    player_id = str(payload.get("player_id", "player"))
                    chars = payload.get("characters", {})
                    player_data = chars.get(player_id, {}) if isinstance(chars, dict) else {}
                    if isinstance(player_data, dict):
                        char_name = str(player_data.get("name", char_name))
                        location_id = str(player_data.get("location_id", ""))
                        needs = player_data.get("needs", {})
                        if isinstance(needs, dict):
                            gold = float(needs.get("wealth", 0.0))
                    locs = payload.get("locations", {})
                    if isinstance(locs, dict) and location_id in locs and isinstance(locs[location_id], dict):
                        location_name = str(locs[location_id].get("name", location_id))
                    else:
                        location_name = location_id
                    flags = payload.get("flags", {})
                    if isinstance(flags, dict):
                        epithet = str(flags.get("epithet", ""))
                        difficulty = str(flags.get("difficulty", "balanced"))
                        ironman = bool(flags.get("ironman", False))
                    clock_dict = payload.get("clock", {})
                    if isinstance(clock_dict, dict):
                        if "year" in clock_dict:
                            current_year = int(clock_dict["year"])
                        if "day_of_year" in clock_dict:
                            day = int(clock_dict["day_of_year"])
                        elif "day" in clock_dict:
                            day = int(clock_dict["day"])
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

            slots.append(
                {
                    "slot": slot_name,
                    "character_name": char_name,
                    "epithet": epithet,
                    "act": current_act,
                    "year": current_year,
                    "day": day,
                    "location_id": location_id,
                    "location_name": location_name or location_id,
                    "gold": gold,
                    "difficulty": difficulty,
                    "ironman": ironman,
                    "created_at": created_at,
                    "timestamp": current_ts,
                }
            )
        return slots

    def delete_save_slot(self, slot: str) -> bool:
        """Delete a save slot by name. Returns True if deleted, False if not found."""
        existing = self.db.fetchone("SELECT slot FROM save_slots WHERE slot = ?;", (slot,))
        if existing is None:
            return False
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM save_slots WHERE slot = ?;", (slot,))
            ws_row = conn.execute("SELECT active_slot FROM world_state WHERE id = 1;").fetchone()
            if ws_row is not None and str(ws_row["active_slot"]) == slot:
                conn.execute("UPDATE world_state SET active_slot = '' WHERE id = 1;")
        return True

    def get_most_recent_slot(self) -> dict[str, Any] | None:
        """Return metadata for the most recently saved slot, or None if no saves exist."""
        slots = self.list_save_slots()
        return slots[0] if slots else None

    def autosave(
        self,
        world: World,
        reason: str = "autosave",
        autosave_mode: str | None = None,
    ) -> str | None:
        """Perform an autosave respecting `autosave_mode` and Ironman single-slot rules."""
        mode = (
            str(autosave_mode).strip().lower()
            if autosave_mode is not None
            else str(world.flags.get("autosave_mode", "daily_and_precombat")).strip().lower()
        )
        if mode == "off":
            return None
        if mode == "precombat" and str(reason).strip().lower() == "daily":
            return None

        target_slot = "ironman" if bool(world.flags.get("ironman")) else "autosave"
        self.save_game(world, slot=target_slot)
        return target_slot
