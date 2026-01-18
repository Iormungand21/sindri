"""Tests for Team Mode (users and teams collaboration)."""

import pytest
import pytest_asyncio
from datetime import datetime

from sindri.collaboration.users import (
    User,
    UserStore,
    hash_password,
    verify_password,
    generate_user_id,
)
from sindri.collaboration.teams import (
    Team,
    TeamRole,
    TeamMembership,
    TeamSession,
    TeamStore,
    generate_team_id,
    generate_invite_code,
)
from sindri.persistence.database import Database


# ============================================
# Password Hashing Tests
# ============================================


class TestPasswordHashing:
    """Tests for password hashing utilities."""

    def test_hash_password_generates_salt(self):
        """Test that hash_password generates a salt when not provided."""
        hashed, salt = hash_password("testpassword")
        assert hashed
        assert salt
        assert len(salt) == 32  # 16 bytes hex = 32 chars

    def test_hash_password_with_provided_salt(self):
        """Test hash_password with provided salt."""
        hashed1, _ = hash_password("testpassword", "fixedsalt123")
        hashed2, _ = hash_password("testpassword", "fixedsalt123")
        assert hashed1 == hashed2

    def test_hash_password_different_salts(self):
        """Test same password with different salts produces different hashes."""
        hashed1, _ = hash_password("testpassword", "salt1")
        hashed2, _ = hash_password("testpassword", "salt2")
        assert hashed1 != hashed2

    def test_verify_password_correct(self):
        """Test verify_password with correct password."""
        hashed, salt = hash_password("correctpassword")
        assert verify_password("correctpassword", hashed, salt)

    def test_verify_password_incorrect(self):
        """Test verify_password with incorrect password."""
        hashed, salt = hash_password("correctpassword")
        assert not verify_password("wrongpassword", hashed, salt)

    def test_generate_user_id_unique(self):
        """Test that user IDs are unique."""
        ids = [generate_user_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_generate_user_id_length(self):
        """Test user ID length."""
        user_id = generate_user_id()
        assert len(user_id) == 32  # 16 bytes hex


# ============================================
# User Dataclass Tests
# ============================================


class TestUserDataclass:
    """Tests for User dataclass."""

    def test_user_defaults(self):
        """Test User default values."""
        user = User(
            id="test-id",
            username="testuser",
            email="test@example.com",
            display_name="Test User",
        )
        assert user.is_active
        assert user.password_hash == ""
        assert user.password_salt == ""
        assert user.last_login is None
        assert user.preferences == {}

    def test_user_to_dict_excludes_sensitive(self):
        """Test to_dict excludes sensitive data by default."""
        user = User(
            id="test-id",
            username="testuser",
            email="test@example.com",
            display_name="Test User",
            password_hash="secret",
            password_salt="salt",
        )
        data = user.to_dict()
        assert "password_hash" not in data
        assert "password_salt" not in data
        assert data["username"] == "testuser"

    def test_user_to_dict_includes_sensitive(self):
        """Test to_dict can include sensitive data."""
        user = User(
            id="test-id",
            username="testuser",
            email="test@example.com",
            display_name="Test User",
            password_hash="secret",
            password_salt="salt",
        )
        data = user.to_dict(include_sensitive=True)
        assert data["password_hash"] == "secret"
        assert data["password_salt"] == "salt"

    def test_user_check_password(self):
        """Test User.check_password method."""
        user = User(
            id="test-id",
            username="testuser",
            email="test@example.com",
            display_name="Test User",
        )
        user.set_password("mypassword")
        assert user.check_password("mypassword")
        assert not user.check_password("wrongpassword")

    def test_user_check_password_no_password_set(self):
        """Test check_password returns False when no password set."""
        user = User(
            id="test-id",
            username="testuser",
            email="test@example.com",
            display_name="Test User",
        )
        assert not user.check_password("anypassword")

    def test_user_set_password(self):
        """Test User.set_password method."""
        user = User(
            id="test-id",
            username="testuser",
            email="test@example.com",
            display_name="Test User",
        )
        user.set_password("newpassword")
        assert user.password_hash
        assert user.password_salt
        assert user.check_password("newpassword")


# ============================================
# UserStore Tests
# ============================================


@pytest_asyncio.fixture
async def user_store(tmp_path):
    """Create a UserStore with a temporary database."""
    db = Database(tmp_path / "test.db")
    await db.initialize()
    return UserStore(database=db)


class TestUserStore:
    """Tests for UserStore persistence."""

    @pytest.mark.asyncio
    async def test_create_user(self, user_store):
        """Test creating a new user."""
        user = await user_store.create_user(
            username="testuser",
            email="test@example.com",
            display_name="Test User",
            password="testpass",
        )
        assert user.id
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.display_name == "Test User"
        assert user.is_active
        assert user.check_password("testpass")

    @pytest.mark.asyncio
    async def test_create_user_without_password(self, user_store):
        """Test creating a user without a password."""
        user = await user_store.create_user(
            username="nopass",
            email="nopass@example.com",
            display_name="No Password User",
        )
        assert user.id
        assert user.password_hash == ""
        assert not user.check_password("anything")

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username(self, user_store):
        """Test creating user with duplicate username raises error."""
        await user_store.create_user(
            username="duplicate",
            email="first@example.com",
            display_name="First User",
        )
        with pytest.raises(ValueError, match="already exists"):
            await user_store.create_user(
                username="duplicate",
                email="second@example.com",
                display_name="Second User",
            )

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, user_store):
        """Test creating user with duplicate email raises error."""
        await user_store.create_user(
            username="user1",
            email="same@example.com",
            display_name="First User",
        )
        with pytest.raises(ValueError, match="already exists"):
            await user_store.create_user(
                username="user2",
                email="same@example.com",
                display_name="Second User",
            )

    @pytest.mark.asyncio
    async def test_get_user(self, user_store):
        """Test getting a user by ID."""
        created = await user_store.create_user(
            username="getme",
            email="getme@example.com",
            display_name="Get Me",
        )
        retrieved = await user_store.get_user(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.username == "getme"

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, user_store):
        """Test getting non-existent user returns None."""
        result = await user_store.get_user("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_by_username(self, user_store):
        """Test getting user by username."""
        created = await user_store.create_user(
            username="findme",
            email="findme@example.com",
            display_name="Find Me",
        )
        retrieved = await user_store.get_user_by_username("findme")
        assert retrieved is not None
        assert retrieved.id == created.id

    @pytest.mark.asyncio
    async def test_get_user_by_email(self, user_store):
        """Test getting user by email."""
        created = await user_store.create_user(
            username="emailuser",
            email="find@example.com",
            display_name="Email User",
        )
        retrieved = await user_store.get_user_by_email("find@example.com")
        assert retrieved is not None
        assert retrieved.id == created.id

    @pytest.mark.asyncio
    async def test_authenticate_success(self, user_store):
        """Test successful authentication."""
        await user_store.create_user(
            username="authuser",
            email="auth@example.com",
            display_name="Auth User",
            password="correctpass",
        )
        user = await user_store.authenticate("authuser", "correctpass")
        assert user is not None
        assert user.username == "authuser"
        assert user.last_login is not None

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password(self, user_store):
        """Test authentication with wrong password."""
        await user_store.create_user(
            username="wrongpass",
            email="wrong@example.com",
            display_name="Wrong Pass",
            password="realpass",
        )
        user = await user_store.authenticate("wrongpass", "badpass")
        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_inactive_user(self, user_store):
        """Test authentication of inactive user fails."""
        created = await user_store.create_user(
            username="inactive",
            email="inactive@example.com",
            display_name="Inactive",
            password="pass",
        )
        await user_store.update_user(created.id, is_active=False)
        user = await user_store.authenticate("inactive", "pass")
        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_nonexistent_user(self, user_store):
        """Test authentication of non-existent user."""
        user = await user_store.authenticate("nobody", "pass")
        assert user is None

    @pytest.mark.asyncio
    async def test_update_user(self, user_store):
        """Test updating user profile."""
        created = await user_store.create_user(
            username="updateme",
            email="old@example.com",
            display_name="Old Name",
        )
        updated = await user_store.update_user(
            created.id,
            display_name="New Name",
            email="new@example.com",
        )
        assert updated is not None
        assert updated.display_name == "New Name"
        assert updated.email == "new@example.com"

    @pytest.mark.asyncio
    async def test_update_user_preferences(self, user_store):
        """Test updating user preferences."""
        created = await user_store.create_user(
            username="prefs",
            email="prefs@example.com",
            display_name="Prefs User",
        )
        prefs = {"theme": "dark", "notifications": True}
        updated = await user_store.update_user(created.id, preferences=prefs)
        assert updated.preferences == prefs

    @pytest.mark.asyncio
    async def test_change_password(self, user_store):
        """Test changing user password."""
        created = await user_store.create_user(
            username="changepw",
            email="change@example.com",
            display_name="Change PW",
            password="oldpass",
        )
        success = await user_store.change_password(created.id, "newpass")
        assert success

        # Old password should fail
        user = await user_store.authenticate("changepw", "oldpass")
        assert user is None

        # New password should work
        user = await user_store.authenticate("changepw", "newpass")
        assert user is not None

    @pytest.mark.asyncio
    async def test_delete_user(self, user_store):
        """Test deleting a user."""
        created = await user_store.create_user(
            username="deleteme",
            email="delete@example.com",
            display_name="Delete Me",
        )
        deleted = await user_store.delete_user(created.id)
        assert deleted

        # User should no longer exist
        user = await user_store.get_user(created.id)
        assert user is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user(self, user_store):
        """Test deleting non-existent user returns False."""
        deleted = await user_store.delete_user("nonexistent")
        assert not deleted

    @pytest.mark.asyncio
    async def test_list_users(self, user_store):
        """Test listing users with pagination."""
        # Create several users
        for i in range(5):
            await user_store.create_user(
                username=f"user{i}",
                email=f"user{i}@example.com",
                display_name=f"User {i}",
            )

        users = await user_store.list_users(limit=3)
        assert len(users) == 3

        users = await user_store.list_users(limit=10, offset=2)
        assert len(users) == 3

    @pytest.mark.asyncio
    async def test_list_users_active_only(self, user_store):
        """Test listing only active users."""
        active = await user_store.create_user(
            username="active",
            email="active@example.com",
            display_name="Active",
        )
        inactive = await user_store.create_user(
            username="inactive",
            email="inactive@example.com",
            display_name="Inactive",
        )
        await user_store.update_user(inactive.id, is_active=False)

        users = await user_store.list_users(active_only=True)
        assert len(users) == 1
        assert users[0].id == active.id

    @pytest.mark.asyncio
    async def test_search_users(self, user_store):
        """Test searching users."""
        await user_store.create_user(
            username="alice",
            email="alice@example.com",
            display_name="Alice Smith",
        )
        await user_store.create_user(
            username="bob",
            email="bob@example.com",
            display_name="Bob Jones",
        )
        await user_store.create_user(
            username="charlie",
            email="charlie@example.com",
            display_name="Alice Jones",
        )

        # Search by username
        results = await user_store.search_users("alice")
        assert len(results) == 2  # alice and charlie (Alice in display_name)

        # Search by display name
        results = await user_store.search_users("Jones")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_user_count(self, user_store):
        """Test getting user statistics."""
        await user_store.create_user(
            username="user1",
            email="u1@example.com",
            display_name="User 1",
        )
        inactive = await user_store.create_user(
            username="user2",
            email="u2@example.com",
            display_name="User 2",
        )
        await user_store.update_user(inactive.id, is_active=False)

        stats = await user_store.get_user_count()
        assert stats["total"] == 2
        assert stats["active"] == 1
        assert stats["inactive"] == 1


# ============================================
# Team ID/Invite Code Generation Tests
# ============================================


class TestTeamIdGeneration:
    """Tests for team ID and invite code generation."""

    def test_generate_team_id_unique(self):
        """Test team IDs are unique."""
        ids = [generate_team_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_generate_team_id_length(self):
        """Test team ID length."""
        team_id = generate_team_id()
        assert len(team_id) == 24  # 12 bytes hex

    def test_generate_invite_code_unique(self):
        """Test invite codes are unique."""
        codes = [generate_invite_code() for _ in range(100)]
        assert len(set(codes)) == 100

    def test_generate_invite_code_url_safe(self):
        """Test invite codes are URL-safe."""
        code = generate_invite_code()
        # URL-safe base64 uses only alphanumeric, hyphen, underscore
        assert all(c.isalnum() or c in "-_" for c in code)


# ============================================
# TeamRole Tests
# ============================================


class TestTeamRole:
    """Tests for TeamRole enum and permissions."""

    def test_viewer_permissions(self):
        """Test VIEWER role permissions."""
        role = TeamRole.VIEWER
        assert role.can_view
        assert not role.can_create_sessions
        assert not role.can_manage_members
        assert not role.can_manage_team
        assert not role.can_delete_team
        assert not role.can_transfer_ownership

    def test_member_permissions(self):
        """Test MEMBER role permissions."""
        role = TeamRole.MEMBER
        assert role.can_view
        assert role.can_create_sessions
        assert not role.can_manage_members
        assert not role.can_manage_team
        assert not role.can_delete_team
        assert not role.can_transfer_ownership

    def test_admin_permissions(self):
        """Test ADMIN role permissions."""
        role = TeamRole.ADMIN
        assert role.can_view
        assert role.can_create_sessions
        assert role.can_manage_members
        assert role.can_manage_team
        assert not role.can_delete_team
        assert not role.can_transfer_ownership

    def test_owner_permissions(self):
        """Test OWNER role permissions."""
        role = TeamRole.OWNER
        assert role.can_view
        assert role.can_create_sessions
        assert role.can_manage_members
        assert role.can_manage_team
        assert role.can_delete_team
        assert role.can_transfer_ownership

    def test_can_manage_role_hierarchy(self):
        """Test role management hierarchy."""
        # Owner can manage everyone except other owners
        assert TeamRole.OWNER.can_manage_role(TeamRole.ADMIN)
        assert TeamRole.OWNER.can_manage_role(TeamRole.MEMBER)
        assert TeamRole.OWNER.can_manage_role(TeamRole.VIEWER)
        assert not TeamRole.OWNER.can_manage_role(TeamRole.OWNER)

        # Admin can manage members and viewers
        assert TeamRole.ADMIN.can_manage_role(TeamRole.MEMBER)
        assert TeamRole.ADMIN.can_manage_role(TeamRole.VIEWER)
        assert not TeamRole.ADMIN.can_manage_role(TeamRole.ADMIN)
        assert not TeamRole.ADMIN.can_manage_role(TeamRole.OWNER)

        # Members can't manage anyone
        assert not TeamRole.MEMBER.can_manage_role(TeamRole.VIEWER)
        assert not TeamRole.MEMBER.can_manage_role(TeamRole.MEMBER)

        # Viewers can't manage anyone
        assert not TeamRole.VIEWER.can_manage_role(TeamRole.VIEWER)


# ============================================
# Team Dataclass Tests
# ============================================


class TestTeamDataclass:
    """Tests for Team dataclass."""

    def test_team_defaults(self):
        """Test Team default values."""
        team = Team(
            id="test-id",
            name="Test Team",
            description="A test team",
            owner_id="owner-123",
        )
        assert team.is_active
        assert team.settings == {}
        assert team.invite_code  # Auto-generated

    def test_team_to_dict_excludes_invite(self):
        """Test to_dict excludes invite code by default."""
        team = Team(
            id="test-id",
            name="Test Team",
            description="A test team",
            owner_id="owner-123",
            invite_code="secret-code",
        )
        data = team.to_dict()
        assert "invite_code" not in data
        assert data["name"] == "Test Team"

    def test_team_to_dict_includes_invite(self):
        """Test to_dict can include invite code."""
        team = Team(
            id="test-id",
            name="Test Team",
            description="A test team",
            owner_id="owner-123",
            invite_code="secret-code",
        )
        data = team.to_dict(include_invite_code=True)
        assert data["invite_code"] == "secret-code"


# ============================================
# TeamMembership Dataclass Tests
# ============================================


class TestTeamMembershipDataclass:
    """Tests for TeamMembership dataclass."""

    def test_membership_defaults(self):
        """Test TeamMembership default values."""
        membership = TeamMembership(
            id=1,
            team_id="team-123",
            user_id="user-456",
            role=TeamRole.MEMBER,
        )
        assert membership.invited_by is None
        assert membership.joined_at is not None

    def test_membership_to_dict(self):
        """Test TeamMembership.to_dict."""
        membership = TeamMembership(
            id=1,
            team_id="team-123",
            user_id="user-456",
            role=TeamRole.ADMIN,
            invited_by="owner-789",
        )
        data = membership.to_dict()
        assert data["role"] == "admin"
        assert data["team_id"] == "team-123"
        assert data["user_id"] == "user-456"
        assert data["invited_by"] == "owner-789"


# ============================================
# TeamSession Dataclass Tests
# ============================================


class TestTeamSessionDataclass:
    """Tests for TeamSession dataclass."""

    def test_team_session_defaults(self):
        """Test TeamSession default values."""
        session = TeamSession(
            id=1,
            team_id="team-123",
            session_id="session-456",
            created_by="user-789",
        )
        assert session.is_shared
        assert session.created_at is not None

    def test_team_session_to_dict(self):
        """Test TeamSession.to_dict."""
        session = TeamSession(
            id=1,
            team_id="team-123",
            session_id="session-456",
            created_by="user-789",
            is_shared=False,
        )
        data = session.to_dict()
        assert data["team_id"] == "team-123"
        assert data["session_id"] == "session-456"
        assert data["is_shared"] is False


# ============================================
# TeamStore Tests
# ============================================


@pytest_asyncio.fixture
async def team_store(tmp_path):
    """Create a TeamStore with a temporary database."""
    db = Database(tmp_path / "test.db")
    await db.initialize()
    return TeamStore(database=db)


class TestTeamStore:
    """Tests for TeamStore persistence."""

    @pytest.mark.asyncio
    async def test_create_team(self, team_store):
        """Test creating a new team."""
        team = await team_store.create_team(
            name="Test Team",
            owner_id="owner-123",
            description="A test team",
        )
        assert team.id
        assert team.name == "Test Team"
        assert team.owner_id == "owner-123"
        assert team.invite_code

        # Owner should be auto-added as member
        members = await team_store.get_team_members(team.id)
        assert len(members) == 1
        assert members[0].user_id == "owner-123"
        assert members[0].role == TeamRole.OWNER

    @pytest.mark.asyncio
    async def test_create_team_with_settings(self, team_store):
        """Test creating team with custom settings."""
        settings = {"max_sessions": 100, "allow_guests": False}
        team = await team_store.create_team(
            name="Settings Team",
            owner_id="owner-123",
            settings=settings,
        )
        assert team.settings == settings

    @pytest.mark.asyncio
    async def test_get_team(self, team_store):
        """Test getting a team by ID."""
        created = await team_store.create_team(
            name="Get Team",
            owner_id="owner-123",
        )
        retrieved = await team_store.get_team(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Get Team"

    @pytest.mark.asyncio
    async def test_get_team_not_found(self, team_store):
        """Test getting non-existent team returns None."""
        result = await team_store.get_team("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_team_by_invite_code(self, team_store):
        """Test getting team by invite code."""
        created = await team_store.create_team(
            name="Invite Team",
            owner_id="owner-123",
        )
        retrieved = await team_store.get_team_by_invite_code(created.invite_code)
        assert retrieved is not None
        assert retrieved.id == created.id

    @pytest.mark.asyncio
    async def test_update_team(self, team_store):
        """Test updating team details."""
        created = await team_store.create_team(
            name="Old Name",
            owner_id="owner-123",
            description="Old description",
        )
        updated = await team_store.update_team(
            created.id,
            name="New Name",
            description="New description",
        )
        assert updated.name == "New Name"
        assert updated.description == "New description"

    @pytest.mark.asyncio
    async def test_regenerate_invite_code(self, team_store):
        """Test regenerating invite code."""
        created = await team_store.create_team(
            name="Regen Team",
            owner_id="owner-123",
        )
        old_code = created.invite_code
        new_code = await team_store.regenerate_invite_code(created.id)
        assert new_code != old_code

        # Old code should not work
        team = await team_store.get_team_by_invite_code(old_code)
        assert team is None

        # New code should work
        team = await team_store.get_team_by_invite_code(new_code)
        assert team is not None

    @pytest.mark.asyncio
    async def test_delete_team(self, team_store):
        """Test deleting a team."""
        created = await team_store.create_team(
            name="Delete Team",
            owner_id="owner-123",
        )
        deleted = await team_store.delete_team(created.id)
        assert deleted

        team = await team_store.get_team(created.id)
        assert team is None

    @pytest.mark.asyncio
    async def test_list_teams(self, team_store):
        """Test listing teams with pagination."""
        for i in range(5):
            await team_store.create_team(
                name=f"Team {i}",
                owner_id=f"owner-{i}",
            )

        teams = await team_store.list_teams(limit=3)
        assert len(teams) == 3

        teams = await team_store.list_teams(limit=10, offset=2)
        assert len(teams) == 3

    # ========== Membership Tests ==========

    @pytest.mark.asyncio
    async def test_add_member(self, team_store):
        """Test adding a member to a team."""
        team = await team_store.create_team(
            name="Member Team",
            owner_id="owner-123",
        )
        membership = await team_store.add_member(
            team.id,
            "user-456",
            role=TeamRole.MEMBER,
            invited_by="owner-123",
        )
        assert membership.user_id == "user-456"
        assert membership.role == TeamRole.MEMBER
        assert membership.invited_by == "owner-123"

    @pytest.mark.asyncio
    async def test_add_member_duplicate(self, team_store):
        """Test adding duplicate member raises error."""
        team = await team_store.create_team(
            name="Dup Team",
            owner_id="owner-123",
        )
        await team_store.add_member(team.id, "user-456")

        with pytest.raises(ValueError, match="already a member"):
            await team_store.add_member(team.id, "user-456")

    @pytest.mark.asyncio
    async def test_remove_member(self, team_store):
        """Test removing a member."""
        team = await team_store.create_team(
            name="Remove Team",
            owner_id="owner-123",
        )
        await team_store.add_member(team.id, "user-456")

        removed = await team_store.remove_member(team.id, "user-456")
        assert removed

        membership = await team_store.get_membership(team.id, "user-456")
        assert membership is None

    @pytest.mark.asyncio
    async def test_remove_owner_fails(self, team_store):
        """Test removing owner raises error."""
        team = await team_store.create_team(
            name="Owner Team",
            owner_id="owner-123",
        )
        with pytest.raises(ValueError, match="Cannot remove team owner"):
            await team_store.remove_member(team.id, "owner-123")

    @pytest.mark.asyncio
    async def test_update_member_role(self, team_store):
        """Test updating a member's role."""
        team = await team_store.create_team(
            name="Role Team",
            owner_id="owner-123",
        )
        await team_store.add_member(team.id, "user-456", role=TeamRole.MEMBER)

        updated = await team_store.update_member_role(
            team.id, "user-456", TeamRole.ADMIN
        )
        assert updated.role == TeamRole.ADMIN

    @pytest.mark.asyncio
    async def test_update_owner_role_fails(self, team_store):
        """Test changing owner's role raises error."""
        team = await team_store.create_team(
            name="Owner Role Team",
            owner_id="owner-123",
        )
        with pytest.raises(ValueError, match="Cannot change owner role"):
            await team_store.update_member_role(
                team.id, "owner-123", TeamRole.ADMIN
            )

    @pytest.mark.asyncio
    async def test_get_team_members(self, team_store):
        """Test getting all team members."""
        team = await team_store.create_team(
            name="Members Team",
            owner_id="owner-123",
        )
        await team_store.add_member(team.id, "user-1", role=TeamRole.ADMIN)
        await team_store.add_member(team.id, "user-2", role=TeamRole.MEMBER)
        await team_store.add_member(team.id, "user-3", role=TeamRole.VIEWER)

        members = await team_store.get_team_members(team.id)
        assert len(members) == 4  # Owner + 3 added

        # Filter by role
        admins = await team_store.get_team_members(team.id, role=TeamRole.ADMIN)
        assert len(admins) == 1

    @pytest.mark.asyncio
    async def test_get_user_teams(self, team_store):
        """Test getting all teams a user belongs to."""
        # Create teams
        team1 = await team_store.create_team(
            name="Team 1",
            owner_id="owner-1",
        )
        team2 = await team_store.create_team(
            name="Team 2",
            owner_id="owner-2",
        )
        team3 = await team_store.create_team(
            name="Team 3",
            owner_id="owner-3",
        )

        # Add user to some teams
        await team_store.add_member(team1.id, "user-123")
        await team_store.add_member(team2.id, "user-123", role=TeamRole.ADMIN)

        teams = await team_store.get_user_teams("user-123")
        assert len(teams) == 2
        team_ids = [t.id for t, m in teams]
        assert team1.id in team_ids
        assert team2.id in team_ids
        assert team3.id not in team_ids

    @pytest.mark.asyncio
    async def test_transfer_ownership(self, team_store):
        """Test transferring team ownership."""
        team = await team_store.create_team(
            name="Transfer Team",
            owner_id="owner-123",
        )
        await team_store.add_member(team.id, "new-owner", role=TeamRole.ADMIN)

        success = await team_store.transfer_ownership(team.id, "new-owner")
        assert success

        # New owner should have OWNER role
        new_owner_membership = await team_store.get_membership(team.id, "new-owner")
        assert new_owner_membership.role == TeamRole.OWNER

        # Old owner should be ADMIN
        old_owner_membership = await team_store.get_membership(team.id, "owner-123")
        assert old_owner_membership.role == TeamRole.ADMIN

        # Team owner should be updated
        team = await team_store.get_team(team.id)
        assert team.owner_id == "new-owner"

    @pytest.mark.asyncio
    async def test_transfer_ownership_non_member(self, team_store):
        """Test transfer to non-member fails."""
        team = await team_store.create_team(
            name="Transfer Fail Team",
            owner_id="owner-123",
        )
        with pytest.raises(ValueError, match="must be a team member"):
            await team_store.transfer_ownership(team.id, "nonmember")

    @pytest.mark.asyncio
    async def test_join_by_invite_code(self, team_store):
        """Test joining team by invite code."""
        team = await team_store.create_team(
            name="Join Team",
            owner_id="owner-123",
        )
        membership = await team_store.join_by_invite_code(
            team.invite_code, "user-456"
        )
        assert membership is not None
        assert membership.user_id == "user-456"
        assert membership.role == TeamRole.MEMBER

    @pytest.mark.asyncio
    async def test_join_by_invalid_invite_code(self, team_store):
        """Test joining with invalid code returns None."""
        result = await team_store.join_by_invite_code("invalid-code", "user-456")
        assert result is None

    # ========== Team Sessions Tests ==========

    @pytest.mark.asyncio
    async def test_add_session_to_team(self, team_store):
        """Test adding a session to a team."""
        team = await team_store.create_team(
            name="Session Team",
            owner_id="owner-123",
        )
        session = await team_store.add_session_to_team(
            team.id,
            "session-456",
            created_by="owner-123",
        )
        assert session.team_id == team.id
        assert session.session_id == "session-456"
        assert session.is_shared

    @pytest.mark.asyncio
    async def test_add_private_session(self, team_store):
        """Test adding a private session."""
        team = await team_store.create_team(
            name="Private Session Team",
            owner_id="owner-123",
        )
        session = await team_store.add_session_to_team(
            team.id,
            "session-789",
            created_by="owner-123",
            is_shared=False,
        )
        assert not session.is_shared

    @pytest.mark.asyncio
    async def test_get_team_sessions(self, team_store):
        """Test getting team sessions."""
        team = await team_store.create_team(
            name="Get Sessions Team",
            owner_id="owner-123",
        )
        await team_store.add_session_to_team(
            team.id, "session-1", created_by="owner-123"
        )
        await team_store.add_session_to_team(
            team.id, "session-2", created_by="user-456"
        )
        await team_store.add_session_to_team(
            team.id, "session-3", created_by="owner-123", is_shared=False
        )

        # Without user_id filter, only shared sessions
        sessions = await team_store.get_team_sessions(team.id)
        assert len(sessions) == 2

        # With user_id, includes user's private sessions
        sessions = await team_store.get_team_sessions(team.id, user_id="owner-123")
        assert len(sessions) == 3

    @pytest.mark.asyncio
    async def test_get_session_team(self, team_store):
        """Test getting the team a session belongs to."""
        team = await team_store.create_team(
            name="Session Lookup Team",
            owner_id="owner-123",
        )
        await team_store.add_session_to_team(
            team.id, "session-456", created_by="owner-123"
        )

        result = await team_store.get_session_team("session-456")
        assert result is not None
        found_team, team_session = result
        assert found_team.id == team.id
        assert team_session.session_id == "session-456"

    @pytest.mark.asyncio
    async def test_get_session_team_not_found(self, team_store):
        """Test session not in team returns None."""
        result = await team_store.get_session_team("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_remove_session_from_team(self, team_store):
        """Test removing a session from a team."""
        team = await team_store.create_team(
            name="Remove Session Team",
            owner_id="owner-123",
        )
        await team_store.add_session_to_team(
            team.id, "session-456", created_by="owner-123"
        )

        removed = await team_store.remove_session_from_team(team.id, "session-456")
        assert removed

        result = await team_store.get_session_team("session-456")
        assert result is None

    # ========== Permission Checking Tests ==========

    @pytest.mark.asyncio
    async def test_can_user_access_session_member(self, team_store):
        """Test member can access shared session."""
        team = await team_store.create_team(
            name="Access Team",
            owner_id="owner-123",
        )
        await team_store.add_member(team.id, "user-456")
        await team_store.add_session_to_team(
            team.id, "session-789", created_by="owner-123"
        )

        can_access = await team_store.can_user_access_session("user-456", "session-789")
        assert can_access

    @pytest.mark.asyncio
    async def test_can_user_access_session_non_member(self, team_store):
        """Test non-member cannot access team session."""
        team = await team_store.create_team(
            name="No Access Team",
            owner_id="owner-123",
        )
        await team_store.add_session_to_team(
            team.id, "session-789", created_by="owner-123"
        )

        can_access = await team_store.can_user_access_session(
            "nonmember", "session-789"
        )
        assert not can_access

    @pytest.mark.asyncio
    async def test_can_user_access_private_session(self, team_store):
        """Test only creator can access private session."""
        team = await team_store.create_team(
            name="Private Access Team",
            owner_id="owner-123",
        )
        await team_store.add_member(team.id, "user-456")
        await team_store.add_session_to_team(
            team.id, "private-session", created_by="owner-123", is_shared=False
        )

        # Creator can access
        can_access = await team_store.can_user_access_session(
            "owner-123", "private-session"
        )
        assert can_access

        # Other member cannot
        can_access = await team_store.can_user_access_session(
            "user-456", "private-session"
        )
        assert not can_access

    @pytest.mark.asyncio
    async def test_can_user_access_non_team_session(self, team_store):
        """Test non-team sessions are accessible."""
        can_access = await team_store.can_user_access_session(
            "anyone", "individual-session"
        )
        assert can_access  # Individual sessions are open

    @pytest.mark.asyncio
    async def test_get_user_role(self, team_store):
        """Test getting user's role in team."""
        team = await team_store.create_team(
            name="Role Test Team",
            owner_id="owner-123",
        )
        await team_store.add_member(team.id, "user-456", role=TeamRole.ADMIN)

        role = await team_store.get_user_role(team.id, "owner-123")
        assert role == TeamRole.OWNER

        role = await team_store.get_user_role(team.id, "user-456")
        assert role == TeamRole.ADMIN

        role = await team_store.get_user_role(team.id, "nonmember")
        assert role is None

    # ========== Statistics Tests ==========

    @pytest.mark.asyncio
    async def test_get_team_stats(self, team_store):
        """Test getting team statistics."""
        team = await team_store.create_team(
            name="Stats Team",
            owner_id="owner-123",
        )
        await team_store.add_member(team.id, "admin-1", role=TeamRole.ADMIN)
        await team_store.add_member(team.id, "member-1", role=TeamRole.MEMBER)
        await team_store.add_member(team.id, "member-2", role=TeamRole.MEMBER)
        await team_store.add_member(team.id, "viewer-1", role=TeamRole.VIEWER)

        await team_store.add_session_to_team(
            team.id, "session-1", created_by="owner-123"
        )
        await team_store.add_session_to_team(
            team.id, "session-2", created_by="admin-1"
        )

        stats = await team_store.get_team_stats(team.id)
        assert stats["total_members"] == 5
        assert stats["session_count"] == 2
        assert stats["members_by_role"]["owner"] == 1
        assert stats["members_by_role"]["admin"] == 1
        assert stats["members_by_role"]["member"] == 2
        assert stats["members_by_role"]["viewer"] == 1

    @pytest.mark.asyncio
    async def test_get_global_stats(self, team_store):
        """Test getting global statistics."""
        # Create some teams
        team1 = await team_store.create_team(
            name="Team 1",
            owner_id="owner-1",
        )
        team2 = await team_store.create_team(
            name="Team 2",
            owner_id="owner-2",
        )

        await team_store.add_member(team1.id, "user-1")
        await team_store.add_member(team2.id, "user-2")
        await team_store.add_member(team2.id, "user-3")

        await team_store.add_session_to_team(
            team1.id, "session-1", created_by="owner-1"
        )

        stats = await team_store.get_global_stats()
        assert stats["total_teams"] == 2
        assert stats["total_memberships"] == 5  # 2 owners + 3 added
        assert stats["total_team_sessions"] == 1
