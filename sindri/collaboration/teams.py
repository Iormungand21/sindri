"""Team management for multi-user collaboration.

This module provides team-based collaboration:
- Team creation and management
- Role-based membership (owner, admin, member, viewer)
- Permission checking for team resources
- Team session ownership
"""

import secrets
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

import structlog

if TYPE_CHECKING:
    from sindri.persistence.database import Database

log = structlog.get_logger()


def generate_team_id() -> str:
    """Generate a unique team ID."""
    return secrets.token_hex(12)


def generate_invite_code() -> str:
    """Generate a unique team invite code."""
    return secrets.token_urlsafe(16)


class TeamRole(Enum):
    """Roles within a team with increasing permissions.

    VIEWER: Can view team sessions (read-only)
    MEMBER: Can create and run sessions
    ADMIN: Can manage team settings and members
    OWNER: Full control including team deletion
    """

    VIEWER = "viewer"
    MEMBER = "member"
    ADMIN = "admin"
    OWNER = "owner"

    @property
    def can_view(self) -> bool:
        """All roles can view."""
        return True

    @property
    def can_create_sessions(self) -> bool:
        """Members and above can create sessions."""
        return self in (TeamRole.MEMBER, TeamRole.ADMIN, TeamRole.OWNER)

    @property
    def can_manage_members(self) -> bool:
        """Admins and owners can manage members."""
        return self in (TeamRole.ADMIN, TeamRole.OWNER)

    @property
    def can_manage_team(self) -> bool:
        """Admins and owners can manage team settings."""
        return self in (TeamRole.ADMIN, TeamRole.OWNER)

    @property
    def can_delete_team(self) -> bool:
        """Only owners can delete team."""
        return self == TeamRole.OWNER

    @property
    def can_transfer_ownership(self) -> bool:
        """Only owners can transfer ownership."""
        return self == TeamRole.OWNER

    def can_manage_role(self, target_role: "TeamRole") -> bool:
        """Check if this role can manage a target role.

        Args:
            target_role: Role to potentially manage

        Returns:
            True if this role can add/remove/modify target role
        """
        role_hierarchy = {
            TeamRole.VIEWER: 0,
            TeamRole.MEMBER: 1,
            TeamRole.ADMIN: 2,
            TeamRole.OWNER: 3,
        }

        # Must be admin+ and higher than target (can't manage equals or above)
        if not self.can_manage_members:
            return False

        # Owner can manage anyone except other owners
        if self == TeamRole.OWNER:
            return target_role != TeamRole.OWNER

        # Admin can manage members and viewers
        return role_hierarchy[self] > role_hierarchy[target_role]


@dataclass
class Team:
    """A team for collaborative work.

    Attributes:
        id: Unique team identifier
        name: Team name
        description: Team description
        owner_id: User ID of team owner
        invite_code: Code for joining team
        is_active: Whether team is active
        settings: Team-specific settings
        created_at: Creation timestamp
    """

    id: str
    name: str
    description: str
    owner_id: str
    invite_code: str = field(default_factory=generate_invite_code)
    is_active: bool = True
    settings: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self, include_invite_code: bool = False) -> dict:
        """Convert to dictionary for serialization.

        Args:
            include_invite_code: Include invite code (default False for security)

        Returns:
            Dictionary representation
        """
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "owner_id": self.owner_id,
            "is_active": self.is_active,
            "settings": self.settings,
            "created_at": self.created_at.isoformat(),
        }
        if include_invite_code:
            result["invite_code"] = self.invite_code
        return result


@dataclass
class TeamMembership:
    """A user's membership in a team.

    Attributes:
        id: Unique membership identifier
        team_id: Team ID
        user_id: User ID
        role: User's role in the team
        joined_at: When user joined
        invited_by: User ID who invited this member
    """

    id: int
    team_id: str
    user_id: str
    role: TeamRole
    joined_at: datetime = field(default_factory=datetime.now)
    invited_by: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "team_id": self.team_id,
            "user_id": self.user_id,
            "role": self.role.value,
            "joined_at": self.joined_at.isoformat(),
            "invited_by": self.invited_by,
        }


@dataclass
class TeamSession:
    """Associates a session with a team.

    Attributes:
        id: Unique identifier
        team_id: Team that owns the session
        session_id: The Sindri session ID
        created_by: User who created this session
        is_shared: Whether visible to all team members
        created_at: Creation timestamp
    """

    id: int
    team_id: str
    session_id: str
    created_by: str
    is_shared: bool = True
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "team_id": self.team_id,
            "session_id": self.session_id,
            "created_by": self.created_by,
            "is_shared": self.is_shared,
            "created_at": self.created_at.isoformat(),
        }


