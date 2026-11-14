"""Three-stage priority EventBus and GameEvent model (GDD Sections 13 & 14)."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from config import (
    BACKGROUND_EVENT_TYPES,
    CRITICAL_EVENT_TYPES,
    MAX_EVENT_CONSEQUENCE_DEPTH,
    PRIORITY_BACKGROUND,
    PRIORITY_CRITICAL,
    PRIORITY_NORMAL,
)


class EventPriority(str, Enum):
    """Event priority tiers (GDD Section 14)."""

    CRITICAL = PRIORITY_CRITICAL      # Death, combat, major injuries -> Immediately
    NORMAL = PRIORITY_NORMAL          # Memories, relationships, quests -> Current simulation tick
    BACKGROUND = PRIORITY_BACKGROUND  # Economy, population, distant NPCs -> Scheduled update


@dataclass
class GameEvent:
    """Structured simulation event matching GDD Section 13 (lines 589-612)."""

    id: str
    event_type: str
    timestamp: int
    source_id: str | None = None
    target_ids: list[str] = field(default_factory=list)
    location_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5
    priority: str = PRIORITY_NORMAL

    def __post_init__(self) -> None:
        if isinstance(self.priority, Enum):
            self.priority = str(self.priority.value)
        else:
            self.priority = str(self.priority).lower()
        self.timestamp = int(self.timestamp)
        self.importance = float(self.importance)
        self.target_ids = [str(t) for t in self.target_ids]
        self.data = dict(self.data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize GameEvent to plain dictionary."""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "timestamp": int(self.timestamp),
            "source_id": self.source_id,
            "target_ids": list(self.target_ids),
            "location_id": self.location_id,
            "data": dict(self.data),
            "importance": float(self.importance),
            "priority": str(self.priority.value if isinstance(self.priority, Enum) else self.priority),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameEvent:
        """Reconstruct GameEvent from plain dictionary."""
        return cls(
            id=str(data["id"]),
            event_type=str(data["event_type"]),
            timestamp=int(data.get("timestamp", 0)),
            source_id=data.get("source_id"),
            target_ids=list(data.get("target_ids", [])),
            location_id=data.get("location_id"),
            data=dict(data.get("data", {})),
            importance=float(data.get("importance", 0.5)),
            priority=str(data.get("priority", PRIORITY_NORMAL)),
        )


EventHandler = Callable[[GameEvent], Iterable[GameEvent] | GameEvent | None]


