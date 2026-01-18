"""API Keys for programmatic access.

This module provides API key management for automation and CI/CD integration:
- Key generation with secure random values
- Key hashing for secure storage (only prefix is stored in plain text)
- Scope-based permissions (read, write, admin, specific APIs)
- Key expiration and revocation
- Usage tracking with rate limiting
- Audit logging of key usage
"""

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Optional

import structlog

if TYPE_CHECKING:
    from sindri.persistence.database import Database

log = structlog.get_logger()


# Key prefix for identification
KEY_PREFIX = "sk_"  # "sk" = "secret key"
KEY_PREFIX_TEST = "sk_test_"  # For test/sandbox keys


def generate_api_key_id() -> str:
    """Generate a unique API key ID."""
    return secrets.token_hex(16)


def generate_api_key(test_mode: bool = False) -> tuple[str, str]:
    """Generate a new API key.

    Returns:
        Tuple of (full_key, key_id) where:
        - full_key: The complete key to give to the user (only shown once)
        - key_id: The last 8 characters for identification
    """
    prefix = KEY_PREFIX_TEST if test_mode else KEY_PREFIX
    # 32 bytes = 256 bits of entropy
    random_part = secrets.token_urlsafe(32)
    full_key = f"{prefix}{random_part}"
    key_id = random_part[-8:]
    return full_key, key_id


def hash_api_key(key: str) -> str:
    """Hash an API key for secure storage.

    Uses SHA-256 for fast verification (API keys are already high-entropy).

    Args:
        key: The full API key

    Returns:
        Hex-encoded hash
    """
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(key: str, key_hash: str) -> bool:
    """Verify an API key against its hash.

    Args:
        key: The API key to verify
        key_hash: The stored hash

    Returns:
        True if key matches
    """
    computed = hash_api_key(key)
    return secrets.compare_digest(computed, key_hash)


class APIKeyScope(str, Enum):
    """Scopes that define what an API key can access."""

    # Read-only access
    READ = "read"  # Read sessions, history, etc.
    READ_SESSIONS = "read:sessions"
    READ_AGENTS = "read:agents"
    READ_METRICS = "read:metrics"

    # Write access
    WRITE = "write"  # Create and modify sessions
    WRITE_SESSIONS = "write:sessions"
    WRITE_TASKS = "write:tasks"

    # Team operations
    TEAM_READ = "team:read"
    TEAM_WRITE = "team:write"
    TEAM_ADMIN = "team:admin"

    # Webhook operations
    WEBHOOKS = "webhooks"
    WEBHOOKS_MANAGE = "webhooks:manage"

    # Administrative
    ADMIN = "admin"  # Full access


# Scope hierarchy - higher scopes include lower ones
SCOPE_HIERARCHY = {
    APIKeyScope.ADMIN: {
        APIKeyScope.READ,
        APIKeyScope.WRITE,
        APIKeyScope.TEAM_READ,
        APIKeyScope.TEAM_WRITE,
        APIKeyScope.TEAM_ADMIN,
        APIKeyScope.WEBHOOKS,
        APIKeyScope.WEBHOOKS_MANAGE,
        APIKeyScope.READ_SESSIONS,
        APIKeyScope.READ_AGENTS,
        APIKeyScope.READ_METRICS,
        APIKeyScope.WRITE_SESSIONS,
        APIKeyScope.WRITE_TASKS,
    },
    APIKeyScope.WRITE: {
        APIKeyScope.READ,
        APIKeyScope.WRITE_SESSIONS,
        APIKeyScope.WRITE_TASKS,
        APIKeyScope.READ_SESSIONS,
        APIKeyScope.READ_AGENTS,
        APIKeyScope.READ_METRICS,
    },
    APIKeyScope.READ: {
        APIKeyScope.READ_SESSIONS,
        APIKeyScope.READ_AGENTS,
        APIKeyScope.READ_METRICS,
    },
    APIKeyScope.TEAM_ADMIN: {
        APIKeyScope.TEAM_READ,
        APIKeyScope.TEAM_WRITE,
    },
    APIKeyScope.TEAM_WRITE: {
        APIKeyScope.TEAM_READ,
    },
    APIKeyScope.WEBHOOKS_MANAGE: {
        APIKeyScope.WEBHOOKS,
    },
}


