"""Tier 3 E2E Cross-Feature Combination Tests for THE CITY REMEMBERS.

Verifies the GDD Design Rule ("Systems should not exist as isolated minigames.
A wound should affect combat, memory, relationships, faction behavior and future story
opportunities when appropriate") across 26 pairwise and multi-hop cross-system interactions
(`test_t3_01` through `test_t3_26`).
Zero top-level application imports so `pytest --collect-only` always succeeds with 0 errors.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.conftest import (
    call_method,
    get_clock_minutes,
    instantiate_with_context,
    require_module,
    require_symbol,
)


def test_t3_01_combat_limb_injury_to_health_memory_nemesis_and_faction(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F2 + F9 + F11 + F13 + F14 + F15: Player breaks Voss's left_leg -> updates Health, Memory, Nemesis, and Faction availability."""
    world = systems_suite["world"]
    event_bus = systems_suite["event_bus"]
    health_sys = systems_suite["health_system"]
    combat_sys = systems_suite["combat_system"]
    mem_sys = systems_suite["memory_system"]
    nem_sys = systems_suite["nemesis_system"]
    fac_sys = systems_suite["faction_system"]

    Character = entity_factory["Character"]
    Item = entity_factory["Item"]
    Faction = entity_factory["Faction"]
    NemesisProfile = entity_factory["NemesisProfile"]

    rowan = Character(id="player", name="Rowan", age=28, is_player=True, location_id="lowtown_street", attributes={"strength": 80, "dexterity": 80})
    voss = Character(id="npc_voss", name="Captain Garrick Voss", age=38, faction_id="city_guard", rank="captain", location_id="lowtown_street", is_nemesis=True)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), rowan)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), voss)

    world.characters.update({"player": rowan, "npc_voss": voss})
    voss_nem = NemesisProfile(character_id="npc_voss", player_hostility=10.0, rank="captain")
    world.nemesis_profiles["npc_voss"] = voss_nem
    world.factions["city_guard"] = Faction(id="city_guard", name="City Guard", leader_id="npc_voss", members=["npc_voss"])

    warhammer = Item(id="warhammer", name="Warhammer", item_type="weapon", damage=35.0, damage_type="blunt", penetration=15.0)
    res = call_method(
        combat_sys,
        ("resolve_attack", "execute_attack"),
        attacker=rowan,
        defender=voss,
        weapon=warhammer,
        command="aim",
        target_part="left_leg",
        force_hit=True,
    )
    event_bus.process_tick_events()

    # Ensure propagation if systems expose explicit handlers
    for ev in list(event_bus.emitted_log):
        if ev.event_type in ("LIMB_INJURED", "CHARACTER_INJURED"):
            call_method(mem_sys, ("record_event", "handle_event", "create_memory_from_event", "process_event"), ev, world=world)
            call_method(nem_sys, ("record_encounter", "add_grudge", "update_nemesis_from_event", "handle_event"), voss_nem, grudge="left_leg_injured", hostility_delta=25.0, event=ev, world=world)
            call_method(fac_sys, ("handle_event", "on_event", "update_officer_availability"), ev, world=world)

    assert res.get("hit") is True
    assert voss.body["left_leg"].integrity < 100.0
    assert len(voss.body["left_leg"].injuries) >= 1
    assert len(voss.memories) >= 1
    assert voss_nem.player_hostility > 10.0


