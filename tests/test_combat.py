"""Combat system unit tests (GDD Section 6 & 12)."""

import pytest
from entities.character import Character
from entities.item import Item
from systems.combat_system import CombatSystem
from systems.health_system import HealthSystem


def test_combat_attack_resolution():
    combat_sys = CombatSystem()
    health_sys = HealthSystem()
    attacker = Character(id="p1", name="Player", age=25)
    target = Character(id="t1", name="Target", age=30)
    health_sys.initialize_body(target)

    sword = Item(id="sword", name="Sword", item_type="weapon", damage=20.0, damage_type="cutting")
    res = combat_sys.resolve_attack(attacker, target, sword, target_part="torso", force_hit=True)
    assert res["hit"] is True
    assert res["effective_damage"] > 0
    assert target.body["torso"].integrity < 100.0


def test_combat_initiative_ordering():
    combat_sys = CombatSystem()
    c1 = Character(id="slow", name="Slow Guard", age=40, attributes={"agility": 30})
    c2 = Character(id="fast", name="Fast Rogue", age=20, attributes={"agility": 80})
    order = combat_sys.get_initiative_order([c1, c2])
    assert order[0].id == "fast"


def test_combat_morale_states():
    combat_sys = CombatSystem()
    c = Character(id="c1", name="Fighter", age=28)
    assert combat_sys.evaluate_morale_state(c, morale_value=90.0) == "confident"
    assert combat_sys.evaluate_morale_state(c, morale_value=5.0) == "routing"


def test_resolve_attack_propagates_consciousness_morale_and_ko():
    from content import populate_world
    from core.world import World

    w = World(seed=101)
    populate_world(w)
    cs = CombatSystem(event_bus=w.event_bus, clock=w.clock, rng=w.rng, world=w)
    player = w.characters["player"]
    enemy = Character(id="thug", name="Alley Thug", age=29)
    HealthSystem().initialize_body(enemy)
    sword = Item(id="sword", name="Sword", item_type="weapon", damage=20.0, damage_type="cutting", penetration=6.0)

    res1 = cs.resolve_attack(player, enemy, sword, target_part="torso", force_hit=True)
    assert res1["hit"] is True
    assert enemy.consciousness < 100.0
    assert enemy.morale < 75.0
    assert res1["defender_consciousness"] == enemy.consciousness

    # God mode shields player from damage, consciousness loss, and wounds
    w.flags["god_mode"] = True
    res_god = cs.resolve_attack(enemy, player, sword, target_part="torso", force_hit=True)
    assert res_god["effective_damage"] == 0.0
    assert player.consciousness == 100.0
    assert player.body["torso"].integrity == 100.0
    assert len(player.body["torso"].injuries) == 0


def test_clash_turn_returns_turn_log_and_respects_difficulty():
    from content import populate_world
    from core.world import World

    w_story = World(seed=202)
    populate_world(w_story)
    w_story.flags["difficulty"] = "story"
    cs_story = CombatSystem(event_bus=w_story.event_bus, clock=w_story.clock, rng=w_story.rng, world=w_story)
    e_story = Character(id="bandit_s", name="Bandit")
    HealthSystem().initialize_body(e_story)
    s_story = cs_story.start_clash_session(party=[w_story.player], enemies=[e_story], world=w_story)
    r_story = cs_story.resolve_clash_turn(s_story, "1", world=w_story)

    w_gritty = World(seed=202)
    populate_world(w_gritty)
    w_gritty.flags["difficulty"] = "gritty"
    cs_gritty = CombatSystem(event_bus=w_gritty.event_bus, clock=w_gritty.clock, rng=w_gritty.rng, world=w_gritty)
    e_gritty = Character(id="bandit_g", name="Bandit")
    HealthSystem().initialize_body(e_gritty)
    s_gritty = cs_gritty.start_clash_session(party=[w_gritty.player], enemies=[e_gritty], world=w_gritty)
    r_gritty = cs_gritty.resolve_clash_turn(s_gritty, "1", world=w_gritty)

    assert len(r_story["turn_log"]) >= 2
    assert r_story["player_action"]["effective_damage"] > r_gritty["player_action"]["effective_damage"]
    assert w_gritty.player.consciousness < w_story.player.consciousness
