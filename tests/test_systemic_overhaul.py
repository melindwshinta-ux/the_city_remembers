"""Comprehensive unit tests for Milestone M2: Combat Clash, Politics & Petitioners, Relationships, and Economy."""

from __future__ import annotations

from content import COMMODITIES, PROPERTIES_CATALOG, populate_world
from core.world import World
from entities.character import Character, Injury, Memory, create_humanoid_body
from entities.companion import CANONICAL_COMPANIONS, CompanionProfile
from entities.enemy import EnemyCombatant
from systems.combat_system import CombatSystem
from systems.economy_system import EconomySystem
from systems.faction_system import FactionSystem, generate_petitioners, resolve_petitioner
from systems.relationship_system import RelationshipSystem


def _make_world(seed: int = 424242) -> World:
    w = World(seed=seed)
    populate_world(w)
    return w


# =====================================================================
# 1. Combat Clash & Tactical Action Fixes
# =====================================================================


def test_guard_and_apply_bandage_have_real_effects() -> None:
    w = _make_world()
    cs = CombatSystem(event_bus=w.event_bus, clock=w.clock, rng=w.rng, world=w)
    player = w.characters["player"]
    enemy = Character(id="thug_1", name="Alley Thug", attributes={"strength": 60, "dexterity": 60})
    enemy.body = create_humanoid_body("thug_1")

    # Baseline unguarded hit
    res_normal = cs.resolve_attack(enemy, player, force_hit=True)
    # Reset torso integrity & test guarded hit
    player.body["torso"].integrity = 100.0
    guard_res = cs.execute_tactical_action(attacker=player, command="guard")
    assert guard_res["success"] is True
    assert guard_res["guarding"] is True
    res_guarded = cs.resolve_attack(enemy, player, force_hit=True)
    assert res_guarded["effective_damage"] < res_normal["effective_damage"]

    # Inflict bleeding and lower consciousness, then apply_bandage
    player.consciousness = 65.0
    player.body["torso"].injuries.append(
        Injury(id="inj_test_bleed", injury_type="deep_cut", severity=0.6, pain=10.0, bleeding=0.5)
    )
    band_res = cs.execute_tactical_action(attacker=player, defender=player, command="apply_bandage")
    assert band_res["success"] is True
    assert band_res["bleeding_stopped"] >= 1
    assert player.consciousness == 80.0
    assert all(inj.bleeding == 0.0 for inj in player.body["torso"].injuries)
    assert all(inj.treated is True for inj in player.body["torso"].injuries)


def test_clash_session_actions_1_through_7_and_5_line_log() -> None:
    w = _make_world()
    cs = CombatSystem(event_bus=w.event_bus, clock=w.clock, rng=w.rng, world=w)
    player = w.characters["player"]
    marcus = w.characters["comp_marcus"]
    enemy = Character(id="raider_1", name="Syndicate Raider")
    enemy.morale = 75.0
    enemy.body = create_humanoid_body("raider_1")

    session = cs.start_clash_session(party=[player, marcus], enemies=[enemy], victor_faction="lowtown_syndicate", world=w)
    assert session.status == "active"

    # [1] Balanced Strike
    r1 = cs.resolve_clash_turn(session, "1", world=w)
    assert r1["player_action"]["hit"] is True

    # [2] Heavy Brutal Assault (+35% dmg)
    r2 = cs.resolve_clash_turn(session, "2", world=w)
    assert r2["player_action"]["effective_damage"] > r1["player_action"]["effective_damage"]

    # [3] Aimed Limb Strikes (arms, legs, torso)
    r3_arms = cs.resolve_clash_turn(session, "3", aim_target="arms", world=w)
    assert r3_arms["player_action"]["hit_location"] == "left_arm"
    assert enemy.id in session.crippled_enemies

    r3_legs = cs.resolve_clash_turn(session, "3", aim_target="legs", world=w)
    assert r3_legs["player_action"]["hit_location"] == "left_leg"
    assert enemy.id in session.pinned_enemies

    # [4] Defensive Stance & Rally Party
    r4 = cs.resolve_clash_turn(session, "4", world=w)
    assert r4["player_action"]["guarding"] is True
    assert session.party_morale_bonus == 10.0

    # [5] Field Triage & Bandage
    player.consciousness = 70.0
    r5 = cs.resolve_clash_turn(session, "5", world=w)
    assert r5["player_action"]["command"] == "apply_bandage"
    assert player.consciousness >= 70.0

    # [6] Tactical Trick (dirty trick when no mage in party)
    r6 = cs.resolve_clash_turn(session, "6", world=w)
    assert r6["player_action"]["trick"] is True

    # Rolling 5-line log invariant
    assert len(session.combat_log) <= 5

    # [7] Demand Surrender: fails when morale > 30, succeeds when morale <= 30
    enemy.morale = 50.0
    r7_fail = cs.resolve_clash_turn(session, "7", world=w)
    assert r7_fail["status"] == "active"

    enemy.morale = 20.0
    r7_ok = cs.resolve_clash_turn(session, "7", world=w)
    assert r7_ok["status"] == "victory"
    assert r7_ok["outcome"]["result"] == "enemy_surrendered"


