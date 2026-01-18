"""Tests for the API Keys System."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from sindri.collaboration.api_keys import (
    APIKey,
    APIKeyScope,
    APIKeyStore,
    APIKeyUsageRecord,
    generate_api_key_id,
    generate_api_key,
    hash_api_key,
    verify_api_key,
    expand_scopes,
    authenticate_api_key,
    create_api_key_for_user,
    KEY_PREFIX,
    KEY_PREFIX_TEST,
)
from sindri.persistence.database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_api_keys.db"
    database = Database(db_path)
    await database.initialize()
    yield database


@pytest_asyncio.fixture
async def store(db):
    """Create an APIKeyStore with a test database."""
    return APIKeyStore(database=db)


class TestKeyGeneration:
    """Tests for key generation utilities."""

    def test_generate_api_key_id_returns_string(self):
        """Test that generate_api_key_id returns a string."""
        key_id = generate_api_key_id()
        assert isinstance(key_id, str)
        assert len(key_id) == 32  # 16 bytes in hex

    def test_generate_api_key_id_is_unique(self):
        """Test that each generated ID is unique."""
        ids = [generate_api_key_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_generate_api_key_returns_tuple(self):
        """Test that generate_api_key returns correct tuple."""
        full_key, suffix = generate_api_key()
        assert isinstance(full_key, str)
        assert isinstance(suffix, str)
        assert full_key.startswith(KEY_PREFIX)
        assert len(suffix) == 8

    def test_generate_api_key_test_mode(self):
        """Test that test mode generates keys with test prefix."""
        full_key, suffix = generate_api_key(test_mode=True)
        assert full_key.startswith(KEY_PREFIX_TEST)

    def test_generate_api_key_is_unique(self):
        """Test that each generated key is unique."""
        keys = [generate_api_key()[0] for _ in range(100)]
        assert len(set(keys)) == 100


class TestKeyHashing:
    """Tests for key hashing and verification."""

    def test_hash_api_key_returns_string(self):
        """Test that hash returns a hex string."""
        key = "sk_test_12345"
        hashed = hash_api_key(key)
        assert isinstance(hashed, str)
        assert len(hashed) == 64  # SHA-256 hex

    def test_hash_api_key_is_deterministic(self):
        """Test that same key produces same hash."""
        key = "sk_test_12345"
        hash1 = hash_api_key(key)
        hash2 = hash_api_key(key)
        assert hash1 == hash2

    def test_hash_api_key_different_keys(self):
        """Test that different keys produce different hashes."""
        hash1 = hash_api_key("sk_test_12345")
        hash2 = hash_api_key("sk_test_67890")
        assert hash1 != hash2

    def test_verify_api_key_correct(self):
        """Test that correct key verifies."""
        key = "sk_test_12345"
        hashed = hash_api_key(key)
        assert verify_api_key(key, hashed) is True

    def test_verify_api_key_incorrect(self):
        """Test that incorrect key fails verification."""
        hashed = hash_api_key("sk_test_12345")
        assert verify_api_key("sk_test_wrong", hashed) is False


class TestScopeExpansion:
    """Tests for scope hierarchy expansion."""

    def test_expand_admin_scope(self):
        """Test that admin scope expands to all scopes."""
        expanded = expand_scopes([APIKeyScope.ADMIN])
        assert APIKeyScope.READ in expanded
        assert APIKeyScope.WRITE in expanded
        assert APIKeyScope.TEAM_READ in expanded
        assert APIKeyScope.TEAM_WRITE in expanded
        assert APIKeyScope.TEAM_ADMIN in expanded
        assert APIKeyScope.WEBHOOKS in expanded
        assert APIKeyScope.WEBHOOKS_MANAGE in expanded

    def test_expand_write_scope(self):
        """Test that write scope includes read."""
        expanded = expand_scopes([APIKeyScope.WRITE])
        assert APIKeyScope.READ in expanded
        assert APIKeyScope.READ_SESSIONS in expanded
        assert APIKeyScope.WRITE_SESSIONS in expanded

    def test_expand_read_scope(self):
        """Test that read scope includes specific read scopes."""
        expanded = expand_scopes([APIKeyScope.READ])
        assert APIKeyScope.READ_SESSIONS in expanded
        assert APIKeyScope.READ_AGENTS in expanded
        assert APIKeyScope.READ_METRICS in expanded

    def test_expand_team_admin(self):
        """Test that team admin includes team read/write."""
        expanded = expand_scopes([APIKeyScope.TEAM_ADMIN])
        assert APIKeyScope.TEAM_READ in expanded
        assert APIKeyScope.TEAM_WRITE in expanded

    def test_expand_multiple_scopes(self):
        """Test expanding multiple scopes."""
        expanded = expand_scopes([APIKeyScope.READ, APIKeyScope.WEBHOOKS])
        assert APIKeyScope.READ_SESSIONS in expanded
        assert APIKeyScope.WEBHOOKS in expanded
        assert APIKeyScope.WRITE not in expanded


class TestAPIKey:
    """Tests for the APIKey dataclass."""

    def test_create_api_key(self):
        """Test creating an API key."""
        key = APIKey(
            id="test-id",
            user_id="user123",
            name="Test Key",
            key_hash="abc123",
            key_prefix="sk_abcd",
            key_suffix="wxyz",
            scopes=[APIKeyScope.READ, APIKeyScope.WRITE],
        )
        assert key.id == "test-id"
        assert key.user_id == "user123"
        assert key.name == "Test Key"
        assert APIKeyScope.READ in key.scopes
        assert APIKeyScope.WRITE in key.scopes

    def test_api_key_to_dict(self):
        """Test converting API key to dictionary."""
        now = datetime.now()
        expires = now + timedelta(days=30)
        key = APIKey(
            id="test-id",
            user_id="user123",
            name="Test Key",
            key_hash="abc123",
            key_prefix="sk_abcd",
            key_suffix="wxyz",
            scopes=[APIKeyScope.READ],
            description="Test description",
            created_at=now,
            expires_at=expires,
            rate_limit=100,
            team_id="team456",
        )

        data = key.to_dict()
        assert data["id"] == "test-id"
        assert data["user_id"] == "user123"
        assert data["name"] == "Test Key"
        assert data["key_prefix"] == "sk_abcd"
        assert data["key_suffix"] == "wxyz"
        assert data["scopes"] == ["read"]
        assert data["description"] == "Test description"
        assert data["created_at"] == now.isoformat()
        assert data["expires_at"] == expires.isoformat()
        assert data["rate_limit"] == 100
        assert data["team_id"] == "team456"
        # key_hash should NOT be in public dict
        assert "key_hash" not in data

    def test_api_key_is_expired(self):
        """Test expiration check."""
        # Not expired
        key = APIKey(
            id="1",
            user_id="user1",
            name="Key",
            key_hash="hash",
            key_prefix="sk_",
            key_suffix="1234",
            scopes=[],
            expires_at=datetime.now() + timedelta(days=1),
        )
        assert key.is_expired is False

        # Expired
        key = APIKey(
            id="2",
            user_id="user1",
            name="Key",
            key_hash="hash",
            key_prefix="sk_",
            key_suffix="1234",
            scopes=[],
            expires_at=datetime.now() - timedelta(days=1),
        )
        assert key.is_expired is True

        # No expiration
        key = APIKey(
            id="3",
            user_id="user1",
            name="Key",
            key_hash="hash",
            key_prefix="sk_",
            key_suffix="1234",
            scopes=[],
            expires_at=None,
        )
        assert key.is_expired is False

    def test_api_key_is_valid(self):
        """Test validity check."""
        # Active and not expired
        key = APIKey(
            id="1",
            user_id="user1",
            name="Key",
            key_hash="hash",
            key_prefix="sk_",
            key_suffix="1234",
            scopes=[],
            is_active=True,
            expires_at=datetime.now() + timedelta(days=1),
        )
        assert key.is_valid is True

        # Inactive
        key = APIKey(
            id="2",
            user_id="user1",
            name="Key",
            key_hash="hash",
            key_prefix="sk_",
            key_suffix="1234",
            scopes=[],
            is_active=False,
        )
        assert key.is_valid is False

        # Expired
        key = APIKey(
            id="3",
            user_id="user1",
            name="Key",
            key_hash="hash",
            key_prefix="sk_",
            key_suffix="1234",
            scopes=[],
            is_active=True,
            expires_at=datetime.now() - timedelta(days=1),
        )
        assert key.is_valid is False

    def test_api_key_display_key(self):
        """Test display key generation."""
        key = APIKey(
            id="1",
            user_id="user1",
            name="Key",
            key_hash="hash",
            key_prefix="sk_abcd",
            key_suffix="wxyz",
            scopes=[],
        )
        assert key.display_key == "sk_abcd...wxyz"

    def test_api_key_has_scope(self):
        """Test scope checking."""
        key = APIKey(
            id="1",
            user_id="user1",
            name="Key",
            key_hash="hash",
            key_prefix="sk_",
            key_suffix="1234",
            scopes=[APIKeyScope.WRITE],
        )

        # Direct scope
        assert key.has_scope(APIKeyScope.WRITE) is True

        # Implied scope (write implies read)
        assert key.has_scope(APIKeyScope.READ) is True
        assert key.has_scope(APIKeyScope.READ_SESSIONS) is True

        # Not granted
        assert key.has_scope(APIKeyScope.ADMIN) is False
        assert key.has_scope(APIKeyScope.TEAM_ADMIN) is False

    def test_api_key_has_any_scope(self):
        """Test checking for any of multiple scopes."""
        key = APIKey(
            id="1",
            user_id="user1",
            name="Key",
            key_hash="hash",
            key_prefix="sk_",
            key_suffix="1234",
            scopes=[APIKeyScope.READ],
        )

        # Has one of the scopes
        assert key.has_any_scope([APIKeyScope.READ, APIKeyScope.ADMIN]) is True

        # Has none of the scopes
        assert key.has_any_scope([APIKeyScope.ADMIN, APIKeyScope.TEAM_ADMIN]) is False


class TestAPIKeyUsageRecord:
    """Tests for the APIKeyUsageRecord dataclass."""

    def test_create_usage_record(self):
        """Test creating a usage record."""
        now = datetime.now()
        record = APIKeyUsageRecord(
            id="rec-1",
            key_id="key-1",
            timestamp=now,
            ip_address="192.168.1.1",
            endpoint="/api/sessions",
            method="GET",
            status_code=200,
            user_agent="test-agent",
            duration_ms=50,
        )
        assert record.id == "rec-1"
        assert record.key_id == "key-1"
        assert record.ip_address == "192.168.1.1"
        assert record.endpoint == "/api/sessions"
        assert record.status_code == 200

    def test_usage_record_to_dict(self):
        """Test converting usage record to dictionary."""
        now = datetime.now()
        record = APIKeyUsageRecord(
            id="rec-1",
            key_id="key-1",
            timestamp=now,
            ip_address="192.168.1.1",
            endpoint="/api/sessions",
        )

        data = record.to_dict()
        assert data["id"] == "rec-1"
        assert data["key_id"] == "key-1"
        assert data["timestamp"] == now.isoformat()
        assert data["ip_address"] == "192.168.1.1"
        assert data["endpoint"] == "/api/sessions"


class TestAPIKeyStore:
    """Tests for the APIKeyStore class."""

    @pytest.mark.asyncio
    async def test_create_key(self, store):
        """Test creating an API key."""
        api_key, full_key = await store.create_key(
            user_id="user123",
            name="My Test Key",
            scopes=[APIKeyScope.READ, APIKeyScope.WRITE],
            description="Test key for CI/CD",
        )

        assert api_key.id is not None
        assert api_key.user_id == "user123"
        assert api_key.name == "My Test Key"
        assert APIKeyScope.READ in api_key.scopes
        assert APIKeyScope.WRITE in api_key.scopes
        assert api_key.description == "Test key for CI/CD"
        assert api_key.is_active is True
        assert full_key.startswith(KEY_PREFIX)

    @pytest.mark.asyncio
    async def test_create_key_with_expiration(self, store):
        """Test creating a key with expiration."""
        api_key, _ = await store.create_key(
            user_id="user123",
            name="Expiring Key",
            scopes=[APIKeyScope.READ],
            expires_in_days=30,
        )

        assert api_key.expires_at is not None
        # Should expire in approximately 30 days
        delta = api_key.expires_at - datetime.now()
        assert 29 <= delta.days <= 30

    @pytest.mark.asyncio
    async def test_create_key_with_rate_limit(self, store):
        """Test creating a key with rate limit."""
        api_key, _ = await store.create_key(
            user_id="user123",
            name="Rate Limited Key",
            scopes=[APIKeyScope.READ],
            rate_limit=100,
        )

        assert api_key.rate_limit == 100

    @pytest.mark.asyncio
    async def test_create_test_key(self, store):
        """Test creating a test/sandbox key."""
        api_key, full_key = await store.create_key(
            user_id="user123",
            name="Test Key",
            scopes=[APIKeyScope.READ],
            test_mode=True,
        )

        assert full_key.startswith(KEY_PREFIX_TEST)

    @pytest.mark.asyncio
    async def test_verify_key_valid(self, store):
        """Test verifying a valid key."""
        api_key, full_key = await store.create_key(
            user_id="user123",
            name="Verify Test",
            scopes=[APIKeyScope.READ],
        )

        verified = await store.verify_key(full_key)
        assert verified is not None
        assert verified.id == api_key.id

    @pytest.mark.asyncio
    async def test_verify_key_invalid(self, store):
        """Test verifying an invalid key."""
        verified = await store.verify_key("sk_invalid_key_12345")
        assert verified is None

    @pytest.mark.asyncio
    async def test_verify_key_with_scope(self, store):
        """Test verifying key with required scope."""
        _, full_key = await store.create_key(
            user_id="user123",
            name="Scoped Key",
            scopes=[APIKeyScope.READ],
        )

        # Has the scope
        verified = await store.verify_key(full_key, required_scope=APIKeyScope.READ)
        assert verified is not None

        # Missing scope
        verified = await store.verify_key(full_key, required_scope=APIKeyScope.ADMIN)
        assert verified is None

    @pytest.mark.asyncio
    async def test_verify_key_inactive(self, store):
        """Test verifying a revoked key."""
        api_key, full_key = await store.create_key(
            user_id="user123",
            name="Revoke Test",
            scopes=[APIKeyScope.READ],
        )

        # Revoke the key
        await store.revoke_key(api_key.id)

        # Verification should fail
        verified = await store.verify_key(full_key)
        assert verified is None

    @pytest.mark.asyncio
    async def test_verify_key_expired(self, store):
        """Test verifying an expired key."""
        api_key, full_key = await store.create_key(
            user_id="user123",
            name="Expired Key",
            scopes=[APIKeyScope.READ],
            expires_in_days=0,  # Expires immediately (same day)
        )

        # Manually set expiration to past
        async with store.db.get_connection() as conn:
            past = (datetime.now() - timedelta(days=1)).isoformat()
            await conn.execute(
                "UPDATE api_keys SET expires_at = ? WHERE id = ?",
                (past, api_key.id),
            )
            await conn.commit()

        # Verification should fail
        verified = await store.verify_key(full_key)
        assert verified is None

    @pytest.mark.asyncio
    async def test_get_key(self, store):
        """Test getting a key by ID."""
        created, _ = await store.create_key(
            user_id="user123",
            name="Get Test",
            scopes=[APIKeyScope.READ],
        )

        key = await store.get_key(created.id)
        assert key is not None
        assert key.id == created.id
        assert key.name == "Get Test"

    @pytest.mark.asyncio
    async def test_get_key_not_found(self, store):
        """Test getting a non-existent key."""
        key = await store.get_key("nonexistent-id")
        assert key is None

    @pytest.mark.asyncio
    async def test_list_keys(self, store):
        """Test listing keys."""
        # Create several keys
        await store.create_key("user1", "Key 1", [APIKeyScope.READ])
        await store.create_key("user1", "Key 2", [APIKeyScope.WRITE])
        await store.create_key("user2", "Key 3", [APIKeyScope.ADMIN])

        # List all
        keys = await store.list_keys()
        assert len(keys) == 3

        # List by user
        keys = await store.list_keys(user_id="user1")
        assert len(keys) == 2

        keys = await store.list_keys(user_id="user2")
        assert len(keys) == 1

    @pytest.mark.asyncio
    async def test_list_keys_with_team(self, store):
        """Test listing keys by team."""
        await store.create_key("user1", "Key 1", [APIKeyScope.READ], team_id="team1")
        await store.create_key("user1", "Key 2", [APIKeyScope.READ], team_id="team2")
        await store.create_key("user2", "Key 3", [APIKeyScope.READ], team_id="team1")

        keys = await store.list_keys(team_id="team1")
        assert len(keys) == 2

    @pytest.mark.asyncio
    async def test_list_keys_include_inactive(self, store):
        """Test listing keys including inactive ones."""
        key1, _ = await store.create_key("user1", "Active", [APIKeyScope.READ])
        key2, _ = await store.create_key("user1", "Inactive", [APIKeyScope.READ])

        await store.revoke_key(key2.id)

        # Without inactive
        keys = await store.list_keys(user_id="user1")
        assert len(keys) == 1

        # With inactive
        keys = await store.list_keys(user_id="user1", include_inactive=True)
        assert len(keys) == 2

    @pytest.mark.asyncio
    async def test_update_key(self, store):
        """Test updating a key."""
        key, _ = await store.create_key(
            user_id="user123",
            name="Original Name",
            scopes=[APIKeyScope.READ],
            description="Original description",
        )

        updated = await store.update_key(
            key.id,
            name="New Name",
            description="New description",
            rate_limit=50,
        )

        assert updated is not None
        assert updated.name == "New Name"
        assert updated.description == "New description"
        assert updated.rate_limit == 50

    @pytest.mark.asyncio
    async def test_update_key_scopes(self, store):
        """Test updating key scopes."""
        key, _ = await store.create_key(
            user_id="user123",
            name="Scope Test",
            scopes=[APIKeyScope.READ],
        )

        updated = await store.update_key(
            key.id,
            scopes=[APIKeyScope.READ, APIKeyScope.WRITE],
        )

        assert APIKeyScope.READ in updated.scopes
        assert APIKeyScope.WRITE in updated.scopes

    @pytest.mark.asyncio
    async def test_revoke_key(self, store):
        """Test revoking a key."""
        key, _ = await store.create_key(
            user_id="user123",
            name="Revoke Test",
            scopes=[APIKeyScope.READ],
        )

        success = await store.revoke_key(key.id)
        assert success is True

        # Check it's inactive
        updated = await store.get_key(key.id)
        assert updated.is_active is False

    @pytest.mark.asyncio
    async def test_revoke_key_not_found(self, store):
        """Test revoking a non-existent key."""
        success = await store.revoke_key("nonexistent-id")
        assert success is False

    @pytest.mark.asyncio
    async def test_delete_key(self, store):
        """Test permanently deleting a key."""
        key, _ = await store.create_key(
            user_id="user123",
            name="Delete Test",
            scopes=[APIKeyScope.READ],
        )

        success = await store.delete_key(key.id)
        assert success is True

        # Should not exist
        deleted = await store.get_key(key.id)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_delete_key_not_found(self, store):
        """Test deleting a non-existent key."""
        success = await store.delete_key("nonexistent-id")
        assert success is False

    @pytest.mark.asyncio
    async def test_record_usage(self, store):
        """Test recording API key usage."""
        key, _ = await store.create_key(
            user_id="user123",
            name="Usage Test",
            scopes=[APIKeyScope.READ],
        )

        await store.record_usage(
            key_id=key.id,
            ip_address="192.168.1.1",
            endpoint="/api/sessions",
            method="GET",
            status_code=200,
            duration_ms=50,
        )

        # Verify usage was recorded
        stats = await store.get_usage_stats(key.id, days=1)
        assert stats["total_requests"] == 1

    @pytest.mark.asyncio
    async def test_get_usage_stats(self, store):
        """Test getting usage statistics."""
        key, _ = await store.create_key(
            user_id="user123",
            name="Stats Test",
            scopes=[APIKeyScope.READ],
        )

        # Record multiple usages
        for i in range(5):
            await store.record_usage(
                key_id=key.id,
                ip_address=f"192.168.1.{i + 1}",
                endpoint="/api/sessions",
                method="GET",
                status_code=200,
                duration_ms=50 + i * 10,
            )

        stats = await store.get_usage_stats(key.id, days=7)

        assert stats["total_requests"] == 5
        assert stats["unique_ips"] == 5
        assert stats["avg_duration_ms"] > 0
        assert stats["period_days"] == 7

    @pytest.mark.asyncio
    async def test_get_global_stats(self, store):
        """Test getting global statistics."""
        # Create some keys
        key1, _ = await store.create_key("user1", "Key 1", [APIKeyScope.READ])
        key2, _ = await store.create_key("user1", "Key 2", [APIKeyScope.WRITE])
        key3, _ = await store.create_key("user2", "Key 3", [APIKeyScope.ADMIN])

        # Revoke one
        await store.revoke_key(key2.id)

        stats = await store.get_global_stats()

        assert stats["total_keys"] == 3
        assert stats["active_keys"] == 2
        assert stats["revoked_keys"] == 1

    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self, store):
        """Test that rate limiting is enforced."""
        api_key, full_key = await store.create_key(
            user_id="user123",
            name="Rate Limit Test",
            scopes=[APIKeyScope.READ],
            rate_limit=3,  # 3 requests per minute
        )

        # First 3 requests should succeed
        for _ in range(3):
            verified = await store.verify_key(full_key)
            assert verified is not None

        # 4th request should fail (rate limited)
        verified = await store.verify_key(full_key)
        assert verified is None

    @pytest.mark.asyncio
    async def test_cleanup_expired_keys(self, store):
        """Test cleaning up expired keys."""
        # Create an old expired key
        key1, _ = await store.create_key(
            user_id="user123",
            name="Old Expired",
            scopes=[APIKeyScope.READ],
        )

        # Manually set expiration to past
        async with store.db.get_connection() as conn:
            past = (datetime.now() - timedelta(days=100)).isoformat()
            await conn.execute(
                "UPDATE api_keys SET expires_at = ? WHERE id = ?",
                (past, key1.id),
            )
            await conn.commit()

        # Create a recent key
        await store.create_key("user123", "Recent", [APIKeyScope.READ])

        # Dry run
        count = await store.cleanup_expired_keys(delete=False, older_than_days=90)
        assert count == 1

        # Actually delete
        count = await store.cleanup_expired_keys(delete=True, older_than_days=90)
        assert count == 1

        # Should only have 1 key now
        keys = await store.list_keys(include_inactive=True)
        assert len(keys) == 1

    @pytest.mark.asyncio
    async def test_cleanup_old_usage_records(self, store):
        """Test cleaning up old usage records."""
        key, _ = await store.create_key(
            user_id="user123",
            name="Cleanup Test",
            scopes=[APIKeyScope.READ],
        )

        # Record usage
        await store.record_usage(
            key_id=key.id,
            ip_address="192.168.1.1",
            endpoint="/api/test",
        )

        # Manually set timestamp to old
        async with store.db.get_connection() as conn:
            past = (datetime.now() - timedelta(days=100)).isoformat()
            await conn.execute(
                "UPDATE api_key_usage SET timestamp = ? WHERE key_id = ?",
                (past, key.id),
            )
            await conn.commit()

        # Record a recent usage
        await store.record_usage(
            key_id=key.id,
            ip_address="192.168.1.2",
            endpoint="/api/test",
        )

        # Cleanup
        count = await store.cleanup_old_usage_records(older_than_days=30)
        assert count == 1


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.mark.asyncio
    async def test_authenticate_api_key(self, db):
        """Test the authenticate_api_key convenience function."""
        store = APIKeyStore(database=db)
        api_key, full_key = await store.create_key(
            user_id="user123",
            name="Auth Test",
            scopes=[APIKeyScope.READ],
        )

        # Valid key
        result = await authenticate_api_key(full_key, database=db)
        assert result is not None
        assert result.id == api_key.id

        # Invalid key
        result = await authenticate_api_key("sk_invalid", database=db)
        assert result is None

    @pytest.mark.asyncio
    async def test_create_api_key_for_user(self, db):
        """Test the create_api_key_for_user convenience function."""
        api_key, full_key = await create_api_key_for_user(
            user_id="user123",
            name="Convenience Test",
            scopes=[APIKeyScope.READ, APIKeyScope.WRITE],
            description="Created via convenience function",
            database=db,
        )

        assert api_key is not None
        assert api_key.name == "Convenience Test"
        assert APIKeyScope.READ in api_key.scopes
        assert full_key.startswith(KEY_PREFIX)


class TestAPIKeyScopeEnum:
    """Tests for the APIKeyScope enum."""

    def test_all_scopes_have_values(self):
        """Test that all scopes have string values."""
        for scope in APIKeyScope:
            assert isinstance(scope.value, str)
            assert len(scope.value) > 0

    def test_scope_from_string(self):
        """Test creating scope from string value."""
        scope = APIKeyScope("read")
        assert scope == APIKeyScope.READ

        scope = APIKeyScope("admin")
        assert scope == APIKeyScope.ADMIN

    def test_invalid_scope_raises(self):
        """Test that invalid scope raises ValueError."""
        with pytest.raises(ValueError):
            APIKeyScope("invalid_scope")


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_update_nonexistent_key(self, store):
        """Test updating a non-existent key returns None."""
        result = await store.update_key("nonexistent", name="New Name")
        assert result is None

    @pytest.mark.asyncio
    async def test_verify_empty_key(self, store):
        """Test verifying an empty key."""
        result = await store.verify_key("")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_key_with_empty_scopes(self, store):
        """Test creating a key with no scopes."""
        api_key, full_key = await store.create_key(
            user_id="user123",
            name="No Scopes",
            scopes=[],
        )

        assert api_key is not None
        assert len(api_key.scopes) == 0

        # Key with no scopes should verify but fail scope checks
        verified = await store.verify_key(full_key)
        assert verified is not None

        verified = await store.verify_key(full_key, required_scope=APIKeyScope.READ)
        assert verified is None

    @pytest.mark.asyncio
    async def test_verify_updates_usage(self, store):
        """Test that verification updates usage statistics."""
        api_key, full_key = await store.create_key(
            user_id="user123",
            name="Usage Update Test",
            scopes=[APIKeyScope.READ],
        )

        # Initial state
        key = await store.get_key(api_key.id)
        assert key.last_used_at is None
        assert key.use_count == 0

        # Verify with IP
        await store.verify_key(full_key, ip_address="192.168.1.1")

        # Check updated
        key = await store.get_key(api_key.id)
        assert key.last_used_at is not None
        assert key.use_count == 1
        assert key.last_used_ip == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_key_with_metadata(self, store):
        """Test creating and retrieving key with metadata."""
        metadata = {"environment": "production", "service": "api-gateway"}

        api_key, _ = await store.create_key(
            user_id="user123",
            name="Metadata Test",
            scopes=[APIKeyScope.READ],
            metadata=metadata,
        )

        retrieved = await store.get_key(api_key.id)
        assert retrieved.metadata == metadata

    @pytest.mark.asyncio
    async def test_list_keys_pagination(self, store):
        """Test listing keys with pagination."""
        # Create 10 keys
        for i in range(10):
            await store.create_key(
                user_id="user123",
                name=f"Key {i}",
                scopes=[APIKeyScope.READ],
            )

        # Get first page
        page1 = await store.list_keys(limit=3, offset=0)
        assert len(page1) == 3

        # Get second page
        page2 = await store.list_keys(limit=3, offset=3)
        assert len(page2) == 3

        # Pages should be different
        page1_ids = {k.id for k in page1}
        page2_ids = {k.id for k in page2}
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_get_usage_stats_empty(self, store):
        """Test getting stats for key with no usage."""
        api_key, _ = await store.create_key(
            user_id="user123",
            name="No Usage",
            scopes=[APIKeyScope.READ],
        )

        stats = await store.get_usage_stats(api_key.id)

        assert stats["total_requests"] == 0
        assert stats["unique_ips"] == 0
        assert stats["avg_duration_ms"] == 0
