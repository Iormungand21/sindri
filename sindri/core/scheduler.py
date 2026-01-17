"""Task scheduler with priority queue and dependency resolution."""

from typing import Optional
import heapq
import structlog

from sindri.core.tasks import Task, TaskStatus
from sindri.llm.manager import ModelManager

log = structlog.get_logger()


class TaskScheduler:
    """Priority queue with dependency resolution and parallel execution support."""

    def __init__(self, model_manager: ModelManager):
        self.tasks: dict[str, Task] = {}
        self.pending: list[tuple[int, str]] = []  # (priority, task_id) heap
        self.model_manager = model_manager

        log.info("scheduler_initialized")

    def add_task(self, task: Task) -> str:
        """Add task to scheduler."""
        from sindri.agents.registry import AGENTS

        # Populate VRAM requirements from agent registry
        agent = AGENTS.get(task.assigned_agent)
        if agent:
            task.vram_required = agent.estimated_vram_gb
            task.model_name = agent.model

        self.tasks[task.id] = task
        heapq.heappush(self.pending, (task.priority, task.id))

        log.info(
            "task_added",
            task_id=task.id,
            priority=task.priority,
            agent=task.assigned_agent,
            vram_required=task.vram_required,
            description=task.description[:50],
        )

        return task.id

    def get_next_task(self) -> Optional[Task]:
        """Get next executable task."""

        not_ready = []

        while self.pending:
            priority, task_id = heapq.heappop(self.pending)
            task = self.tasks.get(task_id)

            if not task or task.status != TaskStatus.PENDING:
                continue

            if self._dependencies_satisfied(task) and self._resources_available(task):
                log.info(
                    "task_selected",
                    task_id=task.id,
                    priority=priority,
                    agent=task.assigned_agent,
                )
                # Put back non-ready tasks before returning
                for item in not_ready:
                    heapq.heappush(self.pending, item)
                return task

            # Not ready yet
            not_ready.append((priority, task_id))

        # Put back non-ready tasks
        for item in not_ready:
            heapq.heappush(self.pending, item)

        return None

    def get_ready_batch(self, max_vram: Optional[float] = None) -> list[Task]:
        """Get all tasks that can run in parallel within VRAM budget.

        This method implements the core parallel execution logic:
        1. Finds all tasks whose dependencies are satisfied
        2. Groups tasks that can fit within VRAM constraints
        3. Tasks sharing the same model only count VRAM once

        Args:
            max_vram: Maximum VRAM budget. If None, uses model_manager.available.

        Returns:
            List of tasks that can run concurrently.
        """
        if max_vram is None:
            max_vram = self.model_manager.available

        ready_tasks: list[Task] = []
        vram_allocated: float = 0.0
        models_used: set[str] = set()
        not_ready: list[tuple[int, str]] = []

        # Get currently loaded models - they don't need additional VRAM
        loaded_models = set(self.model_manager.loaded.keys())

        while self.pending:
            priority, task_id = heapq.heappop(self.pending)
            task = self.tasks.get(task_id)

            if not task or task.status != TaskStatus.PENDING:
                continue

            # Check dependencies
            if not self._dependencies_satisfied(task):
                not_ready.append((priority, task_id))
                continue

            # Check if task can run in parallel with already selected tasks
            can_add = True
            for selected in ready_tasks:
                if not task.can_run_parallel_with(selected):
                    can_add = False
                    break

            if not can_add:
                not_ready.append((priority, task_id))
                continue

            # Calculate VRAM needed for this task
            model = task.model_name
            vram_needed = task.vram_required

            if model in models_used or model in loaded_models:
                # Model already allocated or loaded - no additional VRAM needed
                vram_needed = 0.0

            # Check if we have VRAM budget
            if vram_allocated + vram_needed > max_vram:
                not_ready.append((priority, task_id))
                continue

            # Add task to batch
            ready_tasks.append(task)
            vram_allocated += vram_needed
            if model:
                models_used.add(model)

            log.debug(
                "task_added_to_batch",
                task_id=task.id,
                agent=task.assigned_agent,
                model=model,
                vram_needed=vram_needed,
                total_vram=vram_allocated,
            )

        # Put back non-ready tasks
        for item in not_ready:
            heapq.heappush(self.pending, item)

        if ready_tasks:
            log.info(
                "batch_ready",
                task_count=len(ready_tasks),
                vram_allocated=vram_allocated,
                models=list(models_used),
            )

        return ready_tasks

    def _dependencies_satisfied(self, task: Task) -> bool:
        """Check if all task dependencies are complete."""
        for dep_id in task.depends_on:
            dep = self.tasks.get(dep_id)
            if not dep or dep.status != TaskStatus.COMPLETE:
                log.debug(
                    "dependency_not_satisfied", task_id=task.id, waiting_for=dep_id
                )
                return False
        return True

    def _resources_available(self, task: Task) -> bool:
        """Check if resources are available for task."""
        from sindri.agents.registry import AGENTS

        agent = AGENTS.get(task.assigned_agent)
        if not agent:
            log.error("unknown_agent", agent=task.assigned_agent)
            return False

        can_load = self.model_manager.can_load(agent.model, agent.estimated_vram_gb)

        if not can_load:
            log.debug(
                "insufficient_resources",
                task_id=task.id,
                agent=agent.name,
                model=agent.model,
                required_vram=agent.estimated_vram_gb,
            )

        return can_load

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def update_task_status(self, task_id: str, status: TaskStatus):
        """Update task status."""
        task = self.tasks.get(task_id)
        if task:
            old_status = task.status
            task.status = status
            log.info(
                "task_status_updated",
                task_id=task_id,
                old_status=old_status.value,
                new_status=status.value,
            )

    def get_pending_count(self) -> int:
        """Get number of pending tasks."""
        return sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)

    def get_running_count(self) -> int:
        """Get number of running tasks."""
        return sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)

    def has_work(self) -> bool:
        """Check if there's any work to do."""
        return any(
            t.status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.WAITING)
            for t in self.tasks.values()
        )