class TeamStore:
    """Persistent storage for teams and memberships."""

    def __init__(self, database: Optional["Database"] = None):
        """Initialize the team store.

        Args:
            database: Database instance (creates default if not provided)
        """
        from sindri.persistence.database import Database

        self.db = database or Database()

    async def _ensure_tables(self) -> None:
        """Ensure team tables exist."""
        await self.db.initialize()
        async with self.db.get_connection() as conn:
            # Teams table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS teams (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    owner_id TEXT NOT NULL,
                    invite_code TEXT UNIQUE NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    settings TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Team memberships table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS team_memberships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'member',
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    invited_by TEXT,
                    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                    UNIQUE(team_id, user_id)
                )
            """)

            # Team sessions table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS team_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    is_shared INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                    UNIQUE(team_id, session_id)
                )
            """)

            # Indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_teams_owner ON teams(owner_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_teams_invite ON teams(invite_code)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memberships_team
                ON team_memberships(team_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memberships_user
                ON team_memberships(user_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_team_sessions_team
                ON team_sessions(team_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_team_sessions_session
                ON team_sessions(session_id)
            """)

            await conn.commit()

    # ========== Team CRUD ==========

    async def create_team(
        self,
        name: str,
        owner_id: str,
        description: str = "",
        settings: Optional[dict] = None,
    ) -> Team:
        """Create a new team.

        The owner is automatically added as a member with OWNER role.

        Args:
            name: Team name
            owner_id: User ID of the owner
            description: Team description
            settings: Initial team settings

        Returns:
            Created Team object
        """
        await self._ensure_tables()

        team = Team(
            id=generate_team_id(),
            name=name,
            description=description,
            owner_id=owner_id,
            settings=settings or {},
        )

        import json

        async with self.db.get_connection() as conn:
            # Create team
            await conn.execute(
                """
                INSERT INTO teams (
                    id, name, description, owner_id, invite_code,
                    is_active, settings, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    team.id,
                    team.name,
                    team.description,
                    team.owner_id,
                    team.invite_code,
                    1,
                    json.dumps(team.settings),
                    team.created_at.isoformat(),
                ),
            )

            # Add owner as member
            await conn.execute(
                """
                INSERT INTO team_memberships (team_id, user_id, role, joined_at)
                VALUES (?, ?, ?, ?)
                """,
                (team.id, owner_id, TeamRole.OWNER.value, team.created_at.isoformat()),
            )

            await conn.commit()

        log.info("team_created", team_id=team.id, name=name, owner_id=owner_id)
        return team

    async def get_team(self, team_id: str) -> Optional[Team]:
        """Get a team by ID.

        Args:
            team_id: Team ID

        Returns:
            Team if found, None otherwise
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM teams WHERE id = ?",
                (team_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_team(row)

    async def get_team_by_invite_code(self, invite_code: str) -> Optional[Team]:
        """Get a team by invite code.

        Args:
            invite_code: Team invite code

        Returns:
            Team if found, None otherwise
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM teams WHERE invite_code = ? AND is_active = 1",
                (invite_code,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_team(row)

    async def update_team(
        self,
        team_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        settings: Optional[dict] = None,
    ) -> Optional[Team]:
        """Update team details.

        Args:
            team_id: Team ID
            name: New name (optional)
            description: New description (optional)
            settings: New settings (optional)

        Returns:
            Updated Team if found
        """
        await self._ensure_tables()

        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)

        if description is not None:
            updates.append("description = ?")
            params.append(description)

        if settings is not None:
            import json

            updates.append("settings = ?")
            params.append(json.dumps(settings))

        if not updates:
            return await self.get_team(team_id)

        params.append(team_id)

        async with self.db.get_connection() as conn:
            await conn.execute(
                f"UPDATE teams SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await conn.commit()

        log.info("team_updated", team_id=team_id)
        return await self.get_team(team_id)

    async def regenerate_invite_code(self, team_id: str) -> Optional[str]:
        """Generate a new invite code for a team.

        Args:
            team_id: Team ID

        Returns:
            New invite code if team exists
        """
        await self._ensure_tables()

        new_code = generate_invite_code()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "UPDATE teams SET invite_code = ? WHERE id = ?",
                (new_code, team_id),
            )
            await conn.commit()

            if cursor.rowcount > 0:
                log.info("invite_code_regenerated", team_id=team_id)
                return new_code

        return None

    async def delete_team(self, team_id: str) -> bool:
        """Delete a team and all associated data.

        Args:
            team_id: Team ID to delete

        Returns:
            True if team was deleted
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            # Delete team (cascades to memberships and sessions)
            cursor = await conn.execute(
                "DELETE FROM teams WHERE id = ?",
                (team_id,),
            )
            await conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            log.info("team_deleted", team_id=team_id)

        return deleted

    async def list_teams(
        self,
        limit: int = 50,
        offset: int = 0,
        active_only: bool = True,
    ) -> list[Team]:
        """List all teams with pagination.

        Args:
            limit: Maximum teams to return
            offset: Teams to skip
            active_only: Only return active teams

        Returns:
            List of Team objects
        """
        await self._ensure_tables()

        query = "SELECT * FROM teams"
        params: list = []

        if active_only:
            query += " WHERE is_active = 1"

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

        return [self._row_to_team(row) for row in rows]

    # ========== Membership Management ==========

    async def add_member(
        self,
        team_id: str,
        user_id: str,
        role: TeamRole = TeamRole.MEMBER,
        invited_by: Optional[str] = None,
    ) -> TeamMembership:
        """Add a user to a team.

        Args:
            team_id: Team ID
            user_id: User ID to add
            role: Role for the new member
            invited_by: User ID who invited (optional)

        Returns:
            Created TeamMembership

        Raises:
            ValueError: If user is already a member
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            try:
                cursor = await conn.execute(
                    """
                    INSERT INTO team_memberships (team_id, user_id, role, invited_by)
                    VALUES (?, ?, ?, ?)
                    """,
                    (team_id, user_id, role.value, invited_by),
                )
                await conn.commit()
                membership_id = cursor.lastrowid
            except Exception as e:
                if "UNIQUE constraint failed" in str(e):
                    raise ValueError(f"User {user_id} is already a member") from e
                raise

        membership = TeamMembership(
            id=membership_id,
            team_id=team_id,
            user_id=user_id,
            role=role,
            invited_by=invited_by,
        )

        log.info(
            "member_added",
            team_id=team_id,
            user_id=user_id,
            role=role.value,
        )
        return membership

    async def remove_member(self, team_id: str, user_id: str) -> bool:
        """Remove a user from a team.

        Args:
            team_id: Team ID
            user_id: User ID to remove

        Returns:
            True if member was removed

        Raises:
            ValueError: If trying to remove the owner
        """
        await self._ensure_tables()

        # Check if user is owner
        team = await self.get_team(team_id)
        if team and team.owner_id == user_id:
            raise ValueError("Cannot remove team owner. Transfer ownership first.")

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM team_memberships WHERE team_id = ? AND user_id = ?",
                (team_id, user_id),
            )
            await conn.commit()
            removed = cursor.rowcount > 0

        if removed:
            log.info("member_removed", team_id=team_id, user_id=user_id)

        return removed

    async def update_member_role(
        self,
        team_id: str,
        user_id: str,
        new_role: TeamRole,
    ) -> Optional[TeamMembership]:
        """Update a member's role.

        Args:
            team_id: Team ID
            user_id: User ID
            new_role: New role to assign

        Returns:
            Updated membership if found

        Raises:
            ValueError: If trying to change owner role
        """
        await self._ensure_tables()

        # Check if user is owner
        team = await self.get_team(team_id)
        if team and team.owner_id == user_id and new_role != TeamRole.OWNER:
            raise ValueError("Cannot change owner role. Transfer ownership first.")

        async with self.db.get_connection() as conn:
            await conn.execute(
                "UPDATE team_memberships SET role = ? WHERE team_id = ? AND user_id = ?",
                (new_role.value, team_id, user_id),
            )
            await conn.commit()

        log.info(
            "member_role_updated",
            team_id=team_id,
            user_id=user_id,
            new_role=new_role.value,
        )
        return await self.get_membership(team_id, user_id)

    async def get_membership(
        self,
        team_id: str,
        user_id: str,
    ) -> Optional[TeamMembership]:
        """Get a user's membership in a team.

        Args:
            team_id: Team ID
            user_id: User ID

        Returns:
            TeamMembership if found
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM team_memberships
                WHERE team_id = ? AND user_id = ?
                """,
                (team_id, user_id),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_membership(row)

    async def get_team_members(
        self,
        team_id: str,
        role: Optional[TeamRole] = None,
    ) -> list[TeamMembership]:
        """Get all members of a team.

        Args:
            team_id: Team ID
            role: Optional role filter

        Returns:
            List of TeamMembership objects
        """
        await self._ensure_tables()

        query = "SELECT * FROM team_memberships WHERE team_id = ?"
        params: list = [team_id]

        if role is not None:
            query += " AND role = ?"
            params.append(role.value)

        query += " ORDER BY joined_at"

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

        return [self._row_to_membership(row) for row in rows]

    async def get_user_teams(self, user_id: str) -> list[tuple[Team, TeamMembership]]:
        """Get all teams a user belongs to.

        Args:
            user_id: User ID

        Returns:
            List of (Team, TeamMembership) tuples
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT t.*, m.*
                FROM teams t
                JOIN team_memberships m ON t.id = m.team_id
                WHERE m.user_id = ? AND t.is_active = 1
                ORDER BY m.joined_at DESC
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()

        results = []
        for row in rows:
            # First 8 columns are team, next 6 are membership
            team = self._row_to_team(row[:8])
            membership = self._row_to_membership(row[8:])
            results.append((team, membership))

        return results

    async def transfer_ownership(
        self,
        team_id: str,
        new_owner_id: str,
    ) -> bool:
        """Transfer team ownership to another member.

        Args:
            team_id: Team ID
            new_owner_id: User ID of new owner (must be member)

        Returns:
            True if successful

        Raises:
            ValueError: If new owner is not a member
        """
        await self._ensure_tables()

        # Verify new owner is a member
        membership = await self.get_membership(team_id, new_owner_id)
        if not membership:
            raise ValueError("New owner must be a team member")

        team = await self.get_team(team_id)
        if not team:
            return False

        old_owner_id = team.owner_id

        async with self.db.get_connection() as conn:
            # Update team owner
            await conn.execute(
                "UPDATE teams SET owner_id = ? WHERE id = ?",
                (new_owner_id, team_id),
            )

            # Update new owner's role to OWNER
            await conn.execute(
                """
                UPDATE team_memberships SET role = ?
                WHERE team_id = ? AND user_id = ?
                """,
                (TeamRole.OWNER.value, team_id, new_owner_id),
            )

            # Demote old owner to ADMIN
            await conn.execute(
                """
                UPDATE team_memberships SET role = ?
                WHERE team_id = ? AND user_id = ?
                """,
                (TeamRole.ADMIN.value, team_id, old_owner_id),
            )

            await conn.commit()

        log.info(
            "ownership_transferred",
            team_id=team_id,
            old_owner=old_owner_id,
            new_owner=new_owner_id,
        )
        return True

    async def join_by_invite_code(
        self,
        invite_code: str,
        user_id: str,
    ) -> Optional[TeamMembership]:
        """Join a team using invite code.

        Args:
            invite_code: Team's invite code
            user_id: User joining

        Returns:
            Created membership if successful

        Raises:
            ValueError: If user is already a member
        """
        team = await self.get_team_by_invite_code(invite_code)
        if not team:
            return None

        return await self.add_member(team.id, user_id)

    # ========== Team Sessions ==========

    async def add_session_to_team(
        self,
        team_id: str,
        session_id: str,
        created_by: str,
        is_shared: bool = True,
    ) -> TeamSession:
        """Associate a session with a team.

        Args:
            team_id: Team ID
            session_id: Sindri session ID
            created_by: User who created the session
            is_shared: Whether visible to team (default True)

        Returns:
            Created TeamSession
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO team_sessions (team_id, session_id, created_by, is_shared)
                VALUES (?, ?, ?, ?)
                """,
                (team_id, session_id, created_by, 1 if is_shared else 0),
            )
            await conn.commit()
            session_link_id = cursor.lastrowid

        team_session = TeamSession(
            id=session_link_id,
            team_id=team_id,
            session_id=session_id,
            created_by=created_by,
            is_shared=is_shared,
        )

        log.info(
            "session_added_to_team",
            team_id=team_id,
            session_id=session_id,
        )
        return team_session

    async def get_team_sessions(
        self,
        team_id: str,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TeamSession]:
        """Get sessions belonging to a team.

        Args:
            team_id: Team ID
            user_id: If provided, include user's private sessions
            limit: Maximum sessions to return
            offset: Sessions to skip

        Returns:
            List of TeamSession objects
        """
        await self._ensure_tables()

        if user_id:
            query = """
                SELECT * FROM team_sessions
                WHERE team_id = ? AND (is_shared = 1 OR created_by = ?)
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            params = [team_id, user_id, limit, offset]
        else:
            query = """
                SELECT * FROM team_sessions
                WHERE team_id = ? AND is_shared = 1
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            params = [team_id, limit, offset]

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

        return [self._row_to_team_session(row) for row in rows]

    async def get_session_team(self, session_id: str) -> Optional[tuple[Team, TeamSession]]:
        """Get the team a session belongs to.

        Args:
            session_id: Session ID

        Returns:
            Tuple of (Team, TeamSession) if found
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT t.*, ts.*
                FROM teams t
                JOIN team_sessions ts ON t.id = ts.team_id
                WHERE ts.session_id = ?
                """,
                (session_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        team = self._row_to_team(row[:8])
        team_session = self._row_to_team_session(row[8:])
        return (team, team_session)

    async def remove_session_from_team(self, team_id: str, session_id: str) -> bool:
        """Remove a session from a team.

        Args:
            team_id: Team ID
            session_id: Session ID

        Returns:
            True if removed
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM team_sessions WHERE team_id = ? AND session_id = ?",
                (team_id, session_id),
            )
            await conn.commit()
            removed = cursor.rowcount > 0

        if removed:
            log.info(
                "session_removed_from_team",
                team_id=team_id,
                session_id=session_id,
            )

        return removed

    # ========== Permission Checking ==========

    async def can_user_access_session(
        self,
        user_id: str,
        session_id: str,
    ) -> bool:
        """Check if a user can access a session.

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            True if user has access
        """
        result = await self.get_session_team(session_id)
        if not result:
            return True  # Session not in a team, allow (individual session)

        team, team_session = result

        # Check if user is a team member
        membership = await self.get_membership(team.id, user_id)
        if not membership:
            return False

        # User is a member - check if session is shared or they created it
        if team_session.is_shared:
            return True

        return team_session.created_by == user_id

    async def get_user_role(self, team_id: str, user_id: str) -> Optional[TeamRole]:
        """Get a user's role in a team.

        Args:
            team_id: Team ID
            user_id: User ID

        Returns:
            TeamRole if user is a member, None otherwise
        """
        membership = await self.get_membership(team_id, user_id)
        return membership.role if membership else None

    # ========== Statistics ==========

    async def get_team_stats(self, team_id: str) -> dict:
        """Get statistics for a team.

        Args:
            team_id: Team ID

        Returns:
            Dictionary with member counts, session counts, etc.
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            # Member counts by role
            cursor = await conn.execute(
                """
                SELECT role, COUNT(*) as count
                FROM team_memberships
                WHERE team_id = ?
                GROUP BY role
                """,
                (team_id,),
            )
            role_rows = await cursor.fetchall()

            # Session count
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM team_sessions WHERE team_id = ?",
                (team_id,),
            )
            session_count = (await cursor.fetchone())[0]

        role_counts = {row[0]: row[1] for row in role_rows}
        total_members = sum(role_counts.values())

        return {
            "total_members": total_members,
            "members_by_role": role_counts,
            "session_count": session_count,
        }

    async def get_global_stats(self) -> dict:
        """Get global team statistics.

        Returns:
            Dictionary with total teams, members, sessions
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM teams WHERE is_active = 1"
            )
            team_count = (await cursor.fetchone())[0]

            cursor = await conn.execute("SELECT COUNT(*) FROM team_memberships")
            membership_count = (await cursor.fetchone())[0]

            cursor = await conn.execute("SELECT COUNT(*) FROM team_sessions")
            session_count = (await cursor.fetchone())[0]

        return {
            "total_teams": team_count,
            "total_memberships": membership_count,
            "total_team_sessions": session_count,
        }

    # ========== Helper Methods ==========

    def _row_to_team(self, row) -> Team:
        """Convert a database row to a Team object."""
        import json

        settings = {}
        if row[6]:
            try:
                settings = json.loads(row[6])
            except json.JSONDecodeError:
                pass

        return Team(
            id=row[0],
            name=row[1],
            description=row[2] or "",
            owner_id=row[3],
            invite_code=row[4],
            is_active=bool(row[5]),
            settings=settings,
            created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(),
        )

    def _row_to_membership(self, row) -> TeamMembership:
        """Convert a database row to a TeamMembership object."""
        return TeamMembership(
            id=row[0],
            team_id=row[1],
            user_id=row[2],
            role=TeamRole(row[3]),
            joined_at=datetime.fromisoformat(row[4]) if row[4] else datetime.now(),
            invited_by=row[5],
        )

    def _row_to_team_session(self, row) -> TeamSession:
        """Convert a database row to a TeamSession object."""
        return TeamSession(
            id=row[0],
            team_id=row[1],
            session_id=row[2],
            created_by=row[3],
            is_shared=bool(row[4]),
            created_at=datetime.fromisoformat(row[5]) if row[5] else datetime.now(),
        )
