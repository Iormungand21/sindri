"""Activity feed system for team collaboration.

This module provides a timeline of team activities:
- Activity types: session_created, session_completed, task_started, comment_added, member_joined, etc.
- Query activities by team, user, or time range
- Pagination support
- SQLite persistence
"""

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Optional

import structlog

if TYPE_CHECKING:
    from sindri.persistence.database import Database

log = structlog.get_logger()


def generate_activity_id() -> str:
    """Generate a unique activity ID."""
    return secrets.token_hex(16)


class ActivityType(str, Enum):
    """Types of activities that can be logged."""

    # Session activities
    SESSION_CREATED = "session_created"
    SESSION_COMPLETED = "session_completed"
    SESSION_FAILED = "session_failed"
    SESSION_RESUMED = "session_resumed"

    # Task activities
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_DELEGATED = "task_delegated"

    # Comment activities
    COMMENT_ADDED = "comment_added"
    COMMENT_RESOLVED = "comment_resolved"
    COMMENT_REPLIED = "comment_replied"

    # Member activities
    MEMBER_JOINED = "member_joined"
    MEMBER_LEFT = "member_left"
    MEMBER_ROLE_CHANGED = "member_role_changed"
    MEMBER_INVITED = "member_invited"

    # Sharing activities
    SESSION_SHARED = "session_shared"
    SHARE_REVOKED = "share_revoked"

    # Team activities
    TEAM_CREATED = "team_created"
    TEAM_UPDATED = "team_updated"
    TEAM_SETTINGS_CHANGED = "team_settings_changed"


class TargetType(str, Enum):
    """Types of targets for activities."""

    SESSION = "session"
    TASK = "task"
    USER = "user"
    TEAM = "team"
    COMMENT = "comment"
    SHARE = "share"


@dataclass
class Activity:
    """A single activity in the team activity feed.

    Attributes:
        id: Unique activity identifier
        team_id: ID of the team this activity belongs to
        actor_id: ID of the user who performed the action
        type: Type of activity
        target_id: ID of the target (session, task, user, etc.)
        target_type: Type of the target
        message: Human-readable activity message
        metadata: Additional activity data (JSON-serializable)
        created_at: When the activity occurred
    """

    id: str
    team_id: str
    actor_id: str
    type: ActivityType
    target_id: Optional[str] = None
    target_type: Optional[TargetType] = None
    message: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "team_id": self.team_id,
            "actor_id": self.actor_id,
            "type": self.type.value,
            "target_id": self.target_id,
            "target_type": self.target_type.value if self.target_type else None,
            "message": self.message,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