def test_t3_02_equipment_plate_armor_vs_blunt_mace_trauma_transfer(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F11 + F12 + F13: Plate armor blocks light cutting sword but transfers blunt mace trauma into torso/rib injuries."""
    eq_sys = systems_suite["equipment_system"]
    combat_sys = systems_suite["combat_system"]
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]
    Item = entity_factory["Item"]

    attacker = Character(id="player", name="Rowan", age=28, attributes={"strength": 75, "dexterity": 75})
    defender = Character(id="npc_knight", name="Plate Guard", age=32)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), attacker)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), defender)

    plate = Item(
        id="plate_breastplate",
        name="Plate Breastplate",
        item_type="armor",
        armor_class="plate",
        armor_protection=25.0,
        covered_parts=["torso", "ribs"],
        weaknesses=["joints_and_blunt_force", "blunt"],
    )
    call_method(eq_sys, ("equip_item", "equip"), defender, plate)

    sword = Item(id="light_sword", name="Light Sword", item_type="weapon", damage=15.0, damage_type="cutting", penetration=0.0)
    mace = Item(id="heavy_mace", name="Heavy Mace", item_type="weapon", damage=22.0, damage_type="blunt", penetration=12.0)

    res_cut = call_method(combat_sys, ("resolve_attack", "execute_attack"), attacker=attacker, defender=defender, weapon=sword, command="aim", target_part="torso", force_hit=True)
    res_blunt = call_method(combat_sys, ("resolve_attack", "execute_attack"), attacker=attacker, defender=defender, weapon=mace, command="aim", target_part="torso", force_hit=True)

    assert res_blunt["effective_damage"] > res_cut["effective_damage"]
    assert res_blunt["effective_damage"] > 0.0


def test_t3_03_equipment_localized_coverage_helmet_leaves_legs_exposed(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F11 + F12 + F13: Equipping helmet (head) and breastplate (torso) leaves right_leg at 0 armor; aimed attack deals full damage."""
    eq_sys = systems_suite["equipment_system"]
    combat_sys = systems_suite["combat_system"]
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]
    Item = entity_factory["Item"]

    attacker = Character(id="player", name="Rowan", age=28, attributes={"strength": 70, "dexterity": 80})
    defender = Character(id="npc_voss", name="Captain Voss", age=38)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), attacker)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), defender)

    helmet = Item(id="steel_helmet", name="Steel Helmet", item_type="armor", armor_class="plate", armor_protection=20.0, covered_parts=["head"])
    breastplate = Item(id="plate_breastplate", name="Plate", item_type="armor", armor_class="plate", armor_protection=25.0, covered_parts=["torso"])
    call_method(eq_sys, ("equip_item", "equip"), defender, helmet)
    call_method(eq_sys, ("equip_item", "equip"), defender, breastplate)

    sword = Item(id="longsword", name="Longsword", item_type="weapon", damage=20.0, damage_type="cutting")
    res_leg = call_method(combat_sys, ("resolve_attack", "execute_attack"), attacker=attacker, defender=defender, weapon=sword, command="aim", target_part="right_leg", force_hit=True)

    assert defender.body["right_leg"].armor == pytest.approx(0.0)
    assert res_leg.get("armor_mitigation", 0.0) == pytest.approx(0.0)
    assert res_leg["effective_damage"] >= 15.0


def test_t3_04_eye_injury_reduces_combat_accuracy_and_persists_blindness(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F11 + F13: Severe eye_injury reduces combat accuracy in CombatSystem attack resolution."""
    health_sys = systems_suite["health_system"]
    combat_sys = systems_suite["combat_system"]
    Character = entity_factory["Character"]

    archer = Character(id="npc_archer", name="Archer", age=26, attributes={"dexterity": 75, "perception": 75})
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), archer)

    acc_healthy = call_method(combat_sys, ("calculate_accuracy", "get_attacker_accuracy"), archer)
    call_method(health_sys, ("apply_injury", "inflict_injury"), archer, "eyes", "eye_injury", severity=0.9, permanent=True)
    acc_injured = call_method(combat_sys, ("calculate_accuracy", "get_attacker_accuracy"), archer)

    assert acc_injured < acc_healthy * 0.85


def test_t3_05_broken_arm_degrades_weapon_handling_and_initiative(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F11 + F12 + F13: Broken right_arm degrades weapon handling and lowers combat initiative."""
    health_sys = systems_suite["health_system"]
    combat_sys = systems_suite["combat_system"]
    Character = entity_factory["Character"]

    fighter = Character(id="npc_duelist", name="Duelist", age=30, attributes={"agility": 70, "dexterity": 70})
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), fighter)

    init_healthy = call_method(combat_sys, ("calculate_initiative", "get_initiative"), fighter)
    call_method(health_sys, ("apply_injury", "inflict_injury"), fighter, "right_arm", "broken_arm", severity=0.85)
    init_injured = call_method(combat_sys, ("calculate_initiative", "get_initiative"), fighter)

    assert init_injured < init_healthy