def expand_scopes(scopes: list[APIKeyScope]) -> set[APIKeyScope]:
    """Expand scopes to include all implied scopes.

    Args:
        scopes: List of explicitly granted scopes

    Returns:
        Set of all effective scopes including implied ones
    """
    result = set(scopes)
    for scope in scopes:
        if scope in SCOPE_HIERARCHY:
            result.update(SCOPE_HIERARCHY[scope])
    return result


@dataclass
class APIKey:
    """An API key for programmatic access.

    Attributes:
        id: Unique key identifier
        user_id: User who owns this key
        name: Human-readable name for the key
        key_hash: SHA-256 hash of the key (key itself is not stored)
        key_prefix: First few characters of key for identification
        key_suffix: Last 4 characters for display (e.g., "...abc1")
        scopes: List of granted scopes
        description: Optional description of key purpose
        created_at: When key was created
        expires_at: When key expires (None = never)
        last_used_at: Last time key was used
        last_used_ip: IP address of last use
        use_count: Total number of times key has been used
        rate_limit: Max requests per minute (0 = unlimited)
        is_active: Whether key is currently active
        team_id: Optional team this key is restricted to
        metadata: Additional key metadata
    """

    id: str
    user_id: str
    name: str
    key_hash: str
    key_prefix: str
    key_suffix: str
    scopes: list[APIKeyScope]
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    last_used_ip: Optional[str] = None
    use_count: int = 0
    rate_limit: int = 0
    is_active: bool = True
    team_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization.

        Note: key_hash is never included in public representation.

        Returns:
            Dictionary representation
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "key_prefix": self.key_prefix,
            "key_suffix": self.key_suffix,
            "scopes": [s.value for s in self.scopes],
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": (
                self.last_used_at.isoformat() if self.last_used_at else None
            ),
            "last_used_ip": self.last_used_ip,
            "use_count": self.use_count,
            "rate_limit": self.rate_limit,
            "is_active": self.is_active,
            "team_id": self.team_id,
            "metadata": self.metadata,
        }

    @property
    def is_expired(self) -> bool:
        """Check if key has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if key is valid for use."""
        return self.is_active and not self.is_expired

    @property
    def display_key(self) -> str:
        """Get a safe display version of the key."""
        return f"{self.key_prefix}...{self.key_suffix}"

    def has_scope(self, scope: APIKeyScope) -> bool:
        """Check if key has a specific scope.

        Args:
            scope: Scope to check

        Returns:
            True if key has the scope (directly or via hierarchy)
        """
        effective_scopes = expand_scopes(self.scopes)
        return scope in effective_scopes

    def has_any_scope(self, scopes: list[APIKeyScope]) -> bool:
        """Check if key has any of the given scopes.

        Args:
            scopes: List of scopes to check

        Returns:
            True if key has at least one of the scopes
        """
        effective_scopes = expand_scopes(self.scopes)
        return bool(effective_scopes & set(scopes))


@dataclass
class APIKeyUsageRecord:
    """Record of an API key usage.

    Attributes:
        id: Unique record identifier
        key_id: API key that was used
        timestamp: When the key was used
        ip_address: Client IP address
        endpoint: API endpoint that was called
        method: HTTP method used
        status_code: Response status code
        user_agent: Client user agent
        duration_ms: Request duration in milliseconds
    """

    id: str
    key_id: str
    timestamp: datetime
    ip_address: str
    endpoint: str
    method: str = "GET"
    status_code: int = 200
    user_agent: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "key_id": self.key_id,
            "timestamp": self.timestamp.isoformat(),
            "ip_address": self.ip_address,
            "endpoint": self.endpoint,
            "method": self.method,
            "status_code": self.status_code,
            "user_agent": self.user_agent,
            "duration_ms": self.duration_ms,
        }


