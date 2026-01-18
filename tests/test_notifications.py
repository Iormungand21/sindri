"""Tests for the Notification System."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

from sindri.collaboration.notifications import (
    Notification,
    NotificationType,
    NotificationPriority,
    NotificationPreferences,
    NotificationStore,
    generate_notification_id,
    notify_mention,
    notify_comment,
    notify_team_invite,
    notify_session_shared,
)
from sindri.persistence.database import Database


# ============================================
# Notification ID Generation Tests
# ============================================


class TestNotificationIdGeneration:
    """Tests for notification ID generation."""

    def test_generate_notification_id_unique(self):
        """Test that notification IDs are unique."""
        ids = [generate_notification_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_generate_notification_id_length(self):
        """Test notification ID length."""
        notification_id = generate_notification_id()
        assert len(notification_id) == 32  # 16 bytes hex


# ============================================
# NotificationType Tests
# ============================================


class TestNotificationType:
    """Tests for NotificationType enum."""

    def test_notification_types_exist(self):
        """Test all expected notification types exist."""
        assert NotificationType.MENTION.value == "mention"
        assert NotificationType.COMMENT.value == "comment"
        assert NotificationType.COMMENT_REPLY.value == "comment_reply"
        assert NotificationType.TEAM_INVITE.value == "team_invite"
        assert NotificationType.TEAM_JOINED.value == "team_joined"
        assert NotificationType.TEAM_LEFT.value == "team_left"
        assert NotificationType.TEAM_ROLE_CHANGED.value == "team_role_changed"
        assert NotificationType.SESSION_SHARED.value == "session_shared"
        assert NotificationType.SESSION_ACTIVITY.value == "session_activity"

    def test_notification_type_is_string_enum(self):
        """Test NotificationType is a string enum."""
        assert isinstance(NotificationType.MENTION, str)
        assert NotificationType.MENTION == "mention"


# ============================================
# NotificationPriority Tests
# ============================================


class TestNotificationPriority:
    """Tests for NotificationPriority enum."""

    def test_priority_levels(self):
        """Test priority level values."""
        assert NotificationPriority.LOW.value == "low"
        assert NotificationPriority.NORMAL.value == "normal"
        assert NotificationPriority.HIGH.value == "high"
        assert NotificationPriority.URGENT.value == "urgent"


# ============================================
# Notification Dataclass Tests
# ============================================


class TestNotificationDataclass:
    """Tests for Notification dataclass."""

    def test_notification_defaults(self):
        """Test Notification default values."""
        notification = Notification(
            id="test-id",
            user_id="user-123",
            type=NotificationType.MENTION,
            title="Test Title",
            message="Test message",
        )
        assert notification.priority == NotificationPriority.NORMAL
        assert not notification.is_read
        assert not notification.is_archived
        assert notification.read_at is None
        assert notification.data == {}
        assert notification.source_user_id is None
        assert notification.source_team_id is None
        assert notification.source_session_id is None
        assert notification.source_comment_id is None

    def test_notification_to_dict(self):
        """Test Notification.to_dict method."""
        notification = Notification(
            id="test-id",
            user_id="user-123",
            type=NotificationType.COMMENT,
            title="New Comment",
            message="Someone commented",
            priority=NotificationPriority.HIGH,
            source_user_id="commenter-456",
            source_session_id="session-789",
        )
        data = notification.to_dict()
        assert data["id"] == "test-id"
        assert data["user_id"] == "user-123"
        assert data["type"] == "comment"
        assert data["title"] == "New Comment"
        assert data["message"] == "Someone commented"
        assert data["priority"] == "high"
        assert not data["is_read"]
        assert not data["is_archived"]
        assert data["source_user_id"] == "commenter-456"
        assert data["source_session_id"] == "session-789"

    def test_notification_mark_read(self):
        """Test marking notification as read."""
        notification = Notification(
            id="test-id",
            user_id="user-123",
            type=NotificationType.MENTION,
            title="Test",
            message="Test",
        )
        assert not notification.is_read
        assert notification.read_at is None

        notification.mark_read()

        assert notification.is_read
        assert notification.read_at is not None

    def test_notification_mark_read_idempotent(self):
        """Test that marking read multiple times is idempotent."""
        notification = Notification(
            id="test-id",
            user_id="user-123",
            type=NotificationType.MENTION,
            title="Test",
            message="Test",
        )
        notification.mark_read()
        first_read_at = notification.read_at

        notification.mark_read()
        assert notification.read_at == first_read_at


# ============================================
# NotificationPreferences Tests
# ============================================


class TestNotificationPreferences:
    """Tests for NotificationPreferences dataclass."""

    def test_preferences_defaults(self):
        """Test NotificationPreferences default values."""
        prefs = NotificationPreferences(user_id="user-123")
        assert prefs.enabled
        assert not prefs.email_enabled
        assert prefs.mention_enabled
        assert prefs.comment_enabled
        assert prefs.team_enabled
        assert prefs.session_enabled
        assert prefs.quiet_hours_start is None
        assert prefs.quiet_hours_end is None

    def test_preferences_to_dict(self):
        """Test NotificationPreferences.to_dict method."""
        prefs = NotificationPreferences(
            user_id="user-123",
            enabled=True,
            email_enabled=True,
            mention_enabled=False,
            quiet_hours_start=22,
            quiet_hours_end=7,
        )
        data = prefs.to_dict()
        assert data["user_id"] == "user-123"
        assert data["enabled"]
        assert data["email_enabled"]
        assert not data["mention_enabled"]
        assert data["quiet_hours_start"] == 22
        assert data["quiet_hours_end"] == 7

    def test_is_type_enabled_globally_disabled(self):
        """Test is_type_enabled when globally disabled."""
        prefs = NotificationPreferences(user_id="user-123", enabled=False)
        assert not prefs.is_type_enabled(NotificationType.MENTION)
        assert not prefs.is_type_enabled(NotificationType.COMMENT)
        assert not prefs.is_type_enabled(NotificationType.TEAM_INVITE)

    def test_is_type_enabled_specific_disabled(self):
        """Test is_type_enabled with specific types disabled."""
        prefs = NotificationPreferences(
            user_id="user-123",
            mention_enabled=False,
            comment_enabled=True,
        )
        assert not prefs.is_type_enabled(NotificationType.MENTION)
        assert prefs.is_type_enabled(NotificationType.COMMENT)

    def test_is_type_enabled_team_notifications(self):
        """Test is_type_enabled for team notification types."""
        prefs = NotificationPreferences(user_id="user-123", team_enabled=False)
        assert not prefs.is_type_enabled(NotificationType.TEAM_INVITE)
        assert not prefs.is_type_enabled(NotificationType.TEAM_JOINED)
        assert not prefs.is_type_enabled(NotificationType.TEAM_LEFT)
        assert not prefs.is_type_enabled(NotificationType.TEAM_ROLE_CHANGED)

    def test_is_type_enabled_session_notifications(self):
        """Test is_type_enabled for session notification types."""
        prefs = NotificationPreferences(user_id="user-123", session_enabled=False)
        assert not prefs.is_type_enabled(NotificationType.SESSION_SHARED)
        assert not prefs.is_type_enabled(NotificationType.SESSION_ACTIVITY)

    def test_is_in_quiet_hours_no_quiet_hours(self):
        """Test is_in_quiet_hours when not configured."""
        prefs = NotificationPreferences(user_id="user-123")
        assert not prefs.is_in_quiet_hours()

    def test_is_in_quiet_hours_normal_range(self):
        """Test is_in_quiet_hours with normal range (e.g., 9-17)."""
        prefs = NotificationPreferences(
            user_id="user-123",
            quiet_hours_start=9,
            quiet_hours_end=17,
        )
        with patch("sindri.collaboration.notifications.datetime") as mock_dt:
            # Within quiet hours
            mock_dt.now.return_value.hour = 12
            assert prefs.is_in_quiet_hours()

            # Before quiet hours
            mock_dt.now.return_value.hour = 8
            assert not prefs.is_in_quiet_hours()

            # After quiet hours
            mock_dt.now.return_value.hour = 18
            assert not prefs.is_in_quiet_hours()

    def test_is_in_quiet_hours_midnight_span(self):
        """Test is_in_quiet_hours spanning midnight (e.g., 22-7)."""
        prefs = NotificationPreferences(
            user_id="user-123",
            quiet_hours_start=22,
            quiet_hours_end=7,
        )
        with patch("sindri.collaboration.notifications.datetime") as mock_dt:
            # Late night (after start)
            mock_dt.now.return_value.hour = 23
            assert prefs.is_in_quiet_hours()

            # Early morning (before end)
            mock_dt.now.return_value.hour = 5
            assert prefs.is_in_quiet_hours()

            # Daytime (outside quiet hours)
            mock_dt.now.return_value.hour = 14
            assert not prefs.is_in_quiet_hours()


# ============================================
# NotificationStore Tests
# ============================================


@pytest_asyncio.fixture
async def notification_store(tmp_path):
    """Create a NotificationStore with a temporary database."""
    db = Database(tmp_path / "test.db")
    await db.initialize()
    return NotificationStore(database=db)


class TestNotificationStore:
    """Tests for NotificationStore persistence."""

    @pytest.mark.asyncio
    async def test_create_notification(self, notification_store):
        """Test creating a new notification."""
        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="You were mentioned",
            message="@user mentioned you in a comment",
            check_preferences=False,
        )
        assert notification is not None
        assert notification.id
        assert notification.user_id == "user-123"
        assert notification.type == NotificationType.MENTION
        assert notification.title == "You were mentioned"
        assert notification.message == "@user mentioned you in a comment"
        assert not notification.is_read

    @pytest.mark.asyncio
    async def test_create_notification_with_source_ids(self, notification_store):
        """Test creating notification with source IDs."""
        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.COMMENT,
            title="New comment",
            message="Someone commented on your session",
            source_user_id="commenter-456",
            source_session_id="session-789",
            source_comment_id="comment-abc",
            check_preferences=False,
        )
        assert notification.source_user_id == "commenter-456"
        assert notification.source_session_id == "session-789"
        assert notification.source_comment_id == "comment-abc"

    @pytest.mark.asyncio
    async def test_create_notification_with_priority(self, notification_store):
        """Test creating notification with custom priority."""
        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.TEAM_INVITE,
            title="Team invite",
            message="You've been invited to join a team",
            priority=NotificationPriority.HIGH,
            check_preferences=False,
        )
        assert notification.priority == NotificationPriority.HIGH

    @pytest.mark.asyncio
    async def test_create_notification_with_data(self, notification_store):
        """Test creating notification with extra data."""
        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.SESSION_SHARED,
            title="Session shared",
            message="A session was shared with you",
            data={"permission": "write", "session_name": "My Session"},
            check_preferences=False,
        )
        assert notification.data["permission"] == "write"
        assert notification.data["session_name"] == "My Session"

    @pytest.mark.asyncio
    async def test_create_notification_checks_preferences(self, notification_store):
        """Test that notification creation respects user preferences."""
        # Disable mention notifications
        await notification_store.update_preferences(
            user_id="user-123",
            mention_enabled=False,
        )

        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="You were mentioned",
            message="@user mentioned you",
            check_preferences=True,
        )
        assert notification is None

    @pytest.mark.asyncio
    async def test_create_notification_respects_global_disable(self, notification_store):
        """Test that globally disabled notifications are not created."""
        await notification_store.update_preferences(
            user_id="user-123",
            enabled=False,
        )

        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.COMMENT,
            title="New comment",
            message="Someone commented",
            check_preferences=True,
        )
        assert notification is None

    @pytest.mark.asyncio
    async def test_get_notification(self, notification_store):
        """Test retrieving a notification by ID."""
        created = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="Test",
            message="Test message",
            check_preferences=False,
        )

        retrieved = await notification_store.get_notification(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.user_id == "user-123"
        assert retrieved.title == "Test"

    @pytest.mark.asyncio
    async def test_get_notification_not_found(self, notification_store):
        """Test get_notification returns None for non-existent ID."""
        result = await notification_store.get_notification("non-existent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_notifications(self, notification_store):
        """Test getting all notifications for a user."""
        # Create multiple notifications
        for i in range(5):
            await notification_store.create_notification(
                user_id="user-123",
                notification_type=NotificationType.COMMENT,
                title=f"Notification {i}",
                message=f"Message {i}",
                check_preferences=False,
            )

        notifications = await notification_store.get_user_notifications("user-123")
        assert len(notifications) == 5

    @pytest.mark.asyncio
    async def test_get_user_notifications_unread_only(self, notification_store):
        """Test getting only unread notifications."""
        # Create 3 notifications
        notif_ids = []
        for i in range(3):
            n = await notification_store.create_notification(
                user_id="user-123",
                notification_type=NotificationType.COMMENT,
                title=f"Notification {i}",
                message=f"Message {i}",
                check_preferences=False,
            )
            notif_ids.append(n.id)

        # Mark first one as read
        await notification_store.mark_read(notif_ids[0])

        unread = await notification_store.get_user_notifications(
            "user-123", unread_only=True
        )
        assert len(unread) == 2

    @pytest.mark.asyncio
    async def test_get_user_notifications_by_type(self, notification_store):
        """Test filtering notifications by type."""
        await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="Mention",
            message="Mention message",
            check_preferences=False,
        )
        await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.COMMENT,
            title="Comment",
            message="Comment message",
            check_preferences=False,
        )

        mentions = await notification_store.get_user_notifications(
            "user-123", notification_type=NotificationType.MENTION
        )
        assert len(mentions) == 1
        assert mentions[0].type == NotificationType.MENTION

    @pytest.mark.asyncio
    async def test_get_user_notifications_pagination(self, notification_store):
        """Test notification pagination."""
        for i in range(10):
            await notification_store.create_notification(
                user_id="user-123",
                notification_type=NotificationType.COMMENT,
                title=f"Notification {i}",
                message=f"Message {i}",
                check_preferences=False,
            )

        page1 = await notification_store.get_user_notifications(
            "user-123", limit=5, offset=0
        )
        page2 = await notification_store.get_user_notifications(
            "user-123", limit=5, offset=5
        )

        assert len(page1) == 5
        assert len(page2) == 5
        # Ensure no overlap
        page1_ids = {n.id for n in page1}
        page2_ids = {n.id for n in page2}
        assert not page1_ids & page2_ids

    @pytest.mark.asyncio
    async def test_get_unread_count(self, notification_store):
        """Test getting unread notification count."""
        for i in range(5):
            await notification_store.create_notification(
                user_id="user-123",
                notification_type=NotificationType.COMMENT,
                title=f"Notification {i}",
                message=f"Message {i}",
                check_preferences=False,
            )

        count = await notification_store.get_unread_count("user-123")
        assert count == 5

    @pytest.mark.asyncio
    async def test_get_unread_count_after_mark_read(self, notification_store):
        """Test unread count decreases after marking read."""
        notifs = []
        for i in range(3):
            n = await notification_store.create_notification(
                user_id="user-123",
                notification_type=NotificationType.COMMENT,
                title=f"Notification {i}",
                message=f"Message {i}",
                check_preferences=False,
            )
            notifs.append(n)

        await notification_store.mark_read(notifs[0].id)

        count = await notification_store.get_unread_count("user-123")
        assert count == 2

    @pytest.mark.asyncio
    async def test_mark_read(self, notification_store):
        """Test marking a notification as read."""
        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="Test",
            message="Test",
            check_preferences=False,
        )

        result = await notification_store.mark_read(notification.id)
        assert result

        updated = await notification_store.get_notification(notification.id)
        assert updated.is_read
        assert updated.read_at is not None

    @pytest.mark.asyncio
    async def test_mark_read_already_read(self, notification_store):
        """Test marking an already-read notification."""
        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="Test",
            message="Test",
            check_preferences=False,
        )

        await notification_store.mark_read(notification.id)
        result = await notification_store.mark_read(notification.id)
        assert not result  # No rows updated

    @pytest.mark.asyncio
    async def test_mark_all_read(self, notification_store):
        """Test marking all notifications as read."""
        for i in range(5):
            await notification_store.create_notification(
                user_id="user-123",
                notification_type=NotificationType.COMMENT,
                title=f"Notification {i}",
                message=f"Message {i}",
                check_preferences=False,
            )

        count = await notification_store.mark_all_read("user-123")
        assert count == 5

        unread = await notification_store.get_unread_count("user-123")
        assert unread == 0

    @pytest.mark.asyncio
    async def test_archive_notification(self, notification_store):
        """Test archiving a notification."""
        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="Test",
            message="Test",
            check_preferences=False,
        )

        result = await notification_store.archive_notification(notification.id)
        assert result

        updated = await notification_store.get_notification(notification.id)
        assert updated.is_archived

    @pytest.mark.asyncio
    async def test_archived_excluded_by_default(self, notification_store):
        """Test that archived notifications are excluded by default."""
        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="Test",
            message="Test",
            check_preferences=False,
        )

        await notification_store.archive_notification(notification.id)

        notifications = await notification_store.get_user_notifications("user-123")
        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_include_archived(self, notification_store):
        """Test including archived notifications."""
        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="Test",
            message="Test",
            check_preferences=False,
        )

        await notification_store.archive_notification(notification.id)

        notifications = await notification_store.get_user_notifications(
            "user-123", include_archived=True
        )
        assert len(notifications) == 1

    @pytest.mark.asyncio
    async def test_delete_notification(self, notification_store):
        """Test deleting a notification."""
        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="Test",
            message="Test",
            check_preferences=False,
        )

        result = await notification_store.delete_notification(notification.id)
        assert result

        deleted = await notification_store.get_notification(notification.id)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_delete_notification_not_found(self, notification_store):
        """Test deleting non-existent notification."""
        result = await notification_store.delete_notification("non-existent")
        assert not result

    @pytest.mark.asyncio
    async def test_delete_old_notifications(self, notification_store):
        """Test deleting old read notifications."""
        # Create and mark old notification as read
        old_notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.COMMENT,
            title="Old",
            message="Old message",
            check_preferences=False,
        )
        await notification_store.mark_read(old_notification.id)

        # Manually update created_at to be old
        async with notification_store.db.get_connection() as conn:
            old_date = (datetime.now() - timedelta(days=60)).isoformat()
            await conn.execute(
                "UPDATE notifications SET created_at = ? WHERE id = ?",
                (old_date, old_notification.id),
            )
            await conn.commit()

        # Create recent notification
        await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="Recent",
            message="Recent message",
            check_preferences=False,
        )

        deleted = await notification_store.delete_old_notifications(days=30)
        assert deleted == 1

        remaining = await notification_store.get_user_notifications(
            "user-123", include_archived=True
        )
        assert len(remaining) == 1
        assert remaining[0].title == "Recent"


# ============================================
# NotificationPreferences Persistence Tests
# ============================================


class TestNotificationPreferencesPersistence:
    """Tests for NotificationPreferences persistence."""

    @pytest.mark.asyncio
    async def test_get_preferences_default(self, notification_store):
        """Test getting preferences returns defaults for new user."""
        prefs = await notification_store.get_preferences("new-user")
        assert prefs.user_id == "new-user"
        assert prefs.enabled
        assert prefs.mention_enabled
        assert prefs.comment_enabled

    @pytest.mark.asyncio
    async def test_update_preferences(self, notification_store):
        """Test updating preferences."""
        prefs = await notification_store.update_preferences(
            user_id="user-123",
            enabled=True,
            email_enabled=True,
            mention_enabled=False,
            quiet_hours_start=22,
            quiet_hours_end=7,
        )
        assert prefs.email_enabled
        assert not prefs.mention_enabled
        assert prefs.quiet_hours_start == 22
        assert prefs.quiet_hours_end == 7

    @pytest.mark.asyncio
    async def test_update_preferences_persists(self, notification_store):
        """Test that updated preferences persist."""
        await notification_store.update_preferences(
            user_id="user-123",
            team_enabled=False,
        )

        prefs = await notification_store.get_preferences("user-123")
        assert not prefs.team_enabled

    @pytest.mark.asyncio
    async def test_update_preferences_partial(self, notification_store):
        """Test partial preference updates."""
        await notification_store.update_preferences(
            user_id="user-123",
            mention_enabled=False,
        )

        # Update different field
        await notification_store.update_preferences(
            user_id="user-123",
            comment_enabled=False,
        )

        prefs = await notification_store.get_preferences("user-123")
        assert not prefs.mention_enabled
        assert not prefs.comment_enabled


# ============================================
# Statistics Tests
# ============================================


class TestNotificationStatistics:
    """Tests for notification statistics."""

    @pytest.mark.asyncio
    async def test_get_statistics_user(self, notification_store):
        """Test getting statistics for a specific user."""
        for i in range(5):
            await notification_store.create_notification(
                user_id="user-123",
                notification_type=NotificationType.COMMENT,
                title=f"Notification {i}",
                message=f"Message {i}",
                check_preferences=False,
            )

        notifications = await notification_store.get_user_notifications("user-123")
        await notification_store.mark_read(notifications[0].id)
        await notification_store.mark_read(notifications[1].id)
        await notification_store.archive_notification(notifications[2].id)

        stats = await notification_store.get_statistics("user-123")
        assert stats["total"] == 5
        assert stats["unread"] == 3  # 5 total - 2 marked read = 3 unread (archived one not read)
        assert stats["read"] == 2
        assert stats["archived"] == 1

    @pytest.mark.asyncio
    async def test_get_statistics_global(self, notification_store):
        """Test getting global statistics."""
        for i in range(3):
            await notification_store.create_notification(
                user_id="user-1",
                notification_type=NotificationType.COMMENT,
                title=f"Notification {i}",
                message=f"Message {i}",
                check_preferences=False,
            )

        for i in range(2):
            await notification_store.create_notification(
                user_id="user-2",
                notification_type=NotificationType.MENTION,
                title=f"Notification {i}",
                message=f"Message {i}",
                check_preferences=False,
            )

        stats = await notification_store.get_statistics()
        assert stats["total"] == 5
        assert stats["users_with_notifications"] == 2

    @pytest.mark.asyncio
    async def test_get_type_counts(self, notification_store):
        """Test getting notification counts by type."""
        await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="Mention 1",
            message="Message",
            check_preferences=False,
        )
        await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="Mention 2",
            message="Message",
            check_preferences=False,
        )
        await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.COMMENT,
            title="Comment",
            message="Message",
            check_preferences=False,
        )

        counts = await notification_store.get_type_counts("user-123")
        assert counts.get("mention") == 2
        assert counts.get("comment") == 1


# ============================================
# Convenience Function Tests
# ============================================


class TestConvenienceFunctions:
    """Tests for notification convenience functions."""

    @pytest.mark.asyncio
    async def test_notify_mention(self, notification_store):
        """Test notify_mention convenience function."""
        notification = await notify_mention(
            store=notification_store,
            user_id="mentioned-user",
            mentioned_by="mentioner",
            mentioned_by_name="John Doe",
            comment_id="comment-123",
            session_id="session-456",
            context="Check out this code",
        )
        assert notification is not None
        assert notification.type == NotificationType.MENTION
        assert notification.priority == NotificationPriority.HIGH
        assert "John Doe" in notification.title
        assert notification.source_user_id == "mentioner"
        assert notification.source_session_id == "session-456"
        assert notification.source_comment_id == "comment-123"

    @pytest.mark.asyncio
    async def test_notify_comment(self, notification_store):
        """Test notify_comment convenience function."""
        notification = await notify_comment(
            store=notification_store,
            user_id="session-owner",
            commenter_id="commenter",
            commenter_name="Jane Smith",
            session_id="session-123",
            comment_preview="This looks great!",
        )
        assert notification is not None
        assert notification.type == NotificationType.COMMENT
        assert "Jane Smith" in notification.title
        assert notification.source_user_id == "commenter"
        assert notification.source_session_id == "session-123"

    @pytest.mark.asyncio
    async def test_notify_team_invite(self, notification_store):
        """Test notify_team_invite convenience function."""
        notification = await notify_team_invite(
            store=notification_store,
            user_id="invited-user",
            team_id="team-123",
            team_name="Code Warriors",
            invited_by="admin",
            invited_by_name="Admin User",
        )
        assert notification is not None
        assert notification.type == NotificationType.TEAM_INVITE
        assert notification.priority == NotificationPriority.HIGH
        assert "Code Warriors" in notification.title
        assert notification.source_user_id == "admin"
        assert notification.source_team_id == "team-123"

    @pytest.mark.asyncio
    async def test_notify_session_shared(self, notification_store):
        """Test notify_session_shared convenience function."""
        notification = await notify_session_shared(
            store=notification_store,
            user_id="recipient",
            session_id="session-123",
            shared_by="sharer",
            shared_by_name="Bob",
            permission="write",
        )
        assert notification is not None
        assert notification.type == NotificationType.SESSION_SHARED
        assert "Bob" in notification.title
        assert notification.source_user_id == "sharer"
        assert notification.source_session_id == "session-123"
        assert notification.data["permission"] == "write"


# ============================================
# Edge Case Tests
# ============================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_notification_with_long_message(self, notification_store):
        """Test notification with very long message."""
        long_message = "A" * 10000
        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.COMMENT,
            title="Test",
            message=long_message,
            check_preferences=False,
        )
        assert notification is not None
        retrieved = await notification_store.get_notification(notification.id)
        assert len(retrieved.message) == len(long_message)

    @pytest.mark.asyncio
    async def test_notification_with_special_characters(self, notification_store):
        """Test notification with special characters."""
        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.MENTION,
            title="@user mentioned you",
            message="Check this: <script>alert('xss')</script> & \"quotes\"",
            check_preferences=False,
        )
        assert notification is not None
        retrieved = await notification_store.get_notification(notification.id)
        assert "<script>" in retrieved.message

    @pytest.mark.asyncio
    async def test_notification_with_unicode(self, notification_store):
        """Test notification with unicode characters."""
        notification = await notification_store.create_notification(
            user_id="user-123",
            notification_type=NotificationType.COMMENT,
            title="Comment on your session",
            message="Great work! Here's a thumbs up: \U0001F44D",
            check_preferences=False,
        )
        assert notification is not None
        retrieved = await notification_store.get_notification(notification.id)
        assert "\U0001F44D" in retrieved.message

    @pytest.mark.asyncio
    async def test_concurrent_notifications(self, notification_store):
        """Test creating many notifications concurrently."""
        import asyncio

        async def create_notif(i):
            return await notification_store.create_notification(
                user_id="user-123",
                notification_type=NotificationType.COMMENT,
                title=f"Notification {i}",
                message=f"Message {i}",
                check_preferences=False,
            )

        notifications = await asyncio.gather(*[create_notif(i) for i in range(50)])
        assert len(notifications) == 50
        assert all(n is not None for n in notifications)

        # Verify all were created
        count = await notification_store.get_unread_count("user-123")
        assert count == 50