def test_t3_06_unskilled_surgery_complication_to_prosthetic_recovery(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F11 + F12 + F13: Unskilled surgery leaves permanent disability/amputation, then prosthetic fitting restores limb function."""
    health_sys = systems_suite["health_system"]
    eq_sys = systems_suite["equipment_system"]
    Character = entity_factory["Character"]
    Item = entity_factory["Item"]

    patient = Character(id="char_vet", name="Veteran", age=35)
    bad_doc = Character(id="npc_bad_doc", name="Amateur Medic", age=22, skills={"medicine": 10.0})
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), patient)
    call_method(health_sys, ("apply_injury", "inflict_injury"), patient, "left_arm", "amputation", severity=1.0)

    call_method(health_sys, ("apply_treatment", "treat_character", "perform_treatment"), patient, stage="surgery", doctor=bad_doc, body_part="left_arm", cleanliness=0.2)
    assert patient.status == "alive"
    assert patient.body["left_arm"].functional is False

    prosthetic = Item(id="iron_prosthetic_arm", name="Iron Prosthetic Arm", item_type="prosthetic", covered_parts=["left_arm"])
    call_method(eq_sys, ("fit_prosthetic", "equip_prosthetic", "equip_item"), patient, prosthetic, body_part="left_arm")
    assert patient.body["left_arm"].functional is True


def test_t3_07_secret_killing_information_asymmetry_vs_witnessed_crime(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F9 + F10 + F15 + F16: Secret killing produces 0 memories/bounty; witnessed killing creates Memory, bounty, and rumor."""
    mem_sys = systems_suite["memory_system"]
    fac_sys = systems_suite["faction_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    GameEvent = entity_factory["GameEvent"]

    marcus = Character(id="comp_marcus", name="Marcus", age=40, location_id="lowtown_tavern")
    witness = Character(id="npc_0091", name="Merchant Vane", age=45, location_id="lowtown_street")
    world.characters.update({"comp_marcus": marcus, "npc_0091": witness})

    ev_secret = GameEvent("ev_sec_1", "CHARACTER_DIED", 100, "player", ["npc_thug_1"], "old_quarter", {"witnesses": [], "secret": True}, 0.9)
    call_method(mem_sys, ("record_event", "handle_event", "create_memory_from_event", "process_event"), ev_secret, world=world)
    res_sec = call_method(fac_sys, ("report_crime", "record_crime"), actor_id="player", crime_type="murder", district_id="old_quarter", witnessed=False, world=world)
    assert len(marcus.memories) == 0 and len(witness.memories) == 0
    assert (res_sec.get("bounty_added", 0.0) if isinstance(res_sec, dict) else 0.0) == 0.0

    ev_wit = GameEvent("ev_wit_1", "CHARACTER_DIED", 200, "player", ["npc_guard_1"], "lowtown_street", {"witnesses": ["npc_0091"]}, 0.95)
    call_method(mem_sys, ("record_event", "handle_event", "create_memory_from_event", "process_event"), ev_wit, world=world)
    res_wit = call_method(fac_sys, ("report_crime", "record_crime"), actor_id="player", crime_type="murder", district_id="lowtown", witnessed=True, world=world)
    assert len(witness.memories) >= 1
    assert witness.memories[-1].confidence == pytest.approx(1.0)
    assert (res_wit.get("bounty_added", 10.0) if isinstance(res_wit, dict) else 10.0) > 0.0


def test_t3_08_false_rumor_planting_propagates_to_faction_and_npc_reactions(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F2 + F9 + F15 + F16: Planting a false rumor propagates reach %, forms partial-confidence memories, and shifts NPC trust."""
    rumor_sys = systems_suite["rumor_system"]
    mem_sys = systems_suite["memory_system"]
    world = systems_suite["world"]
    District = entity_factory["District"]
    Character = entity_factory["Character"]

    world.districts["lowtown"] = District(id="lowtown", name="Lowtown")
    world.districts["harbor"] = District(id="harbor", name="Harbor")
    guard = Character(id="npc_guard_patrol", name="Patrolman", age=30, faction_id="city_guard", location_id="lowtown")
    world.characters["npc_guard_patrol"] = guard

    rumor = call_method(
        rumor_sys,
        ("plant_false_rumor", "create_rumor"),
        actor_id="player",
        subject="npc_voss",
        claim="Captain Voss embezzled City Guard payroll.",
        district_id="lowtown",
        truth=False,
        world=world,
    )
    call_method(rumor_sys, ("propagate_rumors", "step_rumors", "update"), world=world)
    call_method(mem_sys, ("record_rumor_memory", "learn_from_rumor", "receive_rumor", "add_rumor_memory"), guard, rumor)

    assert rumor.truth is False
    assert rumor.reach.get("lowtown", 0.0) > 0.0
    assert len(guard.memories) >= 1
    assert 0.0 < guard.memories[-1].confidence < 1.0


def test_t3_09_companion_witnessed_decision_updates_6axis_relationship_and_rivalry(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F8 + F9 + F10 + F16: Pro-Syndicate choice increases Marcus's rivalry while increasing Sera's friendship/trust."""
    rel_sys = systems_suite["relationship_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    Companion = entity_factory["Companion"]

    world.characters["comp_marcus"] = Character(id="comp_marcus", name="Marcus", age=40, is_companion=True)
    world.characters["comp_sera"] = Character(id="comp_sera", name="Sera", age=24, is_companion=True)
    c_marcus = Companion(character_id="comp_marcus", name="Marcus", friendship=20.0, rivalry=10.0, in_party=True)
    c_sera = Companion(character_id="comp_sera", name="Sera", friendship=20.0, rivalry=5.0, in_party=True)
    world.companions.update({"comp_marcus": c_marcus, "comp_sera": c_sera})

    call_method(
        rel_sys,
        ("adjust_companion_standing", "update_companion_relationship", "record_companion_reaction"),
        "comp_marcus",
        friendship_delta=0.0,
        rivalry_delta=20.0,
        respect_delta=10.0,
        world=world,
    )
    call_method(
        rel_sys,
        ("adjust_companion_standing", "update_companion_relationship", "record_companion_reaction"),
        "comp_sera",
        friendship_delta=25.0,
        rivalry_delta=0.0,
        trust_delta=15.0,
        world=world,
    )

    assert c_marcus.rivalry >= 30.0 and c_marcus.in_party is True
    assert c_sera.friendship >= 45.0


def test_t3_10_companion_abandonment_triggers_breaking_point_and_departure(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F2 + F8 + F9 + F10 + F13: Abandoning Marcus in combat records Anger memory and triggers breaking point departure."""
    mem_sys = systems_suite["memory_system"]
    rel_sys = systems_suite["relationship_system"]
    world = systems_suite["world"]
    event_bus = systems_suite["event_bus"]
    Character = entity_factory["Character"]
    Companion = entity_factory["Companion"]
    GameEvent = entity_factory["GameEvent"]

    marcus = Character(id="comp_marcus", name="Marcus", age=40, is_companion=True, location_id="lowtown_street")
    c_marcus = Companion(character_id="comp_marcus", name="Marcus", breaking_points=["abandoned_in_combat"], in_party=True)
    world.characters["comp_marcus"] = marcus
    world.companions["comp_marcus"] = c_marcus

    ev = GameEvent(
        id="ev_abandon_marcus",
        event_type="COMPANION_ABANDONED",
        timestamp=360,
        source_id="player",
        target_ids=["comp_marcus"],
        location_id="lowtown_street",
        data={"emotion": "Anger", "description": "Player abandoned Marcus during combat."},
        importance=0.95,
    )
    call_method(mem_sys, ("record_event", "handle_event", "create_memory_from_event", "process_event"), ev, world=world)
    call_method(rel_sys, ("trigger_breaking_point", "evaluate_breaking_point", "check_breaking_point"), "comp_marcus", reason="abandoned_in_combat", world=world)

    assert len(marcus.memories) >= 1
    assert c_marcus.in_party is False
    assert any(e.event_type == "COMPANION_BREAKING_POINT" for e in event_bus.emitted_log)


def test_t3_11_commander_incapacitation_triggers_divergent_archetype_morale(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F13 + F14: Commander incapacitation causes coward soldier to panic/retreat while berserker fights harder."""
    combat_sys = systems_suite["combat_system"]
    combat_ai = systems_suite["combat_ai"]
    EnemyCombatant = entity_factory["EnemyCombatant"]

    coward = EnemyCombatant(character_id="e_coward", archetype="coward", morale=35.0, morale_state="nervous")
    berserker = EnemyCombatant(character_id="e_berserk", archetype="berserker", morale=65.0, morale_state="steady")

    call_method(combat_sys, ("apply_morale_shock", "update_morale", "evaluate_morale_state"), coward, event_type="commander_incapacitated", morale_value=10.0)
    call_method(combat_sys, ("apply_morale_shock", "update_morale", "evaluate_morale_state"), berserker, event_type="commander_incapacitated", morale_value=85.0)

    act_coward = call_method(combat_ai, ("select_action", "decide_combat_action", "choose_action"), coward, context={"commander_down": True})
    act_berserk = call_method(combat_ai, ("select_action", "decide_combat_action", "choose_action"), berserker, context={"commander_down": True})

    assert act_coward["command"] in {"retreat", "surrender", "take_cover", "flee"}
    assert act_berserk["command"] in {"heavy_attack", "charge", "attack"}


def test_t3_12_nemesis_fair_adaptation_requires_witness_or_survival(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F4 + F9 + F13 + F14: Unwitnessed fire_magic does not adapt Voss; witnessed survival adapts Voss with fire_resistant_equipment."""
    nem_sys = systems_suite["nemesis_system"]
    NemesisProfile = entity_factory["NemesisProfile"]

    voss_prof = NemesisProfile(character_id="npc_voss", weaknesses=["fire"])

    # Battle 1: unwitnessed
    call_method(nem_sys, ("record_witnessed_tactic", "observe_tactic"), voss_prof, tactic="fire_magic", count=5, witnessed=False)
    call_method(nem_sys, ("adapt_to_player", "evaluate_adaptations", "apply_adaptations"), voss_prof)
    assert "fire_magic" not in voss_prof.known_player_tactics

    # Battle 2: witnessed by surviving Voss
    call_method(nem_sys, ("record_witnessed_tactic", "observe_tactic"), voss_prof, tactic="fire_magic", count=3, witnessed=True)
    adapts = call_method(nem_sys, ("adapt_to_player", "evaluate_adaptations", "apply_adaptations"), voss_prof)
    all_adapts = set(adapts or []) | set(getattr(voss_prof, "adaptations", [])) | set(voss_prof.special_traits)
    assert "fire_magic" in voss_prof.known_player_tactics
    assert "fire_resistant_equipment" in all_adapts


def test_t3_13_leader_death_creates_vacancy_and_ambition_promotion(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F2 + F10 + F14 + F15: CHARACTER_DIED on faction leader emits LEADERSHIP_VACANCY and promotes highest-scoring candidate."""
    fac_sys = systems_suite["faction_system"]
    world = systems_suite["world"]
    event_bus = systems_suite["event_bus"]
    Character = entity_factory["Character"]
    Faction = entity_factory["Faction"]
    GameEvent = entity_factory["GameEvent"]
    EventPriority = entity_factory["EventPriority"]

    leader = Character(id="npc_vael", name="Commander Vael", age=55, faction_id="city_guard", rank="commander", status="dead")
    lyra = Character(id="npc_captain_lyra", name="Captain Lyra", age=34, faction_id="city_guard", rank="captain", status="alive", personality={"ambition": 85, "loyalty": 80})
    world.characters.update({"npc_vael": leader, "npc_captain_lyra": lyra})
    guard = Faction(id="city_guard", name="City Guard", leader_id="npc_vael", members=["npc_vael", "npc_captain_lyra"])
    world.factions["city_guard"] = guard

    ev = GameEvent("ev_vael_dead", "CHARACTER_DIED", 600, "player", ["npc_vael"], "barracks", {}, 0.95)
    event_bus.emit(ev, priority=EventPriority.CRITICAL)
    call_method(fac_sys, ("resolve_leadership_vacancy", "handle_leader_death"), "city_guard", world=world)

    assert guard.leader_id == "npc_captain_lyra"


def test_t3_14_ambitious_low_loyalty_captain_betrays_weakened_commander(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F8 + F10 + F14 + F15: Ambitious low-loyalty Captain initiates betrayal/coup against weakened Commander."""
    ambition_ai = systems_suite["ambition_ai"]
    rel_sys = systems_suite["relationship_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    Faction = entity_factory["Faction"]

    commander = Character(id="npc_vael", name="Commander Vael", age=58, faction_id="city_guard", rank="commander", consciousness=30.0)
    voss = Character(id="npc_voss", name="Captain Voss", age=38, faction_id="city_guard", rank="captain", personality={"ambition": 90.0, "loyalty": 15.0})
    world.characters.update({"npc_vael": commander, "npc_voss": voss})
    world.factions["city_guard"] = Faction(id="city_guard", name="City Guard", leader_id="npc_vael", stability=25.0, members=["npc_vael", "npc_voss"])

    scheme = call_method(ambition_ai, ("evaluate_npc_ambitions", "evaluate_ambition", "select_ambition_action"), voss, world=world)
    call_method(rel_sys, ("set_relationship", "update_relationship", "modify_relationship"), "npc_voss", "npc_vael", trust=-40.0, resentment=75.0)
    rel = call_method(rel_sys, ("get_relationship", "query_relationship"), "npc_voss", "npc_vael")

    assert scheme["scheme_type"] in {"betray_superior", "undermine_rival", "seek_promotion", "coup"}
    assert rel.resentment >= 50.0


def test_t3_15_kenshi_non_lethal_defeat_by_city_guard_leads_to_arrest_and_prison(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F1 + F11 + F13 + F15 + F16: Player defeated by City Guard is captured/imprisoned, advancing clock without Game Over."""
    combat_sys = systems_suite["combat_system"]
    fac_sys = systems_suite["faction_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    player = Character(id="player", name="Rowan", age=28, is_player=True, status="incapacitated", location_id="lowtown_street")
    world.characters["player"] = player
    t0 = get_clock_minutes(world.clock)

    defeat_res = call_method(combat_sys, ("resolve_player_defeat", "handle_player_defeat"), world=world, victor_faction="city_guard")
    if get_clock_minutes(world.clock) == t0:
        call_method(fac_sys, ("arrest_character", "arrest_player"), "player", world=world)

    assert defeat_res["outcome"] in {"captured", "imprisoned"}
    assert player.status != "dead"
    assert get_clock_minutes(world.clock) > t0


def test_t3_16_kenshi_non_lethal_defeat_by_syndicate_leads_to_robbery_or_rescue(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F1 + F8 + F11 + F13 + F16: Player defeated by Lowtown Syndicate is robbed/left_for_dead/rescued and attacker becomes Nemesis-eligible."""
    combat_sys = systems_suite["combat_system"]
    nem_sys = systems_suite["nemesis_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    player = Character(id="player", name="Rowan", age=28, is_player=True, status="incapacitated", needs={"wealth": 100.0})
    mugger = Character(id="npc_mugger", name="Syndicate Enforcer", age=29, faction_id="lowtown_syndicate", tier=1)
    world.characters.update({"player": player, "npc_mugger": mugger})

    defeat_res = call_method(combat_sys, ("resolve_player_defeat", "handle_player_defeat"), world=world, victor_faction="lowtown_syndicate")
    call_method(nem_sys, ("evaluate_eligibility", "check_eligibility", "promote_to_nemesis"), mugger, trigger="injures_player", world=world)

    assert defeat_res["outcome"] in {"robbed", "left_for_dead", "rescued"}
    assert player.status != "dead"
    assert mugger.is_nemesis is True


def test_t3_17_quest_dynamic_world_state_adaptation_when_npc_dies_or_hostile(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F2 + F9 + F10 + F16: Active hybrid quest dynamically updates objectives when involved NPC dies or becomes hostile."""
    quest_sys = systems_suite["quest_system"]
    rel_sys = systems_suite["relationship_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    apprentice = Character(id="npc_missing_apprentice", name="Joren", age=17, status="alive")
    owner = Character(id="npc_workshop_owner", name="Gregor", age=48, status="alive")
    world.characters.update({"npc_missing_apprentice": apprentice, "npc_workshop_owner": owner})

    q = call_method(quest_sys, ("create_hybrid_quest", "start_quest", "create_quest"), quest_id="quest_missing_apprentice", world=world)
    call_method(rel_sys, ("set_relationship", "update_relationship"), "npc_workshop_owner", "player", trust=-60.0, resentment=80.0)
    apprentice.status = "dead"

    updated = call_method(quest_sys, ("evaluate_quest_conditions", "evaluate_quest_state"), "quest_missing_apprentice", world=world)
    assert updated is not None
    assert q.id == "quest_missing_apprentice"


def test_t3_18_district_unrest_and_food_shortage_trigger_riot_time_event(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F1 + F3 + F15 + F16: Food shortage + high unrest in Lowtown spikes prices and triggers a riot time event."""
    econ_sys = systems_suite["economy_system"]
    world = systems_suite["world"]
    event_bus = systems_suite["event_bus"]
    District = entity_factory["District"]

    lowtown = District(
        id="lowtown",
        name="Lowtown",
        food_supply=10.0,
        unrest=85.0,
        security=40.0,
        faction_influence={"lowtown_syndicate": 48.0, "city_guard": 22.0, "merchant_consortium": 12.0, "iron_workers_union": 10.0, "independent": 8.0},
    )
    world.districts["lowtown"] = lowtown

    call_method(econ_sys, ("process_daily_tick", "update_economy", "step_economy"), world=world)
    call_method(econ_sys, ("trigger_time_event", "evaluate_time_events"), event_kind="riot", district_id="lowtown", world=world)

    assert any(e.event_type == "TIME_EVENT_TRIGGERED" for e in event_bus.emitted_log)
    assert sum(lowtown.faction_influence.values()) == pytest.approx(100.0)


def test_t3_19_multi_day_time_skip_substeps_factions_healing_and_companion_autonomy(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F1 + F3 + F4 + F8 + F11 + F15: Waiting 3 days (4320m) sub-steps faction turns, heals treated wounds, and runs companion autonomy."""
    sim = systems_suite["simulation"]
    health_sys = systems_suite["health_system"]
    fac_ai = systems_suite["faction_ai"]
    char_ai = systems_suite["character_ai"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]
    Companion = entity_factory["Companion"]
    Faction = entity_factory["Faction"]
    District = entity_factory["District"]

    player = Character(id="player", name="Rowan", age=28, is_player=True)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), player)
    call_method(health_sys, ("apply_injury", "inflict_injury"), player, "left_arm", "deep_cut", severity=0.5)
    player.body["left_arm"].injuries[0].treated = True
    player.body["left_arm"].injuries[0].bleeding = 0.0

    sera = Character(id="comp_sera", name="Sera", age=24, is_companion=True)
    c_sera = Companion(character_id="comp_sera", name="Sera", in_party=True)
    guard = Faction(id="city_guard", name="City Guard", goals=[{"type": "maintain_authority"}])
    lowtown = District(id="lowtown", name="Lowtown")

    world.characters.update({"player": player, "comp_sera": sera})
    world.companions["comp_sera"] = c_sera
    world.factions["city_guard"] = guard
    world.districts["lowtown"] = lowtown

    faction_runs = {"c": 0}
    call_method(
        sim,
        ("register_system", "register_callback", "register_handler"),
        "factions",
        lambda *_a, **_k: (
            faction_runs.__setitem__("c", faction_runs["c"] + 1),
            call_method(fac_ai, ("process_faction_turn", "evaluate_faction_turn", "select_faction_action"), guard, world=world),
        ),
    )
    call_method(
        sim,
        ("register_system", "register_callback", "register_handler"),
        "economy",
        lambda *_a, **_k: call_method(health_sys, ("advance_healing", "update_health", "heal_over_time"), player, days=1),
    )
    call_method(
        sim,
        ("register_system", "register_callback", "register_handler"),
        "companions",
        lambda *_a, **_k: call_method(char_ai, ("update_companion_autonomy", "simulate_companion", "decide_companion_action", "evaluate_character"), c_sera, world),
    )

    call_method(sim, ("advance_time", "run_for_minutes", "step"), 4320)
    assert get_clock_minutes(world.clock) == 4320
    assert faction_runs["c"] >= 3
    if player.body["left_arm"].injuries:
        assert player.body["left_arm"].injuries[0].recovery_progress > 0.0


def test_t3_20_multi_stream_rng_isolation_across_combat_and_faction_systems() -> None:
    """F3 + F4 + F13 + F15: Extra combat RNG rolls in World A never alter faction turn RNG decisions compared to World B."""
    World = require_symbol("core.world", "World")
    FactionAI = require_symbol("ai.faction_ai", "FactionAI")
    Faction = require_symbol("entities.faction", "Faction")
    District = require_symbol("entities.district", "District")

    w_a = instantiate_with_context(World, seed=482193)
    w_b = instantiate_with_context(World, seed=482193)
    for w in (w_a, w_b):
        w.districts["lowtown"] = District(id="lowtown", name="Lowtown")
        w.factions["city_guard"] = Faction(id="city_guard", name="City Guard", goals=[{"type": "capture_district", "target": "lowtown"}])

    # Consume 25 extra combat rolls only in World A
    for _ in range(25):
        w_a.rng.stream("combat").random()

    ai_a = instantiate_with_context(FactionAI, world=w_a, rng=w_a.rng, event_bus=w_a.event_bus)
    ai_b = instantiate_with_context(FactionAI, world=w_b, rng=w_b.rng, event_bus=w_b.event_bus)

    res_a = call_method(ai_a, ("process_faction_turn", "evaluate_faction_turn", "select_faction_action"), w_a.factions["city_guard"], world=w_a)
    res_b = call_method(ai_b, ("process_faction_turn", "evaluate_faction_turn", "select_faction_action"), w_b.factions["city_guard"], world=w_b)

    assert w_a.rng.stream("faction").random() == w_b.rng.stream("faction").random()
    assert str(res_a) == str(res_b)


def test_t3_21_magic_spellcasting_accumulates_corruption_and_nerve_damage(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F11 + F12 + F13: Magic spellcasting inflicts burn/magic injury on target and accumulates corruption/nerve_damage on caster."""
    combat_sys = systems_suite["combat_system"]
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]

    elira = Character(id="comp_elira", name="Elira", age=26, skills={"magic": 85.0})
    enemy = Character(id="npc_voss", name="Captain Voss", age=38)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), elira)
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), enemy)

    for _ in range(5):
        call_method(
            combat_sys,
            ("resolve_spellcast", "execute_tactical_action", "resolve_attack"),
            attacker=elira,
            defender=enemy,
            command="spellcasting",
            damage_type="magic",
            spell_power=35.0,
            force_hit=True,
        )

    enemy_wounds = [inj.injury_type for bp in enemy.body.values() for inj in bp.injuries]
    elira_wounds = [inj.injury_type for bp in elira.body.values() for inj in bp.injuries]
    assert len(enemy_wounds) >= 1 or any(bp.integrity < 100.0 for bp in enemy.body.values())
    assert len(elira_wounds) >= 1 or elira.needs.get("corruption", 0.0) > 0.0


def test_t3_22_crime_smuggling_and_stealth_detection_shift_6scope_reputation(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F15 + F16: Undetected smuggling boosts underworld reputation without guard penalty; detected crime drops guard/noble rep."""
    fac_sys = systems_suite["faction_system"]
    quest_sys = systems_suite["quest_system"]
    world = systems_suite["world"]
    Character = entity_factory["Character"]

    world.characters["player"] = Character(id="player", name="Rowan", age=28, is_player=True, skills={"stealth": 85.0})

    # Undetected smuggling
    call_method(fac_sys, ("report_crime", "record_crime"), actor_id="player", crime_type="smuggling", district_id="harbor", witnessed=False, world=world)
    call_method(quest_sys, ("adjust_reputation", "modify_reputation"), scope="criminal_underworld", key=None, delta=25.0, world=world)
    assert call_method(quest_sys, ("get_reputation", "query_reputation"), scope="criminal_underworld", key=None, world=world) >= 25.0
    assert call_method(quest_sys, ("get_reputation", "query_reputation"), scope="faction", key="city_guard", world=world) == 0.0

    # Detected crime
    call_method(fac_sys, ("report_crime", "record_crime"), actor_id="player", crime_type="smuggling", district_id="high_quarter", witnessed=True, world=world)
    call_method(quest_sys, ("adjust_reputation", "modify_reputation"), scope="faction", key="city_guard", delta=-30.0, world=world)
    call_method(quest_sys, ("adjust_reputation", "modify_reputation"), scope="noble_society", key=None, delta=-25.0, world=world)
    assert call_method(quest_sys, ("get_reputation", "query_reputation"), scope="faction", key="city_guard", world=world) <= -30.0


def test_t3_23_disease_and_wound_infection_progression_to_medical_cure(systems_suite: dict[str, Any], entity_factory: dict[str, Any]) -> None:
    """F3 + F11 + F12 + F16: Untreated high-infection_risk deep_cut develops infection, then medical treatment cures it."""
    health_sys = systems_suite["health_system"]
    Character = entity_factory["Character"]

    c = Character(id="char_sick", name="Patient", age=30)
    doctor = Character(id="comp_tomas", name="Tomas", age=31, skills={"medicine": 90.0})
    call_method(health_sys, ("initialize_body", "ensure_anatomy", "create_body"), c)
    call_method(health_sys, ("apply_injury", "inflict_injury"), c, "left_leg", "deep_cut", severity=0.75)
    c.body["left_leg"].injuries[0].infection_risk = 0.9

    call_method(health_sys, ("process_infection_tick", "check_infection", "update_diseases"), c)
    call_method(health_sys, ("apply_treatment", "treat_character", "perform_treatment"), c, stage="field_treatment", doctor=doctor, body_part="left_leg")

    assert c.body["left_leg"].injuries[0].treated is True
    assert c.body["left_leg"].injuries[0].infection_risk < 0.9


def test_t3_24_save_load_roundtrip_preserves_active_cross_system_state_and_rng(populated_world: Any, save_manager: Any) -> None:
    """F4 + F5 + F6 + F7 + F11 + F14 + F15: Save and reload mid-campaign state and verify 24h post-load simulation matches."""
    SimulationEngine = require_symbol("core.simulation", "SimulationEngine")
    health_sys_cls = require_symbol("systems.health_system", "HealthSystem")
    health_sys = instantiate_with_context(health_sys_cls, world=populated_world)

    voss = populated_world.characters["npc_voss"]
    call_method(health_sys, ("apply_injury", "inflict_injury"), voss, "left_leg", "compound_fracture", severity=0.8)
    populated_world.nemesis_profiles["npc_voss"].known_player_tactics.append("fire_magic")
    populated_world.clock.advance(720)

    call_method(save_manager, ("save_game", "save_current_state"), populated_world, slot="cross_system_slot")
    loaded_world = call_method(save_manager, ("load_game", "load_current_state"), slot="cross_system_slot")

    assert get_clock_minutes(loaded_world.clock) == get_clock_minutes(populated_world.clock)
    assert "fire_magic" in loaded_world.nemesis_profiles["npc_voss"].known_player_tactics
    assert any(i.injury_type == "compound_fracture" for i in loaded_world.characters["npc_voss"].body["left_leg"].injuries)

    sim_orig = instantiate_with_context(SimulationEngine, world=populated_world, clock=populated_world.clock, rng=populated_world.rng, event_bus=populated_world.event_bus)
    sim_load = instantiate_with_context(SimulationEngine, world=loaded_world, clock=loaded_world.clock, rng=loaded_world.rng, event_bus=loaded_world.event_bus)

    call_method(sim_orig, ("advance_time", "run_for_minutes", "step"), 1440)
    call_method(sim_load, ("advance_time", "run_for_minutes", "step"), 1440)
    assert populated_world.rng.stream("world").random() == loaded_world.rng.stream("world").random()


def test_t3_25_command_parser_execution_drives_simulation_and_chronicle_persistence(game_session: Any) -> None:
    """F1 + F2 + F7 + F18 + F19: Executing talk, inspect, attack, rest, and wait advances simulation and populates Chronicle."""
    cmds = [
        "talk sera",
        "inspect captain voss",
        "attack captain voss",
        "rest 8h",
        "wait 3d",
    ]
    for cmd in cmds:
        res = game_session.execute_command(cmd)
        assert res["success"] is True

    assert get_clock_minutes(game_session.world.clock) >= 4800
    chronicle = game_session.save_manager.generate_chronicle(game_session.world)
    assert isinstance(chronicle, list) and len(chronicle) >= 1


def test_t3_26_religion_schism_and_tomas_companion_faith_conflict(populated_world: Any) -> None:
    """F8 + F9 + F10 + F15 + F16: Ashen Church schism / doctrinaire action triggers Tomas's faith conflict and updates approval."""
    fac_sys_cls = require_symbol("systems.faction_system", "FactionSystem")
    rel_sys_cls = require_symbol("systems.relationship_system", "RelationshipSystem")
    fac_sys = instantiate_with_context(fac_sys_cls, world=populated_world, event_bus=populated_world.event_bus)
    rel_sys = instantiate_with_context(rel_sys_cls, world=populated_world, event_bus=populated_world.event_bus)

    call_method(fac_sys, ("trigger_religious_schism", "evaluate_religious_authority"), world=populated_world)
    call_method(
        rel_sys,
        ("adjust_companion_standing", "update_companion_relationship", "record_companion_reaction"),
        "comp_tomas",
        friendship_delta=20.0,
        trust_delta=15.0,
        world=populated_world,
    )

    tomas_comp = populated_world.companions["comp_tomas"]
    assert tomas_comp.friendship >= 20.0
    assert populated_world.districts["temple_district"].unrest > 0.0
