"""Content package and world population factory for THE CITY REMEMBERS (GDD Sections 2, 7, 8, 9, 17)."""

from __future__ import annotations

from typing import Any

from entities.character import Character, Injury, BodyPart, create_humanoid_body
from entities.companion import Companion, CompanionProfile
from entities.district import District, Location
from entities.enemy import NemesisProfile, EnemyCombatant
from entities.faction import Faction
from entities.item import Item
from entities.quest import Quest


RANDOM_EVENTS_LIST = [
    {"id": f"rnd_ev_{i}", "title": f"City Event {i}", "description": desc, "district": dist}
    for i, (desc, dist) in enumerate([
        ("A tavern brawl spills into Lowtown gutters.", "lowtown"),
        ("Smugglers signal from a lantern in the Harbor mist.", "harbor"),
        ("Foundry workers strike outside Iron Ward gates.", "iron_ward"),
        ("A heated succession debate echoes in High Quarter salons.", "high_quarter"),
        ("Priests chant ominous hymns in the Temple District.", "temple_district"),
        ("Strange whispers echo from the ruins of Old Quarter.", "old_quarter"),
        ("City Guards conduct sudden checkpoint searches.", "barracks"),
        ("A pickpocket is chased through Lowtown markets.", "lowtown"),
        ("A merchant vessel arrives carrying exotic spices.", "harbor"),
        ("A foundry steam-boiler explodes with deafening force.", "iron_ward"),
        ("A clandestine duel takes place at dawn in the gardens.", "high_quarter"),
        ("An Ashen Church acolyte secretly distributes forbidden bread.", "temple_district"),
        ("Scavengers unearth an imperial crypt in Old Quarter.", "old_quarter"),
        ("Guards demand extra tolls at the Lowtown gate.", "lowtown"),
        ("A drunken sailor tells wild tales of sea monsters.", "harbor"),
        ("Labor leaders meet in secret behind the iron foundry.", "iron_ward"),
        ("A noble carriage is pelted with rotting vegetables.", "high_quarter"),
        ("A miraculous healing is proclaimed at the cathedral.", "temple_district"),
        ("A collapsed cellar reveals ancient imperial masonry.", "old_quarter"),
        ("Sergeant Merek inspects weapons in the armory courtyard.", "barracks"),
        ("Syndicate runners plant extortion marks on storefronts.", "lowtown"),
        ("Foreign envoys arrive at the Harbor customs house.", "harbor"),
    ], 1)
]


def load_events() -> list[dict[str, Any]]:
    return list(RANDOM_EVENTS_LIST)


def get_random_events() -> list[dict[str, Any]]:
    return list(RANDOM_EVENTS_LIST)


def list_random_events() -> list[dict[str, Any]]:
    return list(RANDOM_EVENTS_LIST)


COMMODITIES: dict[str, dict[str, Any]] = {
    "grain_rations": {
        "id": "grain_rations",
        "name": "Grain & Rations",
        "base_price": 12.0,
        "category": "food",
        "contraband": False,
        "description": "Staple grain sacks and salted travel rations.",
    },
    "iron_tools": {
        "id": "iron_tools",
        "name": "Iron & Tools",
        "base_price": 24.0,
        "category": "industry",
        "contraband": False,
        "description": "Forged ingots, hammers, and foundry fittings.",
    },
    "weapons_armor": {
        "id": "weapons_armor",
        "name": "Weapons & Armor",
        "base_price": 55.0,
        "category": "martial",
        "contraband": False,
        "description": "Tempered blades, mail links, and leather harness.",
    },
    "medical_supplies": {
        "id": "medical_supplies",
        "name": "Medical Supplies",
        "base_price": 32.0,
        "category": "medicine",
        "contraband": False,
        "description": "Linen bandages, antiseptic spirits, and surgical salves.",
    },
    "luxury_silk_wine": {
        "id": "luxury_silk_wine",
        "name": "Luxury Silk & Wine",
        "base_price": 75.0,
        "category": "luxury",
        "contraband": False,
        "description": "Imported silks and vintage estates coveted in the High Quarter.",
    },
    "smuggled_contraband": {
        "id": "smuggled_contraband",
        "name": "Smuggled Contraband",
        "base_price": 60.0,
        "category": "contraband",
        "contraband": True,
        "description": "Untaxed arcane relics, black-lotus vials, and forged writs.",
    },
}


