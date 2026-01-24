"""TriggerStore for Triggers & Automations (ROADMAP Item 9).

Provides SQLite persistence for trigger definitions and run history.
"""

import json
import time
from datetime import datetime, timezone
from typing import Optional

import structlog

from sindri.persistence.database import Database
from sindri.triggers.models import (
    TriggerDefinition,
    TriggerRun,
    TriggerStatus,
    TriggerType,
    NotificationHook,
)

log = structlog.get_logger()


class TriggerStore:
    """Manages persistence of triggers and runs to SQLite."""

    def __init__(self, database: Optional[Database] = None):
        """Initialize trigger store.

        Args:
            database: Database instance (uses default if not provided)
        """
        self.db = database or Database()

    def _get_connection(self):
        """Get an async database connection context manager."""
        return self.db.get_connection()

    # ============== Trigger CRUD ==============

    async def save_trigger(self, trigger: TriggerDefinition) -> str:
        """Save a trigger to the database.

        Args:
            trigger: The trigger to save

        Returns:
            The trigger ID
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO triggers (
                    id, name, description, trigger_type, status,
                    task_description, agent, max_iterations, work_dir,
                    cron_expression, timezone, webhook_secret, rate_limit_per_minute,
                    event_types, event_filters, notifications_json,
                    created_at, updated_at, last_run_at, next_run_at,
                    run_count, failure_count, consecutive_failures
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trigger.id,
                    trigger.name,
                    trigger.description,
                    trigger.trigger_type.value,
                    trigger.status.value,
                    trigger.task_description,
                    trigger.agent,
                    trigger.max_iterations,
                    trigger.work_dir,
                    trigger.cron_expression,
                    trigger.timezone,
                    trigger.webhook_secret,
                    trigger.rate_limit_per_minute,
                    json.dumps(trigger.event_types),
                    json.dumps(trigger.event_filters),
                    json.dumps([n.model_dump() for n in trigger.notifications]),
                    trigger.created_at.isoformat(),
                    trigger.updated_at.isoformat(),
                    trigger.last_run_at.isoformat() if trigger.last_run_at else None,
                    trigger.next_run_at.isoformat() if trigger.next_run_at else None,
                    trigger.run_count,
                    trigger.failure_count,
                    trigger.consecutive_failures,
                ),
            )
            await db.commit()

        log.info("trigger_saved", trigger_id=trigger.id, name=trigger.name)
        return trigger.id

    async def load_trigger(self, trigger_id: str) -> Optional[TriggerDefinition]:
        """Load a trigger from the database.

        Args:
            trigger_id: The trigger ID

        Returns:
            The trigger or None if not found
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            async with db.execute(
                "SELECT * FROM triggers WHERE id = ?", (trigger_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                # Get column names
                columns = [d[0] for d in cursor.description]
                data = dict(zip(columns, row))

                return self._row_to_trigger(data)

    async def update_trigger(self, trigger_id: str, updates: dict) -> bool:
        """Update specific fields of a trigger.

        Args:
            trigger_id: The trigger ID
            updates: Dictionary of field names to new values

        Returns:
            True if updated, False if trigger not found
        """
        await self.db.initialize()

        # Always update updated_at
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Build SET clause
        set_parts = []
        values = []
        for key, value in updates.items():
            set_parts.append(f"{key} = ?")
            # Handle special serialization
            if key == "event_types" and isinstance(value, list):
                values.append(json.dumps(value))
            elif key == "event_filters" and isinstance(value, dict):
                values.append(json.dumps(value))
            elif key == "notifications" and isinstance(value, list):
                values.append(json.dumps([n.model_dump() if hasattr(n, "model_dump") else n for n in value]))
            elif key == "status" and isinstance(value, TriggerStatus):
                values.append(value.value)
            elif key == "trigger_type" and isinstance(value, TriggerType):
                values.append(value.value)
            elif isinstance(value, datetime):
                values.append(value.isoformat())
            else:
                values.append(value)

        values.append(trigger_id)

        async with self._get_connection() as db:
            result = await db.execute(
                f"UPDATE triggers SET {', '.join(set_parts)} WHERE id = ?",
                values,
            )
            await db.commit()

            return result.rowcount > 0

    async def delete_trigger(self, trigger_id: str) -> bool:
        """Delete a trigger and its run history.

        Args:
            trigger_id: The trigger ID

        Returns:
            True if deleted, False if not found
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            # Delete runs first (foreign key constraint)
            await db.execute(
                "DELETE FROM trigger_runs WHERE trigger_id = ?", (trigger_id,)
            )
            # Delete rate limits
            await db.execute(
                "DELETE FROM webhook_rate_limits WHERE trigger_id = ?", (trigger_id,)
            )
            # Delete trigger
            result = await db.execute(
                "DELETE FROM triggers WHERE id = ?", (trigger_id,)
            )
            await db.commit()

            deleted = result.rowcount > 0
            if deleted:
                log.info("trigger_deleted", trigger_id=trigger_id)
            return deleted

    async def list_triggers(
        self,
        trigger_type: Optional[TriggerType] = None,
        status: Optional[TriggerStatus] = None,
        limit: int = 100,
    ) -> list[TriggerDefinition]:
        """List triggers with optional filtering.

        Args:
            trigger_type: Filter by trigger type
            status: Filter by status
            limit: Maximum number of triggers to return

        Returns:
            List of triggers
        """
        await self.db.initialize()

        conditions = []
        params = []

        if trigger_type:
            conditions.append("trigger_type = ?")
            params.append(trigger_type.value)
        if status:
            conditions.append("status = ?")
            params.append(status.value)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        async with self._get_connection() as db:
            async with db.execute(
                f"SELECT * FROM triggers {where_clause} ORDER BY created_at DESC LIMIT ?",
                params,
            ) as cursor:
                rows = await cursor.fetchall()
                columns = [d[0] for d in cursor.description]

                return [
                    self._row_to_trigger(dict(zip(columns, row)))
                    for row in rows
                ]

    # ============== Cron Scheduling Helpers ==============

    async def get_due_triggers(self, now: datetime) -> list[TriggerDefinition]:
        """Get all cron triggers that are due to run.

        Args:
            now: Current timestamp

        Returns:
            List of triggers with next_run_at <= now
        """
        await self.db.initialize()

        now_iso = now.isoformat()

        async with self._get_connection() as db:
            async with db.execute(
                """
                SELECT * FROM triggers
                WHERE trigger_type = ?
                  AND status = ?
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= ?
                ORDER BY next_run_at ASC
                """,
                (TriggerType.CRON.value, TriggerStatus.ENABLED.value, now_iso),
            ) as cursor:
                rows = await cursor.fetchall()
                columns = [d[0] for d in cursor.description]

                return [
                    self._row_to_trigger(dict(zip(columns, row)))
                    for row in rows
                ]

    async def update_next_run(
        self, trigger_id: str, next_run: datetime
    ) -> bool:
        """Update the next run time for a trigger.

        Args:
            trigger_id: The trigger ID
            next_run: Next scheduled run time

        Returns:
            True if updated
        """
        return await self.update_trigger(
            trigger_id, {"next_run_at": next_run.isoformat()}
        )

    async def increment_run_count(
        self, trigger_id: str, success: bool, last_run: datetime
    ) -> bool:
        """Increment run count and update stats after execution.

        Args:
            trigger_id: The trigger ID
            success: Whether the run was successful
            last_run: Timestamp of the run

        Returns:
            True if updated
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            if success:
                await db.execute(
                    """
                    UPDATE triggers SET
                        run_count = run_count + 1,
                        consecutive_failures = 0,
                        last_run_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        last_run.isoformat(),
                        datetime.now(timezone.utc).isoformat(),
                        trigger_id,
                    ),
                )
            else:
                await db.execute(
                    """
                    UPDATE triggers SET
                        run_count = run_count + 1,
                        failure_count = failure_count + 1,
                        consecutive_failures = consecutive_failures + 1,
                        last_run_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        last_run.isoformat(),
                        datetime.now(timezone.utc).isoformat(),
                        trigger_id,
                    ),
                )

                # Auto-pause after too many consecutive failures
                await db.execute(
                    """
                    UPDATE triggers SET
                        status = ?
                    WHERE id = ? AND consecutive_failures >= 3
                    """,
                    (TriggerStatus.PAUSED.value, trigger_id),
                )

            await db.commit()

        return True

    # ============== Run History ==============

    async def save_run(self, run: TriggerRun) -> str:
        """Save a trigger run record.

        Args:
            run: The run to save

        Returns:
            The run ID
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            await db.execute(
                """
                INSERT INTO trigger_runs (
                    id, trigger_id, trigger_name, task_id, session_id,
                    started_at, completed_at, duration_ms,
                    success, error, result_summary,
                    webhook_payload, webhook_headers, event_type, event_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.trigger_id,
                    run.trigger_name,
                    run.task_id,
                    run.session_id,
                    run.started_at.isoformat(),
                    run.completed_at.isoformat() if run.completed_at else None,
                    run.duration_ms,
                    1 if run.success else 0,
                    run.error,
                    run.result_summary,
                    json.dumps(run.webhook_payload) if run.webhook_payload else None,
                    json.dumps(run.webhook_headers) if run.webhook_headers else None,
                    run.event_type,
                    json.dumps(run.event_data) if run.event_data else None,
                ),
            )
            await db.commit()

        log.info("trigger_run_saved", run_id=run.id, trigger_id=run.trigger_id)
        return run.id

    async def load_run(self, run_id: str) -> Optional[TriggerRun]:
        """Load a trigger run from the database.

        Args:
            run_id: The run ID

        Returns:
            The run or None if not found
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            async with db.execute(
                "SELECT * FROM trigger_runs WHERE id = ?", (run_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                columns = [d[0] for d in cursor.description]
                data = dict(zip(columns, row))

                return self._row_to_run(data)

    async def list_runs(
        self, trigger_id: str, limit: int = 50
    ) -> list[TriggerRun]:
        """List runs for a trigger.

        Args:
            trigger_id: The trigger ID
            limit: Maximum number of runs to return

        Returns:
            List of runs (most recent first)
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            async with db.execute(
                """
                SELECT * FROM trigger_runs
                WHERE trigger_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (trigger_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                columns = [d[0] for d in cursor.description]

                return [
                    self._row_to_run(dict(zip(columns, row)))
                    for row in rows
                ]

    async def get_run_stats(self, trigger_id: str) -> dict:
        """Get aggregate statistics for a trigger's runs.

        Args:
            trigger_id: The trigger ID

        Returns:
            Dictionary with stats (total_runs, success_rate, avg_duration_ms)
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            async with db.execute(
                """
                SELECT
                    COUNT(*) as total_runs,
                    SUM(success) as successful_runs,
                    AVG(duration_ms) as avg_duration_ms,
                    MIN(started_at) as first_run,
                    MAX(started_at) as last_run
                FROM trigger_runs
                WHERE trigger_id = ?
                """,
                (trigger_id,),
            ) as cursor:
                row = await cursor.fetchone()
                total = row[0] or 0
                successful = row[1] or 0
                avg_duration = row[2]
                first_run = row[3]
                last_run = row[4]

                return {
                    "total_runs": total,
                    "successful_runs": successful,
                    "failed_runs": total - successful,
                    "success_rate": successful / total if total > 0 else 0.0,
                    "avg_duration_ms": avg_duration,
                    "first_run": first_run,
                    "last_run": last_run,
                }

    # ============== Rate Limiting ==============

    async def check_rate_limit(
        self, trigger_id: str, limit_per_minute: int
    ) -> bool:
        """Check if a webhook trigger is within rate limits.

        Args:
            trigger_id: The trigger ID
            limit_per_minute: Maximum requests per minute

        Returns:
            True if within limits, False if rate limited
        """
        await self.db.initialize()

        minute_bucket = int(time.time() // 60)

        async with self._get_connection() as db:
            async with db.execute(
                """
                SELECT request_count FROM webhook_rate_limits
                WHERE trigger_id = ? AND minute_bucket = ?
                """,
                (trigger_id, minute_bucket),
            ) as cursor:
                row = await cursor.fetchone()
                count = row[0] if row else 0

                return count < limit_per_minute

    async def increment_rate_limit(self, trigger_id: str) -> None:
        """Increment the rate limit counter for a webhook trigger.

        Args:
            trigger_id: The trigger ID
        """
        await self.db.initialize()

        minute_bucket = int(time.time() // 60)

        async with self._get_connection() as db:
            await db.execute(
                """
                INSERT INTO webhook_rate_limits (trigger_id, minute_bucket, request_count)
                VALUES (?, ?, 1)
                ON CONFLICT(trigger_id, minute_bucket)
                DO UPDATE SET request_count = request_count + 1
                """,
                (trigger_id, minute_bucket),
            )
            await db.commit()

    async def cleanup_rate_limits(self, older_than_minutes: int = 60) -> int:
        """Clean up old rate limit entries.

        Args:
            older_than_minutes: Delete entries older than this many minutes

        Returns:
            Number of entries deleted
        """
        await self.db.initialize()

        cutoff_bucket = int(time.time() // 60) - older_than_minutes

        async with self._get_connection() as db:
            result = await db.execute(
                "DELETE FROM webhook_rate_limits WHERE minute_bucket < ?",
                (cutoff_bucket,),
            )
            await db.commit()
            return result.rowcount

    # ============== Private Helpers ==============

    def _row_to_trigger(self, data: dict) -> TriggerDefinition:
        """Convert a database row to a TriggerDefinition."""
        notifications_raw = data.get("notifications_json")
        notifications = []
        if notifications_raw:
            try:
                notifications_data = json.loads(notifications_raw)
                notifications = [
                    NotificationHook(**n) for n in notifications_data
                ]
            except (json.JSONDecodeError, TypeError):
                pass

        event_types = []
        if data.get("event_types"):
            try:
                event_types = json.loads(data["event_types"])
            except (json.JSONDecodeError, TypeError):
                pass

        event_filters = {}
        if data.get("event_filters"):
            try:
                event_filters = json.loads(data["event_filters"])
            except (json.JSONDecodeError, TypeError):
                pass

        return TriggerDefinition(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            trigger_type=TriggerType(data["trigger_type"]),
            status=TriggerStatus(data["status"]),
            task_description=data["task_description"],
            agent=data.get("agent", "brokkr"),
            max_iterations=data.get("max_iterations", 30),
            work_dir=data.get("work_dir"),
            cron_expression=data.get("cron_expression"),
            timezone=data.get("timezone", "UTC"),
            webhook_secret=data.get("webhook_secret"),
            rate_limit_per_minute=data.get("rate_limit_per_minute", 10),
            event_types=event_types,
            event_filters=event_filters,
            notifications=notifications,
            created_at=self._parse_datetime(data.get("created_at")),
            updated_at=self._parse_datetime(data.get("updated_at")),
            last_run_at=self._parse_datetime(data.get("last_run_at")),
            next_run_at=self._parse_datetime(data.get("next_run_at")),
            run_count=data.get("run_count", 0),
            failure_count=data.get("failure_count", 0),
            consecutive_failures=data.get("consecutive_failures", 0),
        )

    def _row_to_run(self, data: dict) -> TriggerRun:
        """Convert a database row to a TriggerRun."""
        webhook_payload = None
        if data.get("webhook_payload"):
            try:
                webhook_payload = json.loads(data["webhook_payload"])
            except (json.JSONDecodeError, TypeError):
                pass

        webhook_headers = None
        if data.get("webhook_headers"):
            try:
                webhook_headers = json.loads(data["webhook_headers"])
            except (json.JSONDecodeError, TypeError):
                pass

        event_data = None
        if data.get("event_data"):
            try:
                event_data = json.loads(data["event_data"])
            except (json.JSONDecodeError, TypeError):
                pass

        return TriggerRun(
            id=data["id"],
            trigger_id=data["trigger_id"],
            trigger_name=data.get("trigger_name", ""),
            task_id=data.get("task_id"),
            session_id=data.get("session_id"),
            started_at=self._parse_datetime(data.get("started_at")),
            completed_at=self._parse_datetime(data.get("completed_at")),
            duration_ms=data.get("duration_ms"),
            success=bool(data.get("success", 0)),
            error=data.get("error"),
            result_summary=data.get("result_summary"),
            webhook_payload=webhook_payload,
            webhook_headers=webhook_headers,
            event_type=data.get("event_type"),
            event_data=event_data,
        )

    def _parse_datetime(self, value) -> Optional[datetime]:
        """Parse a datetime from various formats."""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            # Try ISO format
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None
