"""Warsim-style 1-9 & 0 Hierarchical Choice Engine (GEMINI_PLAN §2)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from content import COMMODITIES, PROPERTIES_CATALOG
from core.dialogue_engine import DialogueEngine
from core.settings import VALID_AUTOSAVE_MODES, VALID_DIFFICULTIES, VALID_LAYOUT_MODES, save_settings
from systems.faction_system import generate_petitioners, resolve_petitioner

if TYPE_CHECKING:
    from core.game import Game


PAGE_SIZE = 8


class MenuEngine:
    """Stack-based numbered menu engine supporting [1]-[9] & [0] navigation, Dialogue, and Combat Clash."""

    def __init__(self, game: Game) -> None:
        self.game = game
        self.stack: list[dict[str, Any]] = []
        self.active_dialogue: DialogueEngine | None = None
        self.active_clash: Any = None
        self._aim_submenu: bool = False
        self.last_message: str = ""

    def reset(self) -> None:
        """Reset navigation stack and active modal engines back to Root Hub."""
        self.stack.clear()
        self.active_dialogue = None
        self.active_clash = None
        self._aim_submenu = False
        self.last_message = ""

    def start_dialogue(self, npc_id: str) -> dict[str, Any]:
        """Enter Interactive Dialogue Mode with `npc_id`."""
        self.active_dialogue = DialogueEngine(self.game, npc_id)
        return self.get_screen()

    def start_combat(self, enemies: list[Any], victor_faction: str = "city_guard") -> dict[str, Any]:
        """Enter Streamlined Combat Clash Mode against `enemies`."""
        world = self.game.world
        party = [world.characters[cid] for cid in (world.player_party or ["player"]) if cid in world.characters]
        if not party and world.player is not None:
            party = [world.player]
        self.active_clash = self.game.combat_system.start_clash_session(
            party=party,
            enemies=list(enemies),
            victor_faction=victor_faction,
            world=world,
        )
        self._aim_submenu = False
        return self.get_screen()

    def _push(self, screen_id: str, **context: Any) -> None:
        self.stack.append({"screen_id": screen_id, "page": 0, "context": context})

    def _pop(self) -> None:
        if self.stack:
            self.stack.pop()

    def _current_frame(self) -> dict[str, Any] | None:
        return self.stack[-1] if self.stack else None

    def _player_gold(self) -> float:
        player = self.game.world.player
        return float(player.needs.get("wealth", 0.0)) if player else 0.0

    def _current_location(self) -> tuple[str, Any, str]:
        world = self.game.world
        loc_id = getattr(world.player, "location_id", "lowtown_street") if world.player else "lowtown_street"
        loc = world.locations.get(loc_id)
        dist_id = getattr(loc, "district_id", None) if loc else None
        if not dist_id:
            dist_id = loc_id if loc_id in world.districts else "lowtown"
        return loc_id, loc, dist_id

    @staticmethod
    def _opt(key: str, label: str, tags: list[str] | None = None, enabled: bool = True, **meta: Any) -> dict[str, Any]:
        d: dict[str, Any] = {
            "key": str(key),
            "label": label,
            "tags": list(tags) if tags else [],
            "enabled": bool(enabled),
        }
        if meta:
            d["_meta"] = meta
        return d

    def _paginate_options(
        self,
        items: list[dict[str, Any]],
        page: int,
        back_label: str = "Back",
    ) -> tuple[list[dict[str, Any]], int, int]:
        total_pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
        cur_page = max(0, min(page, total_pages - 1))
        start = cur_page * PAGE_SIZE
        slice_items = items[start : start + PAGE_SIZE]
        opts: list[dict[str, Any]] = []
        for idx, item in enumerate(slice_items, 1):
            opts.append(
                self._opt(
                    str(idx),
                    item["label"],
                    tags=item.get("tags", []),
                    enabled=item.get("enabled", True),
                    **item.get("_meta", {}),
                )
            )
        if len(items) > PAGE_SIZE:
            next_num = ((cur_page + 1) % total_pages) + 1
            opts.append(
                self._opt(
                    "9",
                    f"Next Page ({cur_page + 1}/{total_pages} -> {next_num})",
                    tags=["Page"],
                    enabled=True,
                    _next_page=(cur_page + 1) % total_pages,
                )
            )
        opts.append(self._opt("0", back_label, tags=["Back"], enabled=True))
        return opts, cur_page, total_pages

    # ------------------------------------------------------------------
    # Public Screen Rendering & Selection
    # ------------------------------------------------------------------

    def get_screen(self) -> dict[str, Any]:
        """Return the active screen dict: {title, subtitle, body, mode, options}."""
        if self.active_clash is not None:
            return self._build_combat_screen()
        if self.active_dialogue is not None:
            return self._build_dialogue_screen()

        frame = self._current_frame()
        if frame is None:
            return self._build_root_hub()

        sid = frame["screen_id"]
        builders = {
            "travel_menu": self._build_travel_menu,
            "fast_travel_menu": self._build_fast_travel_menu,
            "talk_menu": self._build_talk_menu,
            "activities_menu": self._build_activities_menu,
            "petitioner_menu": self._build_petitioner_menu,
            "party_menu": self._build_party_menu,
            "anatomy_detail": self._build_anatomy_detail,
            "medicine_menu": self._build_medicine_menu,
            "equipment_menu": self._build_equipment_menu,
            "counsel_menu": self._build_counsel_menu,
            "politics_menu": self._build_politics_menu,
            "faction_list": self._build_faction_list,
            "nemesis_board": self._build_nemesis_board,
            "edict_menu": self._build_edict_menu,
            "economy_menu": self._build_economy_menu,
            "commodity_menu": self._build_commodity_menu,
            "commodity_action": self._build_commodity_action,
            "property_menu": self._build_property_menu,
            "loan_menu": self._build_loan_menu,
            "caravan_menu": self._build_caravan_menu,
            "quests_menu": self._build_quests_menu,
            "approach_menu": self._build_approach_menu,
            "character_sheet": self._build_character_sheet,
            "system_menu": self._build_system_menu,
            "load_menu": self._build_load_menu,
            "settings_menu": self._build_settings_menu,
            "debug_menu": self._build_debug_menu,
        }
        builder = builders.get(sid, self._build_root_hub)
        screen = builder(frame) if frame is not None and sid in builders else self._build_root_hub()
        # Strip internal _meta before returning clean view
        clean_opts = [
            {"key": o["key"], "label": o["label"], "tags": list(o["tags"]), "enabled": bool(o["enabled"])}
            for o in screen["options"]
        ]
        screen["options"] = clean_opts
        return screen

    def _raw_screen_options(self) -> list[dict[str, Any]]:
        frame = self._current_frame()
        if frame is None:
            return self._build_root_hub()["options"]
        sid = frame["screen_id"]
        builders = {
            "travel_menu": self._build_travel_menu,
            "fast_travel_menu": self._build_fast_travel_menu,
            "talk_menu": self._build_talk_menu,
            "activities_menu": self._build_activities_menu,
            "petitioner_menu": self._build_petitioner_menu,
            "party_menu": self._build_party_menu,
            "anatomy_detail": self._build_anatomy_detail,
            "medicine_menu": self._build_medicine_menu,
            "equipment_menu": self._build_equipment_menu,
            "counsel_menu": self._build_counsel_menu,
            "politics_menu": self._build_politics_menu,
            "faction_list": self._build_faction_list,
            "nemesis_board": self._build_nemesis_board,
            "edict_menu": self._build_edict_menu,
            "economy_menu": self._build_economy_menu,
            "commodity_menu": self._build_commodity_menu,
            "commodity_action": self._build_commodity_action,
            "property_menu": self._build_property_menu,
            "loan_menu": self._build_loan_menu,
            "caravan_menu": self._build_caravan_menu,
            "quests_menu": self._build_quests_menu,
            "approach_menu": self._build_approach_menu,
            "character_sheet": self._build_character_sheet,
            "system_menu": self._build_system_menu,
            "load_menu": self._build_load_menu,
            "settings_menu": self._build_settings_menu,
            "debug_menu": self._build_debug_menu,
        }
        builder = builders.get(sid)
        return builder(frame)["options"] if builder else self._build_root_hub()["options"]

    def select(self, key: str | int) -> dict[str, Any]:
        """Execute numbered option [1]-[9] or [0] on the current screen."""
        choice = str(key).strip()

        if self.active_clash is not None:
            return self._select_combat(choice)

        if self.active_dialogue is not None:
            res = self.active_dialogue.choose(choice)
            self.last_message = res.get("message", "")
            if res.get("enter_combat") and res.get("clash_session") is not None:
                self.active_clash = res["clash_session"]
                self.active_dialogue = None
                self._aim_submenu = False
            elif res.get("closed"):
                self.active_dialogue = None
            return {
                "success": bool(res.get("success", False)),
                "message": self.last_message,
                "screen": self.get_screen(),
            }

        frame = self._current_frame()
        if frame is None:
            return self._select_root_hub(choice)

        raw_opts = self._raw_screen_options()
        matched = next((o for o in raw_opts if o["key"] == choice), None)
        if matched is None:
            self.last_message = f"Invalid choice '{choice}'."
            return {"success": False, "message": self.last_message, "screen": self.get_screen()}

        if choice == "9" and "_meta" in matched and "_next_page" in matched["_meta"]:
            frame["page"] = matched["_meta"]["_next_page"]
            self.last_message = f"Page {frame['page'] + 1}."
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        if choice == "0":
            self._pop()
            self.last_message = "Returned."
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        if not matched.get("enabled", True):
            self.last_message = f"Option unavailable: {matched['label']}"
            return {"success": False, "message": self.last_message, "screen": self.get_screen()}

        return self._dispatch_submenu(frame, choice, matched)

    # ------------------------------------------------------------------
    # Root Hub
    # ------------------------------------------------------------------

    def _build_root_hub(self) -> dict[str, Any]:
        world = self.game.world
        loc_id, loc, dist_id = self._current_location()
        loc_name = getattr(loc, "name", loc_id) if loc else loc_id
        dist = world.districts.get(dist_id)
        dist_name = getattr(dist, "name", dist_id) if dist else dist_id
        debug_on = bool(getattr(getattr(self.game, "settings", None), "enable_debug_cheat", False))

        body_lines = [
            f"Location: {loc_name} ({dist_name})",
            f"Time: {world.clock.act} — Year {world.clock.year}, Day {world.clock.day}, {world.clock.hour:02d}:{world.clock.minute:02d}",
            f"Gold: {self._player_gold():.0f}g | Party: {len(world.player_party)} member(s)",
        ]
        if loc and getattr(loc, "description", ""):
            body_lines.append(loc.description)
        if self.last_message:
            body_lines.append(f"\nLast: {self.last_message}")

        zero_opt = (
            self._opt("0", "Cheat & Debug Menu", tags=["Debug ON"], enabled=True)
            if debug_on
            else self._opt("0", "Pass Time / Rest & City Digest", tags=["24h", "Digest"], enabled=True)
        )

        options = [
            self._opt("1", "Travel & Explore District", tags=["Move", "Inspect"]),
            self._opt("2", "Speak with Someone Nearby", tags=["Dialogue"]),
            self._opt("3", "Local Activities & Establishments", tags=["Tavern/Market/Safehouse"]),
            self._opt("4", "Party, Anatomy & Medicine", tags=["29-Part Health", "Counsel"]),
            self._opt("5", "Faction Politics & Nemesis Board", tags=["7 Factions", "Ops"]),
            self._opt("6", "Trade, Property & Economy", tags=["Market", "Properties"]),
            self._opt("7", "Quests, Rumors & City Chronicle", tags=["Missions", "Chronicle"]),
            self._opt("8", "Character Sheet & Reputation", tags=["Stats", "Epithets"]),
            self._opt("9", "System, Save / Load & Settings", tags=["Save/Load", "Settings"]),
            zero_opt,
        ]
        return {
            "title": "THE CITY REMEMBERS — VEYR",
            "subtitle": f"{loc_name} ({dist_name})",
            "body": "\n".join(body_lines),
            "mode": "hub",
            "options": options,
        }

    def _select_root_hub(self, choice: str) -> dict[str, Any]:
        mapping = {
            "1": "travel_menu",
            "2": "talk_menu",
            "3": "activities_menu",
            "4": "party_menu",
            "5": "politics_menu",
            "6": "economy_menu",
            "7": "quests_menu",
            "8": "character_sheet",
            "9": "system_menu",
        }
        if choice in mapping:
            self._push(mapping[choice])
            self.last_message = ""
            return {"success": True, "message": "", "screen": self.get_screen()}

        if choice == "0":
            debug_on = bool(getattr(getattr(self.game, "settings", None), "enable_debug_cheat", False))
            if debug_on:
                self._push("debug_menu")
                self.last_message = ""
                return {"success": True, "message": "", "screen": self.get_screen()}
            self.game.simulation.advance_time(1440, world=self.game.world)
            digest = self.game.world.flags.get("last_daily_digest", {})
            lines = digest.get("summary_lines", ["A day passes in Veyr."])
            self.last_message = " | ".join(lines)
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        self.last_message = f"Invalid hub choice '{choice}'. Press 1-9 or 0."
        return {"success": False, "message": self.last_message, "screen": self.get_screen()}

    # ------------------------------------------------------------------
    # Dialogue & Combat Adapters
    # ------------------------------------------------------------------

    def _build_dialogue_screen(self) -> dict[str, Any]:
        assert self.active_dialogue is not None
        view = self.active_dialogue.get_view()
        inj_str = ", ".join(view["visible_injuries"]) if view["visible_injuries"] else "None"
        axes = view["axes"]
        bars = view["bars"]
        body_lines = [
            f"{view['name']} ({view['title_rank']} — {view['faction']})",
            f"Relationship: {view['relationship_state']} | Visible Injuries: {inj_str}",
            (
                f"Trust {bars['trust']} | Respect {bars['respect']} | Affection {bars['affection']}\n"
                f"Resentment {bars['resentment']} | Fear {bars['fear']} | Dependency {bars['dependency']}"
            ),
            f"\n\"{view['greeting']}\"",
        ]
        if view.get("last_message"):
            body_lines.append(f"\nOutcome: {view['last_message']}")
        return {
            "title": f"Dialogue — {view['name']}",
            "subtitle": f"{view['faction']} | {view['relationship_state']}",
            "body": "\n".join(body_lines),
            "mode": "dialogue",
            "options": view["options"],
            "dialogue_view": view,
        }

    def _build_combat_screen(self) -> dict[str, Any]:
        session = self.active_clash
        assert session is not None
        party_lines = [
            f"  {c.name}: Consc {getattr(c, 'consciousness', 100):.0f}% | Status {getattr(c, 'status', 'alive')}"
            for c in session.party
        ]
        enemy_lines = [
            f"  {e.name}: Consc {getattr(e, 'consciousness', 100):.0f}% | Morale {getattr(e, 'morale', 75):.0f} ({getattr(e, 'morale_state', 'confident')})"
            for e in session.enemies
        ]
        log_lines = session.combat_log[-5:] if session.combat_log else ["Clash ready."]
        body = (
            f"Round {session.round_number}\n"
            f"Party:\n" + "\n".join(party_lines) + "\n"
            f"Enemies:\n" + "\n".join(enemy_lines) + "\n"
            f"Combat Log:\n  " + "\n  ".join(log_lines)
        )

        if self._aim_submenu:
            options = [
                self._opt("1", "Head (Concussion / Blindness)", tags=["72% Acc"]),
                self._opt("2", "Arms (Cripple Enemy Attack)", tags=["-50% Enemy Dmg"]),
                self._opt("3", "Torso (Vital / Bleeding)", tags=["Standard"]),
                self._opt("4", "Legs (Cripple Mobility)", tags=["Pin Enemy"]),
                self._opt("0", "Back", tags=["Back"]),
            ]
        else:
            can_surrender = any(float(getattr(e, "morale", 75.0)) <= 30.0 for e in session.enemies)
            options = [
                self._opt("1", "Balanced Strike", tags=["Standard"]),
                self._opt("2", "Heavy Brutal Assault", tags=["+35% Dmg", "-Def"]),
                self._opt("3", "Aimed Limb / Organ Strike", tags=["Sub-menu"]),
                self._opt("4", "Defensive Stance & Rally Party", tags=["-50% In-Dmg", "+10 Morale"]),
                self._opt("5", "Field Triage & Bandage", tags=["Stop Bleed", "+15% Consc"]),
                self._opt("6", "Tactical Trick / Arcane Surge", tags=["Disarm/-15 Morale"]),
                self._opt("7", "Demand Surrender", tags=["Enemy Morale <= 30"] if can_surrender else ["Low Chance"]),
                self._opt("0", "Retreat / Non-Lethal Surrender", tags=["Escape"]),
            ]

        return {
            "title": "COMBAT CLASH",
            "subtitle": f"Round {session.round_number} | Status: {session.status}",
            "body": body,
            "mode": "combat",
            "options": [
                {"key": o["key"], "label": o["label"], "tags": o["tags"], "enabled": o["enabled"]}
                for o in options
            ],
        }

    def _select_combat(self, choice: str) -> dict[str, Any]:
        session = self.active_clash
        assert session is not None
        if self._aim_submenu:
            if choice == "0":
                self._aim_submenu = False
                self.last_message = "Cancelled aimed strike."
                return {"success": True, "message": self.last_message, "screen": self.get_screen()}
            if choice not in ("1", "2", "3", "4"):
                self.last_message = "Choose [1]-[4] for aimed limb or [0] Back."
                return {"success": False, "message": self.last_message, "screen": self.get_screen()}
            aim_map = {"1": "head", "2": "arms", "3": "torso", "4": "legs"}
            self._aim_submenu = False
            res = self.game.combat_system.resolve_clash_turn(
                session, "3", aim_target=aim_map[choice], world=self.game.world
            )
        else:
            if choice == "3":
                self._aim_submenu = True
                self.last_message = "Select target limb or organ:"
                return {"success": True, "message": self.last_message, "screen": self.get_screen()}
            if choice not in ("1", "2", "4", "5", "6", "7", "0"):
                self.last_message = f"Invalid combat choice '{choice}'."
                return {"success": False, "message": self.last_message, "screen": self.get_screen()}
            res = self.game.combat_system.resolve_clash_turn(session, choice, world=self.game.world)

        log = res.get("combat_log") or []
        self.last_message = log[-1] if log else f"Clash status: {res.get('status')}"
        if session.status != "active":
            self.active_clash = None
            self._aim_submenu = False
        return {"success": True, "message": self.last_message, "combat_result": res, "screen": self.get_screen()}

    # ------------------------------------------------------------------
    # Submenu Builders & Dispatch
    # ------------------------------------------------------------------

    def _build_travel_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        loc_id, loc, dist_id = self._current_location()
        items: list[dict[str, Any]] = []
        for dest_id in getattr(loc, "connected_locations", []) if loc else []:
            dest = world.locations.get(dest_id)
            dname = getattr(dest, "name", dest_id) if dest else dest_id
            items.append({"label": f"Go to {dname}", "tags": ["25m"], "enabled": True, "_meta": {"op": "move", "target": dest_id}})
        items.append({"label": "District Fast-Travel", "tags": ["Sub-menu"], "enabled": True, "_meta": {"op": "push", "screen": "fast_travel_menu"}})
        items.append({"label": f"Inspect {getattr(loc, 'name', loc_id)}", "tags": ["5m", "Clues"], "enabled": True, "_meta": {"op": "inspect", "target": loc_id}})
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {
            "title": "Travel & Explore District",
            "subtitle": f"Current: {getattr(loc, 'name', loc_id)}",
            "body": self.last_message or (getattr(loc, "description", "") if loc else "Select a destination."),
            "mode": "submenu",
            "options": opts,
        }

    def _build_fast_travel_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        items = [
            {"label": f"{d.name} ({d.major_conflict})", "tags": ["25m"], "enabled": True, "_meta": {"op": "move", "target": d.id}}
            for d in world.districts.values()
        ]
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "District Fast-Travel", "subtitle": "7 Districts of Veyr", "body": self.last_message or "Choose a district.", "mode": "submenu", "options": opts}

    def _build_talk_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        loc_id, loc, _ = self._current_location()
        nearby_ids: list[str] = []
        if loc:
            for nid in getattr(loc, "npcs_present", []):
                if nid != "player" and nid not in nearby_ids:
                    nearby_ids.append(nid)
        for pid in getattr(world, "player_party", []):
            if pid != "player" and pid not in nearby_ids:
                nearby_ids.append(pid)
        for cid, ch in world.characters.items():
            if cid != "player" and getattr(ch, "location_id", None) == loc_id and cid not in nearby_ids:
                nearby_ids.append(cid)

        items = []
        for nid in nearby_ids:
            ch = world.characters.get(nid)
            if ch:
                tag = "Companion" if getattr(ch, "is_companion", False) else (ch.faction_id or "Citizen")
                items.append({"label": f"Speak with {ch.name}", "tags": [tag], "enabled": True, "_meta": {"op": "talk", "target": nid}})
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {
            "title": "Speak with Someone Nearby",
            "subtitle": f"{len(items)} person(s) nearby",
            "body": self.last_message or ("Select someone to speak with." if items else "No one is nearby."),
            "mode": "submenu",
            "options": opts,
        }

    def _build_activities_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        loc_id, loc, _ = self._current_location()
        gold = self._player_gold()
        items: list[dict[str, Any]] = []
        if "tavern" in loc_id:
            items.append({"label": "Buy a Round for Rumors", "tags": ["Cost: 10g", "+Intel"], "enabled": gold >= 10.0, "_meta": {"op": "tavern_round"}})
            items.append({"label": "Play Bones / Dice Wager", "tags": ["Cost: 20g", "RNG"], "enabled": gold >= 20.0, "_meta": {"op": "dice_wager"}})
            items.append({"label": "Hear Petitioners at the Gull", "tags": ["1-3 Petitioners"], "enabled": True, "_meta": {"op": "hear_petitioners", "loc_type": "tavern"}})
        elif "market" in loc_id:
            items.append({"label": "Trade District Commodities", "tags": ["Market"], "enabled": True, "_meta": {"op": "push", "screen": "commodity_menu"}})
            items.append({"label": "Visit Apothecary / Field Aid", "tags": ["Cost: 20g", "Heal"], "enabled": gold >= 20.0, "_meta": {"op": "apothecary"}})
        elif "safehouse" in loc_id:
            items.append({"label": "Rest 8 Hours at Safehouse", "tags": ["8h", "Recover"], "enabled": True, "_meta": {"op": "rest_8h"}})
            items.append({"label": "Hold Court / Hear Petitioners", "tags": ["1-3 Petitioners"], "enabled": True, "_meta": {"op": "hear_petitioners", "loc_type": "safehouse"}})
        items.append({"label": "Rest & Recover (8 Hours)", "tags": ["8h"], "enabled": True, "_meta": {"op": "rest_8h"}})
        items.append({"label": "Inspect Surroundings", "tags": ["5m"], "enabled": True, "_meta": {"op": "inspect", "target": loc_id}})
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {
            "title": "Local Activities & Establishments",
            "subtitle": getattr(loc, "name", loc_id),
            "body": self.last_message or "Choose a local activity.",
            "mode": "submenu",
            "options": opts,
        }

    def _build_petitioner_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        pets = frame["context"].get("petitioners", [])
        idx = frame["context"].get("index", 0)
        if idx >= len(pets):
            opts = [self._opt("0", "Back", tags=["Done"])]
            return {"title": "Petitioners", "subtitle": "Court Adjourned", "body": self.last_message or "All petitioners heard.", "mode": "submenu", "options": opts}
        pet = pets[idx]
        opts = [
            self._opt(str(c["idx"]), c["label"], tags=[c.get("effect", "")], _meta={"op": "resolve_pet", "choice_idx": c["idx"]})
            for c in pet.get("choices", [])
        ]
        opts.append(self._opt("0", "Back", tags=["Leave Court"]))
        return {
            "title": f"Petitioner ({idx + 1}/{len(pets)}): {pet['name']}",
            "subtitle": f"Role: {pet['role'].title()} | District: {pet['district_id']}",
            "body": f"\"{pet['request']}\"\n\n{self.last_message}",
            "mode": "submenu",
            "options": opts,
        }

    def _build_party_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        items = [
            {"label": "Inspect 29-Part Body Health (Rowan)", "tags": [f"Consc {getattr(world.player, 'consciousness', 100):.0f}%"], "enabled": True, "_meta": {"op": "push", "screen": "anatomy_detail"}},
            {"label": "Apply 5-Stage Medical Treatment", "tags": ["Medicine"], "enabled": True, "_meta": {"op": "push", "screen": "medicine_menu"}},
            {"label": "Manage Equipment & Gear", "tags": ["Loadout"], "enabled": True, "_meta": {"op": "push", "screen": "equipment_menu"}},
            {"label": "Companion Campfire Counsel", "tags": ["Resolve Tension"], "enabled": True, "_meta": {"op": "push", "screen": "counsel_menu"}},
        ]
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "Party, Anatomy & Medicine", "subtitle": f"Party Size: {len(world.player_party)}", "body": self.last_message or "Manage party health, gear, and morale.", "mode": "submenu", "options": opts}

    def _build_anatomy_detail(self, frame: dict[str, Any]) -> dict[str, Any]:
        player = self.game.world.player
        body = getattr(player, "body", {}) if player else {}
        injured = [p for p in body.values() if p.injuries or not p.functional or p.integrity < p.max_integrity]
        summary = [f"{p.name}: {p.integrity:.0f}/{p.max_integrity:.0f} ({len(p.injuries)} injuries)" for p in (injured or list(body.values())[:8])]
        return {
            "title": "29-Part Anatomical Status (Rowan)",
            "subtitle": f"Consciousness: {getattr(player, 'consciousness', 100):.0f}% | Parts: {len(body)}",
            "body": "\n".join(summary) if summary else "All 29 body parts intact.",
            "mode": "submenu",
            "options": [self._opt("0", "Back")],
        }

    def _build_medicine_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        stages = [
            ("first_aid", "Stage 1: First Aid (Stop Bleeding)"),
            ("field_treatment", "Stage 2: Field Treatment (Pain & Infection)"),
            ("surgery", "Stage 3: Surgery (Repair Organs)"),
            ("rehabilitation", "Stage 4: Rehabilitation (Restore Limb)"),
            ("prosthetics", "Stage 5: Fit Prosthetic Limb"),
        ]
        items = [{"label": lbl, "tags": [st], "enabled": True, "_meta": {"op": "treat", "stage": st}} for st, lbl in stages]
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "5-Stage Medical Treatment", "subtitle": "Target: Rowan", "body": self.last_message or "Select a medical intervention.", "mode": "submenu", "options": opts}

    def _build_equipment_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        player = world.player
        equip = getattr(player, "equipment", {}) if player else {}
        items = []
        for item_id in getattr(player, "inventory", []) if player else []:
            it = world.items.get(item_id)
            if it and getattr(it, "item_type", "") in ("weapon", "armor"):
                items.append({"label": f"Equip {it.name} ({it.item_type})", "tags": [f"Dmg {it.damage}"], "enabled": True, "_meta": {"op": "equip", "item_id": item_id}})
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "Equipment & Loadout", "subtitle": f"Weapon: {equip.get('weapon', 'None')}", "body": self.last_message or "Select an item to equip.", "mode": "submenu", "options": opts}

    def _build_counsel_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        items = []
        for cid, comp in world.companions.items():
            items.append({"label": f"Counsel {comp.name} ({comp.role})", "tags": [f"Friend {comp.friendship:.0f}"], "enabled": True, "_meta": {"op": "counsel", "comp_id": cid}})
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "Companion Campfire Counsel", "subtitle": "Resolve Breaking-Point Tensions", "body": self.last_message or "Speak with a companion.", "mode": "submenu", "options": opts}

    def _build_politics_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        gold = self._player_gold()
        items = [
            {"label": "Inspect 7 Factions & Standings", "tags": ["View"], "enabled": True, "_meta": {"op": "push", "screen": "faction_list"}},
            {"label": "Inspect 5-Rank Nemesis Board", "tags": ["Nemesis"], "enabled": True, "_meta": {"op": "push", "screen": "nemesis_board"}},
            {"label": "Petition City Guard Leader", "tags": ["+25g/+Rep"], "enabled": True, "_meta": {"op": "petition"}},
            {"label": "Donate to City Guard Treasury", "tags": ["Cost: 50g", "+Rep"], "enabled": gold >= 50.0, "_meta": {"op": "donate"}},
            {"label": "Broker Truce (Guard / Syndicate)", "tags": ["Cost: 50g", "+Relations"], "enabled": gold >= 50.0, "_meta": {"op": "truce"}},
            {"label": "Incite Turf War (Lowtown)", "tags": ["Cost: 40g", "+Unrest"], "enabled": gold >= 40.0, "_meta": {"op": "turf_war"}},
            {"label": "Pay Off City Guard Bounty", "tags": ["Cost: 50g", "Clear Record"], "enabled": gold >= 50.0, "_meta": {"op": "clear_bounty"}},
            {"label": "Smear Campaign vs. Captain Voss", "tags": ["Cost: 30g", "Rumor"], "enabled": gold >= 30.0, "_meta": {"op": "smear"}},
            {"label": "Sabotage Lowtown Infrastructure", "tags": ["Cost: 35g", "-Security"], "enabled": gold >= 35.0, "_meta": {"op": "sabotage"}},
            {"label": "Sponsor District Civic Edict", "tags": ["Cost: 60g", "Sub-menu"], "enabled": gold >= 60.0, "_meta": {"op": "push", "screen": "edict_menu"}},
            {"label": "Back Internal Coup (Syndicate)", "tags": ["Cost: 100g", "Coup"], "enabled": gold >= 100.0, "_meta": {"op": "coup"}},
        ]
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "Faction Politics & Nemesis Board", "subtitle": f"Gold: {gold:.0f}g", "body": self.last_message or "Direct political operations in Veyr.", "mode": "submenu", "options": opts}

    def _build_faction_list(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        rep_map = world.reputation.get("faction", {})
        lines = [
            f"{f.name}: Inf {f.influence:.0f}% | Stab {f.stability:.0f}% | Rep {rep_map.get(f.id, 0.0):+.0f}"
            for f in world.factions.values()
        ]
        return {"title": "The 7 Factions of Veyr", "subtitle": "Influence & Standing", "body": "\n".join(lines), "mode": "submenu", "options": [self._opt("0", "Back")]}

    def _build_nemesis_board(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        lines = []
        for pid, prof in world.nemesis_profiles.items():
            ch = world.characters.get(pid)
            cname = ch.name if ch else pid
            lines.append(f"{cname} [{prof.rank.title()}] — Hostility {prof.player_hostility:.0f} | Respect {prof.player_respect:.0f} | Status: {prof.status}")
        return {"title": "5-Rank Nemesis Hierarchy", "subtitle": f"{len(lines)} Tracked Rivals", "body": "\n".join(lines) or "No active nemeses.", "mode": "submenu", "options": [self._opt("0", "Back")]}

    def _build_edict_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        gold = self._player_gold()
        items = [
            {"label": "Sponsor Soup Kitchens (+Food, +Opinion)", "tags": ["Cost: 60g"], "enabled": gold >= 60.0, "_meta": {"op": "edict", "edict": "soup_kitchens"}},
            {"label": "Sponsor Private Watch Patrols (+Security, -Crime)", "tags": ["Cost: 60g"], "enabled": gold >= 60.0, "_meta": {"op": "edict", "edict": "private_watch_patrols"}},
            {"label": "Sponsor District Festival (-Unrest, +Opinion)", "tags": ["Cost: 60g"], "enabled": gold >= 60.0, "_meta": {"op": "edict", "edict": "festival"}},
        ]
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "Sponsor District Civic Edict", "subtitle": f"Gold: {gold:.0f}g", "body": self.last_message or "Choose an edict to fund.", "mode": "submenu", "options": opts}

    def _build_economy_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        gold = self._player_gold()
        items = [
            {"label": "District Commodity Market (6 Goods)", "tags": ["Buy/Sell"], "enabled": True, "_meta": {"op": "push", "screen": "commodity_menu"}},
            {"label": "Income Properties & Upgrades (5 Deeds)", "tags": ["Passive Gold"], "enabled": True, "_meta": {"op": "push", "screen": "property_menu"}},
            {"label": "Consortium & Syndicate Loans", "tags": ["Borrow/Repay"], "enabled": True, "_meta": {"op": "push", "screen": "loan_menu"}},
            {"label": "Merchant Caravans", "tags": ["Invest"], "enabled": True, "_meta": {"op": "push", "screen": "caravan_menu"}},
        ]
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "Trade, Property & Economy", "subtitle": f"Gold: {gold:.0f}g", "body": self.last_message or "Manage trade, properties, and finance.", "mode": "submenu", "options": opts}

    def _build_commodity_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        _, _, dist_id = self._current_location()
        items = []
        for cid, spec in COMMODITIES.items():
            price = self.game.economy_system.get_commodity_price(cid, district_id=dist_id, world=world)
            owned = int(world.commodities.get(cid, 0))
            items.append({
                "label": f"{spec['name']} ({price:.1f}g | Owned: {owned})",
                "tags": [spec["category"]],
                "enabled": True,
                "_meta": {"op": "push_commodity", "commodity_id": cid},
            })
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": f"Commodity Market ({dist_id.replace('_', ' ').title()})", "subtitle": f"Gold: {self._player_gold():.0f}g", "body": self.last_message or "Select a commodity to trade.", "mode": "submenu", "options": opts}

    def _build_commodity_action(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        cid = frame["context"]["commodity_id"]
        _, _, dist_id = self._current_location()
        price = self.game.economy_system.get_commodity_price(cid, district_id=dist_id, world=world)
        owned = int(world.commodities.get(cid, 0))
        gold = self._player_gold()
        items = [
            {"label": f"Buy 1 ({price:.1f}g)", "tags": [f"Cost: {price:.1f}g"], "enabled": gold >= price, "_meta": {"op": "buy_comm", "cid": cid, "qty": 1}},
            {"label": f"Buy 5 ({price * 5:.1f}g)", "tags": [f"Cost: {price * 5:.1f}g"], "enabled": gold >= price * 5, "_meta": {"op": "buy_comm", "cid": cid, "qty": 5}},
            {"label": f"Sell 1 (+{price:.1f}g)", "tags": [f"Owned: {owned}"], "enabled": owned >= 1, "_meta": {"op": "sell_comm", "cid": cid, "qty": 1}},
            {"label": f"Sell 5 (+{price * 5:.1f}g)", "tags": [f"Owned: {owned}"], "enabled": owned >= 5, "_meta": {"op": "sell_comm", "cid": cid, "qty": 5}},
        ]
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": COMMODITIES[cid]["name"], "subtitle": f"Price: {price:.1f}g | Owned: {owned}", "body": self.last_message or COMMODITIES[cid]["description"], "mode": "submenu", "options": opts}

    def _build_property_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        gold = self._player_gold()
        items = []
        for pid, spec in PROPERTIES_CATALOG.items():
            owned = pid in world.properties
            if owned:
                lvl = int(world.properties[pid].get("level", 1))
                up_cost = round(float(spec["upgrade_base_cost"]) * lvl, 2)
                items.append({"label": f"Upgrade {spec['name']} (Lv {lvl} -> {lvl + 1})", "tags": [f"Cost: {up_cost:.0f}g"], "enabled": gold >= up_cost, "_meta": {"op": "upgrade_prop", "pid": pid}})
            else:
                cost = float(spec["base_cost"])
                items.append({"label": f"Buy {spec['name']} (+{spec['daily_income']:.0f}g/day)", "tags": [f"Cost: {cost:.0f}g"], "enabled": gold >= cost, "_meta": {"op": "buy_prop", "pid": pid, "cost": cost}})
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "Income Properties & Upgrades", "subtitle": f"Gold: {gold:.0f}g", "body": self.last_message or "Acquire or upgrade properties.", "mode": "submenu", "options": opts}

    def _build_loan_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        gold = self._player_gold()
        active_loans = [l for l in world.loans if l.get("status") in ("active", "defaulted")]
        items = [
            {"label": "Borrow 100g from Merchant Consortium (5%/day)", "tags": ["+100g"], "enabled": True, "_meta": {"op": "take_loan", "lender": "merchant_consortium", "amount": 100.0}},
            {"label": "Borrow 100g from Lowtown Syndicate (10%/day)", "tags": ["+100g"], "enabled": True, "_meta": {"op": "take_loan", "lender": "lowtown_syndicate", "amount": 100.0}},
        ]
        for ln in active_loans:
            bal = float(ln.get("balance", 0.0))
            tags = [ln["lender"]]
            if ln.get("status") == "defaulted":
                tags.append("DEFAULTED")
            items.append({"label": f"Repay {ln['id']} ({bal:.1f}g)", "tags": tags, "enabled": gold >= bal, "_meta": {"op": "repay_loan", "loan_id": ln["id"], "amount": bal}})
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "Consortium & Syndicate Finance", "subtitle": f"Active Loans: {len(active_loans)}", "body": self.last_message or "Manage loans.", "mode": "submenu", "options": opts}

    def _build_caravan_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        gold = self._player_gold()
        items = [
            {"label": "Invest 100g in Harbor Caravan (3 days, +40%)", "tags": ["Cost: 100g"], "enabled": gold >= 100.0, "_meta": {"op": "invest_caravan", "amount": 100.0}},
        ]
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "Merchant Caravans", "subtitle": f"Active Caravans: {len(self.game.world.caravans)}", "body": self.last_message or "Fund trade caravans.", "mode": "submenu", "options": opts}

    def _build_quests_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        gold = self._player_gold()
        q_lines = [f"- {q.title} [{q.status}]" for q in world.quests.values()]
        items = [
            {"label": "Resolve 'Blood in Lowtown' Approach", "tags": ["4 Approaches"], "enabled": not bool(world.flags.get("blood_in_lowtown_completed")), "_meta": {"op": "push", "screen": "approach_menu"}},
            {"label": "Plant False Rumor in Current District", "tags": ["Cost: 20g"], "enabled": gold >= 20.0, "_meta": {"op": "plant_rumor"}},
            {"label": "View City Chronicle", "tags": ["History"], "enabled": True, "_meta": {"op": "view_chronicle"}},
        ]
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "Quests, Rumors & City Chronicle", "subtitle": f"Active Quests: {len(q_lines)}", "body": (self.last_message + "\n\n" if self.last_message else "") + "\n".join(q_lines), "mode": "submenu", "options": opts}

    def _build_approach_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        approaches = [
            ("support_city_guard", "Support the City Guard"),
            ("support_syndicate", "Support the Lowtown Syndicate"),
            ("investigate_independently", "Investigate Independently"),
            ("exploit_situation", "Exploit Both Sides (+150g)"),
        ]
        items = [{"label": lbl, "tags": [ap], "enabled": True, "_meta": {"op": "resolve_approach", "approach": ap}} for ap, lbl in approaches]
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "Blood in Lowtown — Choose Approach", "subtitle": "Irreversible Choice", "body": self.last_message or "Decide how to resolve the investigation.", "mode": "submenu", "options": opts}

    def _build_character_sheet(self, frame: dict[str, Any]) -> dict[str, Any]:
        world = self.game.world
        p = world.player
        epithet = world.flags.get("epithet", "Unproven Wanderer")
        attrs = ", ".join(f"{k.title()}: {v}" for k, v in getattr(p, "attributes", {}).items())
        skills = ", ".join(f"{k.title()}: {v:.0f}" for k, v in getattr(p, "skills", {}).items())
        body = (
            f"Name: {p.name} — '{epithet}'\n"
            f"Attributes: {attrs}\n"
            f"Skills: {skills}\n"
            f"Public Rep: {world.reputation.get('general_public', 0):+.0f} | "
            f"Noble: {world.reputation.get('noble_society', 0):+.0f} | "
            f"Underworld: {world.reputation.get('criminal_underworld', 0):+.0f}"
        )
        return {"title": "Character Sheet & Reputation", "subtitle": epithet, "body": body, "mode": "submenu", "options": [self._opt("0", "Back")]}

    def _build_system_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        items = [
            {"label": "Quick Save (Autosave / Checkpoint)", "tags": ["Save"], "enabled": True, "_meta": {"op": "quick_save"}},
            {"label": "Save to Slot 1", "tags": ["Save"], "enabled": True, "_meta": {"op": "save_slot", "slot": "slot_1"}},
            {"label": "Load Saved Game", "tags": ["Slot Browser"], "enabled": True, "_meta": {"op": "push", "screen": "load_menu"}},
            {"label": "Settings (Difficulty & Debug Toggle)", "tags": ["Config"], "enabled": True, "_meta": {"op": "push", "screen": "settings_menu"}},
            {"label": "Skip / Complete Tutorial", "tags": ["Tutorial"], "enabled": True, "_meta": {"op": "skip_tutorial"}},
        ]
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "System, Save / Load & Settings", "subtitle": "Persistence & Options", "body": self.last_message or "Manage saves and settings.", "mode": "submenu", "options": opts}

    def _build_load_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        slots = self.game.save_manager.list_save_slots()
        items = [
            {"label": f"{s['slot']} — {s['character_name']} (Y{s['year']}D{s['day']}, {s['gold']:.0f}g)", "tags": [s["difficulty"]], "enabled": True, "_meta": {"op": "load_slot", "slot": s["slot"]}}
            for s in slots
        ]
        opts, _, _ = self._paginate_options(items, frame["page"])
        return {"title": "Load Saved Game", "subtitle": f"{len(slots)} Slot(s)", "body": self.last_message or ("Select a slot to load." if slots else "No save slots found."), "mode": "submenu", "options": opts}

    def _build_settings_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        s = self.game.settings
        items = [
            {"label": f"Difficulty: {s.difficulty.title()}", "tags": ["Cycle"], "enabled": True, "_meta": {"op": "set_diff"}},
            {"label": f"Enable Cheat / Debug Mode: {'ON' if s.enable_debug_cheat else 'OFF'}", "tags": ["Toggle"], "enabled": True, "_meta": {"op": "set_debug"}},
            {"label": f"Auto-Save: {s.autosave_mode}", "tags": ["Cycle"], "enabled": True, "_meta": {"op": "set_autosave"}},
            {"label": f"Guided Tutorial HUD: {'ON' if s.guided_tutorial_hud else 'OFF'}", "tags": ["Toggle"], "enabled": True, "_meta": {"op": "set_tut"}},
            {"label": f"Layout Mode: {s.layout_mode.title()}", "tags": ["Cycle"], "enabled": True, "_meta": {"op": "set_layout"}},
        ]
        opts, _, _ = self._paginate_options(items, frame["page"], back_label="Save & Back")
        return {"title": "Settings", "subtitle": "Persisted to saves/settings.json", "body": self.last_message or "Adjust game settings.", "mode": "submenu", "options": opts}

    def _build_debug_menu(self, frame: dict[str, Any]) -> dict[str, Any]:
        opts = [
            self._opt(o["key"], o["label"], tags=["Debug"] if o["key"] != "0" else ["Back"], enabled=o["enabled"])
            for o in self.game.debug_mode.get_menu_options()
        ]
        return {"title": "Cheat & Debug Menu", "subtitle": f"God Mode: {'ON' if self.game.world.flags.get('god_mode') else 'OFF'}", "body": self.last_message or "Select a debug action [1]-[9].", "mode": "submenu", "options": opts}

    # ------------------------------------------------------------------
    # Submenu Action Dispatch
    # ------------------------------------------------------------------

    def _dispatch_submenu(self, frame: dict[str, Any], choice: str, matched: dict[str, Any]) -> dict[str, Any]:
        if frame["screen_id"] == "debug_menu":
            res = self.game.debug_mode.execute_cheat(int(choice))
            self.last_message = res.get("message", "")
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        meta = matched.get("_meta", {})
        op = meta.get("op", "")
        world = self.game.world
        _, _, dist_id = self._current_location()

        if op == "push":
            self._push(meta["screen"])
            self.last_message = ""
            return {"success": True, "message": "", "screen": self.get_screen()}

        if op == "push_commodity":
            self._push("commodity_action", commodity_id=meta["commodity_id"])
            self.last_message = ""
            return {"success": True, "message": "", "screen": self.get_screen()}

        if op == "move":
            res = self.game.execute_command({"action": "move", "actor": "player", "target": meta["target"]})
            self.last_message = res.get("message", "")
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "inspect":
            res = self.game.execute_command({"action": "inspect", "actor": "player", "target": meta["target"]})
            self.last_message = res.get("message", "")
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "talk":
            self.active_dialogue = DialogueEngine(self.game, meta["target"])
            self.last_message = ""
            return {"success": True, "message": f"Speaking with {meta['target']}.", "screen": self.get_screen()}

        if op == "rest_8h":
            res = self.game.execute_command({"action": "rest", "actor": "player", "hours": 8, "minutes": 480})
            self.last_message = res.get("message", "")
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "tavern_round":
            world.player.needs["wealth"] -= 10.0
            self.last_message = "You buy a round of ale and learn of Guard shifts near Cobblestone Market."
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        if op == "dice_wager":
            world.player.needs["wealth"] -= 20.0
            won = world.rng.roll_chance("economy", 0.5)
            if won:
                world.player.needs["wealth"] += 40.0
                self.last_message = "You roll double sixes and win 40g!"
            else:
                self.last_message = "The dice turn cold—you lose your 20g wager."
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        if op == "apothecary":
            world.player.needs["wealth"] -= 20.0
            self.game.health_system.apply_treatment(world.player, stage="first_aid", doctor=world.player)
            self.last_message = "The apothecary binds your wounds (First Aid applied)."
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        if op == "hear_petitioners":
            pets = generate_petitioners(world, location_type=meta.get("loc_type", "safehouse"))
            self._push("petitioner_menu", petitioners=pets, index=0)
            self.last_message = ""
            return {"success": True, "message": "", "screen": self.get_screen()}

        if op == "resolve_pet":
            pets = frame["context"]["petitioners"]
            idx = frame["context"]["index"]
            res = resolve_petitioner(world, pets[idx], meta["choice_idx"])
            self.last_message = f"Resolved {pets[idx]['name']}: {res.get('label', res.get('reason', ''))}."
            if res.get("success"):
                frame["context"]["index"] = idx + 1
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "treat":
            self.game.health_system.apply_treatment(world.player, stage=meta["stage"], doctor=world.player)
            self.last_message = f"Applied {meta['stage'].replace('_', ' ')} to {world.player.name}."
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        if op == "equip":
            it = world.items.get(meta["item_id"])
            slot = "weapon" if it and it.item_type == "weapon" else "armor"
            world.player.equipment[slot] = meta["item_id"]
            self.last_message = f"Equipped {it.name if it else meta['item_id']}."
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        if op == "counsel":
            res = self.game.relationship_system.campfire_counsel(world, meta["comp_id"], resolve_tension=True)
            self.last_message = f"Counselled {meta['comp_id']}: Friendship {res.get('friendship', 0):.0f}, Resentment {res.get('resentment', 0):.0f}."
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "petition":
            res = self.game.faction_system.petition_faction_leader("city_guard", world=world)
            self.last_message = f"Petitioned City Guard (+{res.get('gold_granted', 0):.0f}g)." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "donate":
            res = self.game.faction_system.donate_to_faction("city_guard", 50.0, world=world)
            self.last_message = f"Donated 50g to City Guard (Rep {res.get('faction_reputation', 0):.0f})."
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "truce":
            res = self.game.faction_system.broker_truce("city_guard", "lowtown_syndicate", world=world)
            self.last_message = "Brokered truce between City Guard and Syndicate." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "turf_war":
            res = self.game.faction_system.incite_turf_war("city_guard", "lowtown_syndicate", dist_id, world=world)
            self.last_message = f"Incited turf war in {dist_id}." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "clear_bounty":
            res = self.game.faction_system.pay_off_bounty(50.0, world=world)
            self.last_message = "Paid off City Guard bounty." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "smear":
            res = self.game.faction_system.smear_campaign("npc_voss", dist_id, world=world)
            self.last_message = "Launched smear campaign against Captain Voss." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "sabotage":
            res = self.game.faction_system.sabotage_district(dist_id, world=world)
            self.last_message = f"Sabotaged {dist_id} infrastructure." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "edict":
            res = self.game.faction_system.sponsor_civic_edict(dist_id, meta["edict"], world=world)
            self.last_message = f"Sponsored {meta['edict'].replace('_', ' ')} in {dist_id}." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "coup":
            res = self.game.faction_system.back_internal_coup("lowtown_syndicate", world=world)
            self.last_message = f"Backed internal coup: new leader {res.get('new_leader_id')}." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "buy_comm":
            res = self.game.economy_system.buy_commodity("player", meta["cid"], meta["qty"], dist_id, world=world)
            self.last_message = f"Bought {meta['qty']}x {meta['cid']} for {res.get('total_cost', 0):.1f}g." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "sell_comm":
            res = self.game.economy_system.sell_commodity("player", meta["cid"], meta["qty"], dist_id, world=world)
            self.last_message = f"Sold {meta['qty']}x {meta['cid']} for +{res.get('revenue', 0):.1f}g." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "buy_prop":
            res = self.game.economy_system.acquire_property("player", meta["pid"], cost=meta["cost"], world=world)
            self.last_message = f"Purchased {res.get('name', meta['pid'])}!" if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "upgrade_prop":
            res = self.game.economy_system.upgrade_property("player", meta["pid"], world=world)
            self.last_message = f"Upgraded {meta['pid']} to Lv {res.get('level')}." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "take_loan":
            res = self.game.economy_system.take_loan("player", meta["amount"], lender=meta["lender"], world=world)
            self.last_message = f"Borrowed {meta['amount']:.0f}g from {meta['lender']}." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "repay_loan":
            res = self.game.economy_system.repay_loan("player", meta["loan_id"], meta["amount"], world=world)
            self.last_message = f"Repaid loan {meta['loan_id']}." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "invest_caravan":
            res = self.game.economy_system.invest_caravan("player", meta["amount"], world=world)
            self.last_message = f"Invested {meta['amount']:.0f}g in merchant caravan." if res.get("success") else str(res)
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "resolve_approach":
            res = self.game.resolve_scenario_approach(meta["approach"])
            self.last_message = res.get("message", "")
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "plant_rumor":
            world.player.needs["wealth"] -= 20.0
            self.game.rumor_system.plant_false_rumor("player", "npc_voss", "Voss is taking Syndicate bribes.", dist_id, truth=False, world=world)
            self.last_message = f"Planted false rumor about Voss in {dist_id}."
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        if op == "view_chronicle":
            chron = self.game.save_manager.generate_chronicle(world)
            if chron:
                last = chron[-1]
                last_str = str(last.get("summary") or last.get("title") or last.get("event_type") or last) if isinstance(last, dict) else str(last)
            else:
                last_str = "No entries yet."
            self.last_message = f"Chronicle ({len(chron)} entries): {last_str}"
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        if op == "quick_save":
            self.game.save_manager.autosave(
                world,
                reason="manual",
                autosave_mode=getattr(self.game.settings, "autosave_mode", "daily_and_precombat"),
            )
            self.game.save_manager.save_game(world, slot="default")
            self.last_message = "Game saved."
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        if op == "save_slot":
            self.game.save_manager.save_game(world, slot=meta["slot"])
            self.last_message = f"Saved to {meta['slot']}."
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        if op == "load_slot":
            res = self.game.execute_command({"action": "load", "actor": "player", "slot": meta["slot"]})
            self.last_message = res.get("message", "")
            if res.get("success"):
                self.stack.clear()
            return {"success": bool(res.get("success")), "message": self.last_message, "screen": self.get_screen()}

        if op == "skip_tutorial":
            res = self.game.skip_tutorial()
            self.last_message = res.get("message", "Tutorial skipped.")
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        if op in ("set_diff", "set_debug", "set_autosave", "set_tut", "set_layout"):
            s = self.game.settings
            if op == "set_diff":
                idx = VALID_DIFFICULTIES.index(s.difficulty) if s.difficulty in VALID_DIFFICULTIES else 1
                s.difficulty = VALID_DIFFICULTIES[(idx + 1) % len(VALID_DIFFICULTIES)]
                world.flags["difficulty"] = s.difficulty
            elif op == "set_debug":
                s.enable_debug_cheat = not s.enable_debug_cheat
            elif op == "set_autosave":
                idx = VALID_AUTOSAVE_MODES.index(s.autosave_mode) if s.autosave_mode in VALID_AUTOSAVE_MODES else 0
                s.autosave_mode = VALID_AUTOSAVE_MODES[(idx + 1) % len(VALID_AUTOSAVE_MODES)]
            elif op == "set_tut":
                s.guided_tutorial_hud = not s.guided_tutorial_hud
            elif op == "set_layout":
                idx = VALID_LAYOUT_MODES.index(s.layout_mode) if s.layout_mode in VALID_LAYOUT_MODES else 0
                s.layout_mode = VALID_LAYOUT_MODES[(idx + 1) % len(VALID_LAYOUT_MODES)]
            save_settings(s)
            self.last_message = "Settings updated and saved."
            return {"success": True, "message": self.last_message, "screen": self.get_screen()}

        self.last_message = "Action not implemented."
        return {"success": False, "message": self.last_message, "screen": self.get_screen()}