class ActivityStore:
    """Async SQLite-backed storage for team activities.

    Provides methods to create, query, and manage activities
    for team collaboration tracking.
    """

    def __init__(self, database: Optional["Database"] = None):
        """Initialize activity store.

        Args:
            database: Database instance (creates default if not provided)
        """
        from sindri.persistence.database import Database

        self.db = database or Database()

    async def _ensure_tables(self) -> None:
        """Ensure activity_feed table exists."""
        await self.db.initialize()
        async with self.db.get_connection() as conn:
            # Activity feed table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS activity_feed (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    target_id TEXT,
                    target_type TEXT,
                    message TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes for common queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activity_team
                ON activity_feed(team_id, created_at DESC)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activity_actor
                ON activity_feed(actor_id, created_at DESC)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activity_target
                ON activity_feed(target_id, target_type)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activity_type
                ON activity_feed(type)
            """)

            await conn.commit()

        log.debug("Activity feed tables initialized")

    async def create(
        self,
        team_id: str,
        actor_id: str,
        activity_type: ActivityType,
        target_id: Optional[str] = None,
        target_type: Optional[TargetType] = None,
        message: str = "",
        metadata: Optional[dict] = None,
    ) -> Activity:
        """Create a new activity.

        Args:
            team_id: Team this activity belongs to
            actor_id: User who performed the action
            activity_type: Type of activity
            target_id: Optional target ID
            target_type: Optional target type
            message: Human-readable message
            metadata: Additional data

        Returns:
            Created Activity object
        """
        await self._ensure_tables()

        activity = Activity(
            id=generate_activity_id(),
            team_id=team_id,
            actor_id=actor_id,
            type=activity_type,
            target_id=target_id,
            target_type=target_type,
            message=message,
            metadata=metadata or {},
        )

        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO activity_feed
                (id, team_id, actor_id, type, target_id, target_type, message, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    activity.id,
                    activity.team_id,
                    activity.actor_id,
                    activity.type.value,
                    activity.target_id,
                    activity.target_type.value if activity.target_type else None,
                    activity.message,
                    json.dumps(activity.metadata),
                    activity.created_at.isoformat(),
                ),
            )
            await conn.commit()

        log.info(
            "Activity created",
            activity_id=activity.id,
            team_id=team_id,
            type=activity_type.value,
        )
        return activity

    async def get(self, activity_id: str) -> Optional[Activity]:
        """Get an activity by ID.

        Args:
            activity_id: Activity ID to retrieve

        Returns:
            Activity if found, None otherwise
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                "SELECT * FROM activity_feed WHERE id = ?",
                (activity_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_activity(row)

    async def list_by_team(
        self,
        team_id: str,
        limit: int = 50,
        offset: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        activity_types: Optional[list[ActivityType]] = None,
    ) -> list[Activity]:
        """List activities for a team.

        Args:
            team_id: Team ID to query
            limit: Maximum number of results
            offset: Number of results to skip
            start_date: Optional start date filter
            end_date: Optional end date filter
            activity_types: Optional list of activity types to filter

        Returns:
            List of Activity objects
        """
        await self._ensure_tables()

        query = "SELECT * FROM activity_feed WHERE team_id = ?"
        params: list = [team_id]

        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date.isoformat())

        if activity_types:
            placeholders = ",".join("?" * len(activity_types))
            query += f" AND type IN ({placeholders})"
            params.extend(t.value for t in activity_types)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.get_connection() as conn:
            async with conn.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()

        return [self._row_to_activity(row) for row in rows]

    async def list_by_user(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Activity]:
        """List activities performed by a user.

        Args:
            user_id: User ID (actor) to query
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of Activity objects
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT * FROM activity_feed
                WHERE actor_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ) as cursor:
                rows = await cursor.fetchall()

        return [self._row_to_activity(row) for row in rows]

    async def list_by_target(
        self,
        target_id: str,
        target_type: Optional[TargetType] = None,
        limit: int = 50,
    ) -> list[Activity]:
        """List activities for a specific target.

        Args:
            target_id: Target ID to query
            target_type: Optional target type filter
            limit: Maximum number of results

        Returns:
            List of Activity objects
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            if target_type:
                async with conn.execute(
                    """
                    SELECT * FROM activity_feed
                    WHERE target_id = ? AND target_type = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (target_id, target_type.value, limit),
                ) as cursor:
                    rows = await cursor.fetchall()
            else:
                async with conn.execute(
                    """
                    SELECT * FROM activity_feed
                    WHERE target_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (target_id, limit),
                ) as cursor:
                    rows = await cursor.fetchall()

        return [self._row_to_activity(row) for row in rows]

    async def delete_old(self, days_old: int = 90) -> int:
        """Delete activities older than specified days.

        Args:
            days_old: Delete activities older than this many days

        Returns:
            Number of deleted activities
        """
        await self._ensure_tables()

        cutoff = datetime.now() - timedelta(days=days_old)

        async with self.db.get_connection() as conn:
            # Get count first
            async with conn.execute(
                "SELECT COUNT(*) FROM activity_feed WHERE created_at < ?",
                (cutoff.isoformat(),),
            ) as cursor:
                row = await cursor.fetchone()
                count = row[0] if row else 0

            # Delete
            await conn.execute(
                "DELETE FROM activity_feed WHERE created_at < ?",
                (cutoff.isoformat(),),
            )
            await conn.commit()

        log.info("Deleted old activities", count=count, days_old=days_old)
        return count

    async def count_by_team(self, team_id: str) -> int:
        """Count total activities for a team.

        Args:
            team_id: Team ID to count

        Returns:
            Number of activities
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM activity_feed WHERE team_id = ?",
                (team_id,),
            ) as cursor:
                row = await cursor.fetchone()

        return row[0] if row else 0

    async def get_stats(self, team_id: Optional[str] = None) -> dict:
        """Get activity statistics.

        Args:
            team_id: Optional team ID to filter stats

        Returns:
            Dictionary with activity statistics
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            # Total count
            if team_id:
                async with conn.execute(
                    "SELECT COUNT(*) FROM activity_feed WHERE team_id = ?",
                    (team_id,),
                ) as cursor:
                    row = await cursor.fetchone()
            else:
                async with conn.execute(
                    "SELECT COUNT(*) FROM activity_feed"
                ) as cursor:
                    row = await cursor.fetchone()
            total = row[0] if row else 0

            # Count by type
            type_counts = {}
            for activity_type in ActivityType:
                if team_id:
                    async with conn.execute(
                        "SELECT COUNT(*) FROM activity_feed WHERE team_id = ? AND type = ?",
                        (team_id, activity_type.value),
                    ) as cursor:
                        row = await cursor.fetchone()
                else:
                    async with conn.execute(
                        "SELECT COUNT(*) FROM activity_feed WHERE type = ?",
                        (activity_type.value,),
                    ) as cursor:
                        row = await cursor.fetchone()
                count = row[0] if row else 0
                if count > 0:
                    type_counts[activity_type.value] = count

            # Recent activity (last 24 hours)
            yesterday = (datetime.now() - timedelta(days=1)).isoformat()
            if team_id:
                async with conn.execute(
                    "SELECT COUNT(*) FROM activity_feed WHERE team_id = ? AND created_at > ?",
                    (team_id, yesterday),
                ) as cursor:
                    row = await cursor.fetchone()
            else:
                async with conn.execute(
                    "SELECT COUNT(*) FROM activity_feed WHERE created_at > ?",
                    (yesterday,),
                ) as cursor:
                    row = await cursor.fetchone()
            recent = row[0] if row else 0

            # Most active users (top 5)
            if team_id:
                async with conn.execute(
                    """
                    SELECT actor_id, COUNT(*) as count
                    FROM activity_feed
                    WHERE team_id = ?
                    GROUP BY actor_id
                    ORDER BY count DESC
                    LIMIT 5
                    """,
                    (team_id,),
                ) as cursor:
                    active_users = await cursor.fetchall()
            else:
                async with conn.execute(
                    """
                    SELECT actor_id, COUNT(*) as count
                    FROM activity_feed
                    GROUP BY actor_id
                    ORDER BY count DESC
                    LIMIT 5
                    """
                ) as cursor:
                    active_users = await cursor.fetchall()

            # Recent activities (last 10)
            if team_id:
                async with conn.execute(
                    """
                    SELECT type, COUNT(*) as count
                    FROM activity_feed
                    WHERE team_id = ?
                    GROUP BY type
                    ORDER BY count DESC
                    """,
                    (team_id,),
                ) as cursor:
                    type_breakdown = await cursor.fetchall()
            else:
                async with conn.execute(
                    """
                    SELECT type, COUNT(*) as count
                    FROM activity_feed
                    GROUP BY type
                    ORDER BY count DESC
                    """
                ) as cursor:
                    type_breakdown = await cursor.fetchall()

        return {
            "total_activities": total,
            "by_type": type_counts,
            "last_24h": recent,
            "most_active_users": [
                {"user_id": row[0], "count": row[1]} for row in active_users
            ],
            "type_breakdown": [
                {"type": row[0], "count": row[1]} for row in type_breakdown
            ],
        }

    def _row_to_activity(self, row) -> Activity:
        """Convert database row to Activity object."""
        return Activity(
            id=row[0],
            team_id=row[1],
            actor_id=row[2],
            type=ActivityType(row[3]),
            target_id=row[4],
            target_type=TargetType(row[5]) if row[5] else None,
            message=row[6] or "",
            metadata=json.loads(row[7]) if row[7] else {},
            created_at=datetime.fromisoformat(row[8]) if row[8] else datetime.now(),
        )


