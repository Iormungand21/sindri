"""Main orchestrator for running hierarchical tasks."""

import asyncio
import structlog
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from sindri.llm.client import OllamaClient
from sindri.llm.router import ModelRouter
from sindri.llm.routing import RoutingPreferences, RoutingTaskCategory

if TYPE_CHECKING:
    from sindri.telemetry.collector import TelemetryCollector
from sindri.llm.manager import ModelManager
from sindri.tools.registry import ToolRegistry
from sindri.persistence.state import SessionState
from sindri.core.tasks import Task, TaskStatus
from sindri.core.scheduler import TaskScheduler
from sindri.core.delegation import DelegationManager
from sindri.core.hierarchical import HierarchicalAgentLoop
from sindri.core.loop import LoopConfig
from sindri.memory.system import MuninnMemory, get_context_budget
from sindri.memory.summarizer import ConversationSummarizer
from sindri.memory.global_memory import GlobalMemoryStore
from sindri.memory.background_indexer import BackgroundIndexer
from sindri.memory.projects import ProjectRegistry
from sindri.core.events import EventBus, Event, EventType
from sindri.config import SindriConfig

log = structlog.get_logger()


class Orchestrator:
    """Main orchestrator for hierarchical task execution."""

    def __init__(
        self,
        client: OllamaClient = None,
        config: LoopConfig = None,
        total_vram_gb: float = 16.0,
        enable_memory: bool = True,
        event_bus: Optional[EventBus] = None,
        work_dir: Optional[Path] = None,
        telemetry_collector: Optional["TelemetryCollector"] = None,
    ):
        self.client = client or OllamaClient()
        self.config = config or LoopConfig()
        self.event_bus = event_bus or EventBus()
        self.work_dir = work_dir

        # Initialize subsystems
        self.model_manager = ModelManager(total_vram_gb=total_vram_gb)
        self.scheduler = TaskScheduler(self.model_manager)
        self.state = SessionState()

        # Register with telemetry collector for live metrics
        self._telemetry_collector = telemetry_collector
        if telemetry_collector:
            telemetry_collector.register_model_manager(self.model_manager)
            telemetry_collector.register_scheduler(self.scheduler)
        # Phase 6.2: Pass model_manager for pre-warming during delegation
        self.delegation = DelegationManager(
            self.scheduler,
            self.state,
            model_manager=self.model_manager,
            event_bus=self.event_bus,
        )
        # Plan-First Execution: Pass event_bus to enable plan events
        self.tools = ToolRegistry.default(work_dir=work_dir, event_bus=self.event_bus)

        # Initialize memory system if enabled (with default config)
        # Context budget will be adjusted on first run based on model
        self._enable_memory = enable_memory
        self._memory_db_path = str(Path.home() / ".sindri" / "memory.db")
        self._context_configured = False
        self._model_context_length = 4096  # Default, updated in configure_for_model

        # Load config for indexer settings
        self._sindri_config = SindriConfig.load()

        # ROADMAP Item 4: Global memory and background indexer
        self.global_memory: Optional[GlobalMemoryStore] = None
        self.project_registry: Optional[ProjectRegistry] = None
        self.background_indexer: Optional[BackgroundIndexer] = None

        if enable_memory:
            Path(self._memory_db_path).parent.mkdir(parents=True, exist_ok=True)

            # Initialize project registry and global memory store
            self.project_registry = ProjectRegistry()
            self.global_memory = GlobalMemoryStore(registry=self.project_registry)

            # Start with default config - will be adjusted in configure_for_model()
            # Pass global_memory for cross-project context injection
            self.memory = MuninnMemory(
                self._memory_db_path, global_memory=self.global_memory
            )
            self.summarizer = ConversationSummarizer(self.client)

            # Initialize background indexer if enabled
            # Note: BackgroundIndexer has its own IndexerConfig dataclass,
            # but SindriConfig.memory.indexer (IndexerConfig pydantic model) has
            # compatible fields. We pass the indexer config, not full SindriConfig.
            if self._sindri_config.memory.indexer.enabled:
                from sindri.memory.background_indexer import IndexerConfig as BGIndexerConfig

                # Convert pydantic IndexerConfig to dataclass IndexerConfig
                bg_config = BGIndexerConfig(
                    enabled=self._sindri_config.memory.indexer.enabled,
                    auto_start=self._sindri_config.memory.indexer.auto_start,
                    schedule_interval_minutes=self._sindri_config.memory.indexer.schedule_interval_minutes,
                    max_vram_percent=self._sindri_config.memory.indexer.max_vram_percent,
                    cooldown_seconds=self._sindri_config.memory.indexer.cooldown_seconds,
                )
                self.background_indexer = BackgroundIndexer(
                    global_memory=self.global_memory,
                    registry=self.project_registry,
                    event_bus=self.event_bus,
                    config=bg_config,
                )

            log.info(
                "memory_system_enabled",
                db_path=self._memory_db_path,
                indexer_enabled=self._sindri_config.memory.indexer.enabled,
                indexer_auto_start=self._sindri_config.memory.indexer.auto_start,
            )
        else:
            self.memory = None
            self.summarizer = None

        # Create hierarchical loop
        self.loop = HierarchicalAgentLoop(
            client=self.client,
            tools=self.tools,
            state=self.state,
            scheduler=self.scheduler,
            delegation=self.delegation,
            config=self.config,
            memory=self.memory,
            summarizer=self.summarizer,
            event_bus=self.event_bus,
        )

        # ROADMAP Item 10: Model-aware routing
        self.router: Optional[ModelRouter] = None
        if self._sindri_config.routing.enabled:
            preferences = self._load_routing_preferences()
            self.router = ModelRouter(
                model_manager=self.model_manager,
                preferences=preferences,
            )
            # Pass router to the loop
            self.loop.router = self.router
            self.loop._routing_enabled = True
            log.info(
                "model_router_enabled",
                speed_preference=preferences.speed_preference,
            )

        # Plan-First Execution: Subscribe to plan approval/rejection events
        self.event_bus.subscribe(EventType.PLAN_APPROVED, self._handle_plan_approved)
        self.event_bus.subscribe(EventType.PLAN_REJECTED, self._handle_plan_rejected)

        log.info("orchestrator_initialized", memory_enabled=enable_memory)

    async def start_background_indexer(self) -> bool:
        """Start the background indexer if not already running.

        Returns:
            True if indexer was started, False if already running or not available.
        """
        if not self.background_indexer:
            log.warning("background_indexer_not_available")
            return False

        if self.background_indexer.is_running:
            log.debug("background_indexer_already_running")
            return False

        await self.background_indexer.start()
        log.info("background_indexer_started")
        return True

    async def stop_background_indexer(self) -> bool:
        """Stop the background indexer if running.

        Returns:
            True if indexer was stopped, False if not running.
        """
        if not self.background_indexer or not self.background_indexer.is_running:
            return False

        await self.background_indexer.stop()
        log.info("background_indexer_stopped")
        return True

    def _handle_plan_approved(self, data: dict):
        """Handle PLAN_APPROVED event - resume waiting task.

        This is called synchronously by EventBus, so we schedule the
        async DelegationManager call.
        """
        task_id = data.get("task_id")
        plan_id = data.get("plan_id")
        if task_id and plan_id:
            asyncio.create_task(self.delegation.plan_approved(task_id, plan_id))

    def _handle_plan_rejected(self, data: dict):
        """Handle PLAN_REJECTED event - fail waiting task.

        This is called synchronously by EventBus, so we schedule the
        async DelegationManager call.
        """
        task_id = data.get("task_id")
        plan_id = data.get("plan_id")
        reason = data.get("reason")
        if task_id and plan_id:
            asyncio.create_task(self.delegation.plan_rejected(task_id, plan_id, reason))

    def _load_routing_preferences(self) -> RoutingPreferences:
        """Load routing preferences from config and active project.

        Combines global config settings with per-project overrides.

        Returns:
            RoutingPreferences for the router
        """
        # Start with global config defaults
        prefs = RoutingPreferences(
            speed_preference=self._sindri_config.routing.speed_preference,
            min_quality_score=self._sindri_config.routing.min_quality_score,
        )

        # Overlay project-specific preferences if work_dir is set
        if self.project_registry and self.work_dir:
            project = self.project_registry.get_project(str(self.work_dir))
            if project and project.routing_preferences:
                proj_prefs = project.routing_preferences
                # Merge model overrides
                for category_str, model in proj_prefs.model_overrides.items():
                    try:
                        category = RoutingTaskCategory(category_str)
                        prefs.model_overrides[category] = model
                    except ValueError:
                        log.warning("unknown_routing_category", category=category_str)
                # Merge locked models
                prefs.locked_models.update(proj_prefs.locked_models)
                # Override speed preference if set
                if proj_prefs.speed_preference is not None:
                    prefs.speed_preference = proj_prefs.speed_preference

                log.debug(
                    "routing_preferences_loaded",
                    project=project.name,
                    overrides=len(prefs.model_overrides),
                    locked=len(prefs.locked_models),
                )

        return prefs

    def cancel_task(self, task_id: str):
        """Request cancellation of a task and its subtasks."""
        task = self.scheduler.tasks.get(task_id)
        if task:
            log.info("task_cancellation_requested", task_id=task_id)
            task.cancel_requested = True

            # Cancel all subtasks recursively
            for subtask_id in task.subtask_ids:
                self.cancel_task(subtask_id)

    def cancel_all(self):
        """Cancel all tasks in the scheduler."""
        log.info("cancel_all_tasks_requested")
        for task_id in list(self.scheduler.tasks.keys()):
            self.cancel_task(task_id)

    async def cleanup(self) -> None:
        """Clean up orchestrator resources.

        Unregisters from telemetry and stops background indexer.
        Should be called when the orchestrator is no longer needed.
        """
        # Unregister from telemetry collector
        if self._telemetry_collector:
            self._telemetry_collector.unregister_model_manager(self.model_manager)
            self._telemetry_collector.unregister_scheduler(self.scheduler)
            log.debug("orchestrator_unregistered_from_telemetry")

        # Stop background indexer if running
        if self.background_indexer and self.background_indexer.is_running:
            await self.background_indexer.stop()

        log.info("orchestrator_cleanup_complete")

    async def configure_for_model(self, model: str) -> None:
        """Configure memory system based on model's context length.

        This queries the model's context window size and adjusts the memory
        configuration to avoid overflowing the context. Should be called
        before running tasks, or will be auto-called on first run().

        Args:
            model: The model name to configure for
        """
        if self._context_configured:
            return

        if not self._enable_memory or not self.memory:
            self._context_configured = True
            return

        try:
            # Get model info from Ollama
            model_info = await self.client.get_model_info(model)
            context_length = model_info.get("context_length", 4096)

            # Store for passing to Ollama API calls
            self._model_context_length = context_length

            # Create appropriately-sized memory config
            memory_config = get_context_budget(context_length)

            # Update memory config with indexer settings from SindriConfig
            memory_config.enable_active_projects = (
                self._sindri_config.memory.indexer.include_active_in_context
            )
            memory_config.active_project_tokens = (
                self._sindri_config.memory.indexer.active_project_budget_tokens
            )

            # Reinitialize memory with new config (pass global_memory for cross-project context)
            self.memory = MuninnMemory(
                self._memory_db_path, memory_config, global_memory=self.global_memory
            )

            # Update the loop's memory reference and context length
            self.loop.memory = self.memory
            self.loop.model_context_length = context_length

            log.info(
                "context_configured",
                model=model,
                context_length=context_length,
                max_context_tokens=memory_config.max_context_tokens,
                episodic_limit=memory_config.episodic_limit,
                semantic_limit=memory_config.semantic_limit,
            )

        except Exception as e:
            log.warning(
                "context_configuration_failed",
                model=model,
                error=str(e),
                fallback="using_defaults",
            )

        self._context_configured = True

    async def run(
        self,
        user_request: str,
        parallel: bool = True,
        root_agent: str = "brokkr",
    ) -> dict:
        """Run a user request through the hierarchical system.

        Args:
            user_request: The task to execute.
            parallel: If True, execute independent tasks concurrently (Phase 6.1).
                     If False, use sequential execution (legacy behavior).
            root_agent: Agent to use for root task (default: brokkr).

        Returns:
            Dict with success status, task_id, result, and subtask count.
        """
        log.info(
            "orchestrator_started",
            request=user_request[:100],
            parallel=parallel,
            root_agent=root_agent,
        )

        # ROADMAP Item 4: Auto-start background indexer if configured
        if (
            self.background_indexer
            and self._sindri_config.memory.indexer.auto_start
            and not self.background_indexer.is_running
        ):
            await self.start_background_indexer()

        # Auto-configure memory for the root agent's model context size
        # This prevents context overflow with small-context models
        from sindri.agents.registry import AGENTS
        agent_def = AGENTS.get(root_agent, AGENTS.get("brokkr", {}))
        if hasattr(agent_def, "model"):
            await self.configure_for_model(agent_def.model)

        # Create root task assigned to specified agent
        root_task = Task(
            description=user_request,
            task_type="orchestration",
            assigned_agent=root_agent,
            priority=0,
        )

        # Emit task created event for UI clients
        self.event_bus.emit(
            Event(
                type=EventType.TASK_CREATED,
                data={
                    "task_id": root_task.id,
                    "description": root_task.description,
                    "status": root_task.status.value,
                    "parent_id": None,
                    "agent": root_task.assigned_agent,
                },
            )
        )

        # Add to scheduler
        self.scheduler.add_task(root_task)

        # Execute task queue
        while self.scheduler.has_work():
            # Check for cancellation
            if root_task.cancel_requested:
                log.info("orchestrator_cancelled", task_id=root_task.id)
                root_task.status = TaskStatus.CANCELLED
                # Update session status to cancelled
                if root_task.session_id:
                    await self.state.cancel_session(
                        root_task.session_id, "Task cancelled by user"
                    )
                return {
                    "success": False,
                    "task_id": root_task.id,
                    "error": "Task cancelled by user",
                    "output": "Task cancelled",
                }

            if parallel:
                # Phase 6.1: Parallel execution
                result = await self._run_parallel_batch()
            else:
                # Legacy sequential execution
                result = await self._run_sequential()

            if result == "waiting":
                await asyncio.sleep(0.5)
                continue
            elif result == "stuck":
                break

        # Check root task status
        if root_task.status == TaskStatus.COMPLETE:
            log.info("orchestrator_success", task_id=root_task.id)
            return {
                "success": True,
                "task_id": root_task.id,
                "result": root_task.result,
                "subtasks": len(root_task.subtask_ids),
            }
        else:
            log.error(
                "orchestrator_failed",
                task_id=root_task.id,
                status=root_task.status.value,
                error=root_task.error,
            )
            return {
                "success": False,
                "task_id": root_task.id,
                "status": root_task.status.value,
                "error": root_task.error,
            }

    async def _run_parallel_batch(self) -> str:
        """Execute a batch of tasks in parallel.

        Returns:
            "ok" if tasks were executed,
            "waiting" if waiting on subtasks,
            "stuck" if no progress possible.
        """
        # Get batch of ready tasks
        batch = self.scheduler.get_ready_batch()

        if not batch:
            # No tasks ready - check if we're waiting
            waiting_count = sum(
                1
                for t in self.scheduler.tasks.values()
                if t.status == TaskStatus.WAITING
            )

            if waiting_count > 0:
                log.info("waiting_for_subtasks", count=waiting_count)
                return "waiting"
            else:
                log.warning(
                    "no_tasks_ready", pending=self.scheduler.get_pending_count()
                )
                return "stuck"

        if len(batch) == 1:
            # Single task - run directly with exception handling
            task = batch[0]
            log.info(
                "executing_task",
                task_id=task.id,
                agent=task.assigned_agent,
                description=task.description[:50],
            )
            try:
                result = await self.loop.run_task(task)
                log.info(
                    "task_result",
                    task_id=task.id,
                    success=result.success,
                    iterations=result.iterations,
                )
            except Exception as e:
                log.error("task_exception", task_id=task.id, error=str(e))
                task.status = TaskStatus.FAILED
                task.error = str(e)

                # Update session status to failed
                if task.session_id:
                    await self.state.fail_session(task.session_id, str(e))

                # Notify parent task of failure (if this is a child task)
                await self.delegation.child_failed(task)

                # Emit error event for TUI/logging
                self.event_bus.emit(
                    Event(
                        type=EventType.ERROR,
                        data={
                            "task_id": task.id,
                            "error": str(e),
                            "error_type": "task_exception",
                            "agent": task.assigned_agent,
                            "description": task.description[:100],
                        },
                    )
                )
        else:
            # Multiple tasks - run in parallel
            log.info(
                "executing_parallel_batch",
                task_count=len(batch),
                tasks=[t.id for t in batch],
            )

            # Execute all tasks concurrently
            results = await asyncio.gather(
                *[self.loop.run_task(task) for task in batch], return_exceptions=True
            )

            # Log results and handle failures
            for task, result in zip(batch, results):
                if isinstance(result, Exception):
                    log.error("task_exception", task_id=task.id, error=str(result))
                    task.status = TaskStatus.FAILED
                    task.error = str(result)

                    # Update session status to failed
                    if task.session_id:
                        await self.state.fail_session(task.session_id, str(result))

                    # Notify parent task of failure (if this is a child task)
                    await self.delegation.child_failed(task)

                    # Emit error event for TUI/logging
                    self.event_bus.emit(
                        Event(
                            type=EventType.ERROR,
                            data={
                                "task_id": task.id,
                                "error": str(result),
                                "error_type": "parallel_task_exception",
                                "agent": task.assigned_agent,
                                "description": task.description[:100],
                            },
                        )
                    )
                else:
                    log.info(
                        "task_result",
                        task_id=task.id,
                        success=result.success,
                        iterations=result.iterations,
                    )

        return "ok"

    async def _run_sequential(self) -> str:
        """Execute tasks sequentially (legacy behavior).

        Returns:
            "ok" if a task was executed,
            "waiting" if waiting on subtasks,
            "stuck" if no progress possible.
        """
        next_task = self.scheduler.get_next_task()

        if next_task is None:
            waiting_count = sum(
                1
                for t in self.scheduler.tasks.values()
                if t.status == TaskStatus.WAITING
            )

            if waiting_count > 0:
                log.info("waiting_for_subtasks", count=waiting_count)
                return "waiting"
            else:
                log.warning(
                    "no_tasks_ready", pending=self.scheduler.get_pending_count()
                )
                return "stuck"

        log.info(
            "executing_task",
            task_id=next_task.id,
            agent=next_task.assigned_agent,
            description=next_task.description[:50],
        )

        try:
            result = await self.loop.run_task(next_task)
            log.info(
                "task_result",
                task_id=next_task.id,
                success=result.success,
                iterations=result.iterations,
            )
        except Exception as e:
            log.error("task_exception", task_id=next_task.id, error=str(e))
            next_task.status = TaskStatus.FAILED
            next_task.error = str(e)

            # Update session status to failed
            if next_task.session_id:
                await self.state.fail_session(next_task.session_id, str(e))

            # Notify parent task of failure (if this is a child task)
            await self.delegation.child_failed(next_task)

            # Emit error event for TUI/logging
            self.event_bus.emit(
                Event(
                    type=EventType.ERROR,
                    data={
                        "task_id": next_task.id,
                        "error": str(e),
                        "error_type": "sequential_task_exception",
                        "agent": next_task.assigned_agent,
                        "description": next_task.description[:100],
                    },
                )
            )

        return "ok"
