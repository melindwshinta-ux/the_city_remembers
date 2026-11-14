"""Global configuration, calendar constants, simulation frequencies, and canonical events."""

from __future__ import annotations

from pathlib import Path

# --- Paths ---
ROOT_DIR: Path = Path(__file__).resolve().parent
CONTENT_DIR: Path = ROOT_DIR / "content"
SAVES_DIR: Path = ROOT_DIR / "saves"
DEFAULT_DB_PATH: Path = SAVES_DIR / "veyr_save.db"

# --- Default Seed (GDD Section 14, Line 656) ---
DEFAULT_WORLD_SEED: int = 482193

# --- RNG Stream Names (GDD Section 14, Line 657 & PROJECT.md F4) ---
RNG_STREAMS: tuple[str, ...] = (
    "world",
    "combat",
    "nemesis",
    "faction",
    "character",
    "health",
    "memory",
    "quest",
    "rumor",
    "economy",
    "ai",
)

# --- Calendar & Time Constants (GDD Section 2, Lines 89-99) ---
MINUTES_PER_HOUR: int = 60
HOURS_PER_DAY: int = 24
MINUTES_PER_DAY: int = MINUTES_PER_HOUR * HOURS_PER_DAY          # 1,440
DAYS_PER_WEEK: int = 7
MINUTES_PER_WEEK: int = MINUTES_PER_DAY * DAYS_PER_WEEK           # 10,080
DAYS_PER_MONTH: int = 30
MINUTES_PER_MONTH: int = MINUTES_PER_DAY * DAYS_PER_MONTH         # 43,200
MONTHS_PER_YEAR: int = 12
DAYS_PER_YEAR: int = DAYS_PER_MONTH * MONTHS_PER_YEAR             # 360
MINUTES_PER_YEAR: int = MINUTES_PER_DAY * DAYS_PER_YEAR           # 518,400

DEFAULT_START_HOUR: int = 8  # Year 1, Day 1, 08:00

# --- Campaign Timeline & Acts (GDD Section 2, Lines 90-94) ---
ACT_PROLOGUE: str = "Prologue"
ACT_I: str = "Act I"
ACT_II: str = "Act II"
ACT_III: str = "Act III"

ACT_THEMES: dict[str, str] = {
    ACT_PROLOGUE: "Arrival and survival",
    ACT_I: "Establishing yourself",
    ACT_II: "Political escalation",
    ACT_III: "Consequences and collapse",
}

ACT_YEAR_RANGES: dict[str, tuple[int, int]] = {
    ACT_PROLOGUE: (1, 1),
    ACT_I: (1, 3),
    ACT_II: (4, 6),
    ACT_III: (7, 10),
}

# --- Standard Action Durations in Minutes (GDD Section 2, Lines 95-97) ---
ACTION_DURATION_RANGES: dict[str, tuple[int, int]] = {
    "small_action": (1, 10),        # 1-10 minutes
    "conversation": (5, 30),        # 5-30 minutes
    "talk": (5, 30),                # alias for conversation
    "combat": (1, 5),               # 1-5 minutes of world time
    "travel": (10, 45),             # calculated by distance and conditions
    "rest": (360, 720),             # 6-12 hours (360-720 minutes)
    "major_project": (1440, 20160), # days or weeks (1-14 days)
    "project": (1440, 20160),       # alias for major_project
}

DEFAULT_ACTION_DURATIONS: dict[str, int] = {
    "small_action": 5,
    "conversation": 15,
    "talk": 15,
    "combat": 3,
    "travel": 15,
    "rest": 480,           # 8 hours default
    "major_project": 1440, # 1 day default
    "project": 1440,
}

# --- Simulation Frequencies & Sub-Stepping (GDD Section 14, Lines 647-655) ---
MAX_SUBSTEP_MINUTES: int = 360  # 6 hours maximum sub-step chunk

FREQ_COMBAT: str = "combat"                     # Every action in combat
FREQ_COMPANIONS: str = "companions"             # Every meaningful action or time update
FREQ_NEARBY_NPCS: str = "nearby_npcs"           # Every time update
FREQ_FACTION_DECISIONS: str = "factions"        # Every 6-24 hours (360-1440 mins)
FREQ_ECONOMY: str = "economy"                   # Daily (1440 mins)
FREQ_DISTRICT_POPULATION: str = "district_pop"  # Weekly (10080 mins)
FREQ_LONG_TERM_AMBITIONS: str = "ambitions"     # Weekly or monthly (10080 / 43200 mins)

SIMULATION_FREQUENCIES: tuple[str, ...] = (
    FREQ_COMBAT,
    FREQ_COMPANIONS,
    FREQ_NEARBY_NPCS,
    FREQ_FACTION_DECISIONS,
    FREQ_ECONOMY,
    FREQ_DISTRICT_POPULATION,
    FREQ_LONG_TERM_AMBITIONS,
)

FREQUENCY_INTERVAL_MINUTES: dict[str, int] = {
    FREQ_COMBAT: 0,                        # Triggered per action
    FREQ_COMPANIONS: 1,                    # Triggered on meaningful action or >=1m time update
    FREQ_NEARBY_NPCS: 1,                   # Triggered on every time update
    FREQ_FACTION_DECISIONS: 360,           # Every 6 hours (6-24h window)
    FREQ_ECONOMY: MINUTES_PER_DAY,         # Every 24 hours (1440m)
    FREQ_DISTRICT_POPULATION: MINUTES_PER_WEEK,  # Every 7 days (10080m)
    FREQ_LONG_TERM_AMBITIONS: MINUTES_PER_WEEK,  # Every 7 days (weekly/monthly)
}