PROPERTIES_CATALOG: dict[str, dict[str, Any]] = {
    "lowtown_safehouse": {
        "id": "lowtown_safehouse",
        "name": "Lowtown Safehouse",
        "district_id": "lowtown",
        "type": "safehouse",
        "base_cost": 150.0,
        "daily_income": 15.0,
        "upgrade_base_cost": 100.0,
        "income_per_level": 12.0,
        "description": "A fortified cellar with a hidden bolt-hole and dry bunks.",
    },
    "cobblestone_stall": {
        "id": "cobblestone_stall",
        "name": "Cobblestone Stall",
        "district_id": "lowtown",
        "type": "business",
        "base_cost": 200.0,
        "daily_income": 25.0,
        "upgrade_base_cost": 140.0,
        "income_per_level": 18.0,
        "description": "A busy corner trading stall in Lowtown's Cobblestone Market.",
    },
    "iron_ward_smithy": {
        "id": "iron_ward_smithy",
        "name": "Iron Ward Smithy",
        "district_id": "iron_ward",
        "type": "workshop",
        "base_cost": 350.0,
        "daily_income": 45.0,
        "upgrade_base_cost": 220.0,
        "income_per_level": 30.0,
        "description": "A soot-blackened forge producing blades and foundry tools.",
    },
    "harbor_smugglers_berth": {
        "id": "harbor_smugglers_berth",
        "name": "Harbor Smuggler's Berth",
        "district_id": "harbor",
        "type": "smuggling",
        "base_cost": 400.0,
        "daily_income": 55.0,
        "upgrade_base_cost": 260.0,
        "income_per_level": 35.0,
        "description": "A private timber slip under the Harbor piers for untaxed cargo.",
    },
    "back_alley_clinic": {
        "id": "back_alley_clinic",
        "name": "Back-Alley Clinic",
        "district_id": "lowtown",
        "type": "clinic",
        "base_cost": 280.0,
        "daily_income": 35.0,
        "upgrade_base_cost": 180.0,
        "income_per_level": 22.0,
        "description": "A discreet chirurgeon's parlor treating wounds without Guard questions.",
    },
}


def get_commodities_catalog() -> dict[str, dict[str, Any]]:
    return {k: dict(v) for k, v in COMMODITIES.items()}


def get_properties_catalog() -> dict[str, dict[str, Any]]:
    return {k: dict(v) for k, v in PROPERTIES_CATALOG.items()}