def test_clash_session_arcane_surge_and_0_retreat_surrender() -> None:
    w = _make_world()
    cs = CombatSystem(event_bus=w.event_bus, clock=w.clock, rng=w.rng, world=w)
    player = w.characters["player"]
    elira = w.characters["comp_elira"]
    enemy = Character(id="guard_1", name="Corrupt Watchman")
    enemy.morale = 80.0
    enemy.body = create_humanoid_body("guard_1")

    s1 = cs.start_clash_session(party=[player, elira], enemies=[enemy], victor_faction="city_guard", world=w)
    r6 = cs.resolve_clash_turn(s1, "6", world=w)
    assert r6["player_action"]["command"] == "spellcasting"

    # [0] Non-lethal surrender delegates to resolve_player_defeat
    r0 = cs.resolve_clash_turn(s1, "0", surrender=True, world=w)
    assert r0["status"] == "surrendered"
    assert r0["outcome"]["outcome"] == "imprisoned"
    assert player.location_id == "barracks_prison"


# =====================================================================
# 2. Political Intrigue & Petitioners
# =====================================================================


def test_political_operations_and_internal_coup() -> None:
    w = _make_world()
    w.characters["player"].needs["wealth"] = 1000.0
    fs = FactionSystem(event_bus=w.event_bus, clock=w.clock, rng=w.rng, world=w)

    # Petition & Donate
    pet_res = fs.petition_faction_leader("city_guard", request_type="contract", world=w)
    assert pet_res["success"] is True
    assert pet_res["gold_granted"] == 40.0

    don_res = fs.donate_to_faction("merchant_consortium", amount=50.0, world=w)
    assert don_res["success"] is True
    assert don_res["faction_reputation"] > 0.0

    # Incite Turf War & Broker Truce
    war_res = fs.incite_turf_war("city_guard", "lowtown_syndicate", district_id="lowtown", world=w)
    assert war_res["success"] is True
    assert fs.get_relation("city_guard", "lowtown_syndicate", world=w) == -35.0

    truce_res = fs.broker_truce("city_guard", "lowtown_syndicate", world=w)
    assert truce_res["success"] is True
    assert fs.get_relation("city_guard", "lowtown_syndicate", world=w) == -5.0

    # Pay Off Bounty
    w.flags["bounty"] = 120.0
    w.flags["wanted"] = True
    bounty_res = fs.pay_off_bounty(amount=50.0, world=w)
    assert bounty_res["success"] is True
    assert w.flags["bounty"] == 0.0
    assert w.flags["wanted"] is False

    # Smear Campaign via RumorSystem
    smear_res = fs.smear_campaign("npc_voss", district_id="lowtown", world=w)
    assert smear_res["success"] is True
    assert smear_res["rumor_id"] in w.rumors

    # Sabotage District
    unrest_before = w.districts["harbor"].unrest
    sab_res = fs.sabotage_district("harbor", world=w)
    assert sab_res["success"] is True
    assert w.districts["harbor"].unrest > unrest_before

    # Civic Edicts (all 3)
    food_before = w.districts["lowtown"].food_supply
    ed1 = fs.sponsor_civic_edict("lowtown", "soup_kitchens", world=w)
    assert ed1["success"] is True
    assert w.districts["lowtown"].food_supply > food_before

    sec_before = w.districts["lowtown"].security
    ed2 = fs.sponsor_civic_edict("lowtown", "private_watch_patrols", world=w)
    assert ed2["success"] is True
    assert w.districts["lowtown"].security > sec_before

    unrest_before2 = w.districts["lowtown"].unrest
    ed3 = fs.sponsor_civic_edict("lowtown", "festival", world=w)
    assert ed3["success"] is True
    assert w.districts["lowtown"].unrest < unrest_before2

    # Back Internal Coup (Voss has ambition=85, loyalty=30 in city_guard)
    coup_res = fs.back_internal_coup("city_guard", bribe_amount=100.0, world=w)
    assert coup_res["success"] is True
    assert coup_res["new_leader_id"] == "npc_voss"
    assert w.factions["city_guard"].leader_id == "npc_voss"


