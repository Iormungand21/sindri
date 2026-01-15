"""Performance metrics tracking for Sindri sessions.

Phase 5.5: Track task duration, iteration timing, tool execution, and model loading.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Any
import structlog

log = structlog.get_logger()


@dataclass
class ToolExecutionMetrics:
    """Metrics for a single tool execution."""

    tool_name: str
    start_time: float
    end_time: float
    success: bool
    arguments: Optional[dict] = None

    @property
    def duration_seconds(self) -> float:
        """Get execution duration in seconds."""
        return self.end_time - self.start_time

    @property
    def duration_ms(self) -> float:
        """Get execution duration in milliseconds."""
        return self.duration_seconds * 1000


@dataclass
class IterationMetrics:
    """Metrics for a single agent iteration."""

    iteration_number: int
    start_time: float
    end_time: float
    agent_name: str
    model_name: str
    tool_executions: list[ToolExecutionMetrics] = field(default_factory=list)
    tokens_generated: int = 0

    @property
    def duration_seconds(self) -> float:
        """Get iteration duration in seconds."""
        return self.end_time - self.start_time

    @property
    def tool_count(self) -> int:
        """Number of tools executed in this iteration."""
        return len(self.tool_executions)

    @property
    def total_tool_time(self) -> float:
        """Total time spent executing tools in seconds."""
        return sum(t.duration_seconds for t in self.tool_executions)

    @property
    def llm_time(self) -> float:
        """Estimated LLM inference time (total - tool time)."""
        return max(0, self.duration_seconds - self.total_tool_time)


@dataclass
class TaskMetrics:
    """Aggregate metrics for a single task."""

    task_id: str
    task_description: str
    agent_name: str
    model_name: str
    start_time: float
    end_time: Optional[float] = None
    status: str = "running"
    iterations: list[IterationMetrics] = field(default_factory=list)
    model_load_time: float = 0.0  # Time spent loading the model

    @property
    def duration_seconds(self) -> float:
        """Get total task duration in seconds."""
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time

    @property
    def iteration_count(self) -> int:
        """Number of iterations completed."""
        return len(self.iterations)

    @property
    def total_tool_executions(self) -> int:
        """Total tool executions across all iterations."""
        return sum(i.tool_count for i in self.iterations)

    @property
    def total_tool_time(self) -> float:
        """Total time spent on tool execution in seconds."""
        return sum(i.total_tool_time for i in self.iterations)

    @property
    def total_llm_time(self) -> float:
        """Total time spent on LLM inference in seconds."""
        return sum(i.llm_time for i in self.iterations)

    @property
    def avg_iteration_time(self) -> float:
        """Average time per iteration in seconds."""
        if not self.iterations:
            return 0.0
        return sum(i.duration_seconds for i in self.iterations) / len(self.iterations)

    def get_tool_breakdown(self) -> dict[str, dict]:
        """Get breakdown of tool usage with counts and times."""
        breakdown = {}
        for iteration in self.iterations:
            for tool in iteration.tool_executions:
                if tool.tool_name not in breakdown:
                    breakdown[tool.tool_name] = {
                        "count": 0,
                        "total_time": 0.0,
                        "successes": 0,
                        "failures": 0
                    }
                breakdown[tool.tool_name]["count"] += 1
                breakdown[tool.tool_name]["total_time"] += tool.duration_seconds
                if tool.success:
                    breakdown[tool.tool_name]["successes"] += 1
                else:
                    breakdown[tool.tool_name]["failures"] += 1

        # Calculate averages
        for tool_name, data in breakdown.items():
            data["avg_time"] = data["total_time"] / data["count"] if data["count"] > 0 else 0.0

        return breakdown


@dataclass
class SessionMetrics:
    """Complete metrics for a Sindri session."""

    session_id: str
    task_description: str
    model_name: str
    start_time: float
    end_time: Optional[float] = None
    status: str = "active"
    tasks: list[TaskMetrics] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        """Total session duration in seconds."""
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time

    @property
    def total_iterations(self) -> int:
        """Total iterations across all tasks."""
        return sum(t.iteration_count for t in self.tasks)

    @property
    def total_tool_executions(self) -> int:
        """Total tool executions across all tasks."""
        return sum(t.total_tool_executions for t in self.tasks)

    @property
    def total_tool_time(self) -> float:
        """Total tool execution time in seconds."""
        return sum(t.total_tool_time for t in self.tasks)

    @property
    def total_llm_time(self) -> float:
        """Total LLM inference time in seconds."""
        return sum(t.total_llm_time for t in self.tasks)

    @property
    def total_model_load_time(self) -> float:
        """Total time spent loading models in seconds."""
        return sum(t.model_load_time for t in self.tasks)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary dictionary of session metrics."""
        return {
            "session_id": self.session_id,
            "status": self.status,
            "duration_seconds": round(self.duration_seconds, 2),
            "duration_formatted": self._format_duration(self.duration_seconds),
            "total_tasks": len(self.tasks),
            "total_iterations": self.total_iterations,
            "total_tool_executions": self.total_tool_executions,
            "time_breakdown": {
                "llm_inference": round(self.total_llm_time, 2),
                "tool_execution": round(self.total_tool_time, 2),
                "model_loading": round(self.total_model_load_time, 2),
            },
            "avg_iteration_time": round(
                sum(t.avg_iteration_time for t in self.tasks) / len(self.tasks), 2
            ) if self.tasks else 0.0,
        }

    def get_tool_breakdown(self) -> dict[str, dict]:
        """Get combined tool breakdown across all tasks."""
        combined = {}
        for task in self.tasks:
            task_breakdown = task.get_tool_breakdown()
            for tool_name, data in task_breakdown.items():
                if tool_name not in combined:
                    combined[tool_name] = {
                        "count": 0,
                        "total_time": 0.0,
                        "successes": 0,
                        "failures": 0
                    }
                combined[tool_name]["count"] += data["count"]
                combined[tool_name]["total_time"] += data["total_time"]
                combined[tool_name]["successes"] += data["successes"]
                combined[tool_name]["failures"] += data["failures"]

        # Calculate averages
        for tool_name, data in combined.items():
            data["avg_time"] = data["total_time"] / data["count"] if data["count"] > 0 else 0.0

        return combined

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration as human-readable string."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.0f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        return {
            "session_id": self.session_id,
            "task_description": self.task_description,
            "model_name": self.model_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "status": self.status,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "task_description": task.task_description,
                    "agent_name": task.agent_name,
                    "model_name": task.model_name,
                    "start_time": task.start_time,
                    "end_time": task.end_time,
                    "status": task.status,
                    "model_load_time": task.model_load_time,
                    "iterations": [
                        {
                            "iteration_number": it.iteration_number,
                            "start_time": it.start_time,
                            "end_time": it.end_time,
                            "agent_name": it.agent_name,
                            "model_name": it.model_name,
                            "tokens_generated": it.tokens_generated,
                            "tool_executions": [
                                {
                                    "tool_name": te.tool_name,
                                    "start_time": te.start_time,
                                    "end_time": te.end_time,
                                    "success": te.success,
                                    "arguments": te.arguments
                                }
                                for te in it.tool_executions
                            ]
                        }
                        for it in task.iterations
                    ]
                }
                for task in self.tasks
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionMetrics":
        """Deserialize from dictionary."""
        tasks = []
        for task_data in data.get("tasks", []):
            iterations = []
            for it_data in task_data.get("iterations", []):
                tool_executions = [
                    ToolExecutionMetrics(
                        tool_name=te["tool_name"],
                        start_time=te["start_time"],
                        end_time=te["end_time"],
                        success=te["success"],
                        arguments=te.get("arguments")
                    )
                    for te in it_data.get("tool_executions", [])
                ]
                iterations.append(IterationMetrics(
                    iteration_number=it_data["iteration_number"],
                    start_time=it_data["start_time"],
                    end_time=it_data["end_time"],
                    agent_name=it_data["agent_name"],
                    model_name=it_data["model_name"],
                    tokens_generated=it_data.get("tokens_generated", 0),
                    tool_executions=tool_executions
                ))

            tasks.append(TaskMetrics(
                task_id=task_data["task_id"],
                task_description=task_data["task_description"],
                agent_name=task_data["agent_name"],
                model_name=task_data["model_name"],
                start_time=task_data["start_time"],
                end_time=task_data.get("end_time"),
                status=task_data.get("status", "completed"),
                model_load_time=task_data.get("model_load_time", 0.0),
                iterations=iterations
            ))

        return cls(
            session_id=data["session_id"],
            task_description=data["task_description"],
            model_name=data["model_name"],
            start_time=data["start_time"],
            end_time=data.get("end_time"),
            status=data.get("status", "completed"),
            tasks=tasks
        )