# Convenience functions for common activity logging


async def log_session_created(
    store: ActivityStore,
    team_id: str,
    actor_id: str,
    session_id: str,
    session_name: str = "",
) -> Activity:
    """Log a session creation activity.

    Args:
        store: ActivityStore instance
        team_id: Team ID
        actor_id: User who created the session
        session_id: Created session ID
        session_name: Optional session name/description

    Returns:
        Created Activity
    """
    message = f"Created session: {session_name}" if session_name else "Created a new session"
    return await store.create(
        team_id=team_id,
        actor_id=actor_id,
        activity_type=ActivityType.SESSION_CREATED,
        target_id=session_id,
        target_type=TargetType.SESSION,
        message=message,
        metadata={"session_name": session_name},
    )


async def log_session_completed(
    store: ActivityStore,
    team_id: str,
    actor_id: str,
    session_id: str,
    session_name: str = "",
    duration_seconds: Optional[int] = None,
) -> Activity:
    """Log a session completion activity.

    Args:
        store: ActivityStore instance
        team_id: Team ID
        actor_id: User who ran the session
        session_id: Completed session ID
        session_name: Optional session name/description
        duration_seconds: Optional session duration

    Returns:
        Created Activity
    """
    message = f"Completed session: {session_name}" if session_name else "Completed a session"
    metadata: dict = {"session_name": session_name}
    if duration_seconds is not None:
        metadata["duration_seconds"] = duration_seconds

    return await store.create(
        team_id=team_id,
        actor_id=actor_id,
        activity_type=ActivityType.SESSION_COMPLETED,
        target_id=session_id,
        target_type=TargetType.SESSION,
        message=message,
        metadata=metadata,
    )