class EventBus:
    """Three-stage priority event engine: Generation, Processing, and Consequence Generation."""

    def __init__(self, max_depth: int = MAX_EVENT_CONSEQUENCE_DEPTH) -> None:
        self.max_depth: int = int(max_depth)
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._persistence_listeners: list[Callable[[GameEvent], None]] = []
        self._normal_queue: deque[tuple[GameEvent, int]] = deque()
        self._background_queue: deque[tuple[GameEvent, int]] = deque()
        self.event_history: list[GameEvent] = []
        self._next_id: int = 1

    def _normalize_priority(
        self,
        event: GameEvent,
        explicit_priority: EventPriority | str | None = None,
    ) -> EventPriority:
        """Resolve canonical EventPriority for `event`."""
        if explicit_priority is not None:
            raw = explicit_priority.value if isinstance(explicit_priority, Enum) else str(explicit_priority).lower()
            return EventPriority(raw)

        current = event.priority.value if isinstance(event.priority, Enum) else str(event.priority).lower()
        if current in (PRIORITY_CRITICAL, PRIORITY_BACKGROUND):
            return EventPriority(current)

        # Infer default priority from canonical event_type if left at default "normal"
        if event.event_type in CRITICAL_EVENT_TYPES:
            return EventPriority.CRITICAL
        if event.event_type in BACKGROUND_EVENT_TYPES:
            return EventPriority.BACKGROUND
        return EventPriority.NORMAL

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe `handler` to `event_type` (or `'*'` for all events)."""
        handlers = self._subscribers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe `handler` from `event_type`."""
        handlers = self._subscribers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)

    def register_persistence_listener(self, listener: Callable[[GameEvent], None]) -> None:
        """Register a callback (e.g. SaveManager.append_event) invoked whenever an event is processed."""
        if listener not in self._persistence_listeners:
            self._persistence_listeners.append(listener)

    def unregister_persistence_listener(self, listener: Callable[[GameEvent], None]) -> None:
        """Remove a previously registered persistence listener."""
        if listener in self._persistence_listeners:
            self._persistence_listeners.remove(listener)

    def create_event(
        self,
        event_type: str,
        timestamp: int = 0,
        source_id: str | None = None,
        target_ids: list[str] | None = None,
        location_id: str | None = None,
        data: dict[str, Any] | None = None,
        importance: float = 0.5,
        priority: EventPriority | str | None = None,
        event_id: str | None = None,
    ) -> GameEvent:
        """Create a GameEvent with an auto-generated sequential ID if not specified."""
        if event_id is None:
            event_id = f"event_{self._next_id:05d}"
            self._next_id += 1
        resolved_prio = (
            priority.value
            if isinstance(priority, Enum)
            else (str(priority).lower() if priority is not None else PRIORITY_NORMAL)
        )
        ev = GameEvent(
            id=event_id,
            event_type=event_type,
            timestamp=timestamp,
            source_id=source_id,
            target_ids=list(target_ids) if target_ids else [],
            location_id=location_id,
            data=dict(data) if data else {},
            importance=importance,
            priority=resolved_prio,
        )
        if priority is None:
            ev.priority = self._normalize_priority(ev).value
        return ev

    def emit(
        self,
        event: GameEvent,
        priority: EventPriority | str | None = None,
    ) -> list[GameEvent]:
        """Stage 1: Emit an event into the bus.

        - CRITICAL events are processed immediately (including any CRITICAL consequences).
        - NORMAL events are queued for `process_tick_events()`.
        - BACKGROUND events are queued for `process_background_events()`.
        """
        resolved = self._normalize_priority(event, priority)
        event.priority = resolved.value

        if resolved == EventPriority.CRITICAL:
            return self._dispatch_event(event, depth=0, allow_background=False)
        if resolved == EventPriority.NORMAL:
            self._normal_queue.append((event, 0))
            return []
        self._background_queue.append((event, 0))
        return []

    def _normalize_consequences(
        self,
        result: Iterable[GameEvent] | GameEvent | None,
    ) -> list[GameEvent]:
        if result is None:
            return []
        if isinstance(result, GameEvent):
            return [result]
        if isinstance(result, Iterable):
            return [ev for ev in result if isinstance(ev, GameEvent)]
        return []

    def _dispatch_event(
        self,
        event: GameEvent,
        depth: int = 0,
        allow_background: bool = False,
    ) -> list[GameEvent]:
        """Stage 2 (Processing) & Stage 3 (Consequence Generation)."""
        processed: list[GameEvent] = [event]
        self.event_history.append(event)

        for listener in list(self._persistence_listeners):
            listener(event)

        # Gather specific and wildcard subscribers in deterministic registration order
        specific_handlers = list(self._subscribers.get(event.event_type, []))
        wildcard_handlers = list(self._subscribers.get("*", []))
        all_handlers: list[EventHandler] = specific_handlers + [
            h for h in wildcard_handlers if h not in specific_handlers
        ]

        consequences: list[GameEvent] = []
        for handler in all_handlers:
            res = handler(event)
            consequences.extend(self._normalize_consequences(res))

        if depth >= self.max_depth:
            return processed

        for cons_event in consequences:
            cons_prio = self._normalize_priority(cons_event)
            cons_event.priority = cons_prio.value
            if cons_prio == EventPriority.BACKGROUND and not allow_background:
                self._background_queue.append((cons_event, depth + 1))
            else:
                processed.extend(
                    self._dispatch_event(cons_event, depth=depth + 1, allow_background=allow_background)
                )

        return processed

    def process_tick_events(self) -> list[GameEvent]:
        """Process all queued NORMAL events for the current simulation tick."""
        processed: list[GameEvent] = []
        while self._normal_queue:
            event, depth = self._normal_queue.popleft()
            if depth > self.max_depth:
                continue
            processed.extend(self._dispatch_event(event, depth=depth, allow_background=False))
        return processed

    def process_background_events(self) -> list[GameEvent]:
        """Process all queued BACKGROUND events for scheduled updates."""
        processed: list[GameEvent] = []
        while self._background_queue:
            event, depth = self._background_queue.popleft()
            if depth > self.max_depth:
                continue
            processed.extend(self._dispatch_event(event, depth=depth, allow_background=True))
            # Also drain any normal events spawned by background processing
            while self._normal_queue:
                norm_ev, norm_depth = self._normal_queue.popleft()
                if norm_depth <= self.max_depth:
                    processed.extend(self._dispatch_event(norm_ev, depth=norm_depth, allow_background=True))
        return processed

    def process_all(self) -> list[GameEvent]:
        """Process all pending NORMAL and BACKGROUND events."""
        processed = self.process_tick_events()
        processed.extend(self.process_background_events())
        return processed

    @property
    def pending_normal_count(self) -> int:
        return len(self._normal_queue)

    @property
    def pending_background_count(self) -> int:
        return len(self._background_queue)

    def get_history(
        self,
        event_type: str | None = None,
        min_importance: float = 0.0,
        limit: int | None = None,
    ) -> list[GameEvent]:
        """Return filtered event history in chronological order."""
        filtered = [
            ev
            for ev in self.event_history
            if ev.importance >= min_importance and (event_type is None or ev.event_type == event_type)
        ]
        if limit is not None and limit >= 0:
            return filtered[-limit:] if limit > 0 else []
        return filtered

    def clear_queues(self) -> None:
        """Clear pending normal and background queues without wiping history."""
        self._normal_queue.clear()
        self._background_queue.clear()
