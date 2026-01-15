"""Main orchestrator for running hierarchical tasks."""

import asyncio
import structlog
from pathlib import Path
from typing import Optional

from sindri.llm.client import OllamaClient
from sindri.llm.manager import ModelManager
from sindri.tools.registry import ToolRegistry
from sindri.persistence.state import SessionState
from sindri.core.tasks import Task, TaskStatus
from sindri.core.scheduler import TaskScheduler
from sindri.core.delegation import DelegationManager
from sindri.core.hierarchical import HierarchicalAgentLoop
from sindri.core.loop import LoopConfig
from sindri.memory.system import MuninnMemory
from sindri.memory.summarizer import ConversationSummarizer
from sindri.core.events import EventBus, Event, EventType

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
        work_dir: Optional[Path] = None
    ):
        self.client = client or OllamaClient()
        self.config = config or LoopConfig()
        self.event_bus = event_bus or EventBus()
        self.work_dir = work_dir

        # Initialize subsystems
        self.model_manager = ModelManager(total_vram_gb=total_vram_gb)
        self.scheduler = TaskScheduler(self.model_manager)
        self.state = SessionState()
        self.delegation = DelegationManager(self.scheduler, self.state)
        self.tools = ToolRegistry.default(work_dir=work_dir)

        # Initialize memory system if enabled
        if enable_memory:
            db_path = str(Path.home() / ".sindri" / "memory.db")
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self.memory = MuninnMemory(db_path)
            self.summarizer = ConversationSummarizer(self.client)
            log.info("memory_system_enabled", db_path=db_path)
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
            event_bus=self.event_bus
        )

        log.info("orchestrator_initialized", memory_enabled=enable_memory)

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

    async def run(self, user_request: str, parallel: bool = True) -> dict:
        """Run a user request through the hierarchical system.

        Args:
            user_request: The task to execute.
            parallel: If True, execute independent tasks concurrently (Phase 6.1).
                     If False, use sequential execution (legacy behavior).

        Returns:
            Dict with success status, task_id, result, and subtask count.
        """
        log.info("orchestrator_started",
                 request=user_request[:100],
                 parallel=parallel)

        # Create root task assigned to Brokkr (orchestrator)
        root_task = Task(
            description=user_request,
            task_type="orchestration",
            assigned_agent="brokkr",
            priority=0
        )

        # Add to scheduler
        self.scheduler.add_task(root_task)

        # Execute task queue
        while self.scheduler.has_work():
            # Check for cancellation
            if root_task.cancel_requested:
                log.info("orchestrator_cancelled", task_id=root_task.id)
                root_task.status = TaskStatus.CANCELLED
                return {
                    "success": False,
                    "task_id": root_task.id,
                    "error": "Task cancelled by user",
                    "output": "Task cancelled"
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
                "subtasks": len(root_task.subtask_ids)
            }
        else:
            log.error("orchestrator_failed",
                      task_id=root_task.id,
                      status=root_task.status.value,
                      error=root_task.error)
            return {
                "success": False,
                "task_id": root_task.id,
                "status": root_task.status.value,
                "error": root_task.error
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
                1 for t in self.scheduler.tasks.values()
                if t.status == TaskStatus.WAITING
            )

            if waiting_count > 0:
                log.info("waiting_for_subtasks", count=waiting_count)
                return "waiting"
            else:
                log.warning("no_tasks_ready",
                            pending=self.scheduler.get_pending_count())
                return "stuck"

        if len(batch) == 1:
            # Single task - run directly
            task = batch[0]
            log.info("executing_task",
                     task_id=task.id,
                     agent=task.assigned_agent,
                     description=task.description[:50])
            result = await self.loop.run_task(task)
            log.info("task_result",
                     task_id=task.id,
                     success=result.success,
                     iterations=result.iterations)
        else:
            # Multiple tasks - run in parallel
            log.info("executing_parallel_batch",
                     task_count=len(batch),
                     tasks=[t.id for t in batch])

            # Execute all tasks concurrently
            results = await asyncio.gather(
                *[self.loop.run_task(task) for task in batch],
                return_exceptions=True
            )

            # Log results
            for task, result in zip(batch, results):
                if isinstance(result, Exception):
                    log.error("task_exception",
                              task_id=task.id,
                              error=str(result))
                    task.status = TaskStatus.FAILED
                    task.error = str(result)
                else:
                    log.info("task_result",
                             task_id=task.id,
                             success=result.success,
                             iterations=result.iterations)

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
                1 for t in self.scheduler.tasks.values()
                if t.status == TaskStatus.WAITING
            )

            if waiting_count > 0:
                log.info("waiting_for_subtasks", count=waiting_count)
                return "waiting"
            else:
                log.warning("no_tasks_ready",
                            pending=self.scheduler.get_pending_count())
                return "stuck"

        log.info("executing_task",
                 task_id=next_task.id,
                 agent=next_task.assigned_agent,
                 description=next_task.description[:50])

        result = await self.loop.run_task(next_task)

        log.info("task_result",
                 task_id=next_task.id,
                 success=result.success,
                 iterations=result.iterations)

        return "ok"
