"""Relationship system unit tests (GDD Section 4 & 12)."""

import pytest
from systems.relationship_system import RelationshipSystem


def test_relationship_directional_asymmetry():
    rel_sys = RelationshipSystem()
    rel_sys.set_relationship("a", "b", trust=70.0, respect=80.0)
    rel_sys.set_relationship("b", "a", trust=20.0, respect=40.0)

    ab = rel_sys.get_relationship("a", "b")
    ba = rel_sys.get_relationship("b", "a")
    assert ab.trust == 70.0
    assert ba.trust == 20.0


def test_relationship_state_derivation():
    rel_sys = RelationshipSystem()
    rel = rel_sys.set_relationship(
        "a", "b",
        trust=70.0,
        respect=85.0,
        affection=45.0,
        resentment=10.0,
        fear=0.0,
        dependency=30.0,
    )
    assert rel.relationship_state == "Loyal associate"
