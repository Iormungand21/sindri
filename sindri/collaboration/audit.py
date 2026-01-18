"""Audit Log System for compliance and security tracking.

This module provides comprehensive audit logging for:
- Authentication events (login, logout, failed attempts)
- Authorization events (permission/role changes)
- Data access events (session access, exports)
- Administrative events (user/team management)
- Security events (suspicious activity detection)
"""

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

import structlog

if TYPE_CHECKING:
    from sindri.persistence.database import Database

log = structlog.get_logger()


def generate_audit_id() -> str:
    """Generate a unique audit log entry ID."""
    return secrets.token_hex(16)


class AuditCategory(str, Enum):
    """Categories of audit events."""

    AUTHENTICATION = "authentication"  # Login, logout, auth failures
    AUTHORIZATION = "authorization"  # Permission/role changes
    DATA_ACCESS = "data_access"  # Session/data access
    DATA_MODIFICATION = "data_modification"  # Create, update, delete
    ADMINISTRATIVE = "administrative"  # User/team management
    SECURITY = "security"  # Security-related events
    SYSTEM = "system"  # System configuration changes


class AuditAction(str, Enum):
    """Specific audit actions."""

    # Authentication actions
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    TOKEN_GENERATED = "token_generated"
    TOKEN_REVOKED = "token_revoked"
    SESSION_EXPIRED = "session_expired"

    # Authorization actions
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REMOVED = "role_removed"
    ACCESS_DENIED = "access_denied"

    # Data access actions
    SESSION_VIEWED = "session_viewed"
    SESSION_EXPORTED = "session_exported"
    DATA_DOWNLOADED = "data_downloaded"
    SEARCH_PERFORMED = "search_performed"
    REPORT_GENERATED = "report_generated"

    # Data modification actions
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_DEACTIVATED = "user_deactivated"
    USER_REACTIVATED = "user_reactivated"
    TEAM_CREATED = "team_created"
    TEAM_UPDATED = "team_updated"
    TEAM_DELETED = "team_deleted"
    TEAM_MEMBER_ADDED = "team_member_added"
    TEAM_MEMBER_REMOVED = "team_member_removed"
    SESSION_CREATED = "session_created"
    SESSION_DELETED = "session_deleted"
    COMMENT_ADDED = "comment_added"
    COMMENT_DELETED = "comment_deleted"
    SHARE_CREATED = "share_created"
    SHARE_REVOKED = "share_revoked"
    WEBHOOK_CREATED = "webhook_created"
    WEBHOOK_DELETED = "webhook_deleted"

    # Administrative actions
    SETTINGS_CHANGED = "settings_changed"
    BACKUP_CREATED = "backup_created"
    BACKUP_RESTORED = "backup_restored"
    MAINTENANCE_STARTED = "maintenance_started"
    MAINTENANCE_COMPLETED = "maintenance_completed"

    # Security actions
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    BRUTE_FORCE_DETECTED = "brute_force_detected"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    INVALID_TOKEN = "invalid_token"
    UNAUTHORIZED_ACCESS_ATTEMPT = "unauthorized_access_attempt"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""

    INFO = "info"  # Normal operations
    WARNING = "warning"  # Potential issues
    ERROR = "error"  # Errors and failures
    CRITICAL = "critical"  # Security incidents