class APIKeyStore:
    """Persistent storage for API keys."""

    def __init__(self, database: Optional["Database"] = None):
        """Initialize the API key store.

        Args:
            database: Database instance (creates default if not provided)
        """
        from sindri.persistence.database import Database

        self.db = database or Database()

    async def _ensure_tables(self) -> None:
        """Ensure API key tables exist."""
        await self.db.initialize()
        async with self.db.get_connection() as conn:
            # Main API keys table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    key_prefix TEXT NOT NULL,
                    key_suffix TEXT NOT NULL,
                    scopes TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    last_used_at TIMESTAMP,
                    last_used_ip TEXT,
                    use_count INTEGER DEFAULT 0,
                    rate_limit INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    team_id TEXT,
                    metadata TEXT DEFAULT '{}'
                )
            """)

            # Index for fast lookups by hash (authentication)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_keys_hash
                ON api_keys(key_hash)
            """)

            # Index for user's keys
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_keys_user
                ON api_keys(user_id)
            """)

            # Index for team keys
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_keys_team
                ON api_keys(team_id)
            """)

            # Usage tracking table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS api_key_usage (
                    id TEXT PRIMARY KEY,
                    key_id TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address TEXT,
                    endpoint TEXT,
                    method TEXT DEFAULT 'GET',
                    status_code INTEGER DEFAULT 200,
                    user_agent TEXT DEFAULT '',
                    duration_ms INTEGER DEFAULT 0,
                    FOREIGN KEY (key_id) REFERENCES api_keys(id) ON DELETE CASCADE
                )
            """)

            # Index for rate limiting queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_key_usage_key_time
                ON api_key_usage(key_id, timestamp)
            """)

            await conn.commit()

    async def create_key(
        self,
        user_id: str,
        name: str,
        scopes: list[APIKeyScope],
        description: str = "",
        expires_in_days: Optional[int] = None,
        rate_limit: int = 0,
        team_id: Optional[str] = None,
        test_mode: bool = False,
        metadata: Optional[dict] = None,
    ) -> tuple[APIKey, str]:
        """Create a new API key.

        Args:
            user_id: User who owns this key
            name: Human-readable name
            scopes: List of scopes to grant
            description: Optional description
            expires_in_days: Days until expiration (None = never)
            rate_limit: Max requests per minute (0 = unlimited)
            team_id: Optional team restriction
            test_mode: Create a test key with limited scope
            metadata: Additional metadata

        Returns:
            Tuple of (APIKey object, full key string)

        Note:
            The full key string is only returned once at creation time.
            It cannot be retrieved later as only the hash is stored.
        """
        await self._ensure_tables()

        key_id = generate_api_key_id()
        full_key, key_suffix = generate_api_key(test_mode)
        key_hash = hash_api_key(full_key)
        key_prefix = full_key[: len(KEY_PREFIX_TEST if test_mode else KEY_PREFIX) + 4]

        expires_at = None
        if expires_in_days is not None:
            expires_at = datetime.now() + timedelta(days=expires_in_days)

        api_key = APIKey(
            id=key_id,
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            key_suffix=key_suffix,
            scopes=scopes,
            description=description,
            expires_at=expires_at,
            rate_limit=rate_limit,
            team_id=team_id,
            metadata=metadata or {},
        )

        import json

        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO api_keys (
                    id, user_id, name, key_hash, key_prefix, key_suffix,
                    scopes, description, created_at, expires_at,
                    rate_limit, team_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    api_key.id,
                    api_key.user_id,
                    api_key.name,
                    api_key.key_hash,
                    api_key.key_prefix,
                    api_key.key_suffix,
                    json.dumps([s.value for s in api_key.scopes]),
                    api_key.description,
                    api_key.created_at.isoformat(),
                    api_key.expires_at.isoformat() if api_key.expires_at else None,
                    api_key.rate_limit,
                    api_key.team_id,
                    json.dumps(api_key.metadata),
                ),
            )
            await conn.commit()

        log.info(
            "api_key_created",
            key_id=key_id,
            user_id=user_id,
            name=name,
            scopes=[s.value for s in scopes],
        )

        return api_key, full_key

    async def verify_key(
        self,
        key: str,
        required_scope: Optional[APIKeyScope] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[APIKey]:
        """Verify an API key and return it if valid.

        Args:
            key: The API key to verify
            required_scope: Optional scope that must be present
            ip_address: Client IP for usage tracking

        Returns:
            APIKey if valid, None if invalid or expired
        """
        await self._ensure_tables()

        key_hash = hash_api_key(key)

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM api_keys WHERE key_hash = ?",
                (key_hash,),
            )
            row = await cursor.fetchone()

        if not row:
            log.warning("api_key_not_found", key_prefix=key[:12])
            return None

        api_key = self._row_to_key(row)

        # Check if key is valid
        if not api_key.is_valid:
            log.warning(
                "api_key_invalid",
                key_id=api_key.id,
                is_active=api_key.is_active,
                is_expired=api_key.is_expired,
            )
            return None

        # Check required scope
        if required_scope and not api_key.has_scope(required_scope):
            log.warning(
                "api_key_missing_scope",
                key_id=api_key.id,
                required=required_scope.value,
                scopes=[s.value for s in api_key.scopes],
            )
            return None

        # Check rate limit
        if api_key.rate_limit > 0:
            is_within_limit = await self._check_rate_limit(
                api_key.id, api_key.rate_limit
            )
            if not is_within_limit:
                log.warning("api_key_rate_limited", key_id=api_key.id)
                return None

        # Update usage statistics
        await self._update_usage(api_key.id, ip_address)

        return api_key

    async def _check_rate_limit(self, key_id: str, limit: int) -> bool:
        """Check if key is within rate limit.

        Args:
            key_id: API key ID
            limit: Requests per minute limit

        Returns:
            True if within limit
        """
        one_minute_ago = (datetime.now() - timedelta(minutes=1)).isoformat()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT COUNT(*) FROM api_key_usage
                WHERE key_id = ? AND timestamp > ?
                """,
                (key_id, one_minute_ago),
            )
            row = await cursor.fetchone()
            count = row[0] if row else 0

        return count < limit

    async def _update_usage(self, key_id: str, ip_address: Optional[str]) -> None:
        """Update key usage statistics.

        Args:
            key_id: API key ID
            ip_address: Client IP address
        """
        now = datetime.now()
        record_id = secrets.token_hex(16)

        async with self.db.get_connection() as conn:
            # Update key stats
            await conn.execute(
                """
                UPDATE api_keys
                SET last_used_at = ?, last_used_ip = ?, use_count = use_count + 1
                WHERE id = ?
                """,
                (now.isoformat(), ip_address, key_id),
            )
            # Insert minimal usage record for rate limiting
            await conn.execute(
                """
                INSERT INTO api_key_usage (id, key_id, timestamp, ip_address, endpoint)
                VALUES (?, ?, ?, ?, ?)
                """,
                (record_id, key_id, now.isoformat(), ip_address, "_internal"),
            )
            await conn.commit()

    async def record_usage(
        self,
        key_id: str,
        ip_address: str,
        endpoint: str,
        method: str = "GET",
        status_code: int = 200,
        user_agent: str = "",
        duration_ms: int = 0,
    ) -> None:
        """Record detailed API key usage.

        Args:
            key_id: API key ID
            ip_address: Client IP
            endpoint: API endpoint called
            method: HTTP method
            status_code: Response status
            user_agent: Client user agent
            duration_ms: Request duration
        """
        await self._ensure_tables()

        record_id = secrets.token_hex(16)

        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO api_key_usage (
                    id, key_id, timestamp, ip_address, endpoint,
                    method, status_code, user_agent, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    key_id,
                    datetime.now().isoformat(),
                    ip_address,
                    endpoint,
                    method,
                    status_code,
                    user_agent,
                    duration_ms,
                ),
            )
            await conn.commit()

    async def get_key(self, key_id: str) -> Optional[APIKey]:
        """Get an API key by ID.

        Args:
            key_id: Key ID to look up

        Returns:
            APIKey if found, None otherwise
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM api_keys WHERE id = ?",
                (key_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_key(row)

    async def list_keys(
        self,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        include_inactive: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[APIKey]:
        """List API keys with optional filters.

        Args:
            user_id: Filter by user
            team_id: Filter by team
            include_inactive: Include revoked/inactive keys
            limit: Maximum results
            offset: Result offset

        Returns:
            List of API keys
        """
        await self._ensure_tables()

        conditions = []
        params: list = []

        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)

        if team_id:
            conditions.append("team_id = ?")
            params.append(team_id)

        if not include_inactive:
            conditions.append("is_active = 1")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                f"""
                SELECT * FROM api_keys
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            )
            rows = await cursor.fetchall()

        return [self._row_to_key(row) for row in rows]

    async def update_key(
        self,
        key_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        scopes: Optional[list[APIKeyScope]] = None,
        rate_limit: Optional[int] = None,
        is_active: Optional[bool] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[APIKey]:
        """Update an API key's settings.

        Args:
            key_id: Key ID to update
            name: New name
            description: New description
            scopes: New scopes
            rate_limit: New rate limit
            is_active: New active status
            metadata: New metadata

        Returns:
            Updated APIKey if found
        """
        await self._ensure_tables()

        updates = []
        params: list = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)

        if description is not None:
            updates.append("description = ?")
            params.append(description)

        if scopes is not None:
            import json

            updates.append("scopes = ?")
            params.append(json.dumps([s.value for s in scopes]))

        if rate_limit is not None:
            updates.append("rate_limit = ?")
            params.append(rate_limit)

        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)

        if metadata is not None:
            import json

            updates.append("metadata = ?")
            params.append(json.dumps(metadata))

        if not updates:
            return await self.get_key(key_id)

        params.append(key_id)

        async with self.db.get_connection() as conn:
            await conn.execute(
                f"UPDATE api_keys SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await conn.commit()

        log.info("api_key_updated", key_id=key_id)
        return await self.get_key(key_id)

    async def revoke_key(self, key_id: str) -> bool:
        """Revoke an API key.

        Args:
            key_id: Key ID to revoke

        Returns:
            True if key was revoked
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "UPDATE api_keys SET is_active = 0 WHERE id = ?",
                (key_id,),
            )
            await conn.commit()
            revoked = cursor.rowcount > 0

        if revoked:
            log.info("api_key_revoked", key_id=key_id)

        return revoked

    async def delete_key(self, key_id: str) -> bool:
        """Permanently delete an API key.

        Args:
            key_id: Key ID to delete

        Returns:
            True if key was deleted
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            # Delete usage records first (FK constraint)
            await conn.execute(
                "DELETE FROM api_key_usage WHERE key_id = ?",
                (key_id,),
            )
            cursor = await conn.execute(
                "DELETE FROM api_keys WHERE id = ?",
                (key_id,),
            )
            await conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            log.info("api_key_deleted", key_id=key_id)

        return deleted

    async def get_usage_stats(
        self,
        key_id: str,
        days: int = 30,
    ) -> dict:
        """Get usage statistics for an API key.

        Args:
            key_id: API key ID
            days: Number of days to look back

        Returns:
            Usage statistics dictionary
        """
        await self._ensure_tables()

        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        async with self.db.get_connection() as conn:
            # Total requests
            cursor = await conn.execute(
                """
                SELECT COUNT(*) FROM api_key_usage
                WHERE key_id = ? AND timestamp > ?
                """,
                (key_id, start_date),
            )
            total_requests = (await cursor.fetchone())[0]

            # Requests by status
            cursor = await conn.execute(
                """
                SELECT status_code, COUNT(*) FROM api_key_usage
                WHERE key_id = ? AND timestamp > ?
                GROUP BY status_code
                """,
                (key_id, start_date),
            )
            status_counts = dict(await cursor.fetchall())

            # Requests by endpoint
            cursor = await conn.execute(
                """
                SELECT endpoint, COUNT(*) FROM api_key_usage
                WHERE key_id = ? AND timestamp > ?
                GROUP BY endpoint
                ORDER BY COUNT(*) DESC
                LIMIT 10
                """,
                (key_id, start_date),
            )
            top_endpoints = dict(await cursor.fetchall())

            # Average duration
            cursor = await conn.execute(
                """
                SELECT AVG(duration_ms) FROM api_key_usage
                WHERE key_id = ? AND timestamp > ? AND duration_ms > 0
                """,
                (key_id, start_date),
            )
            avg_duration = (await cursor.fetchone())[0] or 0

            # Unique IPs
            cursor = await conn.execute(
                """
                SELECT COUNT(DISTINCT ip_address) FROM api_key_usage
                WHERE key_id = ? AND timestamp > ?
                """,
                (key_id, start_date),
            )
            unique_ips = (await cursor.fetchone())[0]

            # Daily breakdown
            cursor = await conn.execute(
                """
                SELECT DATE(timestamp) as day, COUNT(*) FROM api_key_usage
                WHERE key_id = ? AND timestamp > ?
                GROUP BY DATE(timestamp)
                ORDER BY day
                """,
                (key_id, start_date),
            )
            daily_usage = dict(await cursor.fetchall())

        return {
            "total_requests": total_requests,
            "status_counts": status_counts,
            "top_endpoints": top_endpoints,
            "avg_duration_ms": round(avg_duration, 2),
            "unique_ips": unique_ips,
            "daily_usage": daily_usage,
            "period_days": days,
        }

    async def get_global_stats(self) -> dict:
        """Get global API key statistics.

        Returns:
            Statistics dictionary
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            # Total keys
            cursor = await conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active,
                    SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) as revoked,
                    SUM(CASE WHEN expires_at IS NOT NULL
                        AND expires_at < datetime('now') THEN 1 ELSE 0 END) as expired
                FROM api_keys
                """
            )
            row = await cursor.fetchone()

            # Keys by scope (most common)
            cursor = await conn.execute(
                "SELECT scopes FROM api_keys WHERE is_active = 1"
            )
            rows = await cursor.fetchall()

            import json
            from collections import Counter

            scope_counter: Counter = Counter()
            for (scopes_json,) in rows:
                try:
                    scopes = json.loads(scopes_json)
                    scope_counter.update(scopes)
                except json.JSONDecodeError:
                    pass

            # Total usage (last 24h)
            yesterday = (datetime.now() - timedelta(days=1)).isoformat()
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM api_key_usage WHERE timestamp > ?",
                (yesterday,),
            )
            usage_24h = (await cursor.fetchone())[0]

        return {
            "total_keys": row[0] or 0,
            "active_keys": row[1] or 0,
            "revoked_keys": row[2] or 0,
            "expired_keys": row[3] or 0,
            "top_scopes": dict(scope_counter.most_common(10)),
            "usage_24h": usage_24h,
        }

    async def cleanup_expired_keys(
        self,
        delete: bool = False,
        older_than_days: int = 90,
    ) -> int:
        """Clean up expired or old revoked keys.

        Args:
            delete: Actually delete keys (False = just count)
            older_than_days: Clean keys expired more than this many days ago

        Returns:
            Number of keys cleaned up
        """
        await self._ensure_tables()

        cutoff_date = (datetime.now() - timedelta(days=older_than_days)).isoformat()

        async with self.db.get_connection() as conn:
            if delete:
                # Delete usage records for expired keys
                await conn.execute(
                    """
                    DELETE FROM api_key_usage WHERE key_id IN (
                        SELECT id FROM api_keys
                        WHERE (expires_at IS NOT NULL AND expires_at < ?)
                        OR (is_active = 0 AND created_at < ?)
                    )
                    """,
                    (cutoff_date, cutoff_date),
                )

                cursor = await conn.execute(
                    """
                    DELETE FROM api_keys
                    WHERE (expires_at IS NOT NULL AND expires_at < ?)
                    OR (is_active = 0 AND created_at < ?)
                    """,
                    (cutoff_date, cutoff_date),
                )
                await conn.commit()
                count = cursor.rowcount
            else:
                cursor = await conn.execute(
                    """
                    SELECT COUNT(*) FROM api_keys
                    WHERE (expires_at IS NOT NULL AND expires_at < ?)
                    OR (is_active = 0 AND created_at < ?)
                    """,
                    (cutoff_date, cutoff_date),
                )
                count = (await cursor.fetchone())[0]

        if delete:
            log.info("api_keys_cleaned_up", count=count)

        return count

    async def cleanup_old_usage_records(
        self,
        older_than_days: int = 30,
    ) -> int:
        """Clean up old usage records.

        Args:
            older_than_days: Delete records older than this

        Returns:
            Number of records deleted
        """
        await self._ensure_tables()

        cutoff_date = (datetime.now() - timedelta(days=older_than_days)).isoformat()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM api_key_usage WHERE timestamp < ?",
                (cutoff_date,),
            )
            await conn.commit()
            count = cursor.rowcount

        log.info("api_key_usage_cleaned_up", count=count)
        return count

    def _row_to_key(self, row) -> APIKey:
        """Convert a database row to an APIKey object."""
        import json

        scopes = []
        try:
            scopes_raw = json.loads(row[6])
            scopes = [APIKeyScope(s) for s in scopes_raw]
        except (json.JSONDecodeError, ValueError):
            pass

        metadata = {}
        try:
            metadata = json.loads(row[16]) if row[16] else {}
        except json.JSONDecodeError:
            pass

        return APIKey(
            id=row[0],
            user_id=row[1],
            name=row[2],
            key_hash=row[3],
            key_prefix=row[4],
            key_suffix=row[5],
            scopes=scopes,
            description=row[7] or "",
            created_at=(
                datetime.fromisoformat(row[8]) if row[8] else datetime.now()
            ),
            expires_at=datetime.fromisoformat(row[9]) if row[9] else None,
            last_used_at=datetime.fromisoformat(row[10]) if row[10] else None,
            last_used_ip=row[11],
            use_count=row[12] or 0,
            rate_limit=row[13] or 0,
            is_active=bool(row[14]),
            team_id=row[15],
            metadata=metadata,
        )


# Convenience functions for common operations


async def authenticate_api_key(
    key: str,
    required_scope: Optional[APIKeyScope] = None,
    ip_address: Optional[str] = None,
    database: Optional["Database"] = None,
) -> Optional[APIKey]:
    """Authenticate a request using an API key.

    Args:
        key: API key from request header
        required_scope: Scope required for this endpoint
        ip_address: Client IP address
        database: Optional database instance

    Returns:
        APIKey if authentication successful, None otherwise
    """
    store = APIKeyStore(database)
    return await store.verify_key(key, required_scope, ip_address)


async def create_api_key_for_user(
    user_id: str,
    name: str,
    scopes: list[APIKeyScope],
    description: str = "",
    expires_in_days: Optional[int] = None,
    database: Optional["Database"] = None,
) -> tuple[APIKey, str]:
    """Create an API key for a user.

    Args:
        user_id: User ID
        name: Key name
        scopes: Granted scopes
        description: Description
        expires_in_days: Expiration (None = never)
        database: Optional database instance

    Returns:
        Tuple of (APIKey, full_key_string)
    """
    store = APIKeyStore(database)
    return await store.create_key(
        user_id=user_id,
        name=name,
        scopes=scopes,
        description=description,
        expires_in_days=expires_in_days,
    )