async def log_session_failed(
    store: ActivityStore,
    team_id: str,
    actor_id: str,
    session_id: str,
    error_message: str = "",
) -> Activity:
    """Log a session failure activity.

    Args:
        store: ActivityStore instance
        team_id: Team ID
        actor_id: User who ran the session
        session_id: Failed session ID
        error_message: Optional error description

    Returns:
        Created Activity
    """
    message = f"Session failed: {error_message}" if error_message else "Session failed"
    return await store.create(
        team_id=team_id,
        actor_id=actor_id,
        activity_type=ActivityType.SESSION_FAILED,
        target_id=session_id,
        target_type=TargetType.SESSION,
        message=message,
        metadata={"error": error_message},
    )


async def log_member_joined(
    store: ActivityStore,
    team_id: str,
    actor_id: str,
    member_id: str,
    member_name: str = "",
    role: str = "member",
) -> Activity:
    """Log a member joining activity.

    Args:
        store: ActivityStore instance
        team_id: Team ID
        actor_id: User who invited/added the member (or member themselves)
        member_id: New member's user ID
        member_name: New member's display name
        role: Role assigned to the new member

    Returns:
        Created Activity
    """
    if actor_id == member_id:
        message = f"{member_name or 'A user'} joined the team"
    else:
        message = f"{member_name or 'A user'} was added to the team"

    return await store.create(
        team_id=team_id,
        actor_id=actor_id,
        activity_type=ActivityType.MEMBER_JOINED,
        target_id=member_id,
        target_type=TargetType.USER,
        message=message,
        metadata={"member_name": member_name, "role": role},
    )


