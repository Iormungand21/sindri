"""Task scheduler with priority queue and dependency resolution."""

from typing import Optional
import heapq
import structlog

from sindri.core.tasks import Task, TaskStatus
from sindri.llm.manager import ModelManager

log = structlog.get_logger()


class TaskScheduler:
    """Priority queue with dependency resolution."""

    def __init__(self, model_manager: ModelManager):
        self.tasks: dict[str, Task] = {}
        self.pending: list[tuple[int, str]] = []  # (priority, task_id) heap
        self.model_manager = model_manager

        log.info("scheduler_initialized")

    def add_task(self, task: Task) -> str:
        """Add task to scheduler."""
        self.tasks[task.id] = task
        heapq.heappush(self.pending, (task.priority, task.id))

        log.info("task_added",
                 task_id=task.id,
                 priority=task.priority,
                 agent=task.assigned_agent,
                 description=task.description[:50])

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
                log.info("task_selected",
                         task_id=task.id,
                         priority=priority,
                         agent=task.assigned_agent)
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

    def _dependencies_satisfied(self, task: Task) -> bool:
        """Check if all task dependencies are complete."""
        for dep_id in task.depends_on:
            dep = self.tasks.get(dep_id)
            if not dep or dep.status != TaskStatus.COMPLETE:
                log.debug("dependency_not_satisfied",
                          task_id=task.id,
                          waiting_for=dep_id)
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
            log.debug("insufficient_resources",
                      task_id=task.id,
                      agent=agent.name,
                      model=agent.model,
                      required_vram=agent.estimated_vram_gb)

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
            log.info("task_status_updated",
                     task_id=task_id,
                     old_status=old_status.value,
                     new_status=status.value)

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
