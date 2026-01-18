"""Tests for the Activity Feed System."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from sindri.collaboration.activity import (
    Activity,
    ActivityType,
    ActivityStore,
    TargetType,
    generate_activity_id,
    log_session_created,
    log_session_completed,
    log_session_failed,
    log_member_joined,
    log_member_left,
    log_role_changed,
    log_comment_added,
    log_session_shared,
    log_team_updated,
)
from sindri.persistence.database import Database


# ============================================
# Activity ID Generation Tests
# ============================================


class TestActivityIdGeneration:
    """Tests for activity ID generation."""

    def test_generate_activity_id_unique(self):
        """Test that activity IDs are unique."""
        ids = [generate_activity_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_generate_activity_id_length(self):
        """Test activity ID length."""
        activity_id = generate_activity_id()
        assert len(activity_id) == 32  # 16 bytes hex

    def test_generate_activity_id_hex(self):
        """Test activity ID is valid hex."""
        activity_id = generate_activity_id()
        int(activity_id, 16)  # Should not raise


# ============================================
# ActivityType Tests
# ============================================


class TestActivityType:
    """Tests for ActivityType enum."""

    def test_session_activity_types(self):
        """Test session-related activity types."""
        assert ActivityType.SESSION_CREATED.value == "session_created"
        assert ActivityType.SESSION_COMPLETED.value == "session_completed"
        assert ActivityType.SESSION_FAILED.value == "session_failed"
        assert ActivityType.SESSION_RESUMED.value == "session_resumed"

    def test_task_activity_types(self):
        """Test task-related activity types."""
        assert ActivityType.TASK_STARTED.value == "task_started"
        assert ActivityType.TASK_COMPLETED.value == "task_completed"
        assert ActivityType.TASK_DELEGATED.value == "task_delegated"

    def test_comment_activity_types(self):
        """Test comment-related activity types."""
        assert ActivityType.COMMENT_ADDED.value == "comment_added"
        assert ActivityType.COMMENT_RESOLVED.value == "comment_resolved"
        assert ActivityType.COMMENT_REPLIED.value == "comment_replied"

    def test_member_activity_types(self):
        """Test member-related activity types."""
        assert ActivityType.MEMBER_JOINED.value == "member_joined"
        assert ActivityType.MEMBER_LEFT.value == "member_left"
        assert ActivityType.MEMBER_ROLE_CHANGED.value == "member_role_changed"
        assert ActivityType.MEMBER_INVITED.value == "member_invited"

    def test_sharing_activity_types(self):
        """Test sharing-related activity types."""
        assert ActivityType.SESSION_SHARED.value == "session_shared"
        assert ActivityType.SHARE_REVOKED.value == "share_revoked"

    def test_team_activity_types(self):
        """Test team-related activity types."""
        assert ActivityType.TEAM_CREATED.value == "team_created"
        assert ActivityType.TEAM_UPDATED.value == "team_updated"
        assert ActivityType.TEAM_SETTINGS_CHANGED.value == "team_settings_changed"

    def test_activity_type_is_string_enum(self):
        """Test ActivityType is a string enum."""
        assert isinstance(ActivityType.SESSION_CREATED, str)
        assert ActivityType.SESSION_CREATED == "session_created"


# ============================================
# TargetType Tests
# ============================================


class TestTargetType:
    """Tests for TargetType enum."""

    def test_target_types(self):
        """Test all target types."""
        assert TargetType.SESSION.value == "session"
        assert TargetType.TASK.value == "task"
        assert TargetType.USER.value == "user"
        assert TargetType.TEAM.value == "team"
        assert TargetType.COMMENT.value == "comment"
        assert TargetType.SHARE.value == "share"

    def test_target_type_is_string_enum(self):
        """Test TargetType is a string enum."""
        assert isinstance(TargetType.SESSION, str)
        assert TargetType.SESSION == "session"


# ============================================
# Activity Dataclass Tests
# ============================================


class TestActivityDataclass:
    """Tests for Activity dataclass."""

    def test_activity_required_fields(self):
        """Test Activity with required fields only."""
        activity = Activity(
            id="test-id",
            team_id="team-123",
            actor_id="user-456",
            type=ActivityType.SESSION_CREATED,
        )
        assert activity.id == "test-id"
        assert activity.team_id == "team-123"
        assert activity.actor_id == "user-456"
        assert activity.type == ActivityType.SESSION_CREATED

    def test_activity_defaults(self):
        """Test Activity default values."""
        activity = Activity(
            id="test-id",
            team_id="team-123",
            actor_id="user-456",
            type=ActivityType.SESSION_CREATED,
        )
        assert activity.target_id is None
        assert activity.target_type is None
        assert activity.message == ""
        assert activity.metadata == {}
        assert isinstance(activity.created_at, datetime)

    def test_activity_all_fields(self):
        """Test Activity with all fields."""
        created = datetime(2026, 1, 17, 12, 0, 0)
        activity = Activity(
            id="test-id",
            team_id="team-123",
            actor_id="user-456",
            type=ActivityType.SESSION_COMPLETED,
            target_id="session-789",
            target_type=TargetType.SESSION,
            message="Completed task X",
            metadata={"duration": 3600},
            created_at=created,
        )
        assert activity.target_id == "session-789"
        assert activity.target_type == TargetType.SESSION
        assert activity.message == "Completed task X"
        assert activity.metadata == {"duration": 3600}
        assert activity.created_at == created

    def test_activity_to_dict(self):
        """Test Activity to_dict conversion."""
        activity = Activity(
            id="test-id",
            team_id="team-123",
            actor_id="user-456",
            type=ActivityType.MEMBER_JOINED,
            target_id="user-789",
            target_type=TargetType.USER,
            message="User joined",
            metadata={"role": "member"},
        )
        result = activity.to_dict()

        assert result["id"] == "test-id"
        assert result["team_id"] == "team-123"
        assert result["actor_id"] == "user-456"
        assert result["type"] == "member_joined"
        assert result["target_id"] == "user-789"
        assert result["target_type"] == "user"
        assert result["message"] == "User joined"
        assert result["metadata"] == {"role": "member"}
        assert "created_at" in result

    def test_activity_to_dict_none_target_type(self):
        """Test to_dict with no target type."""
        activity = Activity(
            id="test-id",
            team_id="team-123",
            actor_id="user-456",
            type=ActivityType.TEAM_UPDATED,
        )
        result = activity.to_dict()
        assert result["target_type"] is None


# ============================================
# ActivityStore Tests
# ============================================


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield Database(db_path=db_path)


@pytest.fixture
def activity_store(temp_db):
    """Create an ActivityStore with temp database."""
    return ActivityStore(database=temp_db)


class TestActivityStore:
    """Tests for ActivityStore."""

    @pytest.mark.asyncio
    async def test_create_activity(self, activity_store):
        """Test creating an activity."""
        activity = await activity_store.create(
            team_id="team-123",
            actor_id="user-456",
            activity_type=ActivityType.SESSION_CREATED,
            target_id="session-789",
            target_type=TargetType.SESSION,
            message="Created session",
            metadata={"test": "value"},
        )

        assert activity.id is not None
        assert len(activity.id) == 32
        assert activity.team_id == "team-123"
        assert activity.actor_id == "user-456"
        assert activity.type == ActivityType.SESSION_CREATED
        assert activity.target_id == "session-789"
        assert activity.target_type == TargetType.SESSION
        assert activity.message == "Created session"
        assert activity.metadata == {"test": "value"}

    @pytest.mark.asyncio
    async def test_create_activity_minimal(self, activity_store):
        """Test creating activity with minimal fields."""
        activity = await activity_store.create(
            team_id="team-123",
            actor_id="user-456",
            activity_type=ActivityType.TEAM_UPDATED,
        )

        assert activity.id is not None
        assert activity.target_id is None
        assert activity.target_type is None
        assert activity.message == ""
        assert activity.metadata == {}

    @pytest.mark.asyncio
    async def test_get_activity(self, activity_store):
        """Test retrieving an activity by ID."""
        created = await activity_store.create(
            team_id="team-123",
            actor_id="user-456",
            activity_type=ActivityType.SESSION_CREATED,
            message="Test activity",
        )

        retrieved = await activity_store.get(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.team_id == "team-123"
        assert retrieved.actor_id == "user-456"
        assert retrieved.type == ActivityType.SESSION_CREATED
        assert retrieved.message == "Test activity"

    @pytest.mark.asyncio
    async def test_get_activity_not_found(self, activity_store):
        """Test retrieving non-existent activity."""
        result = await activity_store.get("non-existent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_team(self, activity_store):
        """Test listing activities by team."""
        # Create activities for different teams
        for i in range(5):
            await activity_store.create(
                team_id="team-A",
                actor_id=f"user-{i}",
                activity_type=ActivityType.SESSION_CREATED,
            )
        for i in range(3):
            await activity_store.create(
                team_id="team-B",
                actor_id=f"user-{i}",
                activity_type=ActivityType.SESSION_CREATED,
            )

        # List team A activities
        activities = await activity_store.list_by_team("team-A")
        assert len(activities) == 5
        assert all(a.team_id == "team-A" for a in activities)

        # List team B activities
        activities = await activity_store.list_by_team("team-B")
        assert len(activities) == 3

    @pytest.mark.asyncio
    async def test_list_by_team_with_limit(self, activity_store):
        """Test listing with limit."""
        for i in range(10):
            await activity_store.create(
                team_id="team-123",
                actor_id=f"user-{i}",
                activity_type=ActivityType.SESSION_CREATED,
            )

        activities = await activity_store.list_by_team("team-123", limit=5)
        assert len(activities) == 5

    @pytest.mark.asyncio
    async def test_list_by_team_with_offset(self, activity_store):
        """Test listing with offset."""
        for i in range(10):
            await activity_store.create(
                team_id="team-123",
                actor_id=f"user-{i}",
                activity_type=ActivityType.SESSION_CREATED,
            )

        activities = await activity_store.list_by_team("team-123", limit=5, offset=5)
        assert len(activities) == 5

    @pytest.mark.asyncio
    async def test_list_by_team_with_type_filter(self, activity_store):
        """Test listing with activity type filter."""
        await activity_store.create(
            team_id="team-123",
            actor_id="user-1",
            activity_type=ActivityType.SESSION_CREATED,
        )
        await activity_store.create(
            team_id="team-123",
            actor_id="user-2",
            activity_type=ActivityType.SESSION_COMPLETED,
        )
        await activity_store.create(
            team_id="team-123",
            actor_id="user-3",
            activity_type=ActivityType.MEMBER_JOINED,
        )

        activities = await activity_store.list_by_team(
            "team-123",
            activity_types=[ActivityType.SESSION_CREATED, ActivityType.SESSION_COMPLETED],
        )
        assert len(activities) == 2
        assert all(
            a.type in [ActivityType.SESSION_CREATED, ActivityType.SESSION_COMPLETED]
            for a in activities
        )

    @pytest.mark.asyncio
    async def test_list_by_team_ordered_by_date(self, activity_store):
        """Test activities are ordered by date descending."""
        for i in range(5):
            await activity_store.create(
                team_id="team-123",
                actor_id=f"user-{i}",
                activity_type=ActivityType.SESSION_CREATED,
            )

        activities = await activity_store.list_by_team("team-123")

        # Should be ordered newest first
        for i in range(len(activities) - 1):
            assert activities[i].created_at >= activities[i + 1].created_at

    @pytest.mark.asyncio
    async def test_list_by_user(self, activity_store):
        """Test listing activities by user."""
        # Create activities from different users
        for i in range(5):
            await activity_store.create(
                team_id="team-123",
                actor_id="user-A",
                activity_type=ActivityType.SESSION_CREATED,
            )
        for i in range(3):
            await activity_store.create(
                team_id="team-123",
                actor_id="user-B",
                activity_type=ActivityType.SESSION_CREATED,
            )

        activities = await activity_store.list_by_user("user-A")
        assert len(activities) == 5
        assert all(a.actor_id == "user-A" for a in activities)

    @pytest.mark.asyncio
    async def test_list_by_target(self, activity_store):
        """Test listing activities by target."""
        # Create activities for different targets
        for i in range(3):
            await activity_store.create(
                team_id="team-123",
                actor_id=f"user-{i}",
                activity_type=ActivityType.COMMENT_ADDED,
                target_id="session-A",
                target_type=TargetType.SESSION,
            )
        await activity_store.create(
            team_id="team-123",
            actor_id="user-1",
            activity_type=ActivityType.COMMENT_ADDED,
            target_id="session-B",
            target_type=TargetType.SESSION,
        )

        activities = await activity_store.list_by_target("session-A")
        assert len(activities) == 3
        assert all(a.target_id == "session-A" for a in activities)

    @pytest.mark.asyncio
    async def test_list_by_target_with_type(self, activity_store):
        """Test listing activities by target with type filter."""
        await activity_store.create(
            team_id="team-123",
            actor_id="user-1",
            activity_type=ActivityType.COMMENT_ADDED,
            target_id="session-A",
            target_type=TargetType.SESSION,
        )
        await activity_store.create(
            team_id="team-123",
            actor_id="user-2",
            activity_type=ActivityType.COMMENT_ADDED,
            target_id="session-A",
            target_type=TargetType.COMMENT,  # Different target type
        )

        activities = await activity_store.list_by_target(
            "session-A", target_type=TargetType.SESSION
        )
        assert len(activities) == 1
        assert activities[0].target_type == TargetType.SESSION

    @pytest.mark.asyncio
    async def test_count_by_team(self, activity_store):
        """Test counting activities by team."""
        for i in range(7):
            await activity_store.create(
                team_id="team-123",
                actor_id=f"user-{i}",
                activity_type=ActivityType.SESSION_CREATED,
            )

        count = await activity_store.count_by_team("team-123")
        assert count == 7

    @pytest.mark.asyncio
    async def test_count_by_team_empty(self, activity_store):
        """Test counting for empty team."""
        count = await activity_store.count_by_team("non-existent")
        assert count == 0

    @pytest.mark.asyncio
    async def test_delete_old(self, activity_store):
        """Test deleting old activities."""
        # Create some activities (they'll all be recent)
        for i in range(5):
            await activity_store.create(
                team_id="team-123",
                actor_id=f"user-{i}",
                activity_type=ActivityType.SESSION_CREATED,
            )

        # Try to delete activities older than 90 days
        # None should be deleted since all are recent
        deleted = await activity_store.delete_old(days_old=90)
        assert deleted == 0

        # All activities should still exist
        activities = await activity_store.list_by_team("team-123")
        assert len(activities) == 5

    @pytest.mark.asyncio
    async def test_get_stats(self, activity_store):
        """Test getting activity statistics."""
        # Create various activities
        await activity_store.create(
            team_id="team-123",
            actor_id="user-A",
            activity_type=ActivityType.SESSION_CREATED,
        )
        await activity_store.create(
            team_id="team-123",
            actor_id="user-A",
            activity_type=ActivityType.SESSION_COMPLETED,
        )
        await activity_store.create(
            team_id="team-123",
            actor_id="user-B",
            activity_type=ActivityType.MEMBER_JOINED,
        )

        stats = await activity_store.get_stats()

        assert stats["total_activities"] == 3
        assert stats["last_24h"] == 3
        assert "session_created" in stats["by_type"]
        assert "session_completed" in stats["by_type"]
        assert "member_joined" in stats["by_type"]
        assert len(stats["most_active_users"]) > 0

    @pytest.mark.asyncio
    async def test_get_stats_by_team(self, activity_store):
        """Test getting stats for specific team."""
        await activity_store.create(
            team_id="team-A",
            actor_id="user-1",
            activity_type=ActivityType.SESSION_CREATED,
        )
        await activity_store.create(
            team_id="team-B",
            actor_id="user-2",
            activity_type=ActivityType.SESSION_CREATED,
        )

        stats = await activity_store.get_stats(team_id="team-A")
        assert stats["total_activities"] == 1


# ============================================
# Convenience Function Tests
# ============================================


class TestConvenienceFunctions:
    """Tests for activity logging convenience functions."""

    @pytest.mark.asyncio
    async def test_log_session_created(self, activity_store):
        """Test log_session_created function."""
        activity = await log_session_created(
            store=activity_store,
            team_id="team-123",
            actor_id="user-456",
            session_id="session-789",
            session_name="Test Session",
        )

        assert activity.type == ActivityType.SESSION_CREATED
        assert activity.target_id == "session-789"
        assert activity.target_type == TargetType.SESSION
        assert "Test Session" in activity.message
        assert activity.metadata["session_name"] == "Test Session"

    @pytest.mark.asyncio
    async def test_log_session_created_no_name(self, activity_store):
        """Test log_session_created without session name."""
        activity = await log_session_created(
            store=activity_store,
            team_id="team-123",
            actor_id="user-456",
            session_id="session-789",
        )

        assert "Created a new session" in activity.message

    @pytest.mark.asyncio
    async def test_log_session_completed(self, activity_store):
        """Test log_session_completed function."""
        activity = await log_session_completed(
            store=activity_store,
            team_id="team-123",
            actor_id="user-456",
            session_id="session-789",
            session_name="Test Session",
            duration_seconds=3600,
        )

        assert activity.type == ActivityType.SESSION_COMPLETED
        assert activity.target_id == "session-789"
        assert activity.target_type == TargetType.SESSION
        assert "Test Session" in activity.message
        assert activity.metadata["duration_seconds"] == 3600

    @pytest.mark.asyncio
    async def test_log_session_failed(self, activity_store):
        """Test log_session_failed function."""
        activity = await log_session_failed(
            store=activity_store,
            team_id="team-123",
            actor_id="user-456",
            session_id="session-789",
            error_message="Connection timeout",
        )

        assert activity.type == ActivityType.SESSION_FAILED
        assert activity.target_id == "session-789"
        assert "Connection timeout" in activity.message
        assert activity.metadata["error"] == "Connection timeout"

    @pytest.mark.asyncio
    async def test_log_member_joined_self(self, activity_store):
        """Test log_member_joined when user joins themselves."""
        activity = await log_member_joined(
            store=activity_store,
            team_id="team-123",
            actor_id="user-456",
            member_id="user-456",  # Same as actor
            member_name="Alice",
            role="member",
        )

        assert activity.type == ActivityType.MEMBER_JOINED
        assert activity.target_id == "user-456"
        assert activity.target_type == TargetType.USER
        assert "joined the team" in activity.message
        assert activity.metadata["role"] == "member"

    @pytest.mark.asyncio
    async def test_log_member_joined_by_other(self, activity_store):
        """Test log_member_joined when added by another user."""
        activity = await log_member_joined(
            store=activity_store,
            team_id="team-123",
            actor_id="admin-1",
            member_id="user-456",  # Different from actor
            member_name="Bob",
            role="viewer",
        )

        assert "was added to the team" in activity.message

    @pytest.mark.asyncio
    async def test_log_member_left(self, activity_store):
        """Test log_member_left function."""
        activity = await log_member_left(
            store=activity_store,
            team_id="team-123",
            actor_id="user-456",
            member_id="user-456",
            member_name="Alice",
            removed=False,
        )

        assert activity.type == ActivityType.MEMBER_LEFT
        assert "left the team" in activity.message
        assert activity.metadata["removed"] is False

    @pytest.mark.asyncio
    async def test_log_member_removed(self, activity_store):
        """Test log_member_left when member is removed."""
        activity = await log_member_left(
            store=activity_store,
            team_id="team-123",
            actor_id="admin-1",
            member_id="user-456",
            member_name="Bob",
            removed=True,
        )

        assert "was removed from the team" in activity.message
        assert activity.metadata["removed"] is True

    @pytest.mark.asyncio
    async def test_log_role_changed(self, activity_store):
        """Test log_role_changed function."""
        activity = await log_role_changed(
            store=activity_store,
            team_id="team-123",
            actor_id="admin-1",
            member_id="user-456",
            member_name="Alice",
            old_role="member",
            new_role="admin",
        )

        assert activity.type == ActivityType.MEMBER_ROLE_CHANGED
        assert activity.target_id == "user-456"
        assert "member" in activity.message
        assert "admin" in activity.message
        assert activity.metadata["old_role"] == "member"
        assert activity.metadata["new_role"] == "admin"

    @pytest.mark.asyncio
    async def test_log_comment_added(self, activity_store):
        """Test log_comment_added function."""
        activity = await log_comment_added(
            store=activity_store,
            team_id="team-123",
            actor_id="user-456",
            session_id="session-789",
            comment_id="comment-abc",
            comment_preview="This looks good!",
        )

        assert activity.type == ActivityType.COMMENT_ADDED
        assert activity.target_id == "comment-abc"
        assert activity.target_type == TargetType.COMMENT
        assert "This looks good!" in activity.message
        assert activity.metadata["session_id"] == "session-789"

    @pytest.mark.asyncio
    async def test_log_comment_added_long_preview(self, activity_store):
        """Test log_comment_added truncates long previews."""
        long_comment = "x" * 150
        activity = await log_comment_added(
            store=activity_store,
            team_id="team-123",
            actor_id="user-456",
            session_id="session-789",
            comment_id="comment-abc",
            comment_preview=long_comment,
        )

        assert len(activity.metadata["preview"]) <= 103  # 100 + "..."

    @pytest.mark.asyncio
    async def test_log_session_shared(self, activity_store):
        """Test log_session_shared function."""
        activity = await log_session_shared(
            store=activity_store,
            team_id="team-123",
            actor_id="user-456",
            session_id="session-789",
            share_id="share-abc",
            permission="write",
        )

        assert activity.type == ActivityType.SESSION_SHARED
        assert activity.target_id == "session-789"
        assert activity.target_type == TargetType.SESSION
        assert "write" in activity.message
        assert activity.metadata["share_id"] == "share-abc"
        assert activity.metadata["permission"] == "write"

    @pytest.mark.asyncio
    async def test_log_team_updated(self, activity_store):
        """Test log_team_updated function."""
        changes = {"name": "New Name", "description": "New description"}
        activity = await log_team_updated(
            store=activity_store,
            team_id="team-123",
            actor_id="admin-1",
            changes=changes,
        )

        assert activity.type == ActivityType.TEAM_UPDATED
        assert activity.target_id == "team-123"
        assert activity.target_type == TargetType.TEAM
        assert "name" in activity.message
        assert "description" in activity.message
        assert activity.metadata["changes"] == changes


# ============================================
# Date Range Filter Tests
# ============================================


class TestDateRangeFilters:
    """Tests for date range filtering."""

    @pytest.mark.asyncio
    async def test_list_with_start_date(self, activity_store):
        """Test filtering by start date."""
        # Create activity
        await activity_store.create(
            team_id="team-123",
            actor_id="user-1",
            activity_type=ActivityType.SESSION_CREATED,
        )

        # Query with start date in the past should include it
        yesterday = datetime.now() - timedelta(days=1)
        activities = await activity_store.list_by_team(
            "team-123", start_date=yesterday
        )
        assert len(activities) == 1

        # Query with start date in the future should exclude it
        tomorrow = datetime.now() + timedelta(days=1)
        activities = await activity_store.list_by_team(
            "team-123", start_date=tomorrow
        )
        assert len(activities) == 0

    @pytest.mark.asyncio
    async def test_list_with_end_date(self, activity_store):
        """Test filtering by end date."""
        await activity_store.create(
            team_id="team-123",
            actor_id="user-1",
            activity_type=ActivityType.SESSION_CREATED,
        )

        # Query with end date in the future should include it
        tomorrow = datetime.now() + timedelta(days=1)
        activities = await activity_store.list_by_team(
            "team-123", end_date=tomorrow
        )
        assert len(activities) == 1

        # Query with end date in the past should exclude it
        yesterday = datetime.now() - timedelta(days=1)
        activities = await activity_store.list_by_team(
            "team-123", end_date=yesterday
        )
        assert len(activities) == 0


# ============================================
# Edge Cases
# ============================================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_empty_team(self, activity_store):
        """Test listing empty team activities."""
        activities = await activity_store.list_by_team("non-existent-team")
        assert activities == []

    @pytest.mark.asyncio
    async def test_empty_user(self, activity_store):
        """Test listing empty user activities."""
        activities = await activity_store.list_by_user("non-existent-user")
        assert activities == []

    @pytest.mark.asyncio
    async def test_metadata_json_serialization(self, activity_store):
        """Test complex metadata is properly serialized."""
        complex_metadata = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "unicode": "Hello 世界",
        }

        activity = await activity_store.create(
            team_id="team-123",
            actor_id="user-456",
            activity_type=ActivityType.TEAM_UPDATED,
            metadata=complex_metadata,
        )

        retrieved = await activity_store.get(activity.id)
        assert retrieved.metadata == complex_metadata

    @pytest.mark.asyncio
    async def test_special_characters_in_message(self, activity_store):
        """Test special characters in message."""
        message = "Hello 'world' \"test\" <tag> & more"
        activity = await activity_store.create(
            team_id="team-123",
            actor_id="user-456",
            activity_type=ActivityType.COMMENT_ADDED,
            message=message,
        )

        retrieved = await activity_store.get(activity.id)
        assert retrieved.message == message

    def test_activity_type_from_string(self):
        """Test creating ActivityType from string."""
        activity_type = ActivityType("session_created")
        assert activity_type == ActivityType.SESSION_CREATED

    def test_activity_type_invalid_string(self):
        """Test invalid ActivityType string raises error."""
        with pytest.raises(ValueError):
            ActivityType("invalid_type")

    def test_target_type_from_string(self):
        """Test creating TargetType from string."""
        target_type = TargetType("session")
        assert target_type == TargetType.SESSION
