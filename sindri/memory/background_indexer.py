"""Background indexer for multi-project workspace (ROADMAP Item 4).

Provides an async background service that indexes multiple projects
using a priority queue, with progress events and graceful shutdown.
"""

import asyncio
import heapq
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Callable, Awaitable
import structlog

from sindri.core.events import EventBus, Event, EventType
from sindri.core.event_schemas import (
    IndexQueuedData,
    IndexStartedData,
    IndexProgressData,
    IndexCompletedData,
    IndexFailedData,
    IndexFileProcessedData,
    IndexerStartedData,
    IndexerStoppedData,
    IndexerPausedData,
)
from sindri.memory.global_memory import GlobalMemoryStore, IncrementalIndexResult
from sindri.memory.projects import ProjectRegistry

log = structlog.get_logger()


class IndexerStatus(Enum):
    """Background indexer service status."""

    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"


@dataclass
class IndexerConfig:
    """Configuration for background indexer."""

    enabled: bool = True
    auto_start: bool = False  # Start automatically with TUI/Web
    schedule_interval_minutes: int = 60  # Re-index interval (0 = no automatic re-indexing)
    max_vram_percent: float = 0.3  # Max VRAM to use for embedding (not enforced yet)
    cooldown_seconds: float = 1.0  # Pause between projects
    max_concurrent_files: int = 5  # Files to process concurrently (future)
    batch_size: int = 10  # Embeddings per batch (future)


@dataclass(order=True)
class QueuedProject:
    """A project in the indexer queue with priority ordering."""

    priority: int  # Lower = higher priority (for heapq)
    timestamp: float = field(compare=False)  # For FIFO within same priority
    project_path: str = field(compare=False)
    force: bool = field(default=False, compare=False)


@dataclass
class IndexerState:
    """Current state of the background indexer."""

    status: IndexerStatus = IndexerStatus.STOPPED
    current_project: Optional[str] = None
    current_project_name: Optional[str] = None
    queue_length: int = 0
    projects_indexed: int = 0
    last_completed: Optional[str] = None
    last_error: Optional[str] = None
    started_at: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "status": self.status.value,
            "current_project": self.current_project,
            "current_project_name": self.current_project_name,
            "queue_length": self.queue_length,
            "projects_indexed": self.projects_indexed,
            "last_completed": self.last_completed,
            "last_error": self.last_error,
            "started_at": self.started_at,
            "uptime_seconds": (
                time.time() - self.started_at if self.started_at else None
            ),
        }


