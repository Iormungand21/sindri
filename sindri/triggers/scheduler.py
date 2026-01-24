"""TriggerScheduler for Triggers & Automations (ROADMAP Item 9).

Background service that evaluates cron expressions and fires due triggers.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from zoneinfo import ZoneInfo

import structlog

from sindri.core.events import EventBus, Event, EventType
from sindri.triggers.executor import TriggerExecutor
from sindri.triggers.models import TriggerDefinition, TriggerType, TriggerStatus
from sindri.triggers.store import TriggerStore

log = structlog.get_logger()


class SchedulerStatus(Enum):
    """Background scheduler service status."""

    STOPPED = "stopped"
    RUNNING = "running"
    STOPPING = "stopping"


@dataclass
class SchedulerConfig:
    """Configuration for trigger scheduler."""

    enabled: bool = True
    tick_interval_seconds: int = 30  # Check for due triggers every 30s
    max_concurrent_triggers: int = 5  # Max triggers to run in parallel
    auto_pause_after_failures: int = 3  # Pause trigger after N consecutive failures


@dataclass
class SchedulerState:
    """Current state of the trigger scheduler."""

    status: SchedulerStatus = SchedulerStatus.STOPPED
    triggers_fired: int = 0
    last_tick: Optional[float] = None
    started_at: Optional[float] = None
    last_error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "status": self.status.value,
            "triggers_fired": self.triggers_fired,
            "last_tick": self.last_tick,
            "started_at": self.started_at,
            "uptime_seconds": (
                time.time() - self.started_at if self.started_at else None
            ),
            "last_error": self.last_error,
        }


class TriggerScheduler:
    """Background service evaluating cron triggers.

    Uses croniter to parse cron expressions and calculate next run times.
    Runs a tick loop checking for due triggers at configurable intervals.

    Usage:
        scheduler = TriggerScheduler(store, executor, event_bus)
        await scheduler.start()
        # ... later ...
        await scheduler.stop()
    """

    def __init__(
        self,
        store: TriggerStore,
        executor: TriggerExecutor,
        event_bus: Optional[EventBus] = None,
        config: Optional[SchedulerConfig] = None,
    ):
        """Initialize trigger scheduler.

        Args:
            store: TriggerStore for trigger persistence
            executor: TriggerExecutor for running triggers
            event_bus: EventBus for progress events. Optional.
            config: SchedulerConfig for settings. Uses defaults if not provided.
        """
        self.store = store
        self.executor = executor
        self.event_bus = event_bus
        self.config = config or SchedulerConfig()

        # State management
        self._state = SchedulerState()
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._running_triggers: set[str] = set()  # Currently executing trigger IDs

        log.info("trigger_scheduler_initialized", config=self.config)

    @property
    def status(self) -> SchedulerStatus:
        """Get current scheduler status."""
        return self._state.status

    def get_state(self) -> SchedulerState:
        """Get current scheduler state."""
        return self._state

    def _emit(self, event_type: EventType, data: Any) -> None:
        """Emit an event if event bus is configured."""
        if self.event_bus:
            try:
                self.event_bus.emit(Event(type=event_type, data=data, timestamp=time.time()))
            except Exception as e:
                log.warning("event_emit_failed", error=str(e))

    async def start(self) -> bool:
        """Start the trigger scheduler loop.

        Returns:
            True if started successfully, False if already running
        """
        if self._state.status == SchedulerStatus.RUNNING:
            log.warning("trigger_scheduler_already_running")
            return False

        if not self.config.enabled:
            log.info("trigger_scheduler_disabled")
            return False

        self._stop_event.clear()
        self._state.status = SchedulerStatus.RUNNING
        self._state.started_at = time.time()
        self._state.triggers_fired = 0
        self._state.last_error = None

        # Initialize next_run_at for all cron triggers that don't have it set
        await self._initialize_cron_triggers()

        # Start the main scheduler loop
        self._task = asyncio.create_task(self._scheduler_loop())

        self._emit(
            EventType.TRIGGER_SCHEDULER_STARTED,
            {"tick_interval_seconds": self.config.tick_interval_seconds},
        )

        log.info(
            "trigger_scheduler_started",
            tick_interval=self.config.tick_interval_seconds,
        )
        return True

    async def stop(self, reason: str = "user_requested") -> bool:
        """Stop the trigger scheduler gracefully.

        Args:
            reason: Reason for stopping

        Returns:
            True if stopped successfully
        """
        if self._state.status == SchedulerStatus.STOPPED:
            return True

        self._state.status = SchedulerStatus.STOPPING
        self._stop_event.set()

        # Wait for the task to complete
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        self._state.status = SchedulerStatus.STOPPED

        self._emit(
            EventType.TRIGGER_SCHEDULER_STOPPED,
            {"reason": reason, "triggers_fired": self._state.triggers_fired},
        )

        log.info(
            "trigger_scheduler_stopped",
            reason=reason,
            triggers_fired=self._state.triggers_fired,
        )
        return True

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop - checks for due triggers periodically."""
        log.debug("trigger_scheduler_loop_started")

        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception as e:
                self._state.last_error = str(e)
                log.error("trigger_scheduler_tick_error", error=str(e))

            # Wait for next tick or stop signal
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.config.tick_interval_seconds,
                )
                break  # Stop event was set
            except asyncio.TimeoutError:
                pass  # Normal timeout, continue loop

        log.debug("trigger_scheduler_loop_ended")

    async def _tick(self) -> None:
        """Single tick of the scheduler - check and fire due triggers."""
        now = datetime.now(timezone.utc)
        self._state.last_tick = time.time()

        # Get due triggers
        due_triggers = await self.store.get_due_triggers(now)

        if not due_triggers:
            return

        log.debug("trigger_scheduler_tick", due_count=len(due_triggers))

        # Fire triggers (respecting concurrency limit)
        tasks = []
        for trigger in due_triggers:
            # Skip if already running
            if trigger.id in self._running_triggers:
                continue

            # Respect concurrency limit
            if len(self._running_triggers) >= self.config.max_concurrent_triggers:
                break

            self._running_triggers.add(trigger.id)
            tasks.append(self._fire_trigger(trigger))

        # Wait for all fired triggers to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _fire_trigger(self, trigger: TriggerDefinition) -> None:
        """Fire a single trigger and update next run time."""
        try:
            log.info(
                "trigger_firing",
                trigger_id=trigger.id,
                trigger_name=trigger.name,
            )

            # Execute the trigger
            await self.executor.execute_trigger(trigger)

            self._state.triggers_fired += 1

            # Calculate and update next run time
            next_run = self._calculate_next_run(trigger)
            if next_run:
                await self.store.update_next_run(trigger.id, next_run)

        except Exception as e:
            log.error(
                "trigger_fire_failed",
                trigger_id=trigger.id,
                error=str(e),
            )
        finally:
            self._running_triggers.discard(trigger.id)

    async def _initialize_cron_triggers(self) -> None:
        """Initialize next_run_at for cron triggers that don't have it set."""
        triggers = await self.store.list_triggers(
            trigger_type=TriggerType.CRON,
            status=TriggerStatus.ENABLED,
        )

        for trigger in triggers:
            if trigger.next_run_at is None and trigger.cron_expression:
                next_run = self._calculate_next_run(trigger)
                if next_run:
                    await self.store.update_next_run(trigger.id, next_run)
                    log.debug(
                        "trigger_next_run_initialized",
                        trigger_id=trigger.id,
                        next_run=next_run.isoformat(),
                    )

    def _calculate_next_run(self, trigger: TriggerDefinition) -> Optional[datetime]:
        """Calculate next run time from cron expression.

        Args:
            trigger: The trigger with cron_expression

        Returns:
            Next run datetime in UTC, or None if unable to calculate
        """
        if not trigger.cron_expression:
            return None

        try:
            from croniter import croniter

            # Get base time in trigger's timezone for correct cron evaluation
            try:
                tz = ZoneInfo(trigger.timezone) if trigger.timezone else timezone.utc
            except Exception:
                log.warning(
                    "invalid_timezone_using_utc",
                    trigger_id=trigger.id,
                    timezone=trigger.timezone,
                )
                tz = timezone.utc

            base_time = datetime.now(tz)

            cron = croniter(trigger.cron_expression, base_time)
            next_run = cron.get_next(datetime)

            # Ensure timezone awareness (croniter returns naive datetime)
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=tz)

            # Convert to UTC for storage
            next_run_utc = next_run.astimezone(timezone.utc)

            return next_run_utc

        except ImportError:
            log.error("croniter_not_installed")
            return None
        except Exception as e:
            log.error(
                "cron_parse_failed",
                trigger_id=trigger.id,
                expression=trigger.cron_expression,
                error=str(e),
            )
            return None

    def validate_cron_expression(self, expression: str) -> tuple[bool, Optional[str]]:
        """Validate a cron expression.

        Args:
            expression: The cron expression to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            from croniter import croniter

            croniter(expression)
            return True, None
        except ImportError:
            return False, "croniter not installed"
        except Exception as e:
            return False, str(e)

    def get_next_runs(
        self, expression: str, count: int = 5
    ) -> list[datetime]:
        """Get the next N run times for a cron expression.

        Args:
            expression: The cron expression
            count: Number of future runs to calculate

        Returns:
            List of future run datetimes
        """
        try:
            from croniter import croniter

            base_time = datetime.now(timezone.utc)
            cron = croniter(expression, base_time)

            runs = []
            for _ in range(count):
                next_run = cron.get_next(datetime)
                if next_run.tzinfo is None:
                    next_run = next_run.replace(tzinfo=timezone.utc)
                runs.append(next_run)

            return runs
        except Exception:
            return []