# --- Event Priorities (GDD Section 14, Lines 642-646) ---
PRIORITY_CRITICAL: str = "critical"
PRIORITY_NORMAL: str = "normal"
PRIORITY_BACKGROUND: str = "background"

MAX_EVENT_CONSEQUENCE_DEPTH: int = 10

# --- Canonical Event Types (PROJECT.md Interface Contract 1) ---
# Combat & Health
EVENT_ATTACK_RESOLVED: str = "ATTACK_RESOLVED"
EVENT_CHARACTER_INJURED: str = "CHARACTER_INJURED"
EVENT_LIMB_INJURED: str = "LIMB_INJURED"
EVENT_CHARACTER_INCAPACITATED: str = "CHARACTER_INCAPACITATED"
EVENT_CHARACTER_DIED: str = "CHARACTER_DIED"
EVENT_SURGERY_COMPLETED: str = "SURGERY_COMPLETED"
EVENT_PROSTHETIC_FITTED: str = "PROSTHETIC_FITTED"
EVENT_COMBAT_STARTED: str = "COMBAT_STARTED"
EVENT_COMBAT_ENDED: str = "COMBAT_ENDED"
EVENT_PLAYER_DEFEATED: str = "PLAYER_DEFEATED"

# Memory & Social
EVENT_MEMORY_CREATED: str = "MEMORY_CREATED"
EVENT_RELATIONSHIP_CHANGED: str = "RELATIONSHIP_CHANGED"
EVENT_COMPANION_APPROVAL_CHANGED: str = "COMPANION_APPROVAL_CHANGED"
EVENT_COMPANION_BREAKING_POINT: str = "COMPANION_BREAKING_POINT"
EVENT_RUMOR_SPREAD: str = "RUMOR_SPREAD"
EVENT_RUMOR_PLANTED: str = "RUMOR_PLANTED"

# Nemesis & Faction
EVENT_NEMESIS_CREATED: str = "NEMESIS_CREATED"
EVENT_NEMESIS_PROMOTED: str = "NEMESIS_PROMOTED"
EVENT_NEMESIS_ADAPTED: str = "NEMESIS_ADAPTED"
EVENT_NEMESIS_DEFEATED: str = "NEMESIS_DEFEATED"
EVENT_FACTION_ACTION_TAKEN: str = "FACTION_ACTION_TAKEN"
EVENT_LEADERSHIP_VACANCY: str = "LEADERSHIP_VACANCY"
EVENT_RIVAL_PROMOTED: str = "RIVAL_PROMOTED"
EVENT_DISTRICT_INFLUENCE_CHANGED: str = "DISTRICT_INFLUENCE_CHANGED"
EVENT_POLITICAL_CONFLICT_STARTED: str = "POLITICAL_CONFLICT_STARTED"

# World & Quests
EVENT_TIME_ADVANCED: str = "TIME_ADVANCED"
EVENT_QUEST_STARTED: str = "QUEST_STARTED"
EVENT_QUEST_UPDATED: str = "QUEST_UPDATED"
EVENT_QUEST_COMPLETED: str = "QUEST_COMPLETED"
EVENT_CRIME_COMMITTED: str = "CRIME_COMMITTED"
EVENT_PLAYER_ARRESTED: str = "PLAYER_ARRESTED"
EVENT_TIME_EVENT_TRIGGERED: str = "TIME_EVENT_TRIGGERED"
EVENT_ECONOMY_UPDATED: str = "ECONOMY_UPDATED"

CANONICAL_EVENT_TYPES: tuple[str, ...] = (
    EVENT_ATTACK_RESOLVED,
    EVENT_CHARACTER_INJURED,
    EVENT_LIMB_INJURED,
    EVENT_CHARACTER_INCAPACITATED,
    EVENT_CHARACTER_DIED,
    EVENT_SURGERY_COMPLETED,
    EVENT_PROSTHETIC_FITTED,
    EVENT_COMBAT_STARTED,
    EVENT_COMBAT_ENDED,
    EVENT_PLAYER_DEFEATED,
    EVENT_MEMORY_CREATED,
    EVENT_RELATIONSHIP_CHANGED,
    EVENT_COMPANION_APPROVAL_CHANGED,
    EVENT_COMPANION_BREAKING_POINT,
    EVENT_RUMOR_SPREAD,
    EVENT_RUMOR_PLANTED,
    EVENT_NEMESIS_CREATED,
    EVENT_NEMESIS_PROMOTED,
    EVENT_NEMESIS_ADAPTED,
    EVENT_NEMESIS_DEFEATED,
    EVENT_FACTION_ACTION_TAKEN,
    EVENT_LEADERSHIP_VACANCY,
    EVENT_RIVAL_PROMOTED,
    EVENT_DISTRICT_INFLUENCE_CHANGED,
    EVENT_POLITICAL_CONFLICT_STARTED,
    EVENT_TIME_ADVANCED,
    EVENT_QUEST_STARTED,
    EVENT_QUEST_UPDATED,
    EVENT_QUEST_COMPLETED,
    EVENT_CRIME_COMMITTED,
    EVENT_PLAYER_ARRESTED,
    EVENT_TIME_EVENT_TRIGGERED,
    EVENT_ECONOMY_UPDATED,
)

CRITICAL_EVENT_TYPES: frozenset[str] = frozenset({
    EVENT_ATTACK_RESOLVED,
    EVENT_CHARACTER_INJURED,
    EVENT_LIMB_INJURED,
    EVENT_CHARACTER_INCAPACITATED,
    EVENT_CHARACTER_DIED,
    EVENT_COMBAT_STARTED,
    EVENT_COMBAT_ENDED,
    EVENT_PLAYER_DEFEATED,
})

BACKGROUND_EVENT_TYPES: frozenset[str] = frozenset({
    EVENT_ECONOMY_UPDATED,
})