def test_procedural_petitioners_generation_and_resolution() -> None:
    w = _make_world()
    w.characters["player"].needs["wealth"] = 200.0
    pets = generate_petitioners(w, location_type="safehouse", count=3)
    assert len(pets) == 3
    for p in pets:
        assert len(p["choices"]) == 4
        res = resolve_petitioner(w, p, 1)
        assert res["success"] is True


# =====================================================================
# 3. Relationship Social Depth
# =====================================================================


def test_relationship_social_actions() -> None:
    w = _make_world()
    w.characters["player"].needs["wealth"] = 200.0
    rs = RelationshipSystem(event_bus=w.event_bus, clock=w.clock, rng=w.rng, world=w)

    # Give gift
    gift_res = rs.give_gift(w, "player", "npc_trader_brant", gold_cost=25.0)
    assert gift_res["success"] is True
    assert gift_res["affection"] >= 15.0
    assert gift_res["trust"] >= 10.0

    # Extort fails without leverage
    fail_extort = rs.extort_npc(w, "player", "npc_trader_brant")
    assert fail_extort["success"] is False

    # Extort succeeds with secret Memory
    brant = w.characters["npc_trader_brant"]
    brant.memories.append(
        Memory(id="mem_secret_1", event_type="SMUGGLING", description="Skimmed harbor taxes", source_type="secret")
    )
    ok_extort = rs.extort_npc(w, "player", "npc_trader_brant")
    assert ok_extort["success"] is True
    assert ok_extort["gold_gained"] >= 25.0
    assert ok_extort["resentment"] >= 20.0

    # Campfire counsel with canonical CompanionProfile breaking_points & conflict_description
    w.companions["comp_sera"] = CompanionProfile(**CANONICAL_COMPANIONS["comp_sera"])
    rs.set_relationship("comp_sera", "player", resentment=45.0, trust=30.0)
    counsel_res = rs.campfire_counsel(w, "comp_sera", resolve_tension=True)
    assert counsel_res["success"] is True
    assert len(counsel_res["breaking_points"]) >= 1
    assert counsel_res["conflict_description"] != ""
    assert counsel_res["resentment"] < 45.0
    assert counsel_res["trust"] > 30.0

    # Swear Blood Oath
    rs.set_relationship("comp_marcus", "player", trust=75.0, respect=75.0)
    oath_res = rs.swear_blood_oath(w, "player", "comp_marcus")
    assert oath_res["success"] is True
    assert w.flags["blood_oaths"]["comp_marcus"] is True

    # Declare Blood Feud -> Bitter enemy + NemesisProfile
    feud_res = rs.declare_blood_feud(w, "player", "npc_gang_karn")
    assert feud_res["success"] is True
    assert feud_res["relationship_state"] == "Bitter enemy"
    assert "npc_gang_karn" in w.nemesis_profiles
    assert w.characters["npc_gang_karn"].is_nemesis is True


# =====================================================================
# 4. Economy, Properties, Loans, Caravans, Daily Digest & World Serialization
# =====================================================================


