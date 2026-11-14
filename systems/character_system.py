"""Character simulation system: tiers, attributes, skills, personality, needs, and aging (GDD Sections 4 & 13)."""

from __future__ import annotations

import copy
from typing import Any

from core.clock import WorldClock
from core.event_bus import EventBus, EventPriority, GameEvent
from core.random_generator import SeededRNG
from entities.character import Character


ALL_ATTRIBUTES = {
    # Physical
    "strength": 50.0,
    "dexterity": 50.0,
    "endurance": 50.0,
    "agility": 50.0,
    "constitution": 50.0,
    # Mental
    "intelligence": 50.0,
    "perception": 50.0,
    "willpower": 50.0,
    "discipline": 50.0,
    "creativity": 50.0,
    # Social
    "persuasion": 50.0,
    "deception": 50.0,
    "intimidation": 50.0,
    "empathy": 50.0,
    "leadership": 50.0,
}

ALL_PERSONALITY_TRAITS = {
    "courage": 50.0,
    "greed": 30.0,
    "compassion": 50.0,
    "ambition": 50.0,
    "loyalty": 60.0,
    "aggression": 40.0,
    "patience": 50.0,
}

ALL_NEEDS = {
    "hunger": 100.0,  # 100 = satisfied, 0 = starving
    "fatigue": 100.0, # 100 = well-rested, 0 = exhausted
    "safety": 100.0,  # 100 = safe, 0 = in mortal terror
    "social": 80.0,   # 100 = socially fulfilled, 0 = isolated
    "social_interaction": 80.0,
    "wealth": 50.0,
    "purpose": 70.0,
}

ALL_SKILLS = {
    "swordsmanship": 30.0,
    "archery": 20.0,
    "heavy_weapons": 20.0,
    "dual_wielding": 20.0,
    "shield_combat": 25.0,
    "magic": 10.0,
    "stealth": 25.0,
    "medicine": 20.0,
    "crafting": 20.0,
    "negotiation": 30.0,
}


class CharacterSystem:
    """Manages 3-tier character simulation, needs decay, and attributes (GDD Section 4)."""

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

    def initialize_character(self, character: Character) -> Character:
        """Populate default attributes, skills, personality, and needs on character."""
        return self.ensure_character_stats(character)

    def populate_defaults(self, character: Character) -> Character:
        return self.ensure_character_stats(character)

    def register_character(self, character: Character) -> Character:
        return self.ensure_character_stats(character)

    def ensure_character_stats(self, character: Character) -> Character:
        """Ensure all GDD Section 4 categories are present on Character."""
        # Attributes
        if not character.attributes:
            character.attributes = copy.deepcopy(ALL_ATTRIBUTES)
        else:
            for k, v in ALL_ATTRIBUTES.items():
                if k not in character.attributes:
                    character.attributes[k] = v

        # Skills
        if not character.skills:
            character.skills = copy.deepcopy(ALL_SKILLS)
        else:
            for k, v in ALL_SKILLS.items():
                if k not in character.skills:
                    character.skills[k] = v

        # Personality
        if not character.personality:
            character.personality = copy.deepcopy(ALL_PERSONALITY_TRAITS)
        else:
            for k, v in ALL_PERSONALITY_TRAITS.items():
                if k not in character.personality:
                    character.personality[k] = v

        # Needs
        if not character.needs:
            character.needs = copy.deepcopy(ALL_NEEDS)
        else:
            for k, v in ALL_NEEDS.items():
                if k not in character.needs:
                    character.needs[k] = v
        # Ensure social and social_interaction match
        if "social" in character.needs and "social_interaction" not in character.needs:
            character.needs["social_interaction"] = character.needs["social"]
        elif "social_interaction" in character.needs and "social" not in character.needs:
            character.needs["social"] = character.needs["social_interaction"]

        # Ensure tier
        if not hasattr(character, "tier") or character.tier is None:
            if character.is_player or character.is_companion or character.is_nemesis:
                character.tier = 1
            else:
                character.tier = 2

        return character

    def decay_needs(self, character: Character, minutes: int) -> None:
        """Decay character needs over elapsed minutes."""
        self.ensure_character_stats(character)
        hours = minutes / 60.0

        # Hunger decays ~ 2.0 per hour
        hunger_decay = hours * 2.0
        character.needs["hunger"] = max(0.0, character.needs.get("hunger", 100.0) - hunger_decay)

        # Fatigue decays ~ 2.5 per hour
        fatigue_decay = hours * 2.5
        character.needs["fatigue"] = max(0.0, character.needs.get("fatigue", 100.0) - fatigue_decay)

        # Social decays ~ 1.0 per hour
        social_decay = hours * 1.0
        val = max(0.0, character.needs.get("social", 80.0) - social_decay)
        character.needs["social"] = val
        character.needs["social_interaction"] = val

    def update_needs(self, character: Character, minutes: int) -> None:
        self.decay_needs(character, minutes)

    def simulate_characters(self, world: Any, minutes: int) -> None:
        """Simulate all characters across 3 tiers for elapsed minutes."""
        for char in list(world.characters.values()):
            self.ensure_character_stats(char)
            # Tier 1: Full simulation of needs and personal traits
            if getattr(char, "tier", 1) == 1:
                self.decay_needs(char, minutes)
            # Tier 2: Basic needs update
            elif getattr(char, "tier", 2) == 2:
                # Mild decay
                if "hunger" in char.needs:
                    char.needs["hunger"] = max(10.0, char.needs["hunger"] - (minutes / 60.0) * 1.0)
            # Tier 3: Aggregate / no detailed needs decay

    def update(self, world_or_char: Any, minutes: int = 60) -> None:
        if isinstance(world_or_char, Character):
            self.decay_needs(world_or_char, minutes)
        elif hasattr(world_or_char, "characters"):
            self.simulate_characters(world_or_char, minutes)

    def process_yearly_aging(self, character: Character, years: int = 1) -> int:
        """Increment age and check retirement threshold (GDD Section 4 & 11)."""
        character.age += int(years)
        if character.age >= 65 and not getattr(character, "is_player", False):
            character.status = "retired"
            character.retired = True
        return character.age

    def age_character(self, character: Character, years: int = 1) -> int:
        return self.process_yearly_aging(character, years)

    def advance_age(self, character: Character, years: int = 1) -> int:
        return self.process_yearly_aging(character, years)

    def get_effective_attributes(self, character: Character) -> dict[str, float]:
        """Compute effective attributes clamped >= 0 without mutating base attributes."""
        self.ensure_character_stats(character)
        effective = {}
        for k, v in character.attributes.items():
            effective[k] = max(0.0, float(v))
        return effective

    def derive_stats(self, character: Character) -> dict[str, float]:
        return self.get_effective_attributes(character)

    def compute_effective_stats(self, character: Character) -> dict[str, float]:
        return self.get_effective_attributes(character)

    def update_district_population(self, world: Any, minutes: int = 10080) -> None:
        """Simulate aggregate Tier 3 district population (GDD Section 4)."""
        if not hasattr(world, "districts"):
            return
        for dist in world.districts.values():
            dist.population = max(0, int(getattr(dist, "population", 0)))

    def simulate_tier3_population(self, world: Any, minutes: int = 10080) -> None:
        self.update_district_population(world, minutes)
