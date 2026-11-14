"""Health and anatomy system unit tests (GDD Section 5 & 12)."""

import pytest
from entities.character import Character
from systems.health_system import HealthSystem


def test_health_anatomy_initialization():
    health_sys = HealthSystem()
    c = Character(id="c1", name="Test", age=25)
    health_sys.initialize_body(c)
    assert len(c.body) >= 29
    assert "skull" in c.body
    assert "heart" in c.body


def test_health_apply_injury_and_modifiers():
    health_sys = HealthSystem()
    c = Character(id="c1", name="Test", age=25)
    health_sys.initialize_body(c)
    health_sys.apply_injury(c, "left_arm", "broken_arm", severity=0.8)
    mods = health_sys.get_combat_modifiers(c)
    assert mods["weapon_handling"] < 1.0


def test_health_treatment_stages():
    health_sys = HealthSystem()
    c = Character(id="c1", name="Patient", age=30)
    health_sys.initialize_body(c)
    health_sys.apply_injury(c, "torso", "deep_cut", severity=0.7)
    assert c.body["torso"].injuries[0].bleeding > 0.0

    health_sys.apply_treatment(c, "first_aid")
    assert c.body["torso"].injuries[0].bleeding == 0.0