class AuditOutcome(str, Enum):
    """Outcome of the audited action."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"  # Partially successful
    UNKNOWN = "unknown"


@dataclass
class AuditLogEntry:
    """An audit log entry.

    Attributes:
        id: Unique identifier
        timestamp: When the event occurred
        category: Event category
        action: Specific action
        severity: Severity level
        outcome: Action outcome
        actor_id: User who performed the action (None for system)
        actor_type: Type of actor (user, system, api_key)
        target_type: Type of target (user, team, session, etc.)
        target_id: ID of the target
        ip_address: Client IP address
        user_agent: Client user agent
        details: Additional details
        metadata: Structured metadata
        team_id: Associated team (for team-scoped events)
        session_id: Associated Sindri session (if applicable)
        request_id: Request correlation ID
        duration_ms: Action duration in milliseconds
    """

    id: str
    timestamp: datetime
    category: AuditCategory
    action: AuditAction
    severity: AuditSeverity = AuditSeverity.INFO
    outcome: AuditOutcome = AuditOutcome.SUCCESS
    actor_id: Optional[str] = None
    actor_type: str = "user"
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    team_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    duration_ms: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "category": self.category.value,
            "action": self.action.value,
            "severity": self.severity.value,
            "outcome": self.outcome.value,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "details": self.details,
            "metadata": self.metadata,
            "team_id": self.team_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "duration_ms": self.duration_ms,
        }

    @property
    def is_security_event(self) -> bool:
        """Check if this is a security-related event."""
        return (
            self.category == AuditCategory.SECURITY
            or self.severity in (AuditSeverity.ERROR, AuditSeverity.CRITICAL)
            or self.action
            in (
                AuditAction.LOGIN_FAILED,
                AuditAction.ACCESS_DENIED,
                AuditAction.UNAUTHORIZED_ACCESS_ATTEMPT,
            )
        )

    @property
    def is_compliance_relevant(self) -> bool:
        """Check if this event is relevant for compliance reporting."""
        return self.action in (
            AuditAction.LOGIN_SUCCESS,
            AuditAction.LOGIN_FAILED,
            AuditAction.LOGOUT,
            AuditAction.PASSWORD_CHANGED,
            AuditAction.PERMISSION_GRANTED,
            AuditAction.PERMISSION_REVOKED,
            AuditAction.ROLE_ASSIGNED,
            AuditAction.ROLE_REMOVED,
            AuditAction.USER_CREATED,
            AuditAction.USER_DELETED,
            AuditAction.DATA_DOWNLOADED,
            AuditAction.SESSION_EXPORTED,
        )


@dataclass
class AuditQuery:
    """Query parameters for searching audit logs."""

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    categories: Optional[list[AuditCategory]] = None
    actions: Optional[list[AuditAction]] = None
    severities: Optional[list[AuditSeverity]] = None
    outcomes: Optional[list[AuditOutcome]] = None
    actor_id: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    team_id: Optional[str] = None
    ip_address: Optional[str] = None
    search_text: Optional[str] = None
    security_only: bool = False
    compliance_only: bool = False
    limit: int = 100
    offset: int = 0


class AuditStore:
    """Persistent storage for audit logs."""

    def __init__(self, database: Optional["Database"] = None):
        """Initialize the audit store.

        Args:
            database: Database instance (creates default if not provided)
        """
        from sindri.persistence.database import Database

        self.db = database or Database()

    async def _ensure_tables(self) -> None:
        """Ensure audit log tables exist."""
        await self.db.initialize()
        async with self.db.get_connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    category TEXT NOT NULL,
                    action TEXT NOT NULL,
                    severity TEXT DEFAULT 'info',
                    outcome TEXT DEFAULT 'success',
                    actor_id TEXT,
                    actor_type TEXT DEFAULT 'user',
                    target_type TEXT,
                    target_id TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    details TEXT DEFAULT '',
                    metadata TEXT DEFAULT '{}',
                    team_id TEXT,
                    session_id TEXT,
                    request_id TEXT,
                    duration_ms INTEGER
                )
            """)

            # Indexes for common queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp
                ON audit_logs(timestamp DESC)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_category
                ON audit_logs(category)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_action
                ON audit_logs(action)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_id
                ON audit_logs(actor_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_target
                ON audit_logs(target_type, target_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_team_id
                ON audit_logs(team_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_severity
                ON audit_logs(severity)
            """)

            await conn.commit()

    async def log(
        self,
        category: AuditCategory,
        action: AuditAction,
        severity: AuditSeverity = AuditSeverity.INFO,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        actor_id: Optional[str] = None,
        actor_type: str = "user",
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: str = "",
        metadata: Optional[dict[str, Any]] = None,
        team_id: Optional[str] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> AuditLogEntry:
        """Log an audit event.

        Args:
            category: Event category
            action: Specific action
            severity: Severity level
            outcome: Action outcome
            actor_id: User who performed the action
            actor_type: Type of actor
            target_type: Type of target
            target_id: ID of target
            ip_address: Client IP
            user_agent: Client user agent
            details: Human-readable details
            metadata: Structured metadata
            team_id: Associated team
            session_id: Associated Sindri session
            request_id: Request correlation ID
            duration_ms: Action duration

        Returns:
            Created AuditLogEntry
        """
        await self._ensure_tables()

        entry = AuditLogEntry(
            id=generate_audit_id(),
            timestamp=datetime.now(),
            category=category,
            action=action,
            severity=severity,
            outcome=outcome,
            actor_id=actor_id,
            actor_type=actor_type,
            target_type=target_type,
            target_id=target_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
            metadata=metadata or {},
            team_id=team_id,
            session_id=session_id,
            request_id=request_id,
            duration_ms=duration_ms,
        )

        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO audit_logs (
                    id, timestamp, category, action, severity, outcome,
                    actor_id, actor_type, target_type, target_id,
                    ip_address, user_agent, details, metadata,
                    team_id, session_id, request_id, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.timestamp.isoformat(),
                    entry.category.value,
                    entry.action.value,
                    entry.severity.value,
                    entry.outcome.value,
                    entry.actor_id,
                    entry.actor_type,
                    entry.target_type,
                    entry.target_id,
                    entry.ip_address,
                    entry.user_agent,
                    entry.details,
                    json.dumps(entry.metadata),
                    entry.team_id,
                    entry.session_id,
                    entry.request_id,
                    entry.duration_ms,
                ),
            )
            await conn.commit()

        # Log for structlog as well (for real-time monitoring)
        log.info(
            "audit_event",
            audit_id=entry.id,
            category=category.value,
            action=action.value,
            severity=severity.value,
            outcome=outcome.value,
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
        )

        return entry

    async def get_entry(self, entry_id: str) -> Optional[AuditLogEntry]:
        """Get an audit log entry by ID.

        Args:
            entry_id: Entry ID

        Returns:
            AuditLogEntry if found, None otherwise
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM audit_logs WHERE id = ?",
                (entry_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_entry(row)

    async def query(self, query: AuditQuery) -> list[AuditLogEntry]:
        """Query audit logs with filters.

        Args:
            query: Query parameters

        Returns:
            List of matching AuditLogEntry objects
        """
        await self._ensure_tables()

        sql = "SELECT * FROM audit_logs WHERE 1=1"
        params: list[Any] = []

        if query.start_date:
            sql += " AND timestamp >= ?"
            params.append(query.start_date.isoformat())

        if query.end_date:
            sql += " AND timestamp <= ?"
            params.append(query.end_date.isoformat())

        if query.categories:
            placeholders = ",".join("?" * len(query.categories))
            sql += f" AND category IN ({placeholders})"
            params.extend(c.value for c in query.categories)

        if query.actions:
            placeholders = ",".join("?" * len(query.actions))
            sql += f" AND action IN ({placeholders})"
            params.extend(a.value for a in query.actions)

        if query.severities:
            placeholders = ",".join("?" * len(query.severities))
            sql += f" AND severity IN ({placeholders})"
            params.extend(s.value for s in query.severities)

        if query.outcomes:
            placeholders = ",".join("?" * len(query.outcomes))
            sql += f" AND outcome IN ({placeholders})"
            params.extend(o.value for o in query.outcomes)

        if query.actor_id:
            sql += " AND actor_id = ?"
            params.append(query.actor_id)

        if query.target_type:
            sql += " AND target_type = ?"
            params.append(query.target_type)

        if query.target_id:
            sql += " AND target_id = ?"
            params.append(query.target_id)

        if query.team_id:
            sql += " AND team_id = ?"
            params.append(query.team_id)

        if query.ip_address:
            sql += " AND ip_address = ?"
            params.append(query.ip_address)

        if query.search_text:
            sql += " AND (details LIKE ? OR metadata LIKE ?)"
            search = f"%{query.search_text}%"
            params.extend([search, search])

        if query.security_only:
            security_actions = [
                AuditAction.LOGIN_FAILED.value,
                AuditAction.ACCESS_DENIED.value,
                AuditAction.SUSPICIOUS_ACTIVITY.value,
                AuditAction.BRUTE_FORCE_DETECTED.value,
                AuditAction.RATE_LIMIT_EXCEEDED.value,
                AuditAction.INVALID_TOKEN.value,
                AuditAction.UNAUTHORIZED_ACCESS_ATTEMPT.value,
            ]
            placeholders = ",".join("?" * len(security_actions))
            sql += f" AND (category = 'security' OR severity IN ('error', 'critical') OR action IN ({placeholders}))"
            params.extend(security_actions)

        if query.compliance_only:
            compliance_actions = [
                AuditAction.LOGIN_SUCCESS.value,
                AuditAction.LOGIN_FAILED.value,
                AuditAction.LOGOUT.value,
                AuditAction.PASSWORD_CHANGED.value,
                AuditAction.PERMISSION_GRANTED.value,
                AuditAction.PERMISSION_REVOKED.value,
                AuditAction.ROLE_ASSIGNED.value,
                AuditAction.ROLE_REMOVED.value,
                AuditAction.USER_CREATED.value,
                AuditAction.USER_DELETED.value,
                AuditAction.DATA_DOWNLOADED.value,
                AuditAction.SESSION_EXPORTED.value,
            ]
            placeholders = ",".join("?" * len(compliance_actions))
            sql += f" AND action IN ({placeholders})"
            params.extend(compliance_actions)

        sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([query.limit, query.offset])

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()

        return [self._row_to_entry(row) for row in rows]

    async def get_actor_history(
        self,
        actor_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        """Get audit history for a specific actor.

        Args:
            actor_id: Actor ID
            limit: Maximum results
            offset: Results to skip

        Returns:
            List of AuditLogEntry objects
        """
        return await self.query(
            AuditQuery(actor_id=actor_id, limit=limit, offset=offset)
        )

    async def get_target_history(
        self,
        target_type: str,
        target_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        """Get audit history for a specific target.

        Args:
            target_type: Type of target
            target_id: Target ID
            limit: Maximum results
            offset: Results to skip

        Returns:
            List of AuditLogEntry objects
        """
        return await self.query(
            AuditQuery(
                target_type=target_type, target_id=target_id, limit=limit, offset=offset
            )
        )

    async def get_security_events(
        self,
        hours: int = 24,
        team_id: Optional[str] = None,
    ) -> list[AuditLogEntry]:
        """Get security events from the last N hours.

        Args:
            hours: Number of hours to look back
            team_id: Filter by team

        Returns:
            List of security-related AuditLogEntry objects
        """
        return await self.query(
            AuditQuery(
                start_date=datetime.now() - timedelta(hours=hours),
                team_id=team_id,
                security_only=True,
                limit=1000,
            )
        )

    async def get_failed_logins(
        self,
        hours: int = 1,
        ip_address: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> list[AuditLogEntry]:
        """Get failed login attempts.

        Args:
            hours: Number of hours to look back
            ip_address: Filter by IP address
            actor_id: Filter by actor (username)

        Returns:
            List of failed login entries
        """
        return await self.query(
            AuditQuery(
                start_date=datetime.now() - timedelta(hours=hours),
                actions=[AuditAction.LOGIN_FAILED],
                ip_address=ip_address,
                actor_id=actor_id,
                limit=1000,
            )
        )

    async def get_statistics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        team_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get audit log statistics.

        Args:
            start_date: Start of period
            end_date: End of period
            team_id: Filter by team

        Returns:
            Dictionary with statistics
        """
        await self._ensure_tables()

        where_clauses = ["1=1"]
        params: list[Any] = []

        if start_date:
            where_clauses.append("timestamp >= ?")
            params.append(start_date.isoformat())

        if end_date:
            where_clauses.append("timestamp <= ?")
            params.append(end_date.isoformat())

        if team_id:
            where_clauses.append("team_id = ?")
            params.append(team_id)

        where_sql = " AND ".join(where_clauses)

        async with self.db.get_connection() as conn:
            # Total count
            cursor = await conn.execute(
                f"SELECT COUNT(*) FROM audit_logs WHERE {where_sql}",
                params,
            )
            total = (await cursor.fetchone())[0]

            # By category
            cursor = await conn.execute(
                f"""
                SELECT category, COUNT(*) FROM audit_logs
                WHERE {where_sql}
                GROUP BY category
                ORDER BY COUNT(*) DESC
                """,
                params,
            )
            by_category = {row[0]: row[1] for row in await cursor.fetchall()}

            # By severity
            cursor = await conn.execute(
                f"""
                SELECT severity, COUNT(*) FROM audit_logs
                WHERE {where_sql}
                GROUP BY severity
                ORDER BY COUNT(*) DESC
                """,
                params,
            )
            by_severity = {row[0]: row[1] for row in await cursor.fetchall()}

            # By outcome
            cursor = await conn.execute(
                f"""
                SELECT outcome, COUNT(*) FROM audit_logs
                WHERE {where_sql}
                GROUP BY outcome
                ORDER BY COUNT(*) DESC
                """,
                params,
            )
            by_outcome = {row[0]: row[1] for row in await cursor.fetchall()}

            # Top actions
            cursor = await conn.execute(
                f"""
                SELECT action, COUNT(*) FROM audit_logs
                WHERE {where_sql}
                GROUP BY action
                ORDER BY COUNT(*) DESC
                LIMIT 10
                """,
                params,
            )
            top_actions = {row[0]: row[1] for row in await cursor.fetchall()}

            # Top actors
            cursor = await conn.execute(
                f"""
                SELECT actor_id, COUNT(*) FROM audit_logs
                WHERE {where_sql} AND actor_id IS NOT NULL
                GROUP BY actor_id
                ORDER BY COUNT(*) DESC
                LIMIT 10
                """,
                params,
            )
            top_actors = {row[0]: row[1] for row in await cursor.fetchall()}

            # Security events count
            security_where = f"{where_sql} AND (category = 'security' OR severity IN ('error', 'critical'))"
            cursor = await conn.execute(
                f"SELECT COUNT(*) FROM audit_logs WHERE {security_where}",
                params,
            )
            security_count = (await cursor.fetchone())[0]

            # Failed logins
            failed_login_where = f"{where_sql} AND action = 'login_failed'"
            cursor = await conn.execute(
                f"SELECT COUNT(*) FROM audit_logs WHERE {failed_login_where}",
                params,
            )
            failed_logins = (await cursor.fetchone())[0]

        return {
            "total_events": total,
            "by_category": by_category,
            "by_severity": by_severity,
            "by_outcome": by_outcome,
            "top_actions": top_actions,
            "top_actors": top_actors,
            "security_events": security_count,
            "failed_logins": failed_logins,
        }

    async def cleanup_old_entries(
        self,
        days: int = 90,
        keep_security: bool = True,
    ) -> int:
        """Delete old audit log entries.

        Args:
            days: Delete entries older than this many days
            keep_security: Keep security events regardless of age

        Returns:
            Number of entries deleted
        """
        await self._ensure_tables()

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        query = "DELETE FROM audit_logs WHERE timestamp < ?"
        params: list[Any] = [cutoff]

        if keep_security:
            query += " AND category != 'security' AND severity NOT IN ('error', 'critical')"

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, params)
            await conn.commit()

        deleted = cursor.rowcount
        if deleted > 0:
            log.info("audit_logs_cleaned", deleted=deleted, days=days)
        return deleted

    async def export_logs(
        self,
        query: AuditQuery,
        format: str = "json",
    ) -> str:
        """Export audit logs in specified format.

        Args:
            query: Query parameters
            format: Export format (json, csv)

        Returns:
            Exported data as string
        """
        entries = await self.query(query)

        if format == "csv":
            lines = [
                "id,timestamp,category,action,severity,outcome,actor_id,target_type,target_id,ip_address,details"
            ]
            for entry in entries:
                lines.append(
                    ",".join(
                        [
                            entry.id,
                            entry.timestamp.isoformat(),
                            entry.category.value,
                            entry.action.value,
                            entry.severity.value,
                            entry.outcome.value,
                            entry.actor_id or "",
                            entry.target_type or "",
                            entry.target_id or "",
                            entry.ip_address or "",
                            f'"{entry.details}"',
                        ]
                    )
                )
            return "\n".join(lines)
        else:
            return json.dumps([e.to_dict() for e in entries], indent=2, default=str)

    def _row_to_entry(self, row) -> AuditLogEntry:
        """Convert a database row to an AuditLogEntry."""
        metadata = {}
        if row[13]:
            try:
                metadata = json.loads(row[13])
            except json.JSONDecodeError:
                pass

        return AuditLogEntry(
            id=row[0],
            timestamp=datetime.fromisoformat(row[1]) if row[1] else datetime.now(),
            category=AuditCategory(row[2]),
            action=AuditAction(row[3]),
            severity=AuditSeverity(row[4]) if row[4] else AuditSeverity.INFO,
            outcome=AuditOutcome(row[5]) if row[5] else AuditOutcome.SUCCESS,
            actor_id=row[6],
            actor_type=row[7] or "user",
            target_type=row[8],
            target_id=row[9],
            ip_address=row[10],
            user_agent=row[11],
            details=row[12] or "",
            metadata=metadata,
            team_id=row[14],
            session_id=row[15],
            request_id=row[16],
            duration_ms=row[17],
        )


# Convenience functions for common audit events


async def audit_login_success(
    store: AuditStore,
    user_id: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    team_id: Optional[str] = None,
) -> AuditLogEntry:
    """Log a successful login.

    Args:
        store: AuditStore instance
        user_id: User who logged in
        ip_address: Client IP
        user_agent: Client user agent
        team_id: Associated team

    Returns:
        Created AuditLogEntry
    """
    return await store.log(
        category=AuditCategory.AUTHENTICATION,
        action=AuditAction.LOGIN_SUCCESS,
        actor_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        team_id=team_id,
        details=f"User {user_id} logged in successfully",
    )


async def audit_login_failed(
    store: AuditStore,
    username: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    reason: str = "Invalid credentials",
) -> AuditLogEntry:
    """Log a failed login attempt.

    Args:
        store: AuditStore instance
        username: Attempted username
        ip_address: Client IP
        user_agent: Client user agent
        reason: Failure reason

    Returns:
        Created AuditLogEntry
    """
    return await store.log(
        category=AuditCategory.AUTHENTICATION,
        action=AuditAction.LOGIN_FAILED,
        severity=AuditSeverity.WARNING,
        outcome=AuditOutcome.FAILURE,
        actor_id=username,
        ip_address=ip_address,
        user_agent=user_agent,
        details=f"Failed login attempt for {username}: {reason}",
        metadata={"reason": reason},
    )


async def audit_logout(
    store: AuditStore,
    user_id: str,
    ip_address: Optional[str] = None,
) -> AuditLogEntry:
    """Log a logout.

    Args:
        store: AuditStore instance
        user_id: User who logged out
        ip_address: Client IP

    Returns:
        Created AuditLogEntry
    """
    return await store.log(
        category=AuditCategory.AUTHENTICATION,
        action=AuditAction.LOGOUT,
        actor_id=user_id,
        ip_address=ip_address,
        details=f"User {user_id} logged out",
    )


async def audit_permission_change(
    store: AuditStore,
    actor_id: str,
    target_user_id: str,
    permission: str,
    granted: bool,
    team_id: Optional[str] = None,
) -> AuditLogEntry:
    """Log a permission change.

    Args:
        store: AuditStore instance
        actor_id: User who made the change
        target_user_id: User whose permission changed
        permission: Permission name
        granted: True if granted, False if revoked
        team_id: Associated team

    Returns:
        Created AuditLogEntry
    """
    action = (
        AuditAction.PERMISSION_GRANTED if granted else AuditAction.PERMISSION_REVOKED
    )
    verb = "granted to" if granted else "revoked from"

    return await store.log(
        category=AuditCategory.AUTHORIZATION,
        action=action,
        actor_id=actor_id,
        target_type="user",
        target_id=target_user_id,
        team_id=team_id,
        details=f"Permission '{permission}' {verb} user {target_user_id}",
        metadata={"permission": permission, "granted": granted},
    )


async def audit_role_change(
    store: AuditStore,
    actor_id: str,
    target_user_id: str,
    old_role: str,
    new_role: str,
    team_id: str,
) -> AuditLogEntry:
    """Log a role change.

    Args:
        store: AuditStore instance
        actor_id: User who made the change
        target_user_id: User whose role changed
        old_role: Previous role
        new_role: New role
        team_id: Team ID

    Returns:
        Created AuditLogEntry
    """
    return await store.log(
        category=AuditCategory.AUTHORIZATION,
        action=AuditAction.ROLE_ASSIGNED,
        actor_id=actor_id,
        target_type="user",
        target_id=target_user_id,
        team_id=team_id,
        details=f"Role changed from '{old_role}' to '{new_role}' for user {target_user_id}",
        metadata={"old_role": old_role, "new_role": new_role},
    )


async def audit_session_access(
    store: AuditStore,
    user_id: str,
    session_id: str,
    action_type: str = "viewed",
    team_id: Optional[str] = None,
) -> AuditLogEntry:
    """Log session access.

    Args:
        store: AuditStore instance
        user_id: User who accessed the session
        session_id: Session ID
        action_type: Type of access (viewed, exported, etc.)
        team_id: Associated team

    Returns:
        Created AuditLogEntry
    """
    action_map = {
        "viewed": AuditAction.SESSION_VIEWED,
        "exported": AuditAction.SESSION_EXPORTED,
        "downloaded": AuditAction.DATA_DOWNLOADED,
    }
    action = action_map.get(action_type, AuditAction.SESSION_VIEWED)

    return await store.log(
        category=AuditCategory.DATA_ACCESS,
        action=action,
        actor_id=user_id,
        target_type="session",
        target_id=session_id,
        team_id=team_id,
        session_id=session_id,
        details=f"User {user_id} {action_type} session {session_id}",
    )


async def audit_access_denied(
    store: AuditStore,
    user_id: str,
    resource_type: str,
    resource_id: str,
    reason: str = "Insufficient permissions",
    ip_address: Optional[str] = None,
) -> AuditLogEntry:
    """Log an access denied event.

    Args:
        store: AuditStore instance
        user_id: User who was denied
        resource_type: Type of resource
        resource_id: Resource ID
        reason: Denial reason
        ip_address: Client IP

    Returns:
        Created AuditLogEntry
    """
    return await store.log(
        category=AuditCategory.AUTHORIZATION,
        action=AuditAction.ACCESS_DENIED,
        severity=AuditSeverity.WARNING,
        outcome=AuditOutcome.FAILURE,
        actor_id=user_id,
        target_type=resource_type,
        target_id=resource_id,
        ip_address=ip_address,
        details=f"Access denied to {resource_type} {resource_id} for user {user_id}: {reason}",
        metadata={"reason": reason},
    )


async def audit_suspicious_activity(
    store: AuditStore,
    description: str,
    actor_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> AuditLogEntry:
    """Log suspicious activity.

    Args:
        store: AuditStore instance
        description: Description of the suspicious activity
        actor_id: User involved (if known)
        ip_address: Client IP
        metadata: Additional details

    Returns:
        Created AuditLogEntry
    """
    return await store.log(
        category=AuditCategory.SECURITY,
        action=AuditAction.SUSPICIOUS_ACTIVITY,
        severity=AuditSeverity.ERROR,
        actor_id=actor_id,
        ip_address=ip_address,
        details=description,
        metadata=metadata or {},
    )


async def audit_brute_force_detected(
    store: AuditStore,
    ip_address: str,
    attempt_count: int,
    username: Optional[str] = None,
) -> AuditLogEntry:
    """Log a brute force detection.

    Args:
        store: AuditStore instance
        ip_address: Source IP
        attempt_count: Number of failed attempts
        username: Target username (if known)

    Returns:
        Created AuditLogEntry
    """
    return await store.log(
        category=AuditCategory.SECURITY,
        action=AuditAction.BRUTE_FORCE_DETECTED,
        severity=AuditSeverity.CRITICAL,
        actor_id=username,
        ip_address=ip_address,
        details=f"Brute force attack detected from {ip_address}: {attempt_count} failed attempts",
        metadata={"attempt_count": attempt_count, "username": username},
    )


async def check_brute_force(
    store: AuditStore,
    ip_address: str,
    threshold: int = 5,
    window_minutes: int = 15,
) -> bool:
    """Check if an IP is potentially brute forcing.

    Args:
        store: AuditStore instance
        ip_address: IP to check
        threshold: Number of failures to trigger
        window_minutes: Time window in minutes

    Returns:
        True if brute force is detected
    """
    failures = await store.get_failed_logins(
        hours=window_minutes / 60, ip_address=ip_address
    )
    return len(failures) >= threshold
