"""Event system for orchestrator-to-TUI communication."""

import time
from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from enum import Enum, auto
import structlog

log = structlog.get_logger()


class EventType(Enum):
    """Types of events emitted during task execution."""
    TASK_CREATED = auto()
    TASK_STATUS_CHANGED = auto()
    AGENT_OUTPUT = auto()
    TOOL_CALLED = auto()
    MODEL_LOADED = auto()
    MODEL_UNLOADED = auto()
    ERROR = auto()
    ITERATION_START = auto()
    ITERATION_END = auto()
    # Phase 6.1: New event types for parallel execution
    PARALLEL_BATCH_START = auto()
    PARALLEL_BATCH_END = auto()


@dataclass
class Event:
    """An event with type, data, and timestamp for ordering.

    Phase 6.1: Added timestamp for coherent event ordering during parallel execution.
    """
    type: EventType
    data: Any
    timestamp: float = field(default_factory=time.time)  # For ordering parallel events
    task_id: Optional[str] = None  # For filtering events by task


class EventBus:
    """Simple pub/sub event bus for orchestrator events."""

    def __init__(self):
        self._handlers: dict[EventType, list[Callable]] = {}
        self._enabled = True

    def subscribe(self, event_type: EventType, handler: Callable):
        """Subscribe a handler to an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        log.debug("event_handler_subscribed", event_type=event_type.name)

    def unsubscribe(self, event_type: EventType, handler: Callable):
        """Unsubscribe a handler from an event type."""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                log.debug("event_handler_unsubscribed", event_type=event_type.name)
            except ValueError:
                pass

    def emit(self, event: Event):
        """Emit an event to all subscribed handlers."""
        if not self._enabled:
            return

        handlers = self._handlers.get(event.type, [])
        log.debug("event_emitted", event_type=event.type.name, handlers=len(handlers))

        for handler in handlers:
            try:
                handler(event.data)
            except Exception as e:
                log.error("event_handler_failed",
                         event_type=event.type.name,
                         error=str(e))

    def clear(self):
        """Clear all handlers."""
        self._handlers.clear()

    def disable(self):
        """Disable event emission."""
        self._enabled = False

    def enable(self):
        """Enable event emission."""
        self._enabled = True
