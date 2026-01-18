"""Notification system for Team Mode collaboration.

This module provides a notification system for team collaboration:
- Notification types: mentions, comments, team invites, session activity
- Read/unread status tracking
- User notification preferences
- Notification filtering and search
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


def generate_notification_id() -> str:
    """Generate a unique notification ID."""
    return secrets.token_hex(16)


class NotificationType(str, Enum):
    """Types of notifications."""

    MENTION = "mention"  # User was @mentioned in a comment
    COMMENT = "comment"  # Comment added to user's session
    COMMENT_REPLY = "comment_reply"  # Reply to user's comment
    TEAM_INVITE = "team_invite"  # Invited to join a team
    TEAM_JOINED = "team_joined"  # Someone joined user's team
    TEAM_LEFT = "team_left"  # Someone left user's team
    TEAM_ROLE_CHANGED = "team_role_changed"  # User's role changed
    SESSION_SHARED = "session_shared"  # Session was shared with user
    SESSION_ACTIVITY = "session_activity"  # Activity on a session user follows


class NotificationPriority(str, Enum):
    """Notification priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Notification:
    """A notification for a user.

    Attributes:
        id: Unique notification identifier
        user_id: ID of user receiving notification
        type: Type of notification
        title: Short notification title
        message: Full notification message
        priority: Notification priority
        is_read: Whether notification has been read
        is_archived: Whether notification is archived
        created_at: When notification was created
        read_at: When notification was read
        data: Additional data (JSON-serializable)
        source_user_id: User who triggered the notification
        source_team_id: Related team ID (if applicable)
        source_session_id: Related session ID (if applicable)
        source_comment_id: Related comment ID (if applicable)
    """

    id: str
    user_id: str
    type: NotificationType
    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    is_read: bool = False
    is_archived: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    read_at: Optional[datetime] = None
    data: dict = field(default_factory=dict)
    source_user_id: Optional[str] = None
    source_team_id: Optional[str] = None
    source_session_id: Optional[str] = None
    source_comment_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type.value,
            "title": self.title,
            "message": self.message,
            "priority": self.priority.value,
            "is_read": self.is_read,
            "is_archived": self.is_archived,
            "created_at": self.created_at.isoformat(),
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "data": self.data,
            "source_user_id": self.source_user_id,
            "source_team_id": self.source_team_id,
            "source_session_id": self.source_session_id,
            "source_comment_id": self.source_comment_id,
        }

    def mark_read(self) -> None:
        """Mark notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.now()


@dataclass
class NotificationPreferences:
    """User preferences for notifications.

    Attributes:
        user_id: User ID these preferences belong to
        enabled: Global notification enable/disable
        email_enabled: Whether to send email notifications
        mention_enabled: Notify on @mentions
        comment_enabled: Notify on comments
        team_enabled: Notify on team events
        session_enabled: Notify on session events
        quiet_hours_start: Start of quiet hours (hour 0-23)
        quiet_hours_end: End of quiet hours (hour 0-23)
    """

    user_id: str
    enabled: bool = True
    email_enabled: bool = False
    mention_enabled: bool = True
    comment_enabled: bool = True
    team_enabled: bool = True
    session_enabled: bool = True
    quiet_hours_start: Optional[int] = None
    quiet_hours_end: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "user_id": self.user_id,
            "enabled": self.enabled,
            "email_enabled": self.email_enabled,
            "mention_enabled": self.mention_enabled,
            "comment_enabled": self.comment_enabled,
            "team_enabled": self.team_enabled,
            "session_enabled": self.session_enabled,
            "quiet_hours_start": self.quiet_hours_start,
            "quiet_hours_end": self.quiet_hours_end,
        }

    def is_type_enabled(self, notification_type: NotificationType) -> bool:
        """Check if a notification type is enabled.

        Args:
            notification_type: Type to check

        Returns:
            True if this notification type is enabled
        """
        if not self.enabled:
            return False

        type_mapping = {
            NotificationType.MENTION: self.mention_enabled,
            NotificationType.COMMENT: self.comment_enabled,
            NotificationType.COMMENT_REPLY: self.comment_enabled,
            NotificationType.TEAM_INVITE: self.team_enabled,
            NotificationType.TEAM_JOINED: self.team_enabled,
            NotificationType.TEAM_LEFT: self.team_enabled,
            NotificationType.TEAM_ROLE_CHANGED: self.team_enabled,
            NotificationType.SESSION_SHARED: self.session_enabled,
            NotificationType.SESSION_ACTIVITY: self.session_enabled,
        }

        return type_mapping.get(notification_type, True)

    def is_in_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours.

        Returns:
            True if in quiet hours
        """
        if self.quiet_hours_start is None or self.quiet_hours_end is None:
            return False

        current_hour = datetime.now().hour

        if self.quiet_hours_start <= self.quiet_hours_end:
            return self.quiet_hours_start <= current_hour < self.quiet_hours_end
        else:
            # Quiet hours span midnight (e.g., 22:00 - 07:00)
            return current_hour >= self.quiet_hours_start or current_hour < self.quiet_hours_end