def populate_world(world: Any) -> Any:
    """Populate World instance with canonical Veyr districts, factions, NPCs, companions, and items."""
    # 1. Seven Districts
    districts_data = [
        ("lowtown", "Lowtown", "Poor, crowded, criminal activity", "Gang warfare", 12000, 25.0, 25.0, 75.0, 40.0, 80.0, {
            "lowtown_syndicate": 48.0,
            "city_guard": 22.0,
            "merchant_consortium": 12.0,
            "iron_workers_union": 10.0,
            "independent": 8.0,
        }),
        ("high_quarter", "High Quarter", "Nobility, mansions, politics", "Noble succession", 5000, 90.0, 85.0, 20.0, 75.0, 15.0, {
            "noble_houses": 60.0,
            "city_guard": 25.0,
            "merchant_consortium": 15.0,
        }),
        ("iron_ward", "Iron Ward", "Smiths, workshops, foundries", "Labor unrest", 8000, 45.0, 50.0, 65.0, 60.0, 35.0, {
            "iron_workers_union": 55.0,
            "merchant_consortium": 25.0,
            "city_guard": 20.0,
        }),
        ("harbor", "Harbor", "Merchants, sailors, smugglers", "Trade monopoly", 9000, 70.0, 55.0, 40.0, 80.0, 45.0, {
            "merchant_consortium": 50.0,
            "lowtown_syndicate": 25.0,
            "city_guard": 25.0,
        }),
        ("temple_district", "Temple District", "Religious authority", "Religious schism", 6000, 60.0, 70.0, 35.0, 50.0, 20.0, {
            "ashen_church": 70.0,
            "city_guard": 20.0,
            "noble_houses": 10.0,
        }),
        ("old_quarter", "Old Quarter", "Abandoned buildings, ruins", "Ancient secrets", 2000, 10.0, 15.0, 50.0, 10.0, 70.0, {
            "independent_mages": 40.0,
            "lowtown_syndicate": 30.0,
            "independent": 30.0,
        }),
        ("barracks", "Barracks", "Soldiers, prisons, training grounds", "Military corruption", 4000, 50.0, 80.0, 30.0, 90.0, 25.0, {
            "city_guard": 85.0,
            "noble_houses": 15.0,
        }),
    ]

    for did, name, charac, conflict, pop, w, sec, unr, emp, crime, inf in districts_data:
        world.districts[did] = District(
            id=did,
            name=name,
            characteristics=charac,
            major_conflict=conflict,
            population=pop,
            wealth=w,
            security=sec,
            unrest=unr,
            employment=emp,
            crime=crime,
            faction_influence=inf,
            locations=[],
        )

        if did == "lowtown":
            lowtown_locations = [
                Location(
                    id="lowtown_tavern",
                    name="The Drunken Gull Tavern",
                    district_id="lowtown",
                    description="A smoke-stained tavern smelling of cheap ale and damp wool, where off-duty guards and Syndicate informants drink in separate booths.",
                    connected_locations=["lowtown_street", "lowtown_docks"],
                    terrain_features=["hearth", "booths", "back_exit"],
                    npcs_present=["comp_marcus", "comp_elira", "comp_sera", "comp_tomas"],
                ),
                Location(
                    id="lowtown_market",
                    name="Cobblestone Market",
                    district_id="lowtown",
                    description="A bustling open-air square of canvas stalls and slick cobblestones, now cordoned with Guard chalk around a slain merchant's cart.",
                    connected_locations=["lowtown_street", "lowtown_docks", "lowtown_alleys"],
                    terrain_features=["market_stalls", "cover", "chalk_perimeter"],
                    npcs_present=["npc_trader_brant"],
                ),
                Location(
                    id="lowtown_docks",
                    name="Murky Docks",
                    district_id="lowtown",
                    description="Creaking timber piers shrouded in river fog, stacked with tarred cargo crates and watched by wary dockworkers.",
                    connected_locations=["lowtown_market", "lowtown_tavern", "lowtown_warehouse"],
                    terrain_features=["wooden_piers", "fog", "cargo_crates"],
                    npcs_present=[],
                ),
                Location(
                    id="lowtown_alleys",
                    name="Shadow Alleyways",
                    district_id="lowtown",
                    description="A maze of narrow brick passages and dripping eaves linking the market to Syndicate territory.",
                    connected_locations=["lowtown_street", "lowtown_market", "lowtown_safehouse", "lowtown_warehouse"],
                    terrain_features=["narrow_passage", "rooftop_access", "storm_drains"],
                    npcs_present=["npc_gang_karn", "npc_thief_ren"],
                ),
                Location(
                    id="lowtown_safehouse",
                    name="Derelict Safehouse",
                    district_id="lowtown",
                    description="A boarded-up chandler's cellar with a bolted iron grate and a dry cot tucked out of sight of street patrols.",
                    connected_locations=["lowtown_alleys", "lowtown_tenements"],
                    terrain_features=["cellar_grate", "cover", "resting_cot"],
                    npcs_present=[],
                ),
                Location(
                    id="lowtown_watchpost",
                    name="Guard Watchpost",
                    district_id="lowtown",
                    description="A squat stone outpost reinforced with iron shutters, serving as Captain Voss's forward garrison in Lowtown.",
                    connected_locations=["lowtown_street", "lowtown_tenements"],
                    terrain_features=["stone_walls", "iron_gate", "notice_board"],
                    npcs_present=["npc_voss", "npc_merek"],
                ),
                Location(
                    id="lowtown_warehouse",
                    name="Abandoned Fish Warehouse",
                    district_id="lowtown",
                    description="A salt-crusted timber warehouse near the riverfront where Boss Malakor conducts Syndicate business behind locked doors.",
                    connected_locations=["lowtown_docks", "lowtown_alleys"],
                    terrain_features=["crates", "catwalks", "locked_office"],
                    npcs_present=["npc_boss_malakor"],
                ),
                Location(
                    id="lowtown_tenements",
                    name="Crowded Tenements",
                    district_id="lowtown",
                    description="Leaning multi-story wooden flats strung with laundry lines, packed with laborers and watchful neighbors.",
                    connected_locations=["lowtown_street", "lowtown_watchpost", "lowtown_safehouse"],
                    terrain_features=["stairwells", "balconies", "crowds"],
                    npcs_present=[],
                ),
                Location(
                    id="lowtown_street",
                    name="Lowtown Main Thoroughfare",
                    district_id="lowtown",
                    description="The mud-churned main artery of Lowtown, lit by sputtering oil lanterns and flanked by taverns, stalls, and Watch patrols.",
                    connected_locations=["lowtown_market", "lowtown_tavern", "lowtown_watchpost", "lowtown_tenements", "lowtown_alleys"],
                    terrain_features=["cobblestones", "lantern_posts", "crowds"],
                    npcs_present=[],
                ),
            ]
            for loc in lowtown_locations:
                world.add_location(loc)

    # 2. Seven Factions
    factions_data = [
        ("city_guard", "City Guard", "npc_vael", 70.0, 60.0, 80.0, 65.0, ["barracks", "lowtown"], ["npc_vael", "npc_voss", "npc_merek", "npc_captain_lyra"]),
        ("merchant_consortium", "Merchant Consortium", "npc_merchant_aldus", 90.0, 75.0, 40.0, 70.0, ["harbor"], ["npc_merchant_aldus", "npc_trader_brant"]),
        ("ashen_church", "Ashen Church", "npc_bishop_orlin", 65.0, 70.0, 50.0, 60.0, ["temple_district"], ["npc_bishop_orlin", "npc_curate_tess"]),
        ("lowtown_syndicate", "Lowtown Syndicate", "npc_boss_malakor", 55.0, 50.0, 65.0, 60.0, ["lowtown"], ["npc_boss_malakor", "npc_gang_karn", "npc_thief_ren"]),
        ("iron_workers_union", "Iron Workers' Union", "npc_gregor", 40.0, 45.0, 55.0, 55.0, ["iron_ward"], ["npc_gregor", "npc_smith_torvald"]),
        ("noble_houses", "Noble Houses", "npc_lord_vane", 95.0, 85.0, 50.0, 70.0, ["high_quarter"], ["npc_lord_vane", "npc_lady_isolde"]),
        ("independent_mages", "Independent Mages", "npc_archivist_selene", 50.0, 40.0, 60.0, 50.0, ["old_quarter"], ["npc_archivist_selene", "npc_sorcerer_kael"]),
    ]
    for fid, fname, leader, wealth, inf, mil, stab, terr, members in factions_data:
        world.factions[fid] = Faction(
            id=fid,
            name=fname,
            leader_id=leader,
            wealth=wealth,
            influence=inf,
            military_strength=mil,
            stability=stab,
            territories=terr,
            members=members,
            goals=[{"type": "maintain_influence", "target": terr[0]}],
            relations={},
        )

    # 3. Rowan (Player)
    rowan = Character(
        id="player",
        name="Rowan",
        age=28,
        faction_id=None,
        attributes={"strength": 75, "dexterity": 80, "agility": 75, "endurance": 70, "constitution": 70},
        skills={"swordsmanship": 75, "heavy_weapons": 80, "stealth": 60, "medicine": 40},
        personality={"courage": 80, "loyalty": 70, "compassion": 60, "ambition": 75},
        needs={"hunger": 90, "fatigue": 90, "safety": 80, "wealth": 150},
        location_id="lowtown_street",
        is_player=True,
    )
    rowan.body = create_humanoid_body("player")
    world.characters["player"] = rowan
    world.player = rowan
    world.player_party = ["player", "comp_marcus", "comp_sera"]

    # 4. Companions
    comps_data = [
        ("comp_marcus", "Marcus", 40, "city_guard", "tank", 45.0, 10.0, "Believes order matters more than freedom."),
        ("comp_elira", "Elira", 26, "independent_mages", "mage", 35.0, 15.0, "Believes magic should be unrestricted."),
        ("comp_sera", "Sera", 24, "lowtown_syndicate", "rogue", 50.0, 10.0, "Pragmatic, observant, distrustful survivor."),
        ("comp_tomas", "Tomas", 31, "ashen_church", "healer", 40.0, 5.0, "Compassionate temple physician."),
    ]
    for cid, cname, age, fac, role, f_val, r_val, arc in comps_data:
        c = Character(
            id=cid,
            name=cname,
            age=age,
            faction_id=fac,
            attributes={"strength": 70 if role == "tank" else 45, "agility": 80 if role == "rogue" else 50, "intelligence": 80 if role == "mage" else 50},
            skills={"medicine": 85 if role == "healer" else 30, "stealth": 85 if role == "rogue" else 20, "magic": 85 if role == "mage" else 10},
            personality={"loyalty": 70, "courage": 70},
            needs={"hunger": 85, "fatigue": 85, "safety": 85},
            location_id="lowtown_tavern",
            is_companion=True,
        )
        c.body = create_humanoid_body(cid)
        world.characters[cid] = c
        world.companions[cid] = Companion(
            character_id=cid,
            name=cname,
            role=role,
            friendship=f_val,
            rivalry=r_val,
            independent_activity=f"Resting at {c.location_id}",
        )

    # 5. Captain Garrick Voss & Sergeant Merek
    voss = Character(
        id="npc_voss",
        name="Captain Garrick Voss",
        age=38,
        faction_id="city_guard",
        rank="captain",
        personality={"ambition": 85, "courage": 45, "cruelty": 70, "loyalty": 30, "cunning": 65},
        attributes={"strength": 75, "agility": 45, "endurance": 60, "dexterity": 50},
        location_id="lowtown_watchpost",
        is_nemesis=True,
    )
    voss.body = create_humanoid_body("npc_voss")
    world.characters["npc_voss"] = voss
    world.nemesis_profiles["npc_voss"] = NemesisProfile(
        character_id="npc_voss",
        player_hostility=30.0,
        player_respect=40.0,
        encounter_count=1,
        known_player_tactics=[],
        grudges=[],
        career_history=[{"rank": "captain", "year": 1}],
        last_encounter_date=0,
        current_ambition="Become Commander of the City Guard",
        special_traits=["shield_defense", "counterattacks"],
        strengths=["shield_defense", "heavy_armor", "guard_support"],
        weaknesses=["fire", "poor_ranged_defense"],
        rank="captain",
        status="active",
    )

    merek = Character(
        id="npc_merek",
        name="Sergeant Merek",
        age=32,
        faction_id="city_guard",
        rank="sergeant",
        location_id="lowtown_watchpost",
    )
    merek.body = create_humanoid_body("npc_merek")
    world.characters["npc_merek"] = merek

    # 6. Additional Named NPCs (15+ total)
    named_npcs_data = [
        ("npc_vael", "Commander Vael", 58, "city_guard", "barracks"),
        ("npc_captain_lyra", "Captain Lyra", 34, "city_guard", "barracks"),
        ("npc_merchant_aldus", "Merchant Aldus", 52, "merchant_consortium", "harbor"),
        ("npc_trader_brant", "Trader Brant", 39, "merchant_consortium", "lowtown_market"),
        ("npc_bishop_orlin", "Bishop Orlin", 62, "ashen_church", "temple_district"),
        ("npc_curate_tess", "Curate Tess", 27, "ashen_church", "temple_district"),
        ("npc_boss_malakor", "Boss Malakor", 46, "lowtown_syndicate", "lowtown_warehouse"),
        ("npc_gang_karn", "Karn the Bruiser", 33, "lowtown_syndicate", "lowtown_alleys"),
        ("npc_thief_ren", "Ren the Shadow", 22, "lowtown_syndicate", "lowtown_alleys"),
        ("npc_gregor", "Gregor Smith", 48, "iron_workers_union", "iron_ward"),
        ("npc_smith_torvald", "Smith Torvald", 54, "iron_workers_union", "iron_ward"),
        ("npc_lord_vane", "Lord Cassian Vane", 60, "noble_houses", "high_quarter"),
        ("npc_lady_isolde", "Lady Isolde", 29, "noble_houses", "high_quarter"),
        ("npc_archivist_selene", "Archivist Selene", 44, "independent_mages", "old_quarter"),
        ("npc_sorcerer_kael", "Sorcerer Kael", 36, "independent_mages", "old_quarter"),
    ]
    for nid, nname, nage, nfac, nloc in named_npcs_data:
        npc_char = Character(id=nid, name=nname, age=nage, faction_id=nfac, location_id=nloc)
        npc_char.body = create_humanoid_body(nid)
        world.characters[nid] = npc_char

    # 7. Weapons (>= 10 across cutting, piercing, blunt, fire, poison, magic)
    weapons_data = [
        ("iron_longsword", "Iron Longsword", "cutting", 18.0, 6.0),
        ("steel_broadsword", "Steel Broadsword", "cutting", 24.0, 8.0),
        ("hunting_dagger", "Hunting Dagger", "piercing", 12.0, 10.0),
        ("military_spear", "Military Spear", "piercing", 20.0, 14.0),
        ("iron_mace", "Iron Mace", "blunt", 16.0, 12.0),
        ("warhammer", "Heavy Warhammer", "blunt", 28.0, 18.0),
        ("fire_torch", "Alchemist's Fire Torch", "fire", 22.0, 4.0),
        ("flame_blade", "Flame Blade", "fire", 26.0, 8.0),
        ("venom_stiletto", "Venom Stiletto", "poison", 15.0, 12.0),
        ("arcane_staff", "Arcane Staff", "magic", 25.0, 20.0),
        ("spellbook_spark", "Tome of Lightning", "magic", 22.0, 16.0),
    ]
    for wid, wname, dt, dmg, pen in weapons_data:
        world.items[wid] = Item(
            id=wid,
            name=wname,
            item_type="weapon",
            damage=dmg,
            damage_type=dt,
            penetration=pen,
            handling=1.0,
            value=dmg * 2.5,
        )

    # 8. Armor (>= 8 across padded_cloth, leather, chainmail, scale, plate)
    armors_data = [
        ("padded_gambeson", "Padded Gambeson", "padded_cloth", 5.0, ["torso"], ["piercing"]),
        ("padded_coif", "Padded Coif", "padded_cloth", 4.0, ["head"], ["piercing"]),
        ("leather_jerkin", "Leather Jerkin", "leather", 9.0, ["torso"], ["blunt"]),
        ("leather_boots", "Sturdy Leather Boots", "leather", 8.0, ["left_leg", "right_leg"], ["blunt"]),
        ("chainmail_hauberk", "Chainmail Hauberk", "chainmail", 15.0, ["torso", "left_arm", "right_arm"], ["blunt"]),
        ("scale_armor", "Scale Cuirass", "scale", 18.0, ["torso"], ["gaps_and_joints", "piercing"]),
        ("steel_helmet", "Steel Helmet", "plate", 18.0, ["head", "skull", "brain"], ["blunt"]),
        ("plate_breastplate", "Plate Breastplate", "plate", 25.0, ["torso", "ribs", "heart", "lungs"], ["blunt"]),
    ]
    for aid, aname, acls, prot, parts, wk in armors_data:
        world.items[aid] = Item(
            id=aid,
            name=aname,
            item_type="armor",
            armor_class=acls,
            armor_protection=prot,
            covered_parts=parts,
            weaknesses=wk,
            value=prot * 4.0,
        )

    # 9. Quests
    world.quests["quest_blood_in_lowtown"] = Quest(
        id="quest_blood_in_lowtown",
        title="Blood in Lowtown",
        description="A prominent merchant has been murdered in Lowtown. Captain Voss accuses the Syndicate.",
        quest_type="authored",
        status="active",
        objectives=[
            {"id": "investigate_crime_scene", "description": "Examine murder scene at Lowtown Market", "completed": False},
            {"id": "choose_faction_approach", "description": "Support the Guard, Syndicate, or investigate independently", "completed": False},
        ],
        involved_characters=["npc_voss", "comp_sera", "comp_marcus", "comp_elira"],
        involved_factions=["city_guard", "lowtown_syndicate"],
    )
    world.quests["quest_missing_apprentice"] = Quest(
        id="quest_missing_apprentice",
        title="The Missing Apprentice",
        description="Search for Joren the apprentice in Lowtown.",
        quest_type="hybrid",
        status="active",
        objectives=[
            {"id": "find_apprentice", "description": "Find Joren", "completed": False},
        ],
        involved_characters=["npc_gregor"],
    )

    return world


def load_all_content(world: Any = None) -> Any:
    if world is None:
        from core.world import World
        world = World(seed=482193)
    return populate_world(world)


def initialize_world_content(world: Any = None) -> Any:
    return load_all_content(world)
