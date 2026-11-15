"""Directed 6-axis relationship and companion friendship/rivalry system (GDD Sections 4, 9, 13)."""

from __future__ import annotations

import uuid
from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.character import Character, Relationship
from entities.companion import Companion, CompanionProfile


class RelationshipSystem:
    """Manages directed relationships across trust, respect, affection, resentment, fear, and dependency."""

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
        self._relationships: dict[tuple[str, str], Relationship] = {}

        if self.event_bus:
            for ev in ("CHARACTER_RESCUED", "COMPANION_ABANDONED", "CRIMINAL_SOLD"):
                self.event_bus.subscribe(ev, self.handle_event)

    def derive_relationship_state(self, rel: Relationship) -> str:
        """Derive the qualitative descriptor from the 6 numerical axes (GDD Section 4)."""
        if rel.trust >= 60.0 and rel.respect >= 70.0 and rel.affection >= 40.0 and rel.resentment <= 20.0:
            return "Loyal associate"
        if rel.respect >= 60.0 and rel.resentment >= 50.0:
            return "Respected rival"
        if rel.affection >= 60.0 and rel.trust >= 50.0:
            return "Close friend"
        if rel.resentment >= 60.0 and rel.trust <= -20.0:
            return "Bitter enemy"
        if rel.fear >= 60.0:
            return "Terrified subordinate"
        if rel.trust >= 40.0:
            return "Friendly associate"
        if rel.resentment >= 40.0:
            return "Distrusted rival"
        return "Acquaintance"

    def set_relationship(
        self,
        source_id: str,
        target_id: str,
        trust: float | None = None,
        respect: float | None = None,
        affection: float | None = None,
        resentment: float | None = None,
        fear: float | None = None,
        dependency: float | None = None,
        relationship_state: str | None = None,
        shared_memories: list[str] | None = None,
    ) -> Relationship | None:
        """Create or update directed relationship from source_id to target_id."""
        if source_id == target_id:
            return None

        rel = self.get_relationship(source_id, target_id)
        if trust is not None:
            rel.trust = max(-100.0, min(100.0, float(trust)))
        if respect is not None:
            rel.respect = max(-100.0, min(100.0, float(respect)))
        if affection is not None:
            rel.affection = max(-100.0, min(100.0, float(affection)))
        if resentment is not None:
            rel.resentment = max(-100.0, min(100.0, float(resentment)))
        if fear is not None:
            rel.fear = max(-100.0, min(100.0, float(fear)))
        if dependency is not None:
            rel.dependency = max(-100.0, min(100.0, float(dependency)))
        if shared_memories is not None:
            rel.shared_memories = list(shared_memories)

        if relationship_state is not None:
            rel.relationship_state = str(relationship_state)
        else:
            rel.relationship_state = self.derive_relationship_state(rel)

        # Sync to source character if world is available
        if self.world and hasattr(self.world, "characters"):
            source_char = self.world.characters.get(source_id)
            if source_char:
                source_char.relationships[target_id] = rel

        return rel

    def trigger_breaking_point(
        self,
        companion_id: str,
        reason: str = "",
        world: Any = None,
    ) -> bool:
        """Trigger companion departure via breaking point (GDD Section 9)."""
        active_world = world or self.world
        comp = None
        if active_world and hasattr(active_world, "companions"):
            comp = active_world.companions.get(companion_id)
        if comp:
            comp.in_party = False
        if active_world and hasattr(active_world, "player_party") and companion_id in active_world.player_party:
            active_world.player_party.remove(companion_id)

        eb = self.event_bus or (getattr(active_world, "event_bus", None) if active_world else None)
        if eb:
            ev = GameEvent(
                id=f"ev_bp_{uuid.uuid4().hex[:6]}",
                event_type="COMPANION_BREAKING_POINT",
                timestamp=active_world.clock.timestamp if active_world and active_world.clock else 0,
                source_id="player",
                target_ids=[companion_id],
                location_id="",
                data={"reason": reason, "companion_id": companion_id},
                importance=0.9,
            )
            eb.emit(ev, priority=EventPriority.CRITICAL)
        return True

    def evaluate_breaking_point(
        self,
        companion_id: str,
        reason: str = "",
        world: Any = None,
        **kwargs: Any,
    ) -> bool:
        if reason:
            return self.trigger_breaking_point(companion_id, reason=reason, world=world)
        return self.check_companion_retention(companion_id, world=world)

    def check_breaking_point(
        self,
        companion_id: str,
        reason: str = "",
        world: Any = None,
        **kwargs: Any,
    ) -> bool:
        return self.evaluate_breaking_point(companion_id, reason=reason, world=world, **kwargs)

    def check_companion_retention(self, companion_id: str, world: Any = None) -> bool:
        """Check if companion remains in party based on rivalry/respect/resentment."""
        active_world = world or self.world
        comp = None
        if active_world and hasattr(active_world, "companions"):
            comp = active_world.companions.get(companion_id)
        if not comp:
            return True
        rel = self.get_relationship(companion_id, "player")
        if rel.resentment >= 90.0 and rel.respect < 30.0:
            return self.trigger_breaking_point(companion_id, reason="excessive_resentment", world=world)
        return True

    def update_relationship(self, source_id: str, target_id: str, **kwargs: Any) -> Relationship:
        return self.set_relationship(source_id, target_id, **kwargs)

    def modify_relationship(self, source_id: str, target_id: str, **kwargs: Any) -> Relationship:
        return self.set_relationship(source_id, target_id, **kwargs)

    def get_relationship(self, source_id: str, target_id: str) -> Relationship:
        """Get existing relationship or create default Acquaintance."""
        key = (source_id, target_id)
        if key in self._relationships:
            return self._relationships[key]

        # Check world characters
        if self.world and hasattr(self.world, "characters"):
            source_char = self.world.characters.get(source_id)
            if source_char and target_id in source_char.relationships:
                rel = source_char.relationships[target_id]
                self._relationships[key] = rel
                return rel

        new_rel = Relationship(
            source_id=source_id,
            target_id=target_id,
            trust=0.0,
            respect=0.0,
            affection=0.0,
            resentment=0.0,
            fear=0.0,
            dependency=0.0,
            relationship_state="Acquaintance",
        )
        self._relationships[key] = new_rel
        return new_rel

    def query_relationship(self, source_id: str, target_id: str) -> Relationship:
        return self.get_relationship(source_id, target_id)

    def adjust_companion_standing(
        self,
        companion_id: str,
        friendship_delta: float = 0.0,
        rivalry_delta: float = 0.0,
        respect_delta: float = 0.0,
        world: Any = None,
    ) -> None:
        """Adjust separate friendship and rivalry progression tracks for a companion."""
        active_world = world or self.world
        comp = None
        if active_world and hasattr(active_world, "companions"):
            comp = active_world.companions.get(companion_id)

        if comp is not None:
            if hasattr(comp, "friendship"):
                comp.friendship = max(0.0, min(100.0, comp.friendship + friendship_delta))
            if hasattr(comp, "rivalry"):
                comp.rivalry = max(0.0, min(100.0, comp.rivalry + rivalry_delta))

        # Also update relationship toward player
        rel = self.get_relationship(companion_id, "player")
        if friendship_delta != 0.0:
            rel.trust += friendship_delta * 0.8
            rel.affection += friendship_delta * 0.8
        if rivalry_delta != 0.0:
            rel.resentment += rivalry_delta * 0.5
            rel.respect += rivalry_delta * 0.5
        if respect_delta != 0.0:
            rel.respect += respect_delta
        rel.relationship_state = self.derive_relationship_state(rel)

    def update_companion_relationship(self, companion_id: str, **kwargs: Any) -> None:
        self.adjust_companion_standing(companion_id, **kwargs)

    def record_companion_reaction(self, companion_id: str, **kwargs: Any) -> None:
        self.adjust_companion_standing(companion_id, **kwargs)

    def handle_event(self, event: GameEvent, world: Any = None) -> None:
        """Update relationships from GameEvent (e.g. CHARACTER_RESCUED)."""
        active_world = world or self.world
        data = event.data or {}

        trust_d = float(data.get("trust_delta", 0.0))
        affection_d = float(data.get("affection_delta", 0.0))
        respect_d = float(data.get("respect_delta", 0.0))
        resentment_d = float(data.get("resentment_delta", 0.0))
        fear_d = float(data.get("fear_delta", 0.0))
        mem_id = data.get("memory_id")

        if event.source_id and event.target_ids:
            for target_id in event.target_ids:
                rel = self.get_relationship(target_id, event.source_id)
                rel.trust += trust_d
                rel.affection += affection_d
                rel.respect += respect_d
                rel.resentment += resentment_d
                rel.fear += fear_d
                if mem_id and mem_id not in rel.shared_memories:
                    rel.shared_memories.append(str(mem_id))
                rel.relationship_state = self.derive_relationship_state(rel)

                if self.event_bus:
                    change_ev = GameEvent(
                        id=f"rel_chg_{uuid.uuid4().hex[:6]}",
                        event_type="RELATIONSHIP_CHANGED",
                        timestamp=event.timestamp,
                        source_id=target_id,
                        target_ids=[event.source_id],
                        location_id=event.location_id,
                        data={
                            "relationship_state": rel.relationship_state,
                            "trust": rel.trust,
                            "affection": rel.affection,
                        },
                        importance=0.6,
                    )
                    self.event_bus.emit(change_ev, priority=EventPriority.NORMAL)

    def process_event(self, event: GameEvent, world: Any = None) -> None:
        self.handle_event(event, world=world)

    def on_event(self, event: GameEvent, world: Any = None) -> None:
        self.handle_event(event, world=world)

    def _emit_social_event(
        self,
        world: Any,
        event_type: str,
        source_id: str,
        target_id: str,
        data: dict[str, Any],
        importance: float = 0.65,
    ) -> None:
        eb = self.event_bus or (getattr(world, "event_bus", None) if world else None)
        if not eb:
            return
        if hasattr(eb, "create_event"):
            ev = eb.create_event(
                event_type=event_type,
                timestamp=world.clock.timestamp if world and getattr(world, "clock", None) else 0,
                source_id=source_id,
                target_ids=[target_id],
                location_id="",
                data=data,
                importance=importance,
                priority=EventPriority.NORMAL,
            )
        else:
            self._social_seq = getattr(self, "_social_seq", 0) + 1
            ev = GameEvent(
                id=f"ev_rel_{self._social_seq:05d}",
                event_type=event_type,
                timestamp=world.clock.timestamp if world and getattr(world, "clock", None) else 0,
                source_id=source_id,
                target_ids=[target_id],
                location_id="",
                data=data,
                importance=importance,
            )
        eb.emit(ev, priority=EventPriority.NORMAL)

    def give_gift(
        self,
        world: Any,
        giver_id: str,
        target_id: str,
        gold_cost: float = 25.0,
    ) -> dict[str, Any]:
        """Give a gift or share loot with target NPC (+Affection, +Trust)."""
        active_world = world or self.world
        cost = max(0.0, float(gold_cost))
        giver = active_world.characters.get(giver_id) if active_world and hasattr(active_world, "characters") else None
        if giver is not None and cost > 0.0:
            wealth = float(giver.needs.get("wealth", 0.0))
            if wealth < cost:
                return {"success": False, "reason": "insufficient_wealth", "cost": cost, "wealth": wealth}
            giver.needs["wealth"] = max(0.0, wealth - cost)

        scale = max(0.2, cost / 25.0)
        aff_delta = round(15.0 * scale, 2)
        trust_delta = round(10.0 * scale, 2)

        rel = self.get_relationship(target_id, giver_id)
        updated = self.set_relationship(
            target_id,
            giver_id,
            trust=rel.trust + trust_delta,
            affection=rel.affection + aff_delta,
        )
        if active_world and hasattr(active_world, "companions") and target_id in active_world.companions:
            comp = active_world.companions[target_id]
            comp.friendship = min(100.0, float(comp.friendship) + round(5.0 * scale, 2))

        self._emit_social_event(
            active_world,
            "RELATIONSHIP_CHANGED",
            giver_id,
            target_id,
            {"action": "give_gift", "cost": cost, "affection": updated.affection if updated else 0.0, "trust": updated.trust if updated else 0.0},
        )
        return {
            "success": True,
            "action": "give_gift",
            "giver_id": giver_id,
            "target_id": target_id,
            "gold_cost": cost,
            "trust": updated.trust if updated else 0.0,
            "affection": updated.affection if updated else 0.0,
            "relationship_state": updated.relationship_state if updated else "Acquaintance",
        }

    def extort_npc(
        self,
        world: Any,
        player_id: str,
        target_id: str,
    ) -> dict[str, Any]:
        """Extort/blackmail an NPC if Fear >= 50 or a secret Memory is known."""
        from systems.memory_system import MemorySystem

        active_world = world or self.world
        rel_tp = self.get_relationship(target_id, player_id)
        rel_pt = self.get_relationship(player_id, target_id)
        high_fear = rel_tp.fear >= 50.0 or rel_pt.fear >= 50.0

        def _is_secret_memory(mem: Any) -> bool:
            if getattr(mem, "secret", False) or getattr(mem, "source_type", "") == "secret":
                return True
            if "secret" in str(getattr(mem, "event_type", "")).lower():
                return True
            if "secret" in str(getattr(mem, "description", "")).lower():
                return True
            return False

        has_secret = False
        if active_world and hasattr(active_world, "characters"):
            mem_sys = MemorySystem(world=active_world)
            target_char = active_world.characters.get(target_id)
            player_char = active_world.characters.get(player_id)
            if target_char is not None:
                for mem in mem_sys.query_memories(target_char):
                    if _is_secret_memory(mem):
                        has_secret = True
                        break
            if not has_secret and player_char is not None:
                for mem in mem_sys.query_memories(player_char, participant_id=target_id):
                    if _is_secret_memory(mem):
                        has_secret = True
                        break

        if not high_fear and not has_secret:
            return {
                "success": False,
                "reason": "no_leverage",
                "message": "Target neither fears you (Fear >= 50) nor is compromised by a known secret.",
            }

        rng = getattr(active_world, "rng", None) or self.rng
        gold_extorted = float(rng.randint("extort", 25, 50)) if rng is not None else 35.0
        player_char = active_world.characters.get(player_id) if active_world and hasattr(active_world, "characters") else None
        if player_char is not None:
            player_char.needs["wealth"] = float(player_char.needs.get("wealth", 0.0)) + gold_extorted

        if active_world and hasattr(active_world, "flags"):
            active_world.flags.setdefault("extorted_intel", {})[target_id] = True

        updated = self.set_relationship(
            target_id,
            player_id,
            resentment=rel_tp.resentment + 20.0,
            fear=rel_tp.fear + 5.0,
        )
        self._emit_social_event(
            active_world,
            "RELATIONSHIP_CHANGED",
            player_id,
            target_id,
            {"action": "extort_npc", "gold": gold_extorted, "resentment": updated.resentment if updated else 0.0},
        )
        return {
            "success": True,
            "action": "extort_npc",
            "gold_gained": gold_extorted,
            "intel_gained": True,
            "leverage": "secret_memory" if has_secret else "fear",
            "resentment": updated.resentment if updated else 0.0,
            "fear": updated.fear if updated else 0.0,
        }

    def campfire_counsel(
        self,
        world: Any,
        companion_id: str,
        resolve_tension: bool = True,
    ) -> dict[str, Any]:
        """Counsel a companion using their conflict_description and breaking_points to ease tension."""
        active_world = world or self.world
        comp = active_world.companions.get(companion_id) if active_world and hasattr(active_world, "companions") else None
        if comp is None:
            return {"success": False, "reason": "companion_not_found", "companion_id": companion_id}

        rel = self.get_relationship(companion_id, "player")
        breaking_points = list(getattr(comp, "breaking_points", []) or [])
        conflict = str(getattr(comp, "conflict_description", "") or "")

        if resolve_tension:
            updated = self.set_relationship(
                companion_id,
                "player",
                resentment=max(0.0, rel.resentment - 20.0),
                trust=rel.trust + 10.0,
            )
            comp.friendship = min(100.0, float(getattr(comp, "friendship", 0.0)) + 8.0)
            comp.rivalry = max(0.0, float(getattr(comp, "rivalry", 0.0)) - 5.0)
        else:
            updated = rel

        return {
            "success": True,
            "companion_id": companion_id,
            "conflict_description": conflict,
            "breaking_points": breaking_points,
            "tension_resolved": bool(resolve_tension),
            "friendship": float(comp.friendship),
            "rivalry": float(comp.rivalry),
            "resentment": float(updated.resentment if updated else rel.resentment),
            "trust": float(updated.trust if updated else rel.trust),
        }

    def swear_blood_oath(
        self,
        world: Any,
        player_id: str,
        target_id: str,
    ) -> dict[str, Any]:
        """Swear a Blood Oath with a deeply trusted & respected ally."""
        active_world = world or self.world
        rel_tp = self.get_relationship(target_id, player_id)
        rel_pt = self.get_relationship(player_id, target_id)

        trust_val = max(rel_tp.trust, rel_pt.trust)
        respect_val = max(rel_tp.respect, rel_pt.respect)
        if trust_val < 60.0 or respect_val < 60.0:
            return {
                "success": False,
                "reason": "insufficient_trust_or_respect",
                "trust": trust_val,
                "respect": respect_val,
            }

        memories = list(rel_tp.shared_memories)
        if "blood_oath" not in memories:
            memories.append("blood_oath")
        updated = self.set_relationship(
            target_id,
            player_id,
            trust=trust_val + 15.0,
            respect=respect_val + 15.0,
            shared_memories=memories,
        )
        if active_world and hasattr(active_world, "flags"):
            active_world.flags.setdefault("blood_oaths", {})[target_id] = True

        self._emit_social_event(
            active_world,
            "BLOOD_OATH_SWORN",
            player_id,
            target_id,
            {"relationship_state": updated.relationship_state if updated else "Loyal associate"},
            importance=0.85,
        )
        return {
            "success": True,
            "action": "swear_blood_oath",
            "target_id": target_id,
            "trust": updated.trust if updated else trust_val,
            "respect": updated.respect if updated else respect_val,
            "relationship_state": updated.relationship_state if updated else "Loyal associate",
        }

    def declare_blood_feud(
        self,
        world: Any,
        player_id: str,
        target_id: str,
    ) -> dict[str, Any]:
        """Declare an open Blood Feud against a target, creating/escalating a NemesisProfile."""
        from entities.enemy import NemesisProfile

        active_world = world or self.world
        rel_tp = self.get_relationship(target_id, player_id)
        memories = list(rel_tp.shared_memories)
        if "blood_feud" not in memories:
            memories.append("blood_feud")

        updated = self.set_relationship(
            target_id,
            player_id,
            trust=min(rel_tp.trust, -60.0),
            resentment=100.0,
            relationship_state="Bitter enemy",
            shared_memories=memories,
        )
        if active_world and hasattr(active_world, "flags"):
            active_world.flags.setdefault("blood_feuds", {})[target_id] = True

        if active_world and hasattr(active_world, "nemesis_profiles"):
            prof = active_world.nemesis_profiles.get(target_id)
            if prof is None:
                target_char = active_world.characters.get(target_id) if hasattr(active_world, "characters") else None
                rank = str(getattr(target_char, "rank", "soldier") or "soldier")
                prof = NemesisProfile(
                    character_id=target_id,
                    player_hostility=90.0,
                    player_respect=0.0,
                    grudges=["blood_feud"],
                    rank=rank,
                    status="active",
                )
                if hasattr(active_world, "add_nemesis"):
                    active_world.add_nemesis(prof)
                else:
                    active_world.nemesis_profiles[target_id] = prof
            else:
                prof.player_hostility = max(float(prof.player_hostility), 90.0)
                if "blood_feud" not in prof.grudges:
                    prof.grudges.append("blood_feud")

        self._emit_social_event(
            active_world,
            "BLOOD_FEUD_DECLARED",
            player_id,
            target_id,
            {"relationship_state": "Bitter enemy"},
            importance=0.9,
        )
        return {
            "success": True,
            "action": "declare_blood_feud",
            "target_id": target_id,
            "resentment": updated.resentment if updated else 100.0,
            "trust": updated.trust if updated else -60.0,
            "relationship_state": "Bitter enemy",
        }