class BackgroundIndexer:
    """Background indexing service using asyncio patterns.

    Provides:
    - Priority queue for project indexing
    - Incremental indexing (only changed files)
    - Progress events for TUI/Web UI
    - Graceful shutdown
    - Automatic re-indexing on schedule

    Usage:
        indexer = BackgroundIndexer(global_memory, registry, event_bus)
        await indexer.start()
        await indexer.queue_project("/path/to/project", priority=1)
        # ... later ...
        await indexer.stop()
    """

    def __init__(
        self,
        global_memory: GlobalMemoryStore,
        registry: Optional[ProjectRegistry] = None,
        event_bus: Optional[EventBus] = None,
        config: Optional[IndexerConfig] = None,
    ):
        """Initialize background indexer.

        Args:
            global_memory: GlobalMemoryStore instance for indexing
            registry: ProjectRegistry instance. Uses global_memory's if not provided.
            event_bus: EventBus for progress events. Optional.
            config: IndexerConfig for settings. Uses defaults if not provided.
        """
        self.global_memory = global_memory
        self.registry = registry or global_memory.registry
        self.event_bus = event_bus
        self.config = config or IndexerConfig()

        # Queue and state
        self._queue: list[QueuedProject] = []  # heapq
        self._queue_set: set[str] = set()  # Fast membership check
        self._state = IndexerState()
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._schedule_task: Optional[asyncio.Task] = None

        log.info("background_indexer_initialized", config=self.config)

    @property
    def status(self) -> IndexerStatus:
        """Get current indexer status."""
        return self._state.status

    def get_state(self) -> IndexerState:
        """Get current indexer state with queue info."""
        self._state.queue_length = len(self._queue)
        return self._state

    def _emit(self, event_type: EventType, data: Any):
        """Emit an event if event bus is configured."""
        if self.event_bus:
            self.event_bus.emit(Event(type=event_type, data=data))

    async def start(self) -> bool:
        """Start the background indexer loop.

        Returns:
            True if started successfully, False if already running
        """
        if self._state.status == IndexerStatus.RUNNING:
            log.warning("indexer_already_running")
            return False

        self._stop_event.clear()
        self._state.status = IndexerStatus.RUNNING
        self._state.started_at = time.time()
        self._state.projects_indexed = 0

        # Start the main indexer loop
        self._task = asyncio.create_task(self._indexer_loop())

        # Start scheduled re-indexing if configured
        if self.config.schedule_interval_minutes > 0:
            self._schedule_task = asyncio.create_task(self._schedule_loop())

        self._emit(
            EventType.INDEXER_STARTED,
            IndexerStartedData(
                queued_projects=len(self._queue),
                auto_index_enabled=self.config.enabled,
            ),
        )

        log.info("indexer_started", queued=len(self._queue))
        return True

    async def stop(self, reason: str = "user_requested") -> bool:
        """Stop the background indexer gracefully.

        Args:
            reason: Reason for stopping (for event)

        Returns:
            True if stopped successfully
        """
        if self._state.status == IndexerStatus.STOPPED:
            return True

        self._state.status = IndexerStatus.STOPPING
        self._stop_event.set()

        # Wait for tasks to complete
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        if self._schedule_task:
            self._schedule_task.cancel()
            try:
                await self._schedule_task
            except asyncio.CancelledError:
                pass

        self._state.status = IndexerStatus.STOPPED
        self._state.current_project = None
        self._state.current_project_name = None

        self._emit(
            EventType.INDEXER_STOPPED,
            IndexerStoppedData(
                reason=reason,
                projects_indexed=self._state.projects_indexed,
            ),
        )

        log.info("indexer_stopped", reason=reason, indexed=self._state.projects_indexed)
        return True

    async def queue_project(
        self, project_path: str, priority: Optional[int] = None, force: bool = False
    ) -> int:
        """Queue a project for indexing.

        Args:
            project_path: Path to project directory
            priority: Queue priority (1=highest, 10=lowest). Uses project's if not specified.
            force: Force full re-index (ignore file hashes)

        Returns:
            Position in queue (0-indexed)
        """
        from pathlib import Path

        normalized = str(Path(project_path).resolve())

        # Skip if already in queue
        if normalized in self._queue_set:
            log.debug("project_already_queued", path=normalized)
            # Find position
            for i, item in enumerate(self._queue):
                if item.project_path == normalized:
                    return i
            return 0

        # Get project info for priority and name
        project = self.registry.get_project(normalized)
        if not project:
            log.warning("project_not_registered", path=normalized)
            # Still allow indexing, just use default priority
            project_name = Path(normalized).name
            effective_priority = priority if priority is not None else 5
        else:
            project_name = project.name
            effective_priority = priority if priority is not None else project.index_priority

        # Add to queue
        queued = QueuedProject(
            priority=effective_priority,
            timestamp=time.time(),
            project_path=normalized,
            force=force,
        )
        heapq.heappush(self._queue, queued)
        self._queue_set.add(normalized)

        position = len(self._queue) - 1  # Approximate position

        self._emit(
            EventType.INDEX_QUEUED,
            IndexQueuedData(
                project_path=normalized,
                project_name=project_name,
                priority=effective_priority,
                queue_position=position,
            ),
        )

        log.info(
            "project_queued",
            path=normalized,
            name=project_name,
            priority=effective_priority,
            position=position,
        )

        return position

    async def queue_all_projects(self, force: bool = False) -> int:
        """Queue all auto-indexable projects.

        Args:
            force: Force full re-index for all projects

        Returns:
            Number of projects queued
        """
        projects = self.registry.list_auto_index_projects()
        count = 0

        for project in projects:
            if project.path not in self._queue_set:
                await self.queue_project(project.path, force=force)
                count += 1

        log.info("all_projects_queued", count=count)
        return count

    def get_queue(self) -> list[dict[str, Any]]:
        """Get current queue contents.

        Returns:
            List of queued projects with their info
        """
        result = []
        for item in sorted(self._queue):
            project = self.registry.get_project(item.project_path)
            result.append(
                {
                    "project_path": item.project_path,
                    "project_name": project.name if project else Path(item.project_path).name,
                    "priority": item.priority,
                    "force": item.force,
                    "queued_at": item.timestamp,
                }
            )
        return result

    async def _indexer_loop(self):
        """Main indexer loop - processes queue until stopped."""
        log.info("indexer_loop_started")

        while not self._stop_event.is_set():
            # Check if we have work
            if not self._queue:
                # Wait for new items or stop signal
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=1.0
                    )
                    break  # Stop event set
                except asyncio.TimeoutError:
                    continue  # Check queue again

            # Get next project
            queued = heapq.heappop(self._queue)
            self._queue_set.discard(queued.project_path)

            # Index it
            try:
                await self._index_project(queued)
            except Exception as e:
                log.error(
                    "indexer_project_error",
                    path=queued.project_path,
                    error=str(e),
                )
                self._state.last_error = str(e)

            # Cooldown between projects
            if self.config.cooldown_seconds > 0 and not self._stop_event.is_set():
                await asyncio.sleep(self.config.cooldown_seconds)

        log.info("indexer_loop_stopped")

    async def _index_project(self, queued: QueuedProject):
        """Index a single project with progress events."""
        from pathlib import Path

        project_path = queued.project_path
        project = self.registry.get_project(project_path)
        project_name = project.name if project else Path(project_path).name

        self._state.current_project = project_path
        self._state.current_project_name = project_name

        # Estimate file count
        path_obj = Path(project_path)
        if path_obj.exists():
            total_files = sum(
                1 for f in path_obj.rglob("*")
                if f.is_file() and f.suffix in self.global_memory.SUPPORTED_EXTENSIONS
            )
        else:
            total_files = 0

        self._emit(
            EventType.INDEX_STARTED,
            IndexStartedData(
                project_path=project_path,
                project_name=project_name,
                total_files=total_files,
                force=queued.force,
            ),
        )

        log.info(
            "indexing_project",
            path=project_path,
            name=project_name,
            force=queued.force,
        )

        try:
            # Create callback to emit per-file events
            def on_file_indexed(proj_path: str, file_path: str, chunks: int, skipped: bool):
                self._emit(
                    EventType.INDEX_FILE_PROCESSED,
                    IndexFileProcessedData(
                        project_path=proj_path,
                        file_path=file_path,
                        chunks_created=chunks,
                        skipped=skipped,
                    ),
                )

            # Run indexing (this is synchronous, could be wrapped in executor for true async)
            result = self.global_memory.index_project_incremental(
                project_path, force=queued.force, on_file_indexed=on_file_indexed
            )

            if result.error:
                self._emit(
                    EventType.INDEX_FAILED,
                    IndexFailedData(
                        project_path=project_path,
                        project_name=project_name,
                        error=result.error,
                        files_processed=result.files_indexed,
                        duration_seconds=result.duration_seconds,
                    ),
                )
                self._state.last_error = result.error
            else:
                self._emit(
                    EventType.INDEX_COMPLETED,
                    IndexCompletedData(
                        project_path=project_path,
                        project_name=project_name,
                        files_indexed=result.files_indexed,
                        files_skipped=result.files_skipped,
                        files_failed=result.files_failed,
                        chunks_added=result.chunks_added,
                        chunks_removed=result.chunks_removed,
                        duration_seconds=result.duration_seconds,
                    ),
                )
                self._state.projects_indexed += 1
                self._state.last_completed = project_path

                log.info(
                    "project_indexed",
                    path=project_path,
                    files=result.files_indexed,
                    skipped=result.files_skipped,
                    chunks=result.chunks_added,
                    duration=f"{result.duration_seconds:.2f}s",
                )

        except Exception as e:
            self._emit(
                EventType.INDEX_FAILED,
                IndexFailedData(
                    project_path=project_path,
                    project_name=project_name,
                    error=str(e),
                    files_processed=0,
                    duration_seconds=0.0,
                ),
            )
            self._state.last_error = str(e)
            raise

        finally:
            self._state.current_project = None
            self._state.current_project_name = None

    async def _schedule_loop(self):
        """Periodic re-indexing loop."""
        interval = self.config.schedule_interval_minutes * 60

        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=interval
                )
                break  # Stop event set
            except asyncio.TimeoutError:
                # Time to re-index
                log.info("scheduled_reindex_triggered")
                await self.queue_all_projects(force=False)

    def clear_queue(self):
        """Clear all queued projects."""
        self._queue.clear()
        self._queue_set.clear()
        log.info("indexer_queue_cleared")

    async def pause(self, reason: str = "manual"):
        """Pause the indexer (future: for VRAM constraints)."""
        if self._state.status != IndexerStatus.RUNNING:
            return

        self._state.status = IndexerStatus.PAUSED
        self._emit(
            EventType.INDEXER_PAUSED,
            IndexerPausedData(reason=reason, resume_after_seconds=None),
        )
        log.info("indexer_paused", reason=reason)

    async def resume(self):
        """Resume the indexer from paused state."""
        if self._state.status != IndexerStatus.PAUSED:
            return

        self._state.status = IndexerStatus.RUNNING
        log.info("indexer_resumed")
