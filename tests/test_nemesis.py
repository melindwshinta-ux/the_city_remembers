"""Nemesis system unit tests (GDD Section 7 & 12)."""

import pytest
from entities.character import Character
from entities.enemy import NemesisProfile
from systems.nemesis_system import NemesisSystem


def test_nemesis_eligibility():
    nem_sys = NemesisSystem()
    c = Character(id="c1", name="Enemy", age=30)
    profile = nem_sys.evaluate_eligibility(c, "survives_encounter")
    assert c.is_nemesis is True
    assert profile.character_id == "c1"


def test_nemesis_adaptation():
    nem_sys = NemesisSystem()
    profile = NemesisProfile(character_id="c1")
    nem_sys.record_witnessed_tactic(profile, "fire_magic", witnessed=True)
    adaptations = nem_sys.adapt_to_player(profile)
    assert "fire_resistant_equipment" in adaptations