def test_commodities_properties_loans_caravans_and_daily_digest() -> None:
    w = _make_world()
    w.characters["player"].needs["wealth"] = 2000.0
    es = EconomySystem(event_bus=w.event_bus, clock=w.clock, rng=w.rng, world=w)

    assert len(COMMODITIES) == 6
    assert len(PROPERTIES_CATALOG) == 5

    # Dynamic commodity pricing & arbitrage
    p_iron_ward = es.get_commodity_price("iron_tools", district_id="iron_ward", world=w)
    p_high_q = es.get_commodity_price("iron_tools", district_id="high_quarter", world=w)
    assert p_iron_ward < p_high_q

    buy_res = es.buy_commodity("player", "iron_tools", quantity=5, district_id="iron_ward", world=w)
    assert buy_res["success"] is True
    assert w.commodities["iron_tools"] == 5

    sell_res = es.sell_commodity("player", "iron_tools", quantity=5, district_id="high_quarter", world=w)
    assert sell_res["success"] is True
    assert sell_res["revenue"] > buy_res["total_cost"]

    # Embargo raises price
    w.flags["embargoes"] = {"lowtown": True}
    p_embargo = es.get_commodity_price("grain_rations", district_id="lowtown", world=w)
    w.flags["embargoes"] = {}
    p_normal = es.get_commodity_price("grain_rations", district_id="lowtown", world=w)
    assert p_embargo > p_normal

    # Property purchase & upgrade + daily passive income
    prop_res = es.acquire_property("player", "cobblestone_stall", cost=200.0, world=w)
    assert prop_res["success"] is True
    up_res = es.upgrade_property("player", "cobblestone_stall", world=w)
    assert up_res["success"] is True
    assert up_res["level"] == 2
    assert up_res["daily_income"] > 25.0

    # Loans & Syndicate default risk
    loan_res = es.take_loan("player", amount=100.0, lender="lowtown_syndicate", term_days=1, world=w)
    assert loan_res["success"] is True
    loan_id = loan_res["loan"]["id"]

    # Caravan investment
    car_res = es.invest_caravan("player", amount=100.0, world=w)
    assert car_res["success"] is True

    # Process daily tick -> property income + loan default + Daily City Digest
    tick_res = es.process_daily_tick(w)
    assert "daily_digest" in tick_res
    assert "last_daily_digest" in w.flags
    digest = w.flags["last_daily_digest"]
    assert digest["property_income"] == up_res["daily_income"]
    assert loan_id in digest["defaults"]
    assert w.flags.get("syndicate_enforcer_dispatched") is True

    # Repay remaining loan balance
    repay_res = es.repay_loan("player", loan_id, world=w)
    assert repay_res["success"] is True
    assert repay_res["status"] == "paid"

    # Advance 2 more days for caravan completion
    es.process_daily_tick(w)
    es.process_daily_tick(w)
    assert w.caravans[0]["status"] in ("completed", "raided")


def test_world_round_trip_serialization_and_legacy_defaults() -> None:
    w = _make_world()
    w.characters["player"].needs["wealth"] = 1000.0
    es = EconomySystem(event_bus=w.event_bus, clock=w.clock, rng=w.rng, world=w)
    es.acquire_property("player", "lowtown_safehouse", cost=150.0, world=w)
    es.buy_commodity("player", "grain_rations", quantity=3, district_id="lowtown", world=w)
    es.take_loan("player", amount=50.0, world=w)
    es.invest_caravan("player", amount=50.0, world=w)

    raw = w.to_dict()
    restored = World.from_dict(raw)
    assert "lowtown_safehouse" in restored.properties
    assert restored.commodities["grain_rations"] == 3
    assert len(restored.loans) == 1
    assert len(restored.caravans) == 1

    # Old save dict without new keys loads safely with defaults
    legacy = dict(raw)
    for k in ("properties", "commodities", "loans", "caravans"):
        legacy.pop(k, None)
    restored_legacy = World.from_dict(legacy)
    assert restored_legacy.properties == {}
    assert restored_legacy.commodities == {}
    assert restored_legacy.loans == []
    assert restored_legacy.caravans == []
