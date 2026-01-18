"""User management for Team Mode.

This module provides user account management for multi-user collaboration:
- User creation and authentication
- Profile management
- User preferences
"""

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import structlog

if TYPE_CHECKING:
    from sindri.persistence.database import Database

log = structlog.get_logger()


def generate_user_id() -> str:
    """Generate a unique user ID."""
    return secrets.token_hex(16)


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Hash a password with salt.

    Args:
        password: Plain text password
        salt: Optional salt (generated if not provided)

    Returns:
        Tuple of (hashed_password, salt)
    """
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return hashed.hex(), salt


def verify_password(password: str, hashed: str, salt: str) -> bool:
    """Verify a password against its hash.

    Args:
        password: Plain text password to verify
        hashed: Stored password hash
        salt: Salt used for hashing

    Returns:
        True if password matches
    """
    computed, _ = hash_password(password, salt)
    return secrets.compare_digest(computed, hashed)


@dataclass
class User:
    """A user account in the system.

    Attributes:
        id: Unique user identifier
        username: Unique username for login
        email: User's email address
        display_name: Name shown in UI
        password_hash: Hashed password
        password_salt: Salt for password hashing
        is_active: Whether user can log in
        created_at: Account creation time
        last_login: Last successful login time
        preferences: JSON-serializable user preferences
    """

    id: str
    username: str
    email: str
    display_name: str
    password_hash: str = ""
    password_salt: str = ""
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    preferences: dict = field(default_factory=dict)

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Convert to dictionary for serialization.

        Args:
            include_sensitive: Include password hash/salt (default False)

        Returns:
            Dictionary representation
        """
        result = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "preferences": self.preferences,
        }
        if include_sensitive:
            result["password_hash"] = self.password_hash
            result["password_salt"] = self.password_salt
        return result

    def check_password(self, password: str) -> bool:
        """Check if password matches.

        Args:
            password: Plain text password to check

        Returns:
            True if password is correct
        """
        if not self.password_hash or not self.password_salt:
            return False
        return verify_password(password, self.password_hash, self.password_salt)

    def set_password(self, password: str) -> None:
        """Set a new password.

        Args:
            password: New plain text password
        """
        self.password_hash, self.password_salt = hash_password(password)


