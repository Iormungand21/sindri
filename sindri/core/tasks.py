"""Task data model for Sindri."""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    PLANNING = "planning"
    WAITING = "waiting"       # Waiting on subtask
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Task:
    """A hierarchical task that can spawn subtasks."""

    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_id: Optional[str] = None

    # Description
    description: str = ""
    task_type: str = "general"        # plan, code, review, execute
    assigned_agent: str = "brokkr"

    # Status
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 1

    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Hierarchy
    subtask_ids: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)

    # Data
    context: dict = field(default_factory=dict)
    result: Optional[dict] = None
    error: Optional[str] = None
    session_id: Optional[str] = None  # Link to session for resuming

    def add_subtask(self, subtask_id: str):
        """Add a subtask to this task."""
        if subtask_id not in self.subtask_ids:
            self.subtask_ids.append(subtask_id)

    def add_dependency(self, task_id: str):
        """Add a task dependency."""
        if task_id not in self.depends_on:
            self.depends_on.append(task_id)

    def is_ready(self, all_tasks: dict[str, "Task"]) -> bool:
        """Check if task is ready to execute."""
        if self.status != TaskStatus.PENDING:
            return False

        # Check all dependencies are complete
        for dep_id in self.depends_on:
            dep = all_tasks.get(dep_id)
            if not dep or dep.status != TaskStatus.COMPLETE:
                return False

        return True

    def has_pending_subtasks(self, all_tasks: dict[str, "Task"]) -> bool:
        """Check if task has incomplete subtasks."""
        for subtask_id in self.subtask_ids:
            subtask = all_tasks.get(subtask_id)
            if subtask and subtask.status not in (TaskStatus.COMPLETE, TaskStatus.FAILED):
                return True
        return False