async def log_member_left(
    store: ActivityStore,
    team_id: str,
    actor_id: str,
    member_id: str,
    member_name: str = "",
    removed: bool = False,
) -> Activity:
    """Log a member leaving activity.

    Args:
        store: ActivityStore instance
        team_id: Team ID
        actor_id: User who performed the action
        member_id: Member who left
        member_name: Member's display name
        removed: Whether member was removed (vs left voluntarily)

    Returns:
        Created Activity
    """
    if removed:
        message = f"{member_name or 'A user'} was removed from the team"
    else:
        message = f"{member_name or 'A user'} left the team"

    return await store.create(
        team_id=team_id,
        actor_id=actor_id,
        activity_type=ActivityType.MEMBER_LEFT,
        target_id=member_id,
        target_type=TargetType.USER,
        message=message,
        metadata={"member_name": member_name, "removed": removed},
    )


async def log_role_changed(
    store: ActivityStore,
    team_id: str,
    actor_id: str,
    member_id: str,
    member_name: str = "",
    old_role: str = "",
    new_role: str = "",
) -> Activity:
    """Log a role change activity.

    Args:
        store: ActivityStore instance
        team_id: Team ID
        actor_id: User who changed the role
        member_id: Member whose role changed
        member_name: Member's display name
        old_role: Previous role
        new_role: New role

    Returns:
        Created Activity
    """
    message = f"{member_name or 'A user'}'s role changed from {old_role} to {new_role}"
    return await store.create(
        team_id=team_id,
        actor_id=actor_id,
        activity_type=ActivityType.MEMBER_ROLE_CHANGED,
        target_id=member_id,
        target_type=TargetType.USER,
        message=message,
        metadata={"member_name": member_name, "old_role": old_role, "new_role": new_role},
    )


async def log_comment_added(
    store: ActivityStore,
    team_id: str,
    actor_id: str,
    session_id: str,
    comment_id: str,
    comment_preview: str = "",
) -> Activity:
    """Log a comment added activity.

    Args:
        store: ActivityStore instance
        team_id: Team ID
        actor_id: User who added the comment
        session_id: Session the comment is on
        comment_id: Comment ID
        comment_preview: Preview of comment content

    Returns:
        Created Activity
    """
    preview = comment_preview[:100] + "..." if len(comment_preview) > 100 else comment_preview
    message = f"Added a comment: {preview}" if preview else "Added a comment"

    return await store.create(
        team_id=team_id,
        actor_id=actor_id,
        activity_type=ActivityType.COMMENT_ADDED,
        target_id=comment_id,
        target_type=TargetType.COMMENT,
        message=message,
        metadata={"session_id": session_id, "preview": preview},
    )


async def log_session_shared(
    store: ActivityStore,
    team_id: str,
    actor_id: str,
    session_id: str,
    share_id: str,
    permission: str = "read",
) -> Activity:
    """Log a session sharing activity.

    Args:
        store: ActivityStore instance
        team_id: Team ID
        actor_id: User who shared the session
        session_id: Shared session ID
        share_id: Share link ID
        permission: Share permission level

    Returns:
        Created Activity
    """
    message = f"Shared a session with {permission} access"
    return await store.create(
        team_id=team_id,
        actor_id=actor_id,
        activity_type=ActivityType.SESSION_SHARED,
        target_id=session_id,
        target_type=TargetType.SESSION,
        message=message,
        metadata={"share_id": share_id, "permission": permission},
    )


async def log_team_updated(
    store: ActivityStore,
    team_id: str,
    actor_id: str,
    changes: dict,
) -> Activity:
    """Log a team update activity.

    Args:
        store: ActivityStore instance
        team_id: Team ID
        actor_id: User who updated the team
        changes: Dictionary of changed fields

    Returns:
        Created Activity
    """
    changed_fields = list(changes.keys())
    message = f"Updated team: {', '.join(changed_fields)}"

    return await store.create(
        team_id=team_id,
        actor_id=actor_id,
        activity_type=ActivityType.TEAM_UPDATED,
        target_id=team_id,
        target_type=TargetType.TEAM,
        message=message,
        metadata={"changes": changes},
    )
