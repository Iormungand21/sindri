"""Real-time telemetry collection for performance monitoring.

ROADMAP Item 7: Performance Telemetry Stream
"""

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional, Callable, TYPE_CHECKING
import structlog

from sindri.core.events import EventBus, Event, EventType
from sindri.core.event_schemas import (
    TelemetryTickData,
    TelemetrySnapshotData,
    VRAMSnapshot,
    ConcurrencySnapshot,
    AgentTimingStats,
    ToolTimingStats,
)

if TYPE_CHECKING:
    from sindri.llm.manager import ModelManager
    from sindri.core.scheduler import TaskScheduler

log = structlog.get_logger()


@dataclass
class TimingSample:
    """A single timing measurement."""

    timestamp: float
    duration_ms: float
    success: bool = True


@dataclass
class RollingStats:
    """Rolling statistics window for timing data.

    Maintains a sliding window of recent samples for computing
    average, p95, and success rate statistics.
    """

    samples: deque = field(default_factory=lambda: deque(maxlen=100))
    total_count: int = 0
    total_duration_ms: float = 0.0

    def add_sample(self, duration_ms: float, success: bool = True):
        """Add a new timing sample."""
        self.samples.append(TimingSample(time.time(), duration_ms, success))
        self.total_count += 1
        self.total_duration_ms += duration_ms

    @property
    def avg_ms(self) -> float:
        """Average duration in milliseconds."""
        return self.total_duration_ms / self.total_count if self.total_count > 0 else 0.0

    @property
    def p95_ms(self) -> Optional[float]:
        """95th percentile duration in milliseconds."""
        if len(self.samples) < 5:
            return None
        sorted_durations = sorted(s.duration_ms for s in self.samples)
        idx = int(len(sorted_durations) * 0.95)
        return sorted_durations[min(idx, len(sorted_durations) - 1)]

    @property
    def success_rate(self) -> float:
        """Success rate from recent samples (0.0-1.0)."""
        if not self.samples:
            return 1.0
        return sum(1 for s in self.samples if s.success) / len(self.samples)


