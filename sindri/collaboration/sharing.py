"""Session sharing for remote collaboration.

This module provides infrastructure for sharing Sindri sessions with
others via unique share links with configurable permissions.
"""

import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Any
import structlog

from sindri.persistence.database import Database

log = structlog.get_logger()


class SharePermission(str, Enum):
    """Permission levels for shared sessions."""

    READ = "read"  # View session only
    COMMENT = "comment"  # View + add comments
    WRITE = "write"  # View + comment + continue session (future)


@dataclass
class SessionShare:
    """A share link for a session.

    Attributes:
        session_id: The session being shared
        share_token: Unique token for the share link
        permission: Access level (read, comment, write)
        created_by: Who created the share (optional)
        expires_at: When the share expires (None = never)
        max_uses: Maximum number of times the link can be used (None = unlimited)
        use_count: Current number of uses
        is_active: Whether the share is currently active
        id: Database ID (set after save)
        created_at: When the share was created
    """

    session_id: str
    share_token: str
    permission: SharePermission = SharePermission.READ
    created_by: Optional[str] = None
    expires_at: Optional[datetime] = None
    max_uses: Optional[int] = None
    use_count: int = 0
    is_active: bool = True
    id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def is_expired(self) -> bool:
        """Check if the share has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    @property
    def is_exhausted(self) -> bool:
        """Check if the share has reached max uses."""
        if self.max_uses is None:
            return False
        return self.use_count >= self.max_uses

    @property
    def is_valid(self) -> bool:
        """Check if the share is currently valid for use."""
        return self.is_active and not self.is_expired and not self.is_exhausted

    def can_read(self) -> bool:
        """Check if this share grants read permission."""
        return self.permission in [
            SharePermission.READ,
            SharePermission.COMMENT,
            SharePermission.WRITE,
        ]

    def can_comment(self) -> bool:
        """Check if this share grants comment permission."""
        return self.permission in [SharePermission.COMMENT, SharePermission.WRITE]

    def can_write(self) -> bool:
        """Check if this share grants write permission."""
        return self.permission == SharePermission.WRITE

    def get_share_url(self, base_url: str = "http://localhost:8000") -> str:
        """Generate the full share URL.

        Args:
            base_url: Base URL for the Sindri web interface

        Returns:
            Full share URL
        """
        return f"{base_url}/share/{self.share_token}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "share_token": self.share_token,
            "permission": self.permission.value,
            "created_by": self.created_by,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "max_uses": self.max_uses,
            "use_count": self.use_count,
            "is_active": self.is_active,
            "is_valid": self.is_valid,
            "created_at": self.created_at.isoformat(),
        }


def generate_share_token(length: int = 16) -> str:
    """Generate a secure random share token.

    Args:
        length: Length of the token (default 16)

    Returns:
        URL-safe random token
    """
    # Use URL-safe characters
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class ShareStore:
    """Manages session share persistence."""

    def __init__(self, database: Optional[Database] = None):
        """Initialize share store.

        Args:
            database: Database instance (uses default if not provided)
        """
        self.db = database or Database()

    async def create_share(
        self,
        session_id: str,
        permission: SharePermission = SharePermission.READ,
        created_by: Optional[str] = None,
        expires_in_hours: Optional[float] = None,
        max_uses: Optional[int] = None,
    ) -> SessionShare:
        """Create a new share link for a session.

        Args:
            session_id: Session to share
            permission: Access level for the share
            created_by: Username/identifier of creator
            expires_in_hours: Hours until expiration (None = never)
            max_uses: Maximum uses (None = unlimited)

        Returns:
            The created SessionShare
        """
        await self.db.initialize()

        share_token = generate_share_token()
        expires_at = None
        if expires_in_hours is not None:
            expires_at = datetime.now() + timedelta(hours=expires_in_hours)

        share = SessionShare(
            session_id=session_id,
            share_token=share_token,
            permission=permission,
            created_by=created_by,
            expires_at=expires_at,
            max_uses=max_uses,
        )

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO session_shares
                (session_id, share_token, created_by, permission, expires_at, max_uses, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    share.session_id,
                    share.share_token,
                    share.created_by,
                    share.permission.value,
                    share.expires_at,
                    share.max_uses,
                    share.created_at,
                ),
            )
            share.id = cursor.lastrowid
            await conn.commit()

        log.info(
            "share_created",
            session_id=session_id,
            share_token=share_token[:8] + "...",
            permission=permission.value,
        )
        return share

    async def get_share_by_token(self, share_token: str) -> Optional[SessionShare]:
        """Get a share by its token.

        Args:
            share_token: The share token to look up

        Returns:
            SessionShare if found, None otherwise
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT id, session_id, share_token, created_by, permission,
                       expires_at, max_uses, use_count, is_active, created_at
                FROM session_shares
                WHERE share_token = ?
                """,
                (share_token,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                return SessionShare(
                    id=row[0],
                    session_id=row[1],
                    share_token=row[2],
                    created_by=row[3],
                    permission=SharePermission(row[4]),
                    expires_at=datetime.fromisoformat(row[5]) if row[5] else None,
                    max_uses=row[6],
                    use_count=row[7],
                    is_active=bool(row[8]),
                    created_at=datetime.fromisoformat(row[9]) if row[9] else datetime.now(),
                )

    async def validate_and_use_share(self, share_token: str) -> Optional[SessionShare]:
        """Validate a share token and increment use count if valid.

        Args:
            share_token: The share token to validate

        Returns:
            SessionShare if valid, None if invalid or expired
        """
        share = await self.get_share_by_token(share_token)

        if share is None:
            log.warning("share_not_found", token=share_token[:8] + "...")
            return None

        if not share.is_valid:
            reason = "inactive" if not share.is_active else (
                "expired" if share.is_expired else "exhausted"
            )
            log.warning("share_invalid", token=share_token[:8] + "...", reason=reason)
            return None

        # Increment use count
        await self.db.initialize()
        async with self.db.get_connection() as conn:
            await conn.execute(
                "UPDATE session_shares SET use_count = use_count + 1 WHERE id = ?",
                (share.id,),
            )
            await conn.commit()

        share.use_count += 1
        log.info("share_used", session_id=share.session_id, use_count=share.use_count)
        return share

    async def get_shares_for_session(self, session_id: str) -> list[SessionShare]:
        """Get all shares for a session.

        Args:
            session_id: Session ID to get shares for

        Returns:
            List of SessionShare objects
        """
        await self.db.initialize()

        shares = []
        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT id, session_id, share_token, created_by, permission,
                       expires_at, max_uses, use_count, is_active, created_at
                FROM session_shares
                WHERE session_id = ?
                ORDER BY created_at DESC
                """,
                (session_id,),
            ) as cursor:
                async for row in cursor:
                    shares.append(
                        SessionShare(
                            id=row[0],
                            session_id=row[1],
                            share_token=row[2],
                            created_by=row[3],
                            permission=SharePermission(row[4]),
                            expires_at=datetime.fromisoformat(row[5]) if row[5] else None,
                            max_uses=row[6],
                            use_count=row[7],
                            is_active=bool(row[8]),
                            created_at=datetime.fromisoformat(row[9]) if row[9] else datetime.now(),
                        )
                    )

        return shares

    async def revoke_share(self, share_id: int) -> bool:
        """Revoke a share by setting it inactive.

        Args:
            share_id: ID of the share to revoke

        Returns:
            True if revoked, False if not found
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "UPDATE session_shares SET is_active = 0 WHERE id = ?",
                (share_id,),
            )
            await conn.commit()
            if cursor.rowcount > 0:
                log.info("share_revoked", share_id=share_id)
                return True
            return False

    async def revoke_all_shares(self, session_id: str) -> int:
        """Revoke all shares for a session.

        Args:
            session_id: Session to revoke shares for

        Returns:
            Number of shares revoked
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "UPDATE session_shares SET is_active = 0 WHERE session_id = ? AND is_active = 1",
                (session_id,),
            )
            await conn.commit()
            count = cursor.rowcount
            if count > 0:
                log.info("shares_revoked", session_id=session_id, count=count)
            return count

    async def delete_expired_shares(self) -> int:
        """Delete all expired shares from the database.

        Returns:
            Number of shares deleted
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                DELETE FROM session_shares
                WHERE expires_at IS NOT NULL AND expires_at < ?
                """,
                (datetime.now(),),
            )
            await conn.commit()
            count = cursor.rowcount
            if count > 0:
                log.info("expired_shares_deleted", count=count)
            return count

    async def get_share_stats(self) -> dict[str, Any]:
        """Get statistics about shares.

        Returns:
            Dictionary with share statistics
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            # Total shares
            async with conn.execute("SELECT COUNT(*) FROM session_shares") as cursor:
                total_shares = (await cursor.fetchone())[0]

            # Active shares
            async with conn.execute(
                "SELECT COUNT(*) FROM session_shares WHERE is_active = 1"
            ) as cursor:
                active_shares = (await cursor.fetchone())[0]

            # Total uses
            async with conn.execute(
                "SELECT SUM(use_count) FROM session_shares"
            ) as cursor:
                total_uses = (await cursor.fetchone())[0] or 0

            # Sessions with shares
            async with conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM session_shares"
            ) as cursor:
                sessions_shared = (await cursor.fetchone())[0]

            # Permission breakdown
            permission_counts = {}
            async with conn.execute(
                "SELECT permission, COUNT(*) FROM session_shares GROUP BY permission"
            ) as cursor:
                async for row in cursor:
                    permission_counts[row[0]] = row[1]

        return {
            "total_shares": total_shares,
            "active_shares": active_shares,
            "total_uses": total_uses,
            "sessions_shared": sessions_shared,
            "permission_breakdown": permission_counts,
        }