class NotificationStore:
    """Persistent storage for notifications."""

    def __init__(self, database: Optional["Database"] = None):
        """Initialize the notification store.

        Args:
            database: Database instance (creates default if not provided)
        """
        from sindri.persistence.database import Database

        self.db = database or Database()

    async def _ensure_tables(self) -> None:
        """Ensure notification tables exist."""
        await self.db.initialize()
        async with self.db.get_connection() as conn:
            # Notifications table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    priority TEXT DEFAULT 'normal',
                    is_read INTEGER DEFAULT 0,
                    is_archived INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    read_at TIMESTAMP,
                    data TEXT DEFAULT '{}',
                    source_user_id TEXT,
                    source_team_id TEXT,
                    source_session_id TEXT,
                    source_comment_id TEXT
                )
            """)

            # Notification preferences table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS notification_preferences (
                    user_id TEXT PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    email_enabled INTEGER DEFAULT 0,
                    mention_enabled INTEGER DEFAULT 1,
                    comment_enabled INTEGER DEFAULT 1,
                    team_enabled INTEGER DEFAULT 1,
                    session_enabled INTEGER DEFAULT 1,
                    quiet_hours_start INTEGER,
                    quiet_hours_end INTEGER
                )
            """)

            # Indexes for efficient queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_notifications_user_id
                ON notifications(user_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
                ON notifications(user_id, is_read)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_notifications_created_at
                ON notifications(created_at)
            """)

            await conn.commit()

    async def create_notification(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        data: Optional[dict] = None,
        source_user_id: Optional[str] = None,
        source_team_id: Optional[str] = None,
        source_session_id: Optional[str] = None,
        source_comment_id: Optional[str] = None,
        check_preferences: bool = True,
    ) -> Optional[Notification]:
        """Create a new notification.

        Args:
            user_id: ID of user to notify
            notification_type: Type of notification
            title: Short title
            message: Full message
            priority: Priority level
            data: Additional data
            source_user_id: User who triggered this
            source_team_id: Related team
            source_session_id: Related session
            source_comment_id: Related comment
            check_preferences: Check user preferences before creating

        Returns:
            Created Notification, or None if preferences prevent it
        """
        await self._ensure_tables()

        # Check user preferences if requested
        if check_preferences:
            prefs = await self.get_preferences(user_id)
            if not prefs.is_type_enabled(notification_type):
                log.debug(
                    "notification_skipped_preferences",
                    user_id=user_id,
                    type=notification_type.value,
                )
                return None
            if prefs.is_in_quiet_hours() and priority != NotificationPriority.URGENT:
                log.debug(
                    "notification_skipped_quiet_hours",
                    user_id=user_id,
                    type=notification_type.value,
                )
                return None

        notification_id = generate_notification_id()
        notification = Notification(
            id=notification_id,
            user_id=user_id,
            type=notification_type,
            title=title,
            message=message,
            priority=priority,
            data=data or {},
            source_user_id=source_user_id,
            source_team_id=source_team_id,
            source_session_id=source_session_id,
            source_comment_id=source_comment_id,
        )

        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO notifications (
                    id, user_id, type, title, message, priority,
                    is_read, is_archived, created_at, data,
                    source_user_id, source_team_id, source_session_id, source_comment_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    notification.id,
                    notification.user_id,
                    notification.type.value,
                    notification.title,
                    notification.message,
                    notification.priority.value,
                    0,
                    0,
                    notification.created_at.isoformat(),
                    json.dumps(notification.data),
                    notification.source_user_id,
                    notification.source_team_id,
                    notification.source_session_id,
                    notification.source_comment_id,
                ),
            )
            await conn.commit()

        log.info(
            "notification_created",
            notification_id=notification_id,
            user_id=user_id,
            type=notification_type.value,
        )
        return notification

    async def get_notification(self, notification_id: str) -> Optional[Notification]:
        """Get a notification by ID.

        Args:
            notification_id: Notification ID

        Returns:
            Notification if found, None otherwise
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM notifications WHERE id = ?",
                (notification_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_notification(row)

    async def get_user_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        include_archived: bool = False,
        notification_type: Optional[NotificationType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """Get notifications for a user.

        Args:
            user_id: User ID
            unread_only: Only return unread notifications
            include_archived: Include archived notifications
            notification_type: Filter by type
            limit: Maximum results
            offset: Results to skip

        Returns:
            List of Notification objects
        """
        await self._ensure_tables()

        conditions = ["user_id = ?"]
        params: list = [user_id]

        if unread_only:
            conditions.append("is_read = 0")

        if not include_archived:
            conditions.append("is_archived = 0")

        if notification_type:
            conditions.append("type = ?")
            params.append(notification_type.value)

        query = f"""
            SELECT * FROM notifications
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

        return [self._row_to_notification(row) for row in rows]

    async def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications for a user.

        Args:
            user_id: User ID

        Returns:
            Number of unread notifications
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT COUNT(*) FROM notifications
                WHERE user_id = ? AND is_read = 0 AND is_archived = 0
                """,
                (user_id,),
            )
            row = await cursor.fetchone()

        return row[0] if row else 0

    async def mark_read(self, notification_id: str) -> bool:
        """Mark a notification as read.

        Args:
            notification_id: Notification ID

        Returns:
            True if notification was updated
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE notifications
                SET is_read = 1, read_at = ?
                WHERE id = ? AND is_read = 0
                """,
                (datetime.now().isoformat(), notification_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def mark_all_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user.

        Args:
            user_id: User ID

        Returns:
            Number of notifications marked read
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE notifications
                SET is_read = 1, read_at = ?
                WHERE user_id = ? AND is_read = 0
                """,
                (datetime.now().isoformat(), user_id),
            )
            await conn.commit()
            return cursor.rowcount

    async def archive_notification(self, notification_id: str) -> bool:
        """Archive a notification.

        Args:
            notification_id: Notification ID

        Returns:
            True if notification was archived
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "UPDATE notifications SET is_archived = 1 WHERE id = ?",
                (notification_id,),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_notification(self, notification_id: str) -> bool:
        """Delete a notification.

        Args:
            notification_id: Notification ID

        Returns:
            True if notification was deleted
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM notifications WHERE id = ?",
                (notification_id,),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_old_notifications(self, days: int = 30) -> int:
        """Delete notifications older than specified days.

        Args:
            days: Delete notifications older than this many days

        Returns:
            Number of notifications deleted
        """
        await self._ensure_tables()

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM notifications WHERE created_at < ? AND is_read = 1",
                (cutoff,),
            )
            await conn.commit()
            return cursor.rowcount

    async def get_preferences(self, user_id: str) -> NotificationPreferences:
        """Get notification preferences for a user.

        Args:
            user_id: User ID

        Returns:
            NotificationPreferences (default if not set)
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM notification_preferences WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return NotificationPreferences(user_id=user_id)

        return NotificationPreferences(
            user_id=row[0],
            enabled=bool(row[1]),
            email_enabled=bool(row[2]),
            mention_enabled=bool(row[3]),
            comment_enabled=bool(row[4]),
            team_enabled=bool(row[5]),
            session_enabled=bool(row[6]),
            quiet_hours_start=row[7],
            quiet_hours_end=row[8],
        )

    async def update_preferences(
        self,
        user_id: str,
        enabled: Optional[bool] = None,
        email_enabled: Optional[bool] = None,
        mention_enabled: Optional[bool] = None,
        comment_enabled: Optional[bool] = None,
        team_enabled: Optional[bool] = None,
        session_enabled: Optional[bool] = None,
        quiet_hours_start: Optional[int] = None,
        quiet_hours_end: Optional[int] = None,
    ) -> NotificationPreferences:
        """Update notification preferences for a user.

        Args:
            user_id: User ID
            enabled: Global enable/disable
            email_enabled: Email notifications
            mention_enabled: Mention notifications
            comment_enabled: Comment notifications
            team_enabled: Team notifications
            session_enabled: Session notifications
            quiet_hours_start: Quiet hours start (0-23)
            quiet_hours_end: Quiet hours end (0-23)

        Returns:
            Updated NotificationPreferences
        """
        await self._ensure_tables()

        # Get current preferences
        current = await self.get_preferences(user_id)

        # Update with new values
        if enabled is not None:
            current.enabled = enabled
        if email_enabled is not None:
            current.email_enabled = email_enabled
        if mention_enabled is not None:
            current.mention_enabled = mention_enabled
        if comment_enabled is not None:
            current.comment_enabled = comment_enabled
        if team_enabled is not None:
            current.team_enabled = team_enabled
        if session_enabled is not None:
            current.session_enabled = session_enabled
        if quiet_hours_start is not None:
            current.quiet_hours_start = quiet_hours_start
        if quiet_hours_end is not None:
            current.quiet_hours_end = quiet_hours_end

        # Upsert into database
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO notification_preferences (
                    user_id, enabled, email_enabled, mention_enabled,
                    comment_enabled, team_enabled, session_enabled,
                    quiet_hours_start, quiet_hours_end
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    email_enabled = excluded.email_enabled,
                    mention_enabled = excluded.mention_enabled,
                    comment_enabled = excluded.comment_enabled,
                    team_enabled = excluded.team_enabled,
                    session_enabled = excluded.session_enabled,
                    quiet_hours_start = excluded.quiet_hours_start,
                    quiet_hours_end = excluded.quiet_hours_end
                """,
                (
                    current.user_id,
                    1 if current.enabled else 0,
                    1 if current.email_enabled else 0,
                    1 if current.mention_enabled else 0,
                    1 if current.comment_enabled else 0,
                    1 if current.team_enabled else 0,
                    1 if current.session_enabled else 0,
                    current.quiet_hours_start,
                    current.quiet_hours_end,
                ),
            )
            await conn.commit()

        log.info("notification_preferences_updated", user_id=user_id)
        return current

    async def get_statistics(self, user_id: Optional[str] = None) -> dict:
        """Get notification statistics.

        Args:
            user_id: User ID (if None, returns global stats)

        Returns:
            Dictionary with statistics
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            if user_id:
                cursor = await conn.execute(
                    """
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) as unread,
                        SUM(CASE WHEN is_read = 1 THEN 1 ELSE 0 END) as read,
                        SUM(CASE WHEN is_archived = 1 THEN 1 ELSE 0 END) as archived
                    FROM notifications
                    WHERE user_id = ?
                    """,
                    (user_id,),
                )
            else:
                cursor = await conn.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) as unread,
                        SUM(CASE WHEN is_read = 1 THEN 1 ELSE 0 END) as read,
                        SUM(CASE WHEN is_archived = 1 THEN 1 ELSE 0 END) as archived,
                        COUNT(DISTINCT user_id) as users_with_notifications
                    FROM notifications
                """)

            row = await cursor.fetchone()

        if user_id:
            return {
                "total": row[0] or 0,
                "unread": row[1] or 0,
                "read": row[2] or 0,
                "archived": row[3] or 0,
            }
        else:
            return {
                "total": row[0] or 0,
                "unread": row[1] or 0,
                "read": row[2] or 0,
                "archived": row[3] or 0,
                "users_with_notifications": row[4] or 0,
            }

    async def get_type_counts(self, user_id: str) -> dict:
        """Get notification counts by type for a user.

        Args:
            user_id: User ID

        Returns:
            Dictionary mapping type to count
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT type, COUNT(*) as count
                FROM notifications
                WHERE user_id = ? AND is_archived = 0
                GROUP BY type
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()

        return {row[0]: row[1] for row in rows}

    def _row_to_notification(self, row) -> Notification:
        """Convert a database row to a Notification object."""
        data = {}
        if row[10]:
            try:
                data = json.loads(row[10])
            except json.JSONDecodeError:
                pass

        return Notification(
            id=row[0],
            user_id=row[1],
            type=NotificationType(row[2]),
            title=row[3],
            message=row[4],
            priority=NotificationPriority(row[5]) if row[5] else NotificationPriority.NORMAL,
            is_read=bool(row[6]),
            is_archived=bool(row[7]),
            created_at=datetime.fromisoformat(row[8]) if row[8] else datetime.now(),
            read_at=datetime.fromisoformat(row[9]) if row[9] else None,
            data=data,
            source_user_id=row[11],
            source_team_id=row[12],
            source_session_id=row[13],
            source_comment_id=row[14],
        )


# Convenience functions for creating common notifications


async def notify_mention(
    store: NotificationStore,
    user_id: str,
    mentioned_by: str,
    mentioned_by_name: str,
    comment_id: str,
    session_id: str,
    context: str = "",
) -> Optional[Notification]:
    """Create a notification for an @mention.

    Args:
        store: NotificationStore instance
        user_id: User who was mentioned
        mentioned_by: ID of user who mentioned them
        mentioned_by_name: Display name of mentioning user
        comment_id: Comment containing the mention
        session_id: Session containing the comment
        context: Brief context of the mention

    Returns:
        Created Notification, or None if preferences prevent it
    """
    return await store.create_notification(
        user_id=user_id,
        notification_type=NotificationType.MENTION,
        title=f"{mentioned_by_name} mentioned you",
        message=f"@{mentioned_by_name} mentioned you in a comment: {context}"[:200],
        priority=NotificationPriority.HIGH,
        source_user_id=mentioned_by,
        source_session_id=session_id,
        source_comment_id=comment_id,
    )


async def notify_comment(
    store: NotificationStore,
    user_id: str,
    commenter_id: str,
    commenter_name: str,
    session_id: str,
    comment_preview: str = "",
) -> Optional[Notification]:
    """Create a notification for a new comment on user's session.

    Args:
        store: NotificationStore instance
        user_id: Session owner
        commenter_id: User who commented
        commenter_name: Display name of commenter
        session_id: Session that was commented on
        comment_preview: Preview of the comment

    Returns:
        Created Notification, or None if preferences prevent it
    """
    return await store.create_notification(
        user_id=user_id,
        notification_type=NotificationType.COMMENT,
        title=f"{commenter_name} commented on your session",
        message=comment_preview[:200] if comment_preview else "New comment on your session",
        source_user_id=commenter_id,
        source_session_id=session_id,
    )


async def notify_team_invite(
    store: NotificationStore,
    user_id: str,
    team_id: str,
    team_name: str,
    invited_by: str,
    invited_by_name: str,
) -> Optional[Notification]:
    """Create a notification for a team invitation.

    Args:
        store: NotificationStore instance
        user_id: User being invited
        team_id: Team ID
        team_name: Team name
        invited_by: User who sent invite
        invited_by_name: Display name of inviter

    Returns:
        Created Notification, or None if preferences prevent it
    """
    return await store.create_notification(
        user_id=user_id,
        notification_type=NotificationType.TEAM_INVITE,
        title=f"Invited to join {team_name}",
        message=f"{invited_by_name} invited you to join the team '{team_name}'",
        priority=NotificationPriority.HIGH,
        source_user_id=invited_by,
        source_team_id=team_id,
    )


async def notify_session_shared(
    store: NotificationStore,
    user_id: str,
    session_id: str,
    shared_by: str,
    shared_by_name: str,
    permission: str,
) -> Optional[Notification]:
    """Create a notification when a session is shared with user.

    Args:
        store: NotificationStore instance
        user_id: User session is shared with
        session_id: Session ID
        shared_by: User who shared
        shared_by_name: Display name of sharer
        permission: Permission level granted

    Returns:
        Created Notification, or None if preferences prevent it
    """
    return await store.create_notification(
        user_id=user_id,
        notification_type=NotificationType.SESSION_SHARED,
        title=f"{shared_by_name} shared a session with you",
        message=f"You have {permission} access to a session shared by {shared_by_name}",
        source_user_id=shared_by,
        source_session_id=session_id,
        data={"permission": permission},
    )
