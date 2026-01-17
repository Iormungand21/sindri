"""Tests for remote collaboration module (Phase 9.2)."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from sindri.collaboration.sharing import (
    SessionShare,
    SharePermission,
    ShareStore,
    generate_share_token,
)
from sindri.collaboration.comments import (
    SessionComment,
    CommentType,
    CommentStatus,
    CommentStore,
)
from sindri.collaboration.presence import (
    Participant,
    ParticipantStatus,
    PresenceManager,
    PARTICIPANT_COLORS,
)


# ============================================
# Share Token Generation Tests
# ============================================


class TestShareTokenGeneration:
    """Tests for share token generation."""

    def test_generate_share_token_default_length(self):
        """Test default token length is 16."""
        token = generate_share_token()
        assert len(token) == 16

    def test_generate_share_token_custom_length(self):
        """Test custom token length."""
        token = generate_share_token(length=32)
        assert len(token) == 32

    def test_generate_share_token_is_alphanumeric(self):
        """Test token is alphanumeric."""
        token = generate_share_token()
        assert token.isalnum()

    def test_generate_share_token_unique(self):
        """Test tokens are unique."""
        tokens = [generate_share_token() for _ in range(100)]
        assert len(set(tokens)) == 100


# ============================================
# SessionShare Dataclass Tests
# ============================================


class TestSessionShare:
    """Tests for SessionShare dataclass."""

    def test_session_share_defaults(self):
        """Test SessionShare defaults."""
        share = SessionShare(
            session_id="test-session",
            share_token="abc123",
        )
        assert share.permission == SharePermission.READ
        assert share.is_active
        assert share.use_count == 0
        assert share.expires_at is None
        assert share.max_uses is None

    def test_is_expired_no_expiry(self):
        """Test is_expired with no expiry date."""
        share = SessionShare(
            session_id="test-session",
            share_token="abc123",
        )
        assert not share.is_expired

    def test_is_expired_future_expiry(self):
        """Test is_expired with future expiry."""
        share = SessionShare(
            session_id="test-session",
            share_token="abc123",
            expires_at=datetime.now() + timedelta(hours=24),
        )
        assert not share.is_expired

    def test_is_expired_past_expiry(self):
        """Test is_expired with past expiry."""
        share = SessionShare(
            session_id="test-session",
            share_token="abc123",
            expires_at=datetime.now() - timedelta(hours=1),
        )
        assert share.is_expired

    def test_is_exhausted_no_max(self):
        """Test is_exhausted with no max uses."""
        share = SessionShare(
            session_id="test-session",
            share_token="abc123",
        )
        assert not share.is_exhausted

    def test_is_exhausted_under_max(self):
        """Test is_exhausted under max uses."""
        share = SessionShare(
            session_id="test-session",
            share_token="abc123",
            max_uses=10,
            use_count=5,
        )
        assert not share.is_exhausted

    def test_is_exhausted_at_max(self):
        """Test is_exhausted at max uses."""
        share = SessionShare(
            session_id="test-session",
            share_token="abc123",
            max_uses=10,
            use_count=10,
        )
        assert share.is_exhausted

    def test_is_valid_active(self):
        """Test is_valid for active share."""
        share = SessionShare(
            session_id="test-session",
            share_token="abc123",
        )
        assert share.is_valid

    def test_is_valid_inactive(self):
        """Test is_valid for inactive share."""
        share = SessionShare(
            session_id="test-session",
            share_token="abc123",
            is_active=False,
        )
        assert not share.is_valid

    def test_can_read_permissions(self):
        """Test can_read for various permissions."""
        for perm in SharePermission:
            share = SessionShare(
                session_id="test-session",
                share_token="abc123",
                permission=perm,
            )
            assert share.can_read()  # All permissions can read

    def test_can_comment_permissions(self):
        """Test can_comment for various permissions."""
        read_share = SessionShare(
            session_id="test-session",
            share_token="abc123",
            permission=SharePermission.READ,
        )
        assert not read_share.can_comment()

        comment_share = SessionShare(
            session_id="test-session",
            share_token="abc123",
            permission=SharePermission.COMMENT,
        )
        assert comment_share.can_comment()

        write_share = SessionShare(
            session_id="test-session",
            share_token="abc123",
            permission=SharePermission.WRITE,
        )
        assert write_share.can_comment()

    def test_can_write_permissions(self):
        """Test can_write for various permissions."""
        read_share = SessionShare(
            session_id="test-session",
            share_token="abc123",
            permission=SharePermission.READ,
        )
        assert not read_share.can_write()

        comment_share = SessionShare(
            session_id="test-session",
            share_token="abc123",
            permission=SharePermission.COMMENT,
        )
        assert not comment_share.can_write()

        write_share = SessionShare(
            session_id="test-session",
            share_token="abc123",
            permission=SharePermission.WRITE,
        )
        assert write_share.can_write()

    def test_get_share_url(self):
        """Test share URL generation."""
        share = SessionShare(
            session_id="test-session",
            share_token="abc123xyz",
        )
        url = share.get_share_url()
        assert url == "http://localhost:8000/share/abc123xyz"

        url_custom = share.get_share_url(base_url="https://example.com")
        assert url_custom == "https://example.com/share/abc123xyz"

    def test_to_dict(self):
        """Test serialization to dict."""
        share = SessionShare(
            session_id="test-session",
            share_token="abc123",
            permission=SharePermission.COMMENT,
            created_by="alice",
        )
        d = share.to_dict()
        assert d["session_id"] == "test-session"
        assert d["share_token"] == "abc123"
        assert d["permission"] == "comment"
        assert d["created_by"] == "alice"
        assert d["is_valid"] is True


# ============================================
# SessionComment Dataclass Tests
# ============================================


class TestSessionComment:
    """Tests for SessionComment dataclass."""

    def test_session_comment_defaults(self):
        """Test SessionComment defaults."""
        comment = SessionComment(
            session_id="test-session",
            author="alice",
            content="Great code!",
        )
        assert comment.comment_type == CommentType.COMMENT
        assert comment.status == CommentStatus.OPEN
        assert comment.turn_index is None
        assert comment.parent_id is None

    def test_is_reply(self):
        """Test is_reply property."""
        comment = SessionComment(
            session_id="test-session",
            author="alice",
            content="Reply",
            parent_id=1,
        )
        assert comment.is_reply

        root_comment = SessionComment(
            session_id="test-session",
            author="alice",
            content="Root",
        )
        assert not root_comment.is_reply

    def test_is_session_level(self):
        """Test is_session_level property."""
        session_comment = SessionComment(
            session_id="test-session",
            author="alice",
            content="Session level",
        )
        assert session_comment.is_session_level

        turn_comment = SessionComment(
            session_id="test-session",
            author="alice",
            content="Turn comment",
            turn_index=5,
        )
        assert not turn_comment.is_session_level

    def test_is_resolved(self):
        """Test is_resolved property."""
        open_comment = SessionComment(
            session_id="test-session",
            author="alice",
            content="Open",
            status=CommentStatus.OPEN,
        )
        assert not open_comment.is_resolved

        resolved_comment = SessionComment(
            session_id="test-session",
            author="alice",
            content="Resolved",
            status=CommentStatus.RESOLVED,
        )
        assert resolved_comment.is_resolved

        wontfix_comment = SessionComment(
            session_id="test-session",
            author="alice",
            content="Wontfix",
            status=CommentStatus.WONTFIX,
        )
        assert wontfix_comment.is_resolved

    def test_to_dict(self):
        """Test serialization to dict."""
        comment = SessionComment(
            session_id="test-session",
            author="alice",
            content="Nice!",
            turn_index=3,
            line_number=42,
            comment_type=CommentType.PRAISE,
        )
        d = comment.to_dict()
        assert d["session_id"] == "test-session"
        assert d["author"] == "alice"
        assert d["content"] == "Nice!"
        assert d["turn_index"] == 3
        assert d["line_number"] == 42
        assert d["comment_type"] == "praise"
        assert d["is_reply"] is False


# ============================================
# Participant Dataclass Tests
# ============================================


class TestParticipant:
    """Tests for Participant dataclass."""

    def test_participant_defaults(self):
        """Test Participant defaults."""
        p = Participant(
            user_id="user1",
            display_name="Alice",
            session_id="test-session",
        )
        assert p.status == ParticipantStatus.VIEWING
        assert p.cursor_turn is None
        assert p.cursor_line is None

    def test_is_idle(self):
        """Test is_idle property."""
        p = Participant(
            user_id="user1",
            display_name="Alice",
            session_id="test-session",
        )
        # Just created, should not be idle
        assert not p.is_idle

        # Set last_activity to 10 minutes ago
        p.last_activity = datetime.now() - timedelta(minutes=10)
        assert p.is_idle

    def test_touch(self):
        """Test touch updates activity and status."""
        import time

        p = Participant(
            user_id="user1",
            display_name="Alice",
            session_id="test-session",
            status=ParticipantStatus.IDLE,
        )
        old_activity = p.last_activity
        time.sleep(0.01)  # Ensure time difference
        p.touch()
        assert p.last_activity >= old_activity
        assert p.status == ParticipantStatus.ACTIVE

    def test_to_dict(self):
        """Test serialization to dict."""
        p = Participant(
            user_id="user1",
            display_name="Alice",
            session_id="test-session",
            cursor_turn=5,
            cursor_line=10,
            color="#FF6B6B",
        )
        d = p.to_dict()
        assert d["user_id"] == "user1"
        assert d["display_name"] == "Alice"
        assert d["session_id"] == "test-session"
        assert d["cursor_turn"] == 5
        assert d["cursor_line"] == 10
        assert d["color"] == "#FF6B6B"


# ============================================
# PresenceManager Tests
# ============================================


class TestPresenceManager:
    """Tests for PresenceManager."""

    @pytest.fixture
    def manager(self):
        """Create a fresh presence manager."""
        return PresenceManager(idle_timeout_minutes=5, cleanup_interval_seconds=60)

    @pytest.mark.asyncio
    async def test_join_session(self, manager):
        """Test joining a session."""
        participant = await manager.join_session(
            session_id="test-session",
            user_id="user1",
            display_name="Alice",
        )
        assert participant.user_id == "user1"
        assert participant.display_name == "Alice"
        assert participant.session_id == "test-session"
        assert participant.color is not None

    @pytest.mark.asyncio
    async def test_join_assigns_color(self, manager):
        """Test that joining assigns a color from the palette."""
        p1 = await manager.join_session("session", "user1", "Alice")
        p2 = await manager.join_session("session", "user2", "Bob")

        assert p1.color == PARTICIPANT_COLORS[0]
        assert p2.color == PARTICIPANT_COLORS[1]

    @pytest.mark.asyncio
    async def test_join_replaces_existing_session(self, manager):
        """Test that joining a new session leaves the old one."""
        await manager.join_session("session1", "user1", "Alice")
        await manager.join_session("session2", "user1", "Alice")

        # Should not be in session1
        participants = manager.get_session_participants("session1")
        assert len(participants) == 0

        # Should be in session2
        participants = manager.get_session_participants("session2")
        assert len(participants) == 1

    @pytest.mark.asyncio
    async def test_leave_session(self, manager):
        """Test leaving a session."""
        await manager.join_session("session", "user1", "Alice")
        participant = await manager.leave_session("user1")

        assert participant is not None
        assert participant.user_id == "user1"
        assert manager.get_participant("user1") is None

    @pytest.mark.asyncio
    async def test_leave_nonexistent(self, manager):
        """Test leaving when not in a session."""
        result = await manager.leave_session("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_cursor(self, manager):
        """Test updating cursor position."""
        await manager.join_session("session", "user1", "Alice")
        participant = await manager.update_cursor("user1", turn_index=5, line_number=42)

        assert participant is not None
        assert participant.cursor_turn == 5
        assert participant.cursor_line == 42

    @pytest.mark.asyncio
    async def test_update_status(self, manager):
        """Test updating participant status."""
        await manager.join_session("session", "user1", "Alice")
        participant = await manager.update_status("user1", ParticipantStatus.TYPING)

        assert participant is not None
        assert participant.status == ParticipantStatus.TYPING

    def test_get_session_participants(self, manager):
        """Test getting participants for a session."""
        # Empty session
        participants = manager.get_session_participants("empty")
        assert participants == []

    @pytest.mark.asyncio
    async def test_get_session_participants_with_users(self, manager):
        """Test getting participants after users join."""
        await manager.join_session("session", "user1", "Alice")
        await manager.join_session("session", "user2", "Bob")

        participants = manager.get_session_participants("session")
        assert len(participants) == 2

    @pytest.mark.asyncio
    async def test_get_session_count(self, manager):
        """Test getting participant count."""
        assert manager.get_session_count("session") == 0

        await manager.join_session("session", "user1", "Alice")
        assert manager.get_session_count("session") == 1

        await manager.join_session("session", "user2", "Bob")
        assert manager.get_session_count("session") == 2

    @pytest.mark.asyncio
    async def test_get_all_sessions(self, manager):
        """Test getting all sessions with counts."""
        await manager.join_session("session1", "user1", "Alice")
        await manager.join_session("session2", "user2", "Bob")
        await manager.join_session("session2", "user3", "Carol")

        sessions = manager.get_all_sessions()
        assert sessions["session1"] == 1
        assert sessions["session2"] == 2

    @pytest.mark.asyncio
    async def test_callbacks_on_join(self, manager):
        """Test that join callbacks are called."""
        callback = AsyncMock()
        manager.on_join(callback)

        await manager.join_session("session", "user1", "Alice")
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_callbacks_on_leave(self, manager):
        """Test that leave callbacks are called."""
        callback = AsyncMock()
        manager.on_leave(callback)

        await manager.join_session("session", "user1", "Alice")
        await manager.leave_session("user1")
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_callbacks_on_update(self, manager):
        """Test that update callbacks are called."""
        callback = AsyncMock()
        manager.on_update(callback)

        await manager.join_session("session", "user1", "Alice")
        await manager.update_cursor("user1", 5, 10)
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_stats(self, manager):
        """Test getting presence stats."""
        await manager.join_session("session1", "user1", "Alice")
        await manager.join_session("session2", "user2", "Bob")

        stats = manager.get_stats()
        assert stats["total_participants"] == 2
        assert stats["active_sessions"] == 2

    @pytest.mark.asyncio
    async def test_cleanup_empty_sessions(self, manager):
        """Test that empty sessions are cleaned up."""
        await manager.join_session("session", "user1", "Alice")
        await manager.leave_session("user1")

        # Session should be cleaned up
        assert "session" not in manager._sessions


# ============================================
# ShareStore Integration Tests
# ============================================


class TestShareStoreIntegration:
    """Integration tests for ShareStore (requires database)."""

    @pytest_asyncio.fixture
    async def share_store(self, tmp_path):
        """Create a share store with a temp database."""
        from sindri.persistence.database import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        store = ShareStore(database=db)
        yield store

    @pytest.mark.asyncio
    async def test_create_share(self, share_store):
        """Test creating a share."""
        share = await share_store.create_share(
            session_id="test-session",
            permission=SharePermission.READ,
            created_by="alice",
        )

        assert share.id is not None
        assert share.session_id == "test-session"
        assert len(share.share_token) == 16

    @pytest.mark.asyncio
    async def test_get_share_by_token(self, share_store):
        """Test retrieving a share by token."""
        created = await share_store.create_share(
            session_id="test-session",
            permission=SharePermission.COMMENT,
        )

        retrieved = await share_store.get_share_by_token(created.share_token)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.permission == SharePermission.COMMENT

    @pytest.mark.asyncio
    async def test_get_share_not_found(self, share_store):
        """Test retrieving a non-existent share."""
        share = await share_store.get_share_by_token("nonexistent")
        assert share is None

    @pytest.mark.asyncio
    async def test_validate_and_use_share(self, share_store):
        """Test validating and using a share."""
        created = await share_store.create_share(
            session_id="test-session",
            max_uses=2,
        )

        # First use
        share = await share_store.validate_and_use_share(created.share_token)
        assert share is not None
        assert share.use_count == 1

        # Second use
        share = await share_store.validate_and_use_share(created.share_token)
        assert share is not None
        assert share.use_count == 2

        # Third use - should fail (exhausted)
        share = await share_store.validate_and_use_share(created.share_token)
        assert share is None

    @pytest.mark.asyncio
    async def test_revoke_share(self, share_store):
        """Test revoking a share."""
        created = await share_store.create_share(session_id="test-session")

        success = await share_store.revoke_share(created.id)
        assert success

        # Should no longer be valid
        share = await share_store.validate_and_use_share(created.share_token)
        assert share is None

    @pytest.mark.asyncio
    async def test_revoke_all_shares(self, share_store):
        """Test revoking all shares for a session."""
        await share_store.create_share(session_id="test-session")
        await share_store.create_share(session_id="test-session")
        await share_store.create_share(session_id="other-session")

        count = await share_store.revoke_all_shares("test-session")
        assert count == 2

    @pytest.mark.asyncio
    async def test_get_shares_for_session(self, share_store):
        """Test getting all shares for a session."""
        await share_store.create_share(session_id="test-session")
        await share_store.create_share(session_id="test-session")
        await share_store.create_share(session_id="other-session")

        shares = await share_store.get_shares_for_session("test-session")
        assert len(shares) == 2

    @pytest.mark.asyncio
    async def test_get_share_stats(self, share_store):
        """Test getting share statistics."""
        await share_store.create_share(
            session_id="session1",
            permission=SharePermission.READ,
        )
        await share_store.create_share(
            session_id="session2",
            permission=SharePermission.COMMENT,
        )

        stats = await share_store.get_share_stats()
        assert stats["total_shares"] == 2
        assert stats["active_shares"] == 2
        assert stats["sessions_shared"] == 2


# ============================================
# CommentStore Integration Tests
# ============================================


class TestCommentStoreIntegration:
    """Integration tests for CommentStore (requires database)."""

    @pytest_asyncio.fixture
    async def comment_store(self, tmp_path):
        """Create a comment store with a temp database."""
        from sindri.persistence.database import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        store = CommentStore(database=db)
        yield store

    @pytest.mark.asyncio
    async def test_add_comment(self, comment_store):
        """Test adding a comment."""
        comment = SessionComment(
            session_id="test-session",
            author="alice",
            content="Great work!",
            turn_index=5,
        )

        saved = await comment_store.add_comment(comment)
        assert saved.id is not None

    @pytest.mark.asyncio
    async def test_get_comment(self, comment_store):
        """Test retrieving a comment."""
        comment = SessionComment(
            session_id="test-session",
            author="alice",
            content="Test comment",
        )
        saved = await comment_store.add_comment(comment)

        retrieved = await comment_store.get_comment(saved.id)
        assert retrieved is not None
        assert retrieved.author == "alice"
        assert retrieved.content == "Test comment"

    @pytest.mark.asyncio
    async def test_get_comment_not_found(self, comment_store):
        """Test retrieving a non-existent comment."""
        comment = await comment_store.get_comment(99999)
        assert comment is None

    @pytest.mark.asyncio
    async def test_get_comments_for_session(self, comment_store):
        """Test getting all comments for a session."""
        await comment_store.add_comment(
            SessionComment(session_id="session1", author="alice", content="Comment 1")
        )
        await comment_store.add_comment(
            SessionComment(session_id="session1", author="bob", content="Comment 2")
        )
        await comment_store.add_comment(
            SessionComment(session_id="session2", author="alice", content="Comment 3")
        )

        comments = await comment_store.get_comments_for_session("session1")
        assert len(comments) == 2

    @pytest.mark.asyncio
    async def test_get_comments_for_turn(self, comment_store):
        """Test getting comments for a specific turn."""
        await comment_store.add_comment(
            SessionComment(
                session_id="session1", author="alice", content="Turn 5", turn_index=5
            )
        )
        await comment_store.add_comment(
            SessionComment(
                session_id="session1", author="bob", content="Turn 5 too", turn_index=5
            )
        )
        await comment_store.add_comment(
            SessionComment(
                session_id="session1", author="alice", content="Turn 10", turn_index=10
            )
        )

        comments = await comment_store.get_comments_for_turn("session1", 5)
        assert len(comments) == 2

    @pytest.mark.asyncio
    async def test_get_replies(self, comment_store):
        """Test getting replies to a comment."""
        parent = await comment_store.add_comment(
            SessionComment(session_id="session1", author="alice", content="Question?")
        )
        await comment_store.add_comment(
            SessionComment(
                session_id="session1",
                author="bob",
                content="Answer!",
                parent_id=parent.id,
            )
        )
        await comment_store.add_comment(
            SessionComment(
                session_id="session1",
                author="carol",
                content="Me too!",
                parent_id=parent.id,
            )
        )

        replies = await comment_store.get_replies(parent.id)
        assert len(replies) == 2

    @pytest.mark.asyncio
    async def test_update_comment_content(self, comment_store):
        """Test updating comment content."""
        comment = await comment_store.add_comment(
            SessionComment(session_id="session1", author="alice", content="Original")
        )

        success = await comment_store.update_comment(comment.id, content="Updated")
        assert success

        updated = await comment_store.get_comment(comment.id)
        assert updated.content == "Updated"

    @pytest.mark.asyncio
    async def test_update_comment_status(self, comment_store):
        """Test updating comment status."""
        comment = await comment_store.add_comment(
            SessionComment(session_id="session1", author="alice", content="Issue")
        )

        success = await comment_store.update_comment(
            comment.id, status=CommentStatus.RESOLVED
        )
        assert success

        updated = await comment_store.get_comment(comment.id)
        assert updated.status == CommentStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_resolve_comment(self, comment_store):
        """Test resolving a comment."""
        comment = await comment_store.add_comment(
            SessionComment(session_id="session1", author="alice", content="Issue")
        )

        success = await comment_store.resolve_comment(comment.id)
        assert success

        resolved = await comment_store.get_comment(comment.id)
        assert resolved.status == CommentStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_delete_comment(self, comment_store):
        """Test deleting a comment."""
        comment = await comment_store.add_comment(
            SessionComment(session_id="session1", author="alice", content="Delete me")
        )

        success = await comment_store.delete_comment(comment.id)
        assert success

        deleted = await comment_store.get_comment(comment.id)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_delete_comment_with_replies(self, comment_store):
        """Test deleting a comment also deletes replies."""
        parent = await comment_store.add_comment(
            SessionComment(session_id="session1", author="alice", content="Parent")
        )
        reply = await comment_store.add_comment(
            SessionComment(
                session_id="session1",
                author="bob",
                content="Reply",
                parent_id=parent.id,
            )
        )

        await comment_store.delete_comment(parent.id)

        # Both should be deleted
        assert await comment_store.get_comment(parent.id) is None
        assert await comment_store.get_comment(reply.id) is None

    @pytest.mark.asyncio
    async def test_get_comment_count(self, comment_store):
        """Test getting comment counts."""
        await comment_store.add_comment(
            SessionComment(
                session_id="session1",
                author="alice",
                content="Issue",
                comment_type=CommentType.ISSUE,
            )
        )
        await comment_store.add_comment(
            SessionComment(
                session_id="session1",
                author="bob",
                content="Suggestion",
                comment_type=CommentType.SUGGESTION,
            )
        )

        counts = await comment_store.get_comment_count("session1")
        assert counts["total"] == 2
        assert counts["issue"] == 1
        assert counts["suggestion"] == 1

    @pytest.mark.asyncio
    async def test_get_comment_stats(self, comment_store):
        """Test getting comment statistics."""
        await comment_store.add_comment(
            SessionComment(session_id="session1", author="alice", content="Comment 1")
        )
        await comment_store.add_comment(
            SessionComment(session_id="session2", author="bob", content="Comment 2")
        )

        stats = await comment_store.get_comment_stats()
        assert stats["total_comments"] == 2
        assert stats["sessions_commented"] == 2
        assert stats["unique_authors"] == 2

    @pytest.mark.asyncio
    async def test_exclude_resolved_comments(self, comment_store):
        """Test filtering out resolved comments."""
        await comment_store.add_comment(
            SessionComment(
                session_id="session1",
                author="alice",
                content="Open",
                status=CommentStatus.OPEN,
            )
        )
        resolved = await comment_store.add_comment(
            SessionComment(session_id="session1", author="bob", content="Resolved")
        )
        await comment_store.resolve_comment(resolved.id)

        # Without resolved
        comments = await comment_store.get_comments_for_session(
            "session1", include_resolved=False
        )
        assert len(comments) == 1

        # With resolved
        comments = await comment_store.get_comments_for_session(
            "session1", include_resolved=True
        )
        assert len(comments) == 2