class MetricsCollector:
    """Collects and manages metrics during task execution.

    This class provides a simple interface for collecting metrics
    during task execution and storing them to the database.
    """

    def __init__(self, session_id: str, task_description: str, model_name: str):
        """Initialize a new metrics collector for a session."""
        self.session_metrics = SessionMetrics(
            session_id=session_id,
            task_description=task_description,
            model_name=model_name,
            start_time=time.time()
        )
        self._current_task: Optional[TaskMetrics] = None
        self._current_iteration: Optional[IterationMetrics] = None
        self._iteration_start: Optional[float] = None

    def start_task(
        self,
        task_id: str,
        description: str,
        agent_name: str,
        model_name: str,
        model_load_time: float = 0.0
    ):
        """Start tracking a new task."""
        self._current_task = TaskMetrics(
            task_id=task_id,
            task_description=description,
            agent_name=agent_name,
            model_name=model_name,
            start_time=time.time(),
            model_load_time=model_load_time
        )
        log.debug("metrics_task_started", task_id=task_id, agent=agent_name)

    def start_iteration(self, iteration_number: int, agent_name: str, model_name: str):
        """Start tracking a new iteration."""
        self._iteration_start = time.time()
        self._current_iteration = IterationMetrics(
            iteration_number=iteration_number,
            start_time=self._iteration_start,
            end_time=0.0,  # Will be set when iteration ends
            agent_name=agent_name,
            model_name=model_name
        )
        log.debug("metrics_iteration_started", iteration=iteration_number)

    def record_tool_execution(
        self,
        tool_name: str,
        start_time: float,
        end_time: float,
        success: bool,
        arguments: Optional[dict] = None
    ):
        """Record a tool execution."""
        if self._current_iteration:
            tool_metrics = ToolExecutionMetrics(
                tool_name=tool_name,
                start_time=start_time,
                end_time=end_time,
                success=success,
                arguments=arguments
            )
            self._current_iteration.tool_executions.append(tool_metrics)
            log.debug("metrics_tool_recorded",
                     tool=tool_name,
                     duration_ms=tool_metrics.duration_ms)

    def end_iteration(self, tokens_generated: int = 0):
        """End the current iteration."""
        if self._current_iteration and self._current_task:
            self._current_iteration.end_time = time.time()
            self._current_iteration.tokens_generated = tokens_generated
            self._current_task.iterations.append(self._current_iteration)
            log.debug("metrics_iteration_ended",
                     iteration=self._current_iteration.iteration_number,
                     duration=self._current_iteration.duration_seconds)
            self._current_iteration = None

    def end_task(self, status: str = "completed"):
        """End the current task."""
        if self._current_task:
            self._current_task.end_time = time.time()
            self._current_task.status = status
            self.session_metrics.tasks.append(self._current_task)
            log.debug("metrics_task_ended",
                     task_id=self._current_task.task_id,
                     duration=self._current_task.duration_seconds,
                     iterations=self._current_task.iteration_count)
            self._current_task = None

    def end_session(self, status: str = "completed"):
        """Finalize the session metrics."""
        # End any in-progress iteration
        if self._current_iteration:
            self.end_iteration()

        # End any in-progress task
        if self._current_task:
            self.end_task(status="incomplete")

        self.session_metrics.end_time = time.time()
        self.session_metrics.status = status
        log.info("metrics_session_ended",
                session_id=self.session_metrics.session_id,
                duration=self.session_metrics.duration_seconds,
                tasks=len(self.session_metrics.tasks))

    def get_metrics(self) -> SessionMetrics:
        """Get the collected session metrics."""
        return self.session_metrics

    def get_current_task_duration(self) -> float:
        """Get duration of current task (for real-time display)."""
        if self._current_task:
            return time.time() - self._current_task.start_time
        return 0.0

    def get_session_duration(self) -> float:
        """Get current session duration (for real-time display)."""
        return time.time() - self.session_metrics.start_time