class TelemetryCollector:
    """Collects and aggregates real-time telemetry from the EventBus.

    Features:
    - Subscribes to relevant events (iteration, tool, model, task)
    - Maintains rolling statistics for agents and tools
    - Stores time-series history for VRAM and concurrency (5-minute window)
    - Emits periodic TELEMETRY_TICK events (every 2 seconds)
    - Provides get_tick() and get_snapshot() methods
    """

    def __init__(
        self,
        event_bus: EventBus,
        model_manager: Optional["ModelManager"] = None,
        scheduler: Optional["TaskScheduler"] = None,
        tick_interval: float = 2.0,
    ):
        """Initialize the TelemetryCollector.

        Args:
            event_bus: EventBus to subscribe to for events
            model_manager: Optional ModelManager for VRAM stats
            scheduler: Optional TaskScheduler for concurrency stats
            tick_interval: Seconds between telemetry tick emissions
        """
        self.event_bus = event_bus
        self.model_manager = model_manager
        self.scheduler = scheduler
        self.tick_interval = tick_interval

        # State tracking
        self._session_id: Optional[str] = None
        self._session_start: Optional[float] = None
        self._current_agent: Optional[str] = None
        self._current_iteration: int = 0

        # Rolling statistics
        self._agent_stats: dict[str, RollingStats] = defaultdict(RollingStats)
        self._tool_stats: dict[str, RollingStats] = defaultdict(RollingStats)

        # Agent model tracking
        self._agent_models: dict[str, str] = {}

        # Time-series data for charts (last 5 minutes at 2s intervals = 150 samples)
        self._vram_history: deque[tuple[float, VRAMSnapshot]] = deque(maxlen=150)
        self._concurrency_history: deque[tuple[float, ConcurrencySnapshot]] = deque(maxlen=150)

        # Background tick task
        self._tick_task: Optional[asyncio.Task] = None
        self._running = False

        # Callbacks for live updates (used by SSE endpoint)
        self._tick_callbacks: list[Callable[[TelemetryTickData], None]] = []

    async def start(self, session_id: Optional[str] = None):
        """Start telemetry collection.

        Args:
            session_id: Optional session ID to track. Can be set later via set_session().
        """
        self._session_id = session_id
        self._session_start = time.time()
        self._running = True

        # Clear previous state
        self._agent_stats.clear()
        self._tool_stats.clear()
        self._agent_models.clear()
        self._vram_history.clear()
        self._concurrency_history.clear()
        self._current_agent = None
        self._current_iteration = 0

        # Subscribe to events
        self._subscribe_to_events()

        # Start tick loop
        self._tick_task = asyncio.create_task(self._tick_loop())

        log.info("telemetry_collector_started", session_id=session_id)

    def set_session(self, session_id: str):
        """Set or update the current session ID.

        Args:
            session_id: Session ID to track
        """
        self._session_id = session_id
        if self._session_start is None:
            self._session_start = time.time()
        log.debug("telemetry_session_updated", session_id=session_id)

    async def stop(self) -> TelemetrySnapshotData:
        """Stop collection and return final snapshot.

        Returns:
            Final telemetry snapshot for the session
        """
        self._running = False

        if self._tick_task:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass

        # Unsubscribe from events
        self._unsubscribe_from_events()

        # Generate final snapshot
        snapshot = self.get_snapshot()

        # Emit snapshot event
        self.event_bus.emit(
            Event(
                type=EventType.TELEMETRY_SNAPSHOT,
                data=snapshot.model_dump(),
                task_id=self._session_id,
            )
        )

        log.info("telemetry_collector_stopped", session_id=self._session_id)
        return snapshot

    def _subscribe_to_events(self):
        """Subscribe to relevant EventBus events."""
        self.event_bus.subscribe(EventType.ITERATION_START, self._on_iteration_start)
        self.event_bus.subscribe(EventType.ITERATION_END, self._on_iteration_end)
        self.event_bus.subscribe(EventType.TOOL_CALLED, self._on_tool_called)
        self.event_bus.subscribe(EventType.MODEL_LOADED, self._on_model_loaded)
        self.event_bus.subscribe(EventType.TASK_STATUS_CHANGED, self._on_task_status)

    def _unsubscribe_from_events(self):
        """Unsubscribe from EventBus events."""
        self.event_bus.unsubscribe(EventType.ITERATION_START, self._on_iteration_start)
        self.event_bus.unsubscribe(EventType.ITERATION_END, self._on_iteration_end)
        self.event_bus.unsubscribe(EventType.TOOL_CALLED, self._on_tool_called)
        self.event_bus.unsubscribe(EventType.MODEL_LOADED, self._on_model_loaded)
        self.event_bus.unsubscribe(EventType.TASK_STATUS_CHANGED, self._on_task_status)

    # Event handlers
    def _on_iteration_start(self, data: dict):
        """Handle ITERATION_START event."""
        self._current_agent = data.get("agent")
        self._current_iteration = data.get("iteration", 0)

    def _on_iteration_end(self, data: dict):
        """Handle ITERATION_END event."""
        agent = data.get("agent", self._current_agent)
        duration_ms = data.get("duration_ms", 0.0)
        if agent and duration_ms > 0:
            self._agent_stats[agent].add_sample(duration_ms)

    def _on_tool_called(self, data: dict):
        """Handle TOOL_CALLED event."""
        tool_name = data.get("name", "unknown")
        duration_ms = data.get("duration_ms", 0.0)
        success = data.get("success", True)
        self._tool_stats[tool_name].add_sample(duration_ms, success)

    def _on_model_loaded(self, data: dict):
        """Handle MODEL_LOADED event."""
        agent = data.get("agent")
        model = data.get("model")
        if agent and model:
            self._agent_models[agent] = model

    def _on_task_status(self, data: dict):
        """Handle TASK_STATUS_CHANGED event."""
        # Could track task state changes if needed
        pass

    async def _tick_loop(self):
        """Emit periodic telemetry ticks."""
        while self._running:
            try:
                tick = self.get_tick()

                # Store in history
                self._vram_history.append((tick.timestamp, tick.vram))
                self._concurrency_history.append((tick.timestamp, tick.concurrency))

                # Emit event
                self.event_bus.emit(
                    Event(
                        type=EventType.TELEMETRY_TICK,
                        data=tick.model_dump(),
                        task_id=self._session_id,
                    )
                )

                # Notify callbacks
                for callback in self._tick_callbacks:
                    try:
                        callback(tick)
                    except Exception as e:
                        log.warning("tick_callback_error", error=str(e))

                await asyncio.sleep(self.tick_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("tick_loop_error", error=str(e))
                await asyncio.sleep(self.tick_interval)

    def get_tick(self) -> TelemetryTickData:
        """Get current telemetry tick data.

        Returns:
            Current telemetry snapshot
        """
        vram = self._get_vram_snapshot()
        concurrency = self._get_concurrency_snapshot()

        return TelemetryTickData(
            timestamp=time.time(),
            session_id=self._session_id,
            vram=vram,
            concurrency=concurrency,
            session_duration_seconds=(
                time.time() - self._session_start if self._session_start else 0.0
            ),
            current_agent=self._current_agent,
            current_iteration=self._current_iteration,
        )

    def get_snapshot(self) -> TelemetrySnapshotData:
        """Get full telemetry snapshot with all statistics.

        Returns:
            Complete telemetry snapshot with agent/tool stats
        """
        vram = self._get_vram_snapshot()
        concurrency = self._get_concurrency_snapshot()

        agent_stats = [
            AgentTimingStats(
                agent_name=name,
                model_name=self._agent_models.get(name, ""),
                total_iterations=stats.total_count,
                total_duration_ms=stats.total_duration_ms,
                avg_iteration_ms=stats.avg_ms,
                p95_iteration_ms=stats.p95_ms,
            )
            for name, stats in self._agent_stats.items()
        ]

        tool_stats = [
            ToolTimingStats(
                tool_name=name,
                call_count=stats.total_count,
                total_duration_ms=stats.total_duration_ms,
                avg_duration_ms=stats.avg_ms,
                success_rate=stats.success_rate,
                p95_duration_ms=stats.p95_ms,
            )
            for name, stats in self._tool_stats.items()
        ]

        return TelemetrySnapshotData(
            timestamp=time.time(),
            session_id=self._session_id or "",
            session_duration_seconds=(
                time.time() - self._session_start if self._session_start else 0.0
            ),
            vram=vram,
            concurrency=concurrency,
            agent_stats=agent_stats,
            tool_stats=tool_stats,
            total_iterations=sum(s.total_count for s in self._agent_stats.values()),
            total_tool_calls=sum(s.total_count for s in self._tool_stats.values()),
            llm_time_seconds=sum(s.total_duration_ms for s in self._agent_stats.values()) / 1000.0,
            tool_time_seconds=sum(s.total_duration_ms for s in self._tool_stats.values()) / 1000.0,
        )

    def _get_vram_snapshot(self) -> VRAMSnapshot:
        """Get current VRAM state from ModelManager."""
        if self.model_manager:
            stats = self.model_manager.get_vram_stats()
            cache_stats = self.model_manager.get_cache_stats()
            return VRAMSnapshot(
                total_gb=stats.get("total", 16.0),
                used_gb=stats.get("used", 0.0),
                free_gb=stats.get("free", 16.0),
                loaded_models=stats.get("loaded_models", []),
                cache_hit_rate=cache_stats.get("hit_rate", 0.0),
            )
        return VRAMSnapshot(total_gb=16.0, used_gb=0.0, free_gb=16.0)

    def _get_concurrency_snapshot(self) -> ConcurrencySnapshot:
        """Get current task concurrency state from scheduler."""
        if self.scheduler:
            return ConcurrencySnapshot(
                running_tasks=self.scheduler.get_running_count(),
                pending_tasks=self.scheduler.get_pending_count(),
                waiting_tasks=0,
                batch_size=0,
            )
        return ConcurrencySnapshot(running_tasks=0, pending_tasks=0, waiting_tasks=0)

    def get_vram_history(self) -> list[tuple[float, VRAMSnapshot]]:
        """Get VRAM time-series data for charts.

        Returns:
            List of (timestamp, VRAMSnapshot) tuples
        """
        return list(self._vram_history)

    def get_concurrency_history(self) -> list[tuple[float, ConcurrencySnapshot]]:
        """Get concurrency time-series data for charts.

        Returns:
            List of (timestamp, ConcurrencySnapshot) tuples
        """
        return list(self._concurrency_history)

    def add_tick_callback(self, callback: Callable[[TelemetryTickData], None]):
        """Add callback for tick notifications.

        Args:
            callback: Function to call with each telemetry tick
        """
        self._tick_callbacks.append(callback)

    def remove_tick_callback(self, callback: Callable[[TelemetryTickData], None]):
        """Remove tick callback.

        Args:
            callback: Previously registered callback to remove
        """
        if callback in self._tick_callbacks:
            self._tick_callbacks.remove(callback)

    @property
    def is_running(self) -> bool:
        """Check if telemetry collection is active."""
        return self._running

    @property
    def session_id(self) -> Optional[str]:
        """Get the current session ID."""
        return self._session_id
