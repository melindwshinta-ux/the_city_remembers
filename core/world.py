"""Global World state container and entity lookup helpers (GDD Sections 3, 13, 15)."""

from __future__ import annotations

from typing import Any

from config import DEFAULT_WORLD_SEED
from core.clock import WorldClock
from core.event_bus import EventBus, GameEvent
from core.random_generator import SeededRNG
from entities.character import Character
from entities.companion import CompanionProfile
from entities.district import District, Location
from entities.enemy import NemesisProfile
from entities.faction import Faction
from entities.item import InventoryEntry, Item
from entities.quest import Quest, Rumor


class World:
    """Central in-memory state container for the city of Veyr."""

    def __init__(
        self,
        seed: int = DEFAULT_WORLD_SEED,
        clock: WorldClock | None = None,
        rng: SeededRNG | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.seed: int = int(seed)
        self.clock: WorldClock = clock if clock is not None else WorldClock()
        self.rng: SeededRNG = rng if rng is not None else SeededRNG(self.seed)
        self.event_bus: EventBus = event_bus if event_bus is not None else EventBus()

        # Entity collections keyed by stable string IDs (never names)
        self.characters: dict[str, Character] = {}
        self.companions: dict[str, CompanionProfile] = {}
        self.nemesis_profiles: dict[str, NemesisProfile] = {}
        self.factions: dict[str, Faction] = {}
        self.districts: dict[str, District] = {}
        self.locations: dict[str, Location] = {}
        self.items: dict[str, Item] = {}
        self.inventories: dict[str, list[InventoryEntry]] = {}
        self.quests: dict[str, Quest] = {}
        self.rumors: dict[str, Rumor] = {}

        # Global world state
        self.player_id: str = "player"
        self.player_party: list[str] = []
        self.economy: dict[str, Any] = {
            "price_index": 1.0,
            "wage_index": 1.0,
            "shortages": [],
            "trade_volume": 100.0,
        }
        self.reputation: dict[str, Any] = {
            "district": {},
            "faction": {},
            "individual_npc": {},
            "general_public": 0.0,
            "criminal_underworld": 0.0,
            "noble_society": 0.0,
        }
        self.chronicle: list[dict[str, Any]] = []
        self.flags: dict[str, Any] = {}
        self.schema_version: int = 1

    @property
    def player(self) -> Character | None:
        """Return the player Character instance if present."""
        if self.player_id in self.characters:
            return self.characters[self.player_id]
        for char in self.characters.values():
            if char.is_player:
                return char
        return None

    @player.setter
    def player(self, value: Character | None) -> None:
        if value is not None:
            self.player_id = value.id
            self.characters[value.id] = value

    # --- Entity Registration & Direct Lookup ---

    def add_character(self, character: Character) -> None:
        self.characters[character.id] = character
        if character.is_player:
            self.player_id = character.id
        if character.nemesis_profile is not None and isinstance(character.nemesis_profile, NemesisProfile):
            self.nemesis_profiles[character.id] = character.nemesis_profile

    def get_character(self, char_id: str) -> Character | None:
        return self.characters.get(char_id)

    def add_companion(self, companion: CompanionProfile) -> None:
        self.companions[companion.character_id] = companion
        if companion.in_party and companion.character_id not in self.player_party:
            self.player_party.append(companion.character_id)

    def get_companion(self, char_id: str) -> CompanionProfile | None:
        return self.companions.get(char_id)

    def add_nemesis(self, profile: NemesisProfile) -> None:
        self.nemesis_profiles[profile.character_id] = profile
        if profile.character_id in self.characters:
            self.characters[profile.character_id].is_nemesis = True
            self.characters[profile.character_id].nemesis_profile = profile

    def get_nemesis(self, char_id: str) -> NemesisProfile | None:
        return self.nemesis_profiles.get(char_id)

    def add_faction(self, faction: Faction) -> None:
        self.factions[faction.id] = faction

    def get_faction(self, faction_id: str) -> Faction | None:
        return self.factions.get(faction_id)

    def add_district(self, district: District) -> None:
        self.districts[district.id] = district

    def get_district(self, district_id: str) -> District | None:
        return self.districts.get(district_id)

    def add_location(self, location: Location) -> None:
        self.locations[location.id] = location
        if location.district_id in self.districts:
            dist = self.districts[location.district_id]
            if location.id not in dist.locations:
                dist.locations.append(location.id)

    def get_location(self, location_id: str) -> Location | None:
        return self.locations.get(location_id)

    def add_item(self, item: Item) -> None:
        self.items[item.id] = item

    def get_item(self, item_id: str) -> Item | None:
        return self.items.get(item_id)

    def add_inventory_entry(self, entry: InventoryEntry) -> None:
        entries = self.inventories.setdefault(entry.character_id, [])
        for existing in entries:
            if existing.item_id == entry.item_id and existing.slot == entry.slot and existing.equipped == entry.equipped:
                existing.quantity += entry.quantity
                return
        entries.append(entry)

    def get_inventory(self, char_id: str) -> list[InventoryEntry]:
        return list(self.inventories.get(char_id, []))

    def add_quest(self, quest: Quest) -> None:
        self.quests[quest.id] = quest

    def get_quest(self, quest_id: str) -> Quest | None:
        return self.quests.get(quest_id)

    def add_rumor(self, rumor: Rumor) -> None:
        self.rumors[rumor.id] = rumor

    def get_rumor(self, rumor_id: str) -> Rumor | None:
        return self.rumors.get(rumor_id)

    # --- Deterministic Alias & Name Resolution (GDD Section 16) ---

    def find_character_by_name_or_alias(self, query: str) -> Character | None:
        """Resolve an ID, full name, rank+name, or token alias (e.g. 'captain voss', 'sera') to a Character."""
        q = query.strip().lower()
        if not q:
            return None
        if query in self.characters:
            return self.characters[query]
        for cid in sorted(self.characters.keys()):
            if cid.lower() == q:
                return self.characters[cid]

        # Exact case-insensitive name match
        for cid in sorted(self.characters.keys()):
            char = self.characters[cid]
            if char.name.strip().lower() == q:
                return char

        # Rank + name or token match (e.g. "captain voss" matching "Captain Garrick Voss" or "Garrick Voss")
        q_tokens = [t for t in q.replace("_", " ").split() if t]
        for cid in sorted(self.characters.keys()):
            char = self.characters[cid]
            haystack = f"{char.rank or ''} {char.name} {cid}".lower().replace("_", " ")
            hay_tokens = haystack.split()
            if all(any(qt == ht or ht.startswith(qt) for ht in hay_tokens) for qt in q_tokens):
                return char
        return None

    def find_faction_by_name_or_alias(self, query: str) -> Faction | None:
        """Resolve a faction ID or name/alias (e.g. 'city_guard', 'city guard', 'syndicate') to a Faction."""
        q = query.strip().lower()
        if not q:
            return None
        if query in self.factions:
            return self.factions[query]
        q_norm = q.replace(" ", "_")
        if q_norm in self.factions:
            return self.factions[q_norm]
        for fid in sorted(self.factions.keys()):
            fac = self.factions[fid]
            if fid.lower() == q or fac.name.strip().lower() == q:
                return fac
        for fid in sorted(self.factions.keys()):
            fac = self.factions[fid]
            if q in fac.name.lower() or q in fid.lower():
                return fac
        return None

    def find_location_or_district(self, query: str) -> District | Location | None:
        """Resolve a location or district ID/name (e.g. 'harbor', 'lowtown') deterministically."""
        q = query.strip().lower()
        if not q:
            return None
        q_norm = q.replace(" ", "_")
        if query in self.locations:
            return self.locations[query]
        if q_norm in self.locations:
            return self.locations[q_norm]
        if query in self.districts:
            return self.districts[query]
        if q_norm in self.districts:
            return self.districts[q_norm]
        for lid in sorted(self.locations.keys()):
            loc = self.locations[lid]
            if loc.name.strip().lower() == q or q in loc.name.lower():
                return loc
        for did in sorted(self.districts.keys()):
            dist = self.districts[did]
            if dist.name.strip().lower() == q or q in dist.name.lower():
                return dist
        return None

    # --- Full World Dictionary Serialization ---

    def to_dict(self) -> dict[str, Any]:
        """Serialize entire World state to a JSON-compatible dictionary."""
        return {
            "schema_version": self.schema_version,
            "seed": self.seed,
            "player_id": self.player_id,
            "player_party": list(self.player_party),
            "clock": self.clock.to_dict(),
            "rng_state": self.rng.get_state(),
            "characters": {cid: c.to_dict() for cid, c in sorted(self.characters.items())},
            "companions": {cid: comp.to_dict() for cid, comp in sorted(self.companions.items())},
            "nemesis_profiles": {nid: n.to_dict() for nid, n in sorted(self.nemesis_profiles.items())},
            "factions": {fid: f.to_dict() for fid, f in sorted(self.factions.items())},
            "districts": {did: d.to_dict() for did, d in sorted(self.districts.items())},
            "locations": {lid: loc.to_dict() for lid, loc in sorted(self.locations.items())},
            "items": {iid: it.to_dict() for iid, it in sorted(self.items.items())},
            "inventories": {
                cid: [entry.to_dict() for entry in entries]
                for cid, entries in sorted(self.inventories.items())
            },
            "quests": {qid: q.to_dict() for qid, q in sorted(self.quests.items())},
            "rumors": {rid: r.to_dict() for rid, r in sorted(self.rumors.items())},
            "economy": dict(self.economy),
            "reputation": dict(self.reputation),
            "chronicle": list(self.chronicle),
            "flags": dict(self.flags),
            "event_history": [ev.to_dict() for ev in self.event_bus.event_history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> World:
        """Reconstruct a complete World instance from a serialized dictionary."""
        seed = int(data.get("seed", data.get("world_seed", DEFAULT_WORLD_SEED)))
        clock = WorldClock.from_dict(data.get("clock", {}))
        rng = SeededRNG(seed)
        if "rng_state" in data and data["rng_state"]:
            rng.set_state(data["rng_state"])
        event_bus = EventBus()

        world = cls(seed=seed, clock=clock, rng=rng, event_bus=event_bus)
        world.schema_version = int(data.get("schema_version", data.get("version", 1)))
        world.player_id = str(data.get("player_id", "player"))
        world.player_party = [str(p) for p in data.get("player_party", [])]
        world.economy = dict(data.get("economy", world.economy))
        world.reputation = dict(data.get("reputation", world.reputation))
        world.chronicle = list(data.get("chronicle", []))
        world.flags = dict(data.get("flags", {}))

        for did, d_data in data.get("districts", {}).items():
            world.districts[str(did)] = d_data if isinstance(d_data, District) else District.from_dict(d_data)
        for lid, l_data in data.get("locations", {}).items():
            world.locations[str(lid)] = l_data if isinstance(l_data, Location) else Location.from_dict(l_data)
        for fid, f_data in data.get("factions", {}).items():
            world.factions[str(fid)] = f_data if isinstance(f_data, Faction) else Faction.from_dict(f_data)
        for iid, i_data in data.get("items", {}).items():
            world.items[str(iid)] = i_data if isinstance(i_data, Item) else Item.from_dict(i_data)
        for cid, c_data in data.get("characters", {}).items():
            world.characters[str(cid)] = c_data if isinstance(c_data, Character) else Character.from_dict(c_data)
        for cid, comp_data in data.get("companions", {}).items():
            world.companions[str(cid)] = (
                comp_data if isinstance(comp_data, CompanionProfile) else CompanionProfile.from_dict(comp_data)
            )
        for nid, n_data in data.get("nemesis_profiles", {}).items():
            prof = n_data if isinstance(n_data, NemesisProfile) else NemesisProfile.from_dict(n_data)
            world.nemesis_profiles[str(nid)] = prof
            if str(nid) in world.characters:
                world.characters[str(nid)].nemesis_profile = prof
        for cid, inv_list in data.get("inventories", {}).items():
            world.inventories[str(cid)] = [
                e if isinstance(e, InventoryEntry) else InventoryEntry.from_dict(e)
                for e in inv_list
            ]
        for qid, q_data in data.get("quests", {}).items():
            world.quests[str(qid)] = q_data if isinstance(q_data, Quest) else Quest.from_dict(q_data)
        for rid, r_data in data.get("rumors", {}).items():
            world.rumors[str(rid)] = r_data if isinstance(r_data, Rumor) else Rumor.from_dict(r_data)

        for ev_data in data.get("event_history", []):
            ev = ev_data if isinstance(ev_data, GameEvent) else GameEvent.from_dict(ev_data)
            world.event_bus.event_history.append(ev)

        return world