class MetricsStore:
    """Storage backend for session metrics using SQLite."""

    def __init__(self, database=None):
        """Initialize the metrics store.

        Args:
            database: Database instance. If None, creates a new one.
        """
        from sindri.persistence.database import Database
        self.db = database or Database()

    async def save_metrics(self, metrics: SessionMetrics):
        """Save session metrics to database.

        Args:
            metrics: The SessionMetrics to save.
        """
        await self.db.initialize()

        metrics_json = json.dumps(metrics.to_dict())
        summary = metrics.get_summary()

        async with self.db.get_connection() as conn:
            # Use REPLACE to handle updates
            await conn.execute(
                """
                INSERT OR REPLACE INTO session_metrics
                (session_id, metrics_json, duration_seconds, total_iterations,
                 total_tool_executions, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, COALESCE(
                    (SELECT created_at FROM session_metrics WHERE session_id = ?),
                    CURRENT_TIMESTAMP
                ), CURRENT_TIMESTAMP)
                """,
                (
                    metrics.session_id,
                    metrics_json,
                    summary["duration_seconds"],
                    summary["total_iterations"],
                    summary["total_tool_executions"],
                    metrics.session_id  # For the subquery
                )
            )
            await conn.commit()

        log.info("metrics_saved",
                session_id=metrics.session_id,
                duration=summary["duration_seconds"],
                iterations=summary["total_iterations"])

    async def load_metrics(self, session_id: str) -> Optional[SessionMetrics]:
        """Load session metrics from database.

        Args:
            session_id: The session ID to load metrics for.

        Returns:
            SessionMetrics if found, None otherwise.
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                "SELECT metrics_json FROM session_metrics WHERE session_id = ?",
                (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                data = json.loads(row[0])
                return SessionMetrics.from_dict(data)

    async def list_metrics(self, limit: int = 20) -> list[dict]:
        """List recent session metrics summaries.

        Args:
            limit: Maximum number of results.

        Returns:
            List of metrics summary dictionaries.
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT sm.session_id, sm.duration_seconds, sm.total_iterations,
                       sm.total_tool_executions, sm.created_at,
                       s.task, s.model, s.status
                FROM session_metrics sm
                LEFT JOIN sessions s ON sm.session_id = s.id
                ORDER BY sm.created_at DESC
                LIMIT ?
                """,
                (limit,)
            ) as cursor:
                results = []
                async for row in cursor:
                    results.append({
                        "session_id": row[0],
                        "duration_seconds": row[1],
                        "total_iterations": row[2],
                        "total_tool_executions": row[3],
                        "created_at": row[4],
                        "task": row[5] or "Unknown",
                        "model": row[6] or "Unknown",
                        "status": row[7] or "Unknown"
                    })
                return results

    async def get_aggregate_stats(self) -> dict:
        """Get aggregate statistics across all sessions.

        Returns:
            Dictionary with aggregate stats.
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT
                    COUNT(*) as total_sessions,
                    SUM(duration_seconds) as total_duration,
                    AVG(duration_seconds) as avg_duration,
                    SUM(total_iterations) as total_iterations,
                    AVG(total_iterations) as avg_iterations,
                    SUM(total_tool_executions) as total_tool_executions
                FROM session_metrics
                """
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "total_sessions": row[0] or 0,
                        "total_duration_seconds": row[1] or 0.0,
                        "avg_duration_seconds": row[2] or 0.0,
                        "total_iterations": row[3] or 0,
                        "avg_iterations": row[4] or 0.0,
                        "total_tool_executions": row[5] or 0
                    }
                return {
                    "total_sessions": 0,
                    "total_duration_seconds": 0.0,
                    "avg_duration_seconds": 0.0,
                    "total_iterations": 0,
                    "avg_iterations": 0.0,
                    "total_tool_executions": 0
                }

    async def delete_metrics(self, session_id: str) -> bool:
        """Delete metrics for a session.

        Args:
            session_id: The session ID to delete metrics for.

        Returns:
            True if deleted, False if not found.
        """
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM session_metrics WHERE session_id = ?",
                (session_id,)
            )
            await conn.commit()
            return cursor.rowcount > 0
