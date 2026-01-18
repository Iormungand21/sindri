"""Tests for the Audit Log System."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from sindri.collaboration.audit import (
    AuditLogEntry,
    AuditCategory,
    AuditAction,
    AuditSeverity,
    AuditOutcome,
    AuditQuery,
    AuditStore,
    generate_audit_id,
    audit_login_success,
    audit_login_failed,
    audit_logout,
    audit_permission_change,
    audit_role_change,
    audit_session_access,
    audit_access_denied,
    audit_suspicious_activity,
    audit_brute_force_detected,
    check_brute_force,
)
from sindri.persistence.database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_audit.db"
    database = Database(db_path)
    await database.initialize()
    yield database


@pytest_asyncio.fixture
async def store(db):
    """Create an AuditStore with a test database."""
    return AuditStore(database=db)


class TestAuditIdGeneration:
    """Tests for ID generation."""

    def test_generate_audit_id_returns_string(self):
        """Test that generate_audit_id returns a string."""
        audit_id = generate_audit_id()
        assert isinstance(audit_id, str)
        assert len(audit_id) == 32  # 16 bytes in hex

    def test_generate_audit_id_is_unique(self):
        """Test that each generated ID is unique."""
        ids = [generate_audit_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestAuditLogEntry:
    """Tests for the AuditLogEntry dataclass."""

    def test_create_entry(self):
        """Test creating an audit log entry."""
        entry = AuditLogEntry(
            id="test-id",
            timestamp=datetime.now(),
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            actor_id="user123",
        )
        assert entry.id == "test-id"
        assert entry.category == AuditCategory.AUTHENTICATION
        assert entry.action == AuditAction.LOGIN_SUCCESS
        assert entry.actor_id == "user123"

    def test_entry_to_dict(self):
        """Test converting entry to dictionary."""
        now = datetime.now()
        entry = AuditLogEntry(
            id="test-id",
            timestamp=now,
            category=AuditCategory.SECURITY,
            action=AuditAction.SUSPICIOUS_ACTIVITY,
            severity=AuditSeverity.ERROR,
            outcome=AuditOutcome.FAILURE,
            actor_id="user123",
            target_type="session",
            target_id="session456",
            ip_address="192.168.1.1",
            details="Test details",
            metadata={"key": "value"},
        )

        data = entry.to_dict()
        assert data["id"] == "test-id"
        assert data["timestamp"] == now.isoformat()
        assert data["category"] == "security"
        assert data["action"] == "suspicious_activity"
        assert data["severity"] == "error"
        assert data["outcome"] == "failure"
        assert data["actor_id"] == "user123"
        assert data["target_type"] == "session"
        assert data["target_id"] == "session456"
        assert data["ip_address"] == "192.168.1.1"
        assert data["details"] == "Test details"
        assert data["metadata"] == {"key": "value"}

    def test_is_security_event(self):
        """Test security event detection."""
        # Security category
        entry = AuditLogEntry(
            id="1",
            timestamp=datetime.now(),
            category=AuditCategory.SECURITY,
            action=AuditAction.SUSPICIOUS_ACTIVITY,
        )
        assert entry.is_security_event is True

        # Critical severity
        entry = AuditLogEntry(
            id="2",
            timestamp=datetime.now(),
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            severity=AuditSeverity.CRITICAL,
        )
        assert entry.is_security_event is True

        # Login failed action
        entry = AuditLogEntry(
            id="3",
            timestamp=datetime.now(),
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_FAILED,
        )
        assert entry.is_security_event is True

        # Normal event
        entry = AuditLogEntry(
            id="4",
            timestamp=datetime.now(),
            category=AuditCategory.DATA_ACCESS,
            action=AuditAction.SESSION_VIEWED,
        )
        assert entry.is_security_event is False

    def test_is_compliance_relevant(self):
        """Test compliance relevance detection."""
        # Login success is compliance relevant
        entry = AuditLogEntry(
            id="1",
            timestamp=datetime.now(),
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
        )
        assert entry.is_compliance_relevant is True

        # Permission granted is compliance relevant
        entry = AuditLogEntry(
            id="2",
            timestamp=datetime.now(),
            category=AuditCategory.AUTHORIZATION,
            action=AuditAction.PERMISSION_GRANTED,
        )
        assert entry.is_compliance_relevant is True

        # Session viewed is not compliance relevant
        entry = AuditLogEntry(
            id="3",
            timestamp=datetime.now(),
            category=AuditCategory.DATA_ACCESS,
            action=AuditAction.SESSION_VIEWED,
        )
        assert entry.is_compliance_relevant is False


class TestAuditStore:
    """Tests for the AuditStore class."""

    @pytest.mark.asyncio
    async def test_log_basic_event(self, store):
        """Test logging a basic audit event."""
        entry = await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            actor_id="user123",
            ip_address="192.168.1.1",
        )

        assert entry.id is not None
        assert entry.category == AuditCategory.AUTHENTICATION
        assert entry.action == AuditAction.LOGIN_SUCCESS
        assert entry.actor_id == "user123"
        assert entry.ip_address == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_log_event_with_metadata(self, store):
        """Test logging an event with metadata."""
        entry = await store.log(
            category=AuditCategory.AUTHORIZATION,
            action=AuditAction.ROLE_ASSIGNED,
            actor_id="admin",
            target_type="user",
            target_id="user456",
            metadata={"old_role": "viewer", "new_role": "member"},
        )

        assert entry.metadata == {"old_role": "viewer", "new_role": "member"}

    @pytest.mark.asyncio
    async def test_get_entry(self, store):
        """Test retrieving an entry by ID."""
        entry = await store.log(
            category=AuditCategory.SECURITY,
            action=AuditAction.SUSPICIOUS_ACTIVITY,
            details="Test suspicious activity",
        )

        retrieved = await store.get_entry(entry.id)
        assert retrieved is not None
        assert retrieved.id == entry.id
        assert retrieved.category == AuditCategory.SECURITY
        assert retrieved.details == "Test suspicious activity"

    @pytest.mark.asyncio
    async def test_get_entry_not_found(self, store):
        """Test retrieving a non-existent entry."""
        entry = await store.get_entry("nonexistent-id")
        assert entry is None

    @pytest.mark.asyncio
    async def test_query_by_category(self, store):
        """Test querying entries by category."""
        # Log entries in different categories
        await store.log(
            category=AuditCategory.AUTHENTICATION, action=AuditAction.LOGIN_SUCCESS
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION, action=AuditAction.LOGOUT
        )
        await store.log(
            category=AuditCategory.DATA_ACCESS, action=AuditAction.SESSION_VIEWED
        )

        query = AuditQuery(categories=[AuditCategory.AUTHENTICATION])
        entries = await store.query(query)

        assert len(entries) == 2
        for entry in entries:
            assert entry.category == AuditCategory.AUTHENTICATION

    @pytest.mark.asyncio
    async def test_query_by_action(self, store):
        """Test querying entries by action."""
        await store.log(
            category=AuditCategory.AUTHENTICATION, action=AuditAction.LOGIN_SUCCESS
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION, action=AuditAction.LOGIN_FAILED
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION, action=AuditAction.LOGIN_FAILED
        )

        query = AuditQuery(actions=[AuditAction.LOGIN_FAILED])
        entries = await store.query(query)

        assert len(entries) == 2
        for entry in entries:
            assert entry.action == AuditAction.LOGIN_FAILED

    @pytest.mark.asyncio
    async def test_query_by_severity(self, store):
        """Test querying entries by severity."""
        await store.log(
            category=AuditCategory.SECURITY,
            action=AuditAction.SUSPICIOUS_ACTIVITY,
            severity=AuditSeverity.ERROR,
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            severity=AuditSeverity.INFO,
        )

        query = AuditQuery(severities=[AuditSeverity.ERROR])
        entries = await store.query(query)

        assert len(entries) == 1
        assert entries[0].severity == AuditSeverity.ERROR

    @pytest.mark.asyncio
    async def test_query_by_actor(self, store):
        """Test querying entries by actor."""
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            actor_id="user1",
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            actor_id="user2",
        )
        await store.log(
            category=AuditCategory.DATA_ACCESS,
            action=AuditAction.SESSION_VIEWED,
            actor_id="user1",
        )

        query = AuditQuery(actor_id="user1")
        entries = await store.query(query)

        assert len(entries) == 2
        for entry in entries:
            assert entry.actor_id == "user1"

    @pytest.mark.asyncio
    async def test_query_by_target(self, store):
        """Test querying entries by target."""
        await store.log(
            category=AuditCategory.AUTHORIZATION,
            action=AuditAction.ROLE_ASSIGNED,
            target_type="user",
            target_id="user123",
        )
        await store.log(
            category=AuditCategory.DATA_ACCESS,
            action=AuditAction.SESSION_VIEWED,
            target_type="session",
            target_id="session456",
        )

        query = AuditQuery(target_type="user", target_id="user123")
        entries = await store.query(query)

        assert len(entries) == 1
        assert entries[0].target_type == "user"
        assert entries[0].target_id == "user123"

    @pytest.mark.asyncio
    async def test_query_by_team(self, store):
        """Test querying entries by team."""
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            team_id="team1",
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            team_id="team2",
        )

        query = AuditQuery(team_id="team1")
        entries = await store.query(query)

        assert len(entries) == 1
        assert entries[0].team_id == "team1"

    @pytest.mark.asyncio
    async def test_query_by_date_range(self, store):
        """Test querying entries by date range."""
        # Log an entry
        await store.log(
            category=AuditCategory.AUTHENTICATION, action=AuditAction.LOGIN_SUCCESS
        )

        # Query with date range including now
        query = AuditQuery(
            start_date=datetime.now() - timedelta(hours=1),
            end_date=datetime.now() + timedelta(hours=1),
        )
        entries = await store.query(query)
        assert len(entries) == 1

        # Query with date range in the past
        query = AuditQuery(
            start_date=datetime.now() - timedelta(days=30),
            end_date=datetime.now() - timedelta(days=29),
        )
        entries = await store.query(query)
        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_query_security_only(self, store):
        """Test querying security-only events."""
        await store.log(
            category=AuditCategory.SECURITY, action=AuditAction.SUSPICIOUS_ACTIVITY
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_FAILED,
            severity=AuditSeverity.WARNING,
        )
        await store.log(
            category=AuditCategory.DATA_ACCESS,
            action=AuditAction.SESSION_VIEWED,
            severity=AuditSeverity.INFO,
        )

        query = AuditQuery(security_only=True)
        entries = await store.query(query)

        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_query_compliance_only(self, store):
        """Test querying compliance-only events."""
        await store.log(
            category=AuditCategory.AUTHENTICATION, action=AuditAction.LOGIN_SUCCESS
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION, action=AuditAction.LOGIN_FAILED
        )
        await store.log(
            category=AuditCategory.DATA_ACCESS, action=AuditAction.SESSION_VIEWED
        )

        query = AuditQuery(compliance_only=True)
        entries = await store.query(query)

        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_query_with_search_text(self, store):
        """Test querying with search text."""
        await store.log(
            category=AuditCategory.SECURITY,
            action=AuditAction.SUSPICIOUS_ACTIVITY,
            details="Unauthorized access attempt from unknown IP",
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            details="Normal login",
        )

        query = AuditQuery(search_text="unauthorized")
        entries = await store.query(query)

        assert len(entries) == 1
        assert "unauthorized" in entries[0].details.lower()

    @pytest.mark.asyncio
    async def test_query_pagination(self, store):
        """Test query pagination."""
        # Create 10 entries
        for i in range(10):
            await store.log(
                category=AuditCategory.AUTHENTICATION,
                action=AuditAction.LOGIN_SUCCESS,
                actor_id=f"user{i}",
            )

        # First page
        query = AuditQuery(limit=3, offset=0)
        entries = await store.query(query)
        assert len(entries) == 3

        # Second page
        query = AuditQuery(limit=3, offset=3)
        entries = await store.query(query)
        assert len(entries) == 3

        # Third page
        query = AuditQuery(limit=3, offset=6)
        entries = await store.query(query)
        assert len(entries) == 3

    @pytest.mark.asyncio
    async def test_get_actor_history(self, store):
        """Test getting actor history."""
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            actor_id="user123",
        )
        await store.log(
            category=AuditCategory.DATA_ACCESS,
            action=AuditAction.SESSION_VIEWED,
            actor_id="user123",
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            actor_id="other_user",
        )

        entries = await store.get_actor_history("user123")
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_get_target_history(self, store):
        """Test getting target history."""
        await store.log(
            category=AuditCategory.DATA_ACCESS,
            action=AuditAction.SESSION_VIEWED,
            target_type="session",
            target_id="session123",
        )
        await store.log(
            category=AuditCategory.DATA_ACCESS,
            action=AuditAction.SESSION_EXPORTED,
            target_type="session",
            target_id="session123",
        )
        await store.log(
            category=AuditCategory.DATA_ACCESS,
            action=AuditAction.SESSION_VIEWED,
            target_type="session",
            target_id="other_session",
        )

        entries = await store.get_target_history("session", "session123")
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_get_security_events(self, store):
        """Test getting security events."""
        await store.log(
            category=AuditCategory.SECURITY, action=AuditAction.SUSPICIOUS_ACTIVITY
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_FAILED,
            severity=AuditSeverity.WARNING,
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION, action=AuditAction.LOGIN_SUCCESS
        )

        entries = await store.get_security_events(hours=1)
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_get_failed_logins(self, store):
        """Test getting failed login attempts."""
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_FAILED,
            actor_id="user1",
            ip_address="192.168.1.1",
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_FAILED,
            actor_id="user2",
            ip_address="192.168.1.1",
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            actor_id="user3",
            ip_address="192.168.1.1",
        )

        entries = await store.get_failed_logins(hours=1)
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_get_failed_logins_by_ip(self, store):
        """Test getting failed logins filtered by IP."""
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_FAILED,
            ip_address="192.168.1.1",
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_FAILED,
            ip_address="192.168.1.2",
        )

        entries = await store.get_failed_logins(hours=1, ip_address="192.168.1.1")
        assert len(entries) == 1
        assert entries[0].ip_address == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_get_statistics(self, store):
        """Test getting audit statistics."""
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            severity=AuditSeverity.INFO,
            outcome=AuditOutcome.SUCCESS,
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_FAILED,
            severity=AuditSeverity.WARNING,
            outcome=AuditOutcome.FAILURE,
        )
        await store.log(
            category=AuditCategory.SECURITY,
            action=AuditAction.SUSPICIOUS_ACTIVITY,
            severity=AuditSeverity.ERROR,
        )

        stats = await store.get_statistics()

        assert stats["total_events"] == 3
        assert stats["security_events"] >= 1
        assert stats["failed_logins"] == 1
        assert "authentication" in stats["by_category"]
        assert stats["by_category"]["authentication"] == 2
        assert "security" in stats["by_category"]
        assert stats["by_category"]["security"] == 1

    @pytest.mark.asyncio
    async def test_cleanup_old_entries(self, store):
        """Test cleaning up old entries."""
        # We can't easily test old entries without mocking time
        # So we test that cleanup runs without error
        deleted = await store.cleanup_old_entries(days=90)
        assert deleted == 0  # No old entries to delete

    @pytest.mark.asyncio
    async def test_export_logs_json(self, store):
        """Test exporting logs as JSON."""
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            actor_id="user123",
        )

        query = AuditQuery(limit=100)
        exported = await store.export_logs(query, format="json")

        import json

        data = json.loads(exported)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["actor_id"] == "user123"

    @pytest.mark.asyncio
    async def test_export_logs_csv(self, store):
        """Test exporting logs as CSV."""
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_SUCCESS,
            actor_id="user123",
            details="Test login",
        )

        query = AuditQuery(limit=100)
        exported = await store.export_logs(query, format="csv")

        lines = exported.split("\n")
        assert len(lines) == 2  # Header + 1 entry
        assert "id,timestamp,category,action" in lines[0]
        assert "user123" in lines[1]


class TestConvenienceFunctions:
    """Tests for convenience logging functions."""

    @pytest.mark.asyncio
    async def test_audit_login_success(self, store):
        """Test audit_login_success function."""
        entry = await audit_login_success(
            store, user_id="user123", ip_address="192.168.1.1", team_id="team456"
        )

        assert entry.category == AuditCategory.AUTHENTICATION
        assert entry.action == AuditAction.LOGIN_SUCCESS
        assert entry.actor_id == "user123"
        assert entry.ip_address == "192.168.1.1"
        assert entry.team_id == "team456"

    @pytest.mark.asyncio
    async def test_audit_login_failed(self, store):
        """Test audit_login_failed function."""
        entry = await audit_login_failed(
            store,
            username="admin",
            ip_address="192.168.1.1",
            reason="Invalid password",
        )

        assert entry.category == AuditCategory.AUTHENTICATION
        assert entry.action == AuditAction.LOGIN_FAILED
        assert entry.severity == AuditSeverity.WARNING
        assert entry.outcome == AuditOutcome.FAILURE
        assert entry.actor_id == "admin"
        assert "Invalid password" in entry.details

    @pytest.mark.asyncio
    async def test_audit_logout(self, store):
        """Test audit_logout function."""
        entry = await audit_logout(store, user_id="user123", ip_address="192.168.1.1")

        assert entry.category == AuditCategory.AUTHENTICATION
        assert entry.action == AuditAction.LOGOUT
        assert entry.actor_id == "user123"

    @pytest.mark.asyncio
    async def test_audit_permission_change_granted(self, store):
        """Test audit_permission_change for permission granted."""
        entry = await audit_permission_change(
            store,
            actor_id="admin",
            target_user_id="user123",
            permission="edit_sessions",
            granted=True,
            team_id="team456",
        )

        assert entry.category == AuditCategory.AUTHORIZATION
        assert entry.action == AuditAction.PERMISSION_GRANTED
        assert entry.actor_id == "admin"
        assert entry.target_type == "user"
        assert entry.target_id == "user123"
        assert "granted" in entry.details

    @pytest.mark.asyncio
    async def test_audit_permission_change_revoked(self, store):
        """Test audit_permission_change for permission revoked."""
        entry = await audit_permission_change(
            store,
            actor_id="admin",
            target_user_id="user123",
            permission="edit_sessions",
            granted=False,
        )

        assert entry.action == AuditAction.PERMISSION_REVOKED
        assert "revoked" in entry.details

    @pytest.mark.asyncio
    async def test_audit_role_change(self, store):
        """Test audit_role_change function."""
        entry = await audit_role_change(
            store,
            actor_id="admin",
            target_user_id="user123",
            old_role="viewer",
            new_role="member",
            team_id="team456",
        )

        assert entry.category == AuditCategory.AUTHORIZATION
        assert entry.action == AuditAction.ROLE_ASSIGNED
        assert entry.actor_id == "admin"
        assert entry.target_id == "user123"
        assert entry.team_id == "team456"
        assert "viewer" in entry.details
        assert "member" in entry.details

    @pytest.mark.asyncio
    async def test_audit_session_access(self, store):
        """Test audit_session_access function."""
        entry = await audit_session_access(
            store,
            user_id="user123",
            session_id="session456",
            action_type="viewed",
        )

        assert entry.category == AuditCategory.DATA_ACCESS
        assert entry.action == AuditAction.SESSION_VIEWED
        assert entry.actor_id == "user123"
        assert entry.session_id == "session456"

    @pytest.mark.asyncio
    async def test_audit_session_access_exported(self, store):
        """Test audit_session_access for export."""
        entry = await audit_session_access(
            store,
            user_id="user123",
            session_id="session456",
            action_type="exported",
        )

        assert entry.action == AuditAction.SESSION_EXPORTED

    @pytest.mark.asyncio
    async def test_audit_access_denied(self, store):
        """Test audit_access_denied function."""
        entry = await audit_access_denied(
            store,
            user_id="user123",
            resource_type="session",
            resource_id="session456",
            reason="No permission",
            ip_address="192.168.1.1",
        )

        assert entry.category == AuditCategory.AUTHORIZATION
        assert entry.action == AuditAction.ACCESS_DENIED
        assert entry.severity == AuditSeverity.WARNING
        assert entry.outcome == AuditOutcome.FAILURE
        assert entry.actor_id == "user123"
        assert entry.target_type == "session"

    @pytest.mark.asyncio
    async def test_audit_suspicious_activity(self, store):
        """Test audit_suspicious_activity function."""
        entry = await audit_suspicious_activity(
            store,
            description="Multiple failed attempts from same IP",
            actor_id="unknown",
            ip_address="192.168.1.1",
            metadata={"attempt_count": 10},
        )

        assert entry.category == AuditCategory.SECURITY
        assert entry.action == AuditAction.SUSPICIOUS_ACTIVITY
        assert entry.severity == AuditSeverity.ERROR
        assert entry.ip_address == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_audit_brute_force_detected(self, store):
        """Test audit_brute_force_detected function."""
        entry = await audit_brute_force_detected(
            store,
            ip_address="192.168.1.1",
            attempt_count=15,
            username="admin",
        )

        assert entry.category == AuditCategory.SECURITY
        assert entry.action == AuditAction.BRUTE_FORCE_DETECTED
        assert entry.severity == AuditSeverity.CRITICAL
        assert entry.ip_address == "192.168.1.1"
        assert entry.metadata["attempt_count"] == 15


class TestBruteForceDetection:
    """Tests for brute force detection."""

    @pytest.mark.asyncio
    async def test_check_brute_force_below_threshold(self, store):
        """Test brute force check below threshold."""
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_FAILED,
            ip_address="192.168.1.1",
        )
        await store.log(
            category=AuditCategory.AUTHENTICATION,
            action=AuditAction.LOGIN_FAILED,
            ip_address="192.168.1.1",
        )

        is_brute_force = await check_brute_force(
            store, ip_address="192.168.1.1", threshold=5
        )
        assert is_brute_force is False

    @pytest.mark.asyncio
    async def test_check_brute_force_at_threshold(self, store):
        """Test brute force check at threshold."""
        for _ in range(5):
            await store.log(
                category=AuditCategory.AUTHENTICATION,
                action=AuditAction.LOGIN_FAILED,
                ip_address="192.168.1.1",
            )

        is_brute_force = await check_brute_force(
            store, ip_address="192.168.1.1", threshold=5
        )
        assert is_brute_force is True

    @pytest.mark.asyncio
    async def test_check_brute_force_different_ips(self, store):
        """Test brute force check with different IPs."""
        for _ in range(3):
            await store.log(
                category=AuditCategory.AUTHENTICATION,
                action=AuditAction.LOGIN_FAILED,
                ip_address="192.168.1.1",
            )
        for _ in range(3):
            await store.log(
                category=AuditCategory.AUTHENTICATION,
                action=AuditAction.LOGIN_FAILED,
                ip_address="192.168.1.2",
            )

        is_brute_force_ip1 = await check_brute_force(
            store, ip_address="192.168.1.1", threshold=5
        )
        is_brute_force_ip2 = await check_brute_force(
            store, ip_address="192.168.1.2", threshold=5
        )

        assert is_brute_force_ip1 is False
        assert is_brute_force_ip2 is False


class TestAuditEnums:
    """Tests for audit enums."""

    def test_audit_categories(self):
        """Test all audit categories exist."""
        categories = [
            AuditCategory.AUTHENTICATION,
            AuditCategory.AUTHORIZATION,
            AuditCategory.DATA_ACCESS,
            AuditCategory.DATA_MODIFICATION,
            AuditCategory.ADMINISTRATIVE,
            AuditCategory.SECURITY,
            AuditCategory.SYSTEM,
        ]
        assert len(categories) == 7

    def test_audit_severities(self):
        """Test all audit severities exist."""
        severities = [
            AuditSeverity.INFO,
            AuditSeverity.WARNING,
            AuditSeverity.ERROR,
            AuditSeverity.CRITICAL,
        ]
        assert len(severities) == 4

    def test_audit_outcomes(self):
        """Test all audit outcomes exist."""
        outcomes = [
            AuditOutcome.SUCCESS,
            AuditOutcome.FAILURE,
            AuditOutcome.PARTIAL,
            AuditOutcome.UNKNOWN,
        ]
        assert len(outcomes) == 4

    def test_authentication_actions(self):
        """Test authentication-related actions exist."""
        auth_actions = [
            AuditAction.LOGIN_SUCCESS,
            AuditAction.LOGIN_FAILED,
            AuditAction.LOGOUT,
            AuditAction.PASSWORD_CHANGED,
            AuditAction.PASSWORD_RESET_REQUESTED,
            AuditAction.TOKEN_GENERATED,
            AuditAction.TOKEN_REVOKED,
            AuditAction.SESSION_EXPIRED,
        ]
        assert len(auth_actions) == 8

    def test_authorization_actions(self):
        """Test authorization-related actions exist."""
        authz_actions = [
            AuditAction.PERMISSION_GRANTED,
            AuditAction.PERMISSION_REVOKED,
            AuditAction.ROLE_ASSIGNED,
            AuditAction.ROLE_REMOVED,
            AuditAction.ACCESS_DENIED,
        ]
        assert len(authz_actions) == 5

    def test_security_actions(self):
        """Test security-related actions exist."""
        security_actions = [
            AuditAction.SUSPICIOUS_ACTIVITY,
            AuditAction.BRUTE_FORCE_DETECTED,
            AuditAction.RATE_LIMIT_EXCEEDED,
            AuditAction.INVALID_TOKEN,
            AuditAction.UNAUTHORIZED_ACCESS_ATTEMPT,
        ]
        assert len(security_actions) == 5


class TestAuditQuery:
    """Tests for AuditQuery dataclass."""

    def test_default_query(self):
        """Test default query values."""
        query = AuditQuery()
        assert query.start_date is None
        assert query.end_date is None
        assert query.categories is None
        assert query.limit == 100
        assert query.offset == 0
        assert query.security_only is False
        assert query.compliance_only is False

    def test_query_with_filters(self):
        """Test query with filters."""
        query = AuditQuery(
            categories=[AuditCategory.AUTHENTICATION, AuditCategory.SECURITY],
            severities=[AuditSeverity.ERROR, AuditSeverity.CRITICAL],
            actor_id="user123",
            team_id="team456",
            limit=50,
        )

        assert len(query.categories) == 2
        assert len(query.severities) == 2
        assert query.actor_id == "user123"
        assert query.team_id == "team456"
        assert query.limit == 50
