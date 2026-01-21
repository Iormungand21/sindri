"""Tool execution audit logging for Sindri.

This module provides infrastructure for logging all tool executions,
supporting the Granular Tool Permissions feature for:
- Tracking tool usage patterns
- Auditing file modifications
- Debugging agent behavior
- Compliance and security monitoring
"""

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
import structlog

from sindri.persistence.database import Database

log = structlog.get_logger()


@dataclass
class AuditEntry:
    """A single tool execution audit entry.

    Attributes:
        tool_name: Name of the tool that was executed
        arguments: JSON-serialized arguments passed to the tool
        success: Whether the tool execution succeeded
        session_id: Optional session ID for context
        task_id: Optional task ID for context
        output_summary: Truncated output (first 500 chars)
        error: Error message if failed
        duration_ms: Execution duration in milliseconds
        dry_run: Whether this was a dry-run execution
        id: Database ID (set after save)
        created_at: When the tool was executed
    """

    tool_name: str
    success: bool
    arguments: Optional[str] = None
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    output_summary: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    dry_run: bool = False
    id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "success": self.success,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "output_summary": self.output_summary,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "dry_run": self.dry_run,
            "created_at": self.created_at.isoformat(),
        }


class AuditStore:
    """Manages tool execution audit persistence."""

    def __init__(self, database: Optional[Database] = None):
        """Initialize audit store.

        Args:
            database: Database instance (uses default if not provided)
        """
        self.db = database or Database()

    async def log_tool_execution(self, entry: AuditEntry) -> AuditEntry:
        """Log a tool execution.

        Args:
            entry: The audit entry to store

        Returns:
            The entry with ID populated
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO tool_audit_log
                (session_id, task_id, tool_name, arguments, success,
                 output_summary, error, duration_ms, dry_run, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.session_id,
                    entry.task_id,
                    entry.tool_name,
                    entry.arguments,
                    1 if entry.success else 0,
                    entry.output_summary,
                    entry.error,
                    entry.duration_ms,
                    1 if entry.dry_run else 0,
                    entry.created_at,
                ),
            )
            entry.id = cursor.lastrowid
            await conn.commit()

        log.debug(
            "audit_logged",
            tool=entry.tool_name,
            success=entry.success,
            audit_id=entry.id,
        )
        return entry

    async def list_entries(
        self,
        limit: int = 100,
        tool_name: Optional[str] = None,
        session_id: Optional[str] = None,
        success_only: bool = False,
        failed_only: bool = False,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[AuditEntry]:
        """List audit entries with optional filters.

        Args:
            limit: Maximum number of entries to return
            tool_name: Filter by tool name
            session_id: Filter by session ID
            success_only: Only return successful executions
            failed_only: Only return failed executions
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            List of audit entries matching filters
        """
        await self.db.initialize()

        # Build query with filters
        query = """
            SELECT id, session_id, task_id, tool_name, arguments, success,
                   output_summary, error, duration_ms, dry_run, created_at
            FROM tool_audit_log
            WHERE 1=1
        """
        params: list[Any] = []

        if tool_name:
            query += " AND tool_name = ?"
            params.append(tool_name)

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        if success_only:
            query += " AND success = 1"
        elif failed_only:
            query += " AND success = 0"

        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        entries = []
        async with self.db.get_connection() as conn:
            async with conn.execute(query, params) as cursor:
                async for row in cursor:
                    entry = AuditEntry(
                        id=row[0],
                        session_id=row[1],
                        task_id=row[2],
                        tool_name=row[3],
                        arguments=row[4],
                        success=bool(row[5]),
                        output_summary=row[6],
                        error=row[7],
                        duration_ms=row[8],
                        dry_run=bool(row[9]),
                        created_at=(
                            datetime.fromisoformat(row[10])
                            if row[10]
                            else datetime.now()
                        ),
                    )
                    entries.append(entry)

        return entries

    async def get_tool_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict[str, dict[str, Any]]:
        """Get statistics about tool usage.

        Args:
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Dictionary of tool name -> stats (count, success_rate, avg_duration)
        """
        await self.db.initialize()

        query = """
            SELECT tool_name,
                   COUNT(*) as total,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                   AVG(duration_ms) as avg_duration
            FROM tool_audit_log
            WHERE 1=1
        """
        params: list[Any] = []

        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date.isoformat())

        query += " GROUP BY tool_name ORDER BY total DESC"

        stats: dict[str, dict[str, Any]] = {}
        async with self.db.get_connection() as conn:
            async with conn.execute(query, params) as cursor:
                async for row in cursor:
                    tool_name = row[0]
                    total = row[1]
                    successes = row[2]
                    avg_duration = row[3]

                    stats[tool_name] = {
                        "total": total,
                        "successes": successes,
                        "failures": total - successes,
                        "success_rate": (successes / total * 100) if total > 0 else 0,
                        "avg_duration_ms": round(avg_duration, 2) if avg_duration else None,
                    }

        return stats

    async def export_entries(
        self,
        format: str = "json",
        limit: int = 1000,
        **filter_kwargs,
    ) -> str:
        """Export audit entries to JSON or CSV format.

        Args:
            format: Export format ("json" or "csv")
            limit: Maximum entries to export
            **filter_kwargs: Additional filters for list_entries

        Returns:
            Formatted string (JSON or CSV)
        """
        entries = await self.list_entries(limit=limit, **filter_kwargs)

        if format == "json":
            return json.dumps(
                [entry.to_dict() for entry in entries],
                indent=2,
            )
        elif format == "csv":
            output = io.StringIO()
            if entries:
                fieldnames = [
                    "id", "created_at", "tool_name", "success", "duration_ms",
                    "dry_run", "session_id", "task_id", "error", "arguments",
                    "output_summary"
                ]
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                for entry in entries:
                    writer.writerow(entry.to_dict())
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported format: {format}")

    async def clear_old_entries(self, days: int = 30) -> int:
        """Delete audit entries older than specified days.

        Args:
            days: Delete entries older than this many days

        Returns:
            Number of entries deleted
        """
        await self.db.initialize()

        cutoff = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        from datetime import timedelta
        cutoff = cutoff - timedelta(days=days)

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM tool_audit_log WHERE created_at < ?",
                (cutoff.isoformat(),),
            )
            deleted = cursor.rowcount
            await conn.commit()

        log.info("audit_entries_cleared", deleted=deleted, older_than_days=days)
        return deleted
