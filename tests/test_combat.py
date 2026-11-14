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
