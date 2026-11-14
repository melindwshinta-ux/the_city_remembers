"""Campaign timeline and WorldClock implementation (GDD Section 2)."""

from __future__ import annotations

import random
from typing import Any

from config import (
    ACT_I,
    ACT_II,
    ACT_III,
    ACT_PROLOGUE,
    ACT_THEMES,
    ACTION_DURATION_RANGES,
    DAYS_PER_MONTH,
    DAYS_PER_WEEK,
    DEFAULT_ACTION_DURATIONS,
    DEFAULT_START_HOUR,
    MINUTES_PER_DAY,
    MINUTES_PER_HOUR,
    MINUTES_PER_MONTH,
    MINUTES_PER_WEEK,
    MINUTES_PER_YEAR,
)


class WorldClock:
    """Tracks campaign time in minutes across Hours, Days, Weeks, Months, Years, and Acts."""

    def __init__(
        self,
        timestamp: int = 0,
        start_hour: int = DEFAULT_START_HOUR,
        prologue_completed: bool = False,
        act_override: str | None = None,
    ) -> None:
        if timestamp < 0:
            raise ValueError("Initial timestamp cannot be negative")
        self.timestamp: int = int(timestamp)
        self.start_hour: int = int(start_hour)
        self.prologue_completed: bool = bool(prologue_completed)
        self._act_override: str | None = act_override

    @property
    def total_minutes(self) -> int:
        """Alias for timestamp (total elapsed minutes since start of campaign)."""
        return self.timestamp

    @total_minutes.setter
    def total_minutes(self, value: int) -> None:
        if value < 0:
            raise ValueError("total_minutes cannot be negative")
        self.timestamp = int(value)

    @property
    def calendar_minutes(self) -> int:
        """Total minutes including the initial start-of-day wall-clock offset."""
        return self.timestamp + (self.start_hour * MINUTES_PER_HOUR)

    @property
    def year(self) -> int:
        """Current campaign year (1-indexed: Year 1, Year 2, ...)."""
        return (self.calendar_minutes // MINUTES_PER_YEAR) + 1

    @property
    def day_of_year(self) -> int:
        """Current day within the current year (1..360)."""
        return ((self.calendar_minutes % MINUTES_PER_YEAR) // MINUTES_PER_DAY) + 1

    @property
    def total_days(self) -> int:
        """Total campaign days elapsed (1-indexed)."""
        return (self.calendar_minutes // MINUTES_PER_DAY) + 1

    @property
    def month(self) -> int:
        """Current month within the current year (1..12)."""
        return ((self.day_of_year - 1) // DAYS_PER_MONTH) + 1

    @property
    def week(self) -> int:
        """Current week within the current year (1..52)."""
        return ((self.day_of_year - 1) // DAYS_PER_WEEK) + 1

    @property
    def total_weeks(self) -> int:
        """Total campaign weeks elapsed (1-indexed)."""
        return (self.calendar_minutes // MINUTES_PER_WEEK) + 1

    @property
    def day(self) -> int:
        """Current day of the month (1..30)."""
        return ((self.day_of_year - 1) % DAYS_PER_MONTH) + 1

    @property
    def hour(self) -> int:
        """Current hour of the day (0..23)."""
        return (self.calendar_minutes % MINUTES_PER_DAY) // MINUTES_PER_HOUR

    @property
    def minute(self) -> int:
        """Current minute of the hour (0..59)."""
        return self.calendar_minutes % MINUTES_PER_HOUR

    @staticmethod
    def get_act_for_year(
        year: int,
        prologue_completed: bool = True,
        day_of_year: int = 31,
    ) -> str:
        """Map a campaign year to its canonical Act name (GDD Section 2)."""
        if year <= 1 and not prologue_completed and day_of_year <= DAYS_PER_MONTH:
            return ACT_PROLOGUE
        if year <= 3:
            return ACT_I
        if year <= 6:
            return ACT_II
        return ACT_III

    @property
    def act(self) -> str:
        """Current campaign Act: Prologue (Y1), Act I (Y1-3), Act II (Y4-6), Act III (Y7-10)."""
        if self._act_override is not None:
            # Automatically advance override if time progresses into a later Act's year range
            if self._act_override == ACT_PROLOGUE and (self.year > 1 or self.prologue_completed):
                self._act_override = None
            elif self._act_override == ACT_I and self.year >= 4:
                self._act_override = None
            elif self._act_override == ACT_II and self.year >= 7:
                self._act_override = None
            else:
                return self._act_override
        return self.get_act_for_year(
            self.year,
            prologue_completed=self.prologue_completed,
            day_of_year=self.day_of_year,
        )

    @property
    def act_theme(self) -> str:
        """Theme string for the current Act."""
        return ACT_THEMES.get(self.act, "")

    def complete_prologue(self) -> None:
        """Transition from Prologue (Year 1 arrival) into Act I (Years 1-3)."""
        self.prologue_completed = True
        if self._act_override == ACT_PROLOGUE:
            self._act_override = None

    def set_act(self, act_name: str) -> None:
        """Explicitly set the active campaign Act."""
        if act_name not in ACT_THEMES:
            raise ValueError(f"Unknown act: {act_name}")
        if act_name != ACT_PROLOGUE:
            self.prologue_completed = True
        else:
            self.prologue_completed = False
        self._act_override = act_name

    def advance(self, minutes: int) -> list[str]:
        """Advance clock by `minutes` and return list of crossed frequency thresholds.

        Possible threshold tags returned in deterministic order:
        `["action", "time_update", "6h", "daily", "weekly", "monthly", "yearly"]`.
        """
        if minutes < 0:
            raise ValueError("Cannot advance clock by negative minutes")
        minutes = int(minutes)
        if minutes == 0:
            return ["action"]

        old_cal = self.calendar_minutes
        self.timestamp += minutes
        new_cal = self.calendar_minutes

        # Auto-complete Prologue after first month of Year 1
        if not self.prologue_completed and (self.year > 1 or self.day_of_year > DAYS_PER_MONTH):
            self.prologue_completed = True

        crossed: list[str] = ["action", "time_update"]
        if (new_cal // 360) > (old_cal // 360):
            crossed.append("6h")
        if (new_cal // MINUTES_PER_DAY) > (old_cal // MINUTES_PER_DAY):
            crossed.append("daily")
        if (new_cal // MINUTES_PER_WEEK) > (old_cal // MINUTES_PER_WEEK):
            crossed.append("weekly")
        if (new_cal // MINUTES_PER_MONTH) > (old_cal // MINUTES_PER_MONTH):
            crossed.append("monthly")
        if (new_cal // MINUTES_PER_YEAR) > (old_cal // MINUTES_PER_YEAR):
            crossed.append("yearly")
        return crossed

    def advance_hours(self, hours: int) -> list[str]:
        """Advance clock by a given number of hours."""
        return self.advance(int(hours) * MINUTES_PER_HOUR)

    def advance_days(self, days: int) -> list[str]:
        """Advance clock by a given number of days."""
        return self.advance(int(days) * MINUTES_PER_DAY)

    def advance_weeks(self, weeks: int) -> list[str]:
        """Advance clock by a given number of weeks."""
        return self.advance(int(weeks) * MINUTES_PER_WEEK)

    def advance_years(self, years: int) -> list[str]:
        """Advance clock by a given number of years."""
        return self.advance(int(years) * MINUTES_PER_YEAR)

    @staticmethod
    def get_action_duration(
        action_category: str,
        rng: random.Random | None = None,
    ) -> int:
        """Return duration in minutes for standard GDD Section 2 action categories."""
        if action_category not in ACTION_DURATION_RANGES:
            raise ValueError(f"Unknown action category: {action_category}")
        if rng is not None:
            low, high = ACTION_DURATION_RANGES[action_category]
            return rng.randint(low, high)
        return DEFAULT_ACTION_DURATIONS[action_category]

    @staticmethod
    def calculate_travel_duration(
        distance: int = 1,
        condition_modifier: float = 1.0,
        leg_injury_penalty: float = 0.0,
    ) -> int:
        """Calculate travel duration in minutes from distance, conditions, and leg injuries."""
        if distance < 0:
            raise ValueError("Travel distance cannot be negative")
        if distance == 0:
            return 1
        raw = 10.0 * float(distance) * max(0.1, float(condition_modifier)) * (1.0 + max(0.0, float(leg_injury_penalty)))
        return max(1, int(round(raw)))

    def format_date(self) -> str:
        """Return human-readable campaign date/time string."""
        return (
            f"Year {self.year}, Month {self.month}, Day {self.day:02d} "
            f"{self.hour:02d}:{self.minute:02d} ({self.act})"
        )

    def format_datetime(self) -> str:
        return self.format_date()

    def format_time(self) -> str:
        return self.format_date()

    def __str__(self) -> str:
        return self.format_date()

    def to_dict(self) -> dict[str, Any]:
        """Serialize clock state to plain dictionary."""
        return {
            "timestamp": self.timestamp,
            "start_hour": self.start_hour,
            "prologue_completed": self.prologue_completed,
            "act_override": self._act_override,
            "year": self.year,
            "month": self.month,
            "week": self.week,
            "day": self.day,
            "day_of_year": self.day_of_year,
            "hour": self.hour,
            "minute": self.minute,
            "act": self.act,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorldClock:
        """Reconstruct WorldClock from dictionary."""
        return cls(
            timestamp=int(data.get("timestamp", data.get("total_minutes", 0))),
            start_hour=int(data.get("start_hour", DEFAULT_START_HOUR)),
            prologue_completed=bool(data.get("prologue_completed", False)),
            act_override=data.get("act_override"),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WorldClock):
            return NotImplemented
        return (
            self.timestamp == other.timestamp
            and self.start_hour == other.start_hour
            and self.prologue_completed == other.prologue_completed
            and self.act == other.act
        )