class UserStore:
    """Persistent storage for user accounts."""

    def __init__(self, database: Optional["Database"] = None):
        """Initialize the user store.

        Args:
            database: Database instance (creates default if not provided)
        """
        from sindri.persistence.database import Database

        self.db = database or Database()

    async def _ensure_tables(self) -> None:
        """Ensure user tables exist."""
        await self.db.initialize()
        async with self.db.get_connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    password_hash TEXT,
                    password_salt TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    preferences TEXT DEFAULT '{}'
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
            """)
            await conn.commit()

    async def create_user(
        self,
        username: str,
        email: str,
        display_name: str,
        password: Optional[str] = None,
    ) -> User:
        """Create a new user account.

        Args:
            username: Unique username
            email: User's email
            display_name: Display name
            password: Optional password (can be set later)

        Returns:
            Created User object

        Raises:
            ValueError: If username or email already exists
        """
        await self._ensure_tables()

        user_id = generate_user_id()
        password_hash = ""
        password_salt = ""

        if password:
            password_hash, password_salt = hash_password(password)

        user = User(
            id=user_id,
            username=username,
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            password_salt=password_salt,
        )

        async with self.db.get_connection() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO users (
                        id, username, email, display_name,
                        password_hash, password_salt, is_active,
                        created_at, preferences
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user.id,
                        user.username,
                        user.email,
                        user.display_name,
                        user.password_hash,
                        user.password_salt,
                        1 if user.is_active else 0,
                        user.created_at.isoformat(),
                        "{}",
                    ),
                )
                await conn.commit()
            except Exception as e:
                if "UNIQUE constraint failed" in str(e):
                    if "username" in str(e):
                        raise ValueError(f"Username '{username}' already exists") from e
                    if "email" in str(e):
                        raise ValueError(f"Email '{email}' already exists") from e
                raise

        log.info("user_created", user_id=user_id, username=username)
        return user

    async def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID.

        Args:
            user_id: User ID to look up

        Returns:
            User if found, None otherwise
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_user(row)

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username.

        Args:
            username: Username to look up

        Returns:
            User if found, None otherwise
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_user(row)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email.

        Args:
            email: Email to look up

        Returns:
            User if found, None otherwise
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_user(row)

    async def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate a user by username and password.

        Args:
            username: Username to authenticate
            password: Password to verify

        Returns:
            User if authentication successful, None otherwise
        """
        user = await self.get_user_by_username(username)
        if not user:
            return None

        if not user.is_active:
            log.warning("login_inactive_user", username=username)
            return None

        if not user.check_password(password):
            log.warning("login_failed", username=username)
            return None

        # Update last login
        await self.update_last_login(user.id)
        user.last_login = datetime.now()

        log.info("login_success", user_id=user.id, username=username)
        return user

    async def update_last_login(self, user_id: str) -> None:
        """Update a user's last login timestamp.

        Args:
            user_id: User ID to update
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            await conn.execute(
                "UPDATE users SET last_login = ? WHERE id = ?",
                (datetime.now().isoformat(), user_id),
            )
            await conn.commit()

    async def update_user(
        self,
        user_id: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        is_active: Optional[bool] = None,
        preferences: Optional[dict] = None,
    ) -> Optional[User]:
        """Update user profile fields.

        Args:
            user_id: User ID to update
            display_name: New display name (optional)
            email: New email (optional)
            is_active: New active status (optional)
            preferences: New preferences (optional)

        Returns:
            Updated User if found, None otherwise
        """
        await self._ensure_tables()

        updates = []
        params = []

        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name)

        if email is not None:
            updates.append("email = ?")
            params.append(email)

        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)

        if preferences is not None:
            import json

            updates.append("preferences = ?")
            params.append(json.dumps(preferences))

        if not updates:
            return await self.get_user(user_id)

        params.append(user_id)

        async with self.db.get_connection() as conn:
            await conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await conn.commit()

        log.info("user_updated", user_id=user_id)
        return await self.get_user(user_id)

    async def change_password(self, user_id: str, new_password: str) -> bool:
        """Change a user's password.

        Args:
            user_id: User ID
            new_password: New password

        Returns:
            True if successful
        """
        await self._ensure_tables()

        password_hash, password_salt = hash_password(new_password)

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE users
                SET password_hash = ?, password_salt = ?
                WHERE id = ?
                """,
                (password_hash, password_salt, user_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_user(self, user_id: str) -> bool:
        """Delete a user account.

        Args:
            user_id: User ID to delete

        Returns:
            True if user was deleted
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM users WHERE id = ?",
                (user_id,),
            )
            await conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            log.info("user_deleted", user_id=user_id)

        return deleted

    async def list_users(
        self,
        limit: int = 50,
        offset: int = 0,
        active_only: bool = False,
    ) -> list[User]:
        """List users with pagination.

        Args:
            limit: Maximum number of users to return
            offset: Number of users to skip
            active_only: Only return active users

        Returns:
            List of User objects
        """
        await self._ensure_tables()

        query = "SELECT * FROM users"
        params: list = []

        if active_only:
            query += " WHERE is_active = 1"

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

        return [self._row_to_user(row) for row in rows]

    async def search_users(self, query: str, limit: int = 20) -> list[User]:
        """Search users by username or display name.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching users
        """
        await self._ensure_tables()

        search_pattern = f"%{query}%"

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM users
                WHERE (username LIKE ? OR display_name LIKE ?)
                AND is_active = 1
                ORDER BY username
                LIMIT ?
                """,
                (search_pattern, search_pattern, limit),
            )
            rows = await cursor.fetchall()

        return [self._row_to_user(row) for row in rows]

    async def get_user_count(self) -> dict:
        """Get user statistics.

        Returns:
            Dictionary with total, active, inactive counts
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active,
                    SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) as inactive
                FROM users
                """
            )
            row = await cursor.fetchone()

        return {
            "total": row[0] or 0,
            "active": row[1] or 0,
            "inactive": row[2] or 0,
        }

    def _row_to_user(self, row) -> User:
        """Convert a database row to a User object."""
        import json

        preferences = {}
        if row[9]:
            try:
                preferences = json.loads(row[9])
            except json.JSONDecodeError:
                pass

        return User(
            id=row[0],
            username=row[1],
            email=row[2],
            display_name=row[3],
            password_hash=row[4] or "",
            password_salt=row[5] or "",
            is_active=bool(row[6]),
            created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(),
            last_login=datetime.fromisoformat(row[8]) if row[8] else None,
            preferences=preferences,
        )
