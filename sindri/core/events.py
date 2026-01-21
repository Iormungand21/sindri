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
    DELEGATION_START = auto()
    DELEGATION_COMPLETE = auto()
    DELEGATION_FAILED = auto()
    MODEL_LOADED = auto()
    MODEL_UNLOADED = auto()
    ERROR = auto()
    ITERATION_START = auto()
    ITERATION_END = auto()
    # Phase 6.1: New event types for parallel execution
    PARALLEL_BATCH_START = auto()
    PARALLEL_BATCH_END = auto()
    # Phase 5.6: New event types for error handling
    ITERATION_WARNING = auto()  # Warn agent about remaining iterations
    MODEL_DEGRADED = auto()  # Agent falling back to smaller model
    # Phase 6.3: Streaming output
    STREAMING_TOKEN = auto()  # Individual token during streaming response
    STREAMING_START = auto()  # Streaming response started
    STREAMING_END = auto()  # Streaming response completed
    # Phase 7.3: Interactive planning
    PLAN_PROPOSED = auto()  # Execution plan created
    PLAN_APPROVED = auto()  # User approved the plan
    PLAN_REJECTED = auto()  # User rejected the plan
    # Phase 7.2: Learning from success
    PATTERN_LEARNED = auto()  # New pattern extracted from successful task
    # Phase 5.5: Performance metrics
    METRICS_UPDATED = auto()  # Real-time metrics update for TUI
    # Policy + Guardrails events
    POLICY_VIOLATION = auto()  # Policy limit exceeded
    POLICY_WARNING = auto()  # Policy approaching limit (e.g., 80%)
    POLICY_ESCALATION = auto()  # Operation escalated for approval


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
        self._event_handlers: list[Callable[[Event], None]] = []
        self._enabled = True

    def subscribe(self, event_type: EventType, handler: Callable):
        """Subscribe a handler to an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        log.debug("event_handler_subscribed", event_type=event_type.name)

    def subscribe_event(self, handler: Callable[[Event], None]):
        """Subscribe a handler to full Event objects."""
        self._event_handlers.append(handler)
        log.debug("event_handler_subscribed_full_event", handlers=len(self._event_handlers))

    def unsubscribe(self, event_type: EventType, handler: Callable):
        """Unsubscribe a handler from an event type."""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                log.debug("event_handler_unsubscribed", event_type=event_type.name)
            except ValueError:
                pass

    def unsubscribe_event(self, handler: Callable[[Event], None]):
        """Unsubscribe a handler from full Event objects."""
        try:
            self._event_handlers.remove(handler)
            log.debug(
                "event_handler_unsubscribed_full_event",
                handlers=len(self._event_handlers),
            )
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
                log.error(
                    "event_handler_failed", event_type=event.type.name, error=str(e)
                )

        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                log.error(
                    "event_handler_failed_full_event",
                    event_type=event.type.name,
                    error=str(e),
                )

    def clear(self):
        """Clear all handlers."""
        self._handlers.clear()

    def disable(self):
        """Disable event emission."""
        self._enabled = False

    def enable(self):
        """Enable event emission."""
        self._enabled = True
