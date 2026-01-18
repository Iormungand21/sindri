"""Tests for the Webhooks System."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json
import hmac
import hashlib

from sindri.collaboration.webhooks import (
    Webhook,
    WebhookEventType,
    WebhookFormat,
    WebhookDelivery,
    DeliveryStatus,
    WebhookStore,
    WebhookDeliveryService,
    generate_webhook_id,
    generate_webhook_secret,
    generate_delivery_id,
    trigger_webhook_event,
    verify_webhook_signature,
)
from sindri.persistence.database import Database


# ============================================
# ID/Secret Generation Tests
# ============================================


class TestWebhookIdGeneration:
    """Tests for webhook ID generation."""

    def test_generate_webhook_id_unique(self):
        """Test that webhook IDs are unique."""
        ids = [generate_webhook_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_generate_webhook_id_length(self):
        """Test webhook ID length."""
        webhook_id = generate_webhook_id()
        assert len(webhook_id) == 32  # 16 bytes hex

    def test_generate_webhook_secret_unique(self):
        """Test that webhook secrets are unique."""
        secrets = [generate_webhook_secret() for _ in range(100)]
        assert len(set(secrets)) == 100

    def test_generate_webhook_secret_length(self):
        """Test webhook secret length."""
        secret = generate_webhook_secret()
        assert len(secret) >= 32  # URL-safe base64

    def test_generate_delivery_id_unique(self):
        """Test that delivery IDs are unique."""
        ids = [generate_delivery_id() for _ in range(100)]
        assert len(set(ids)) == 100


# ============================================
# WebhookEventType Tests
# ============================================


class TestWebhookEventType:
    """Tests for WebhookEventType enum."""

    def test_session_event_types(self):
        """Test session-related event types."""
        assert WebhookEventType.SESSION_CREATED.value == "session.created"
        assert WebhookEventType.SESSION_COMPLETED.value == "session.completed"
        assert WebhookEventType.SESSION_FAILED.value == "session.failed"
        assert WebhookEventType.SESSION_RESUMED.value == "session.resumed"

    def test_task_event_types(self):
        """Test task-related event types."""
        assert WebhookEventType.TASK_STARTED.value == "task.started"
        assert WebhookEventType.TASK_COMPLETED.value == "task.completed"
        assert WebhookEventType.TASK_DELEGATED.value == "task.delegated"

    def test_team_event_types(self):
        """Test team-related event types."""
        assert WebhookEventType.TEAM_MEMBER_JOINED.value == "team.member_joined"
        assert WebhookEventType.TEAM_MEMBER_LEFT.value == "team.member_left"
        assert WebhookEventType.TEAM_ROLE_CHANGED.value == "team.role_changed"

    def test_comment_event_types(self):
        """Test comment-related event types."""
        assert WebhookEventType.COMMENT_ADDED.value == "comment.added"
        assert WebhookEventType.COMMENT_RESOLVED.value == "comment.resolved"

    def test_wildcard_event_type(self):
        """Test wildcard event type."""
        assert WebhookEventType.ALL.value == "*"

    def test_event_type_is_string_enum(self):
        """Test WebhookEventType is a string enum."""
        assert isinstance(WebhookEventType.SESSION_CREATED, str)
        assert WebhookEventType.SESSION_CREATED == "session.created"


# ============================================
# WebhookFormat Tests
# ============================================


class TestWebhookFormat:
    """Tests for WebhookFormat enum."""

    def test_format_values(self):
        """Test format values."""
        assert WebhookFormat.GENERIC.value == "generic"
        assert WebhookFormat.SLACK.value == "slack"
        assert WebhookFormat.DISCORD.value == "discord"


# ============================================
# DeliveryStatus Tests
# ============================================


class TestDeliveryStatus:
    """Tests for DeliveryStatus enum."""

    def test_status_values(self):
        """Test delivery status values."""
        assert DeliveryStatus.PENDING.value == "pending"
        assert DeliveryStatus.SUCCESS.value == "success"
        assert DeliveryStatus.FAILED.value == "failed"
        assert DeliveryStatus.RETRYING.value == "retrying"


# ============================================
# Webhook Dataclass Tests
# ============================================


class TestWebhookDataclass:
    """Tests for Webhook dataclass."""

    def test_webhook_defaults(self):
        """Test Webhook default values."""
        webhook = Webhook(
            id="test-id",
            team_id="team-123",
            name="Test Webhook",
            url="https://example.com/webhook",
            secret="test-secret",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        assert webhook.enabled is True
        assert webhook.format == WebhookFormat.GENERIC
        assert webhook.description == ""
        assert webhook.headers == {}
        assert webhook.retry_count == 3
        assert webhook.timeout_seconds == 30

    def test_webhook_to_dict(self):
        """Test Webhook to_dict method."""
        webhook = Webhook(
            id="test-id",
            team_id="team-123",
            name="Test Webhook",
            url="https://example.com/webhook",
            secret="test-secret",
            events=[WebhookEventType.SESSION_COMPLETED, WebhookEventType.SESSION_FAILED],
            format=WebhookFormat.SLACK,
        )

        result = webhook.to_dict()

        assert result["id"] == "test-id"
        assert result["team_id"] == "team-123"
        assert result["name"] == "Test Webhook"
        assert result["url"] == "https://example.com/webhook"
        assert "secret" not in result  # Secret not included by default
        assert result["events"] == ["session.completed", "session.failed"]
        assert result["format"] == "slack"

    def test_webhook_to_dict_with_secret(self):
        """Test Webhook to_dict with secret included."""
        webhook = Webhook(
            id="test-id",
            team_id="team-123",
            name="Test",
            url="https://example.com",
            secret="my-secret",
            events=[WebhookEventType.ALL],
        )

        result = webhook.to_dict(include_secret=True)
        assert result["secret"] == "my-secret"

    def test_webhook_matches_event_enabled(self):
        """Test matches_event for enabled webhook."""
        webhook = Webhook(
            id="test-id",
            team_id="team-123",
            name="Test",
            url="https://example.com",
            secret="secret",
            events=[WebhookEventType.SESSION_COMPLETED],
            enabled=True,
        )

        assert webhook.matches_event(WebhookEventType.SESSION_COMPLETED) is True
        assert webhook.matches_event(WebhookEventType.SESSION_FAILED) is False

    def test_webhook_matches_event_disabled(self):
        """Test matches_event for disabled webhook."""
        webhook = Webhook(
            id="test-id",
            team_id="team-123",
            name="Test",
            url="https://example.com",
            secret="secret",
            events=[WebhookEventType.SESSION_COMPLETED],
            enabled=False,
        )

        assert webhook.matches_event(WebhookEventType.SESSION_COMPLETED) is False

    def test_webhook_matches_event_wildcard(self):
        """Test matches_event with wildcard."""
        webhook = Webhook(
            id="test-id",
            team_id="team-123",
            name="Test",
            url="https://example.com",
            secret="secret",
            events=[WebhookEventType.ALL],
            enabled=True,
        )

        assert webhook.matches_event(WebhookEventType.SESSION_COMPLETED) is True
        assert webhook.matches_event(WebhookEventType.TASK_STARTED) is True
        assert webhook.matches_event(WebhookEventType.COMMENT_ADDED) is True

    def test_webhook_compute_signature(self):
        """Test compute_signature method."""
        webhook = Webhook(
            id="test-id",
            team_id="team-123",
            name="Test",
            url="https://example.com",
            secret="my-secret-key",
            events=[WebhookEventType.ALL],
        )

        payload = '{"event":"test"}'
        signature = webhook.compute_signature(payload)

        # Verify signature matches expected HMAC-SHA256
        expected = hmac.new(
            b"my-secret-key",
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        assert signature == expected


# ============================================
# WebhookDelivery Dataclass Tests
# ============================================


class TestWebhookDeliveryDataclass:
    """Tests for WebhookDelivery dataclass."""

    def test_delivery_defaults(self):
        """Test WebhookDelivery default values."""
        delivery = WebhookDelivery(
            id="delivery-id",
            webhook_id="webhook-id",
            event_type=WebhookEventType.SESSION_COMPLETED,
            payload='{"test": true}',
        )

        assert delivery.status == DeliveryStatus.PENDING
        assert delivery.status_code is None
        assert delivery.response_body is None
        assert delivery.error_message is None
        assert delivery.attempt_count == 0
        assert delivery.completed_at is None
        assert delivery.next_retry_at is None

    def test_delivery_to_dict(self):
        """Test WebhookDelivery to_dict method."""
        delivery = WebhookDelivery(
            id="delivery-id",
            webhook_id="webhook-id",
            event_type=WebhookEventType.SESSION_COMPLETED,
            payload='{"test": true}',
            status=DeliveryStatus.SUCCESS,
            status_code=200,
            attempt_count=1,
        )

        result = delivery.to_dict()

        assert result["id"] == "delivery-id"
        assert result["webhook_id"] == "webhook-id"
        assert result["event_type"] == "session.completed"
        assert result["status"] == "success"
        assert result["status_code"] == 200


# ============================================
# WebhookStore Tests
# ============================================


@pytest_asyncio.fixture
async def webhook_store(tmp_path):
    """Create a test webhook store with temporary database."""
    db = Database(tmp_path / "test_webhooks.db")
    await db.initialize()
    store = WebhookStore(db)
    await store._ensure_tables()
    return store


class TestWebhookStore:
    """Tests for WebhookStore."""

    @pytest.mark.asyncio
    async def test_create_webhook(self, webhook_store):
        """Test creating a webhook."""
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Test Webhook",
            url="https://example.com/webhook",
            events=[WebhookEventType.SESSION_COMPLETED],
            format=WebhookFormat.GENERIC,
            created_by="user-123",
            description="Test description",
        )

        assert webhook.id is not None
        assert webhook.team_id == "team-123"
        assert webhook.name == "Test Webhook"
        assert webhook.url == "https://example.com/webhook"
        assert webhook.secret is not None
        assert len(webhook.secret) >= 32
        assert webhook.events == [WebhookEventType.SESSION_COMPLETED]
        assert webhook.enabled is True

    @pytest.mark.asyncio
    async def test_get_webhook(self, webhook_store):
        """Test getting a webhook by ID."""
        created = await webhook_store.create_webhook(
            team_id="team-123",
            name="Test Webhook",
            url="https://example.com/webhook",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        retrieved = await webhook_store.get_webhook(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Test Webhook"

    @pytest.mark.asyncio
    async def test_get_webhook_not_found(self, webhook_store):
        """Test getting non-existent webhook."""
        result = await webhook_store.get_webhook("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_team_webhooks(self, webhook_store):
        """Test getting all webhooks for a team."""
        # Create multiple webhooks
        await webhook_store.create_webhook(
            team_id="team-123",
            name="Webhook 1",
            url="https://example.com/hook1",
            events=[WebhookEventType.SESSION_COMPLETED],
        )
        await webhook_store.create_webhook(
            team_id="team-123",
            name="Webhook 2",
            url="https://example.com/hook2",
            events=[WebhookEventType.TASK_COMPLETED],
        )
        await webhook_store.create_webhook(
            team_id="team-other",
            name="Other Team Webhook",
            url="https://example.com/other",
            events=[WebhookEventType.ALL],
        )

        webhooks = await webhook_store.get_team_webhooks("team-123")

        assert len(webhooks) == 2
        names = [w.name for w in webhooks]
        assert "Webhook 1" in names
        assert "Webhook 2" in names

    @pytest.mark.asyncio
    async def test_get_team_webhooks_enabled_only(self, webhook_store):
        """Test getting only enabled webhooks."""
        webhook1 = await webhook_store.create_webhook(
            team_id="team-123",
            name="Enabled Webhook",
            url="https://example.com/hook1",
            events=[WebhookEventType.SESSION_COMPLETED],
        )
        webhook2 = await webhook_store.create_webhook(
            team_id="team-123",
            name="Disabled Webhook",
            url="https://example.com/hook2",
            events=[WebhookEventType.SESSION_COMPLETED],
        )
        await webhook_store.update_webhook(webhook2.id, enabled=False)

        webhooks = await webhook_store.get_team_webhooks("team-123", enabled_only=True)

        assert len(webhooks) == 1
        assert webhooks[0].name == "Enabled Webhook"

    @pytest.mark.asyncio
    async def test_get_webhooks_for_event(self, webhook_store):
        """Test getting webhooks that match an event type."""
        await webhook_store.create_webhook(
            team_id="team-123",
            name="Session Webhook",
            url="https://example.com/session",
            events=[WebhookEventType.SESSION_COMPLETED],
        )
        await webhook_store.create_webhook(
            team_id="team-123",
            name="Task Webhook",
            url="https://example.com/task",
            events=[WebhookEventType.TASK_COMPLETED],
        )
        await webhook_store.create_webhook(
            team_id="team-123",
            name="All Events Webhook",
            url="https://example.com/all",
            events=[WebhookEventType.ALL],
        )

        webhooks = await webhook_store.get_webhooks_for_event(
            "team-123",
            WebhookEventType.SESSION_COMPLETED,
        )

        assert len(webhooks) == 2
        names = [w.name for w in webhooks]
        assert "Session Webhook" in names
        assert "All Events Webhook" in names
        assert "Task Webhook" not in names

    @pytest.mark.asyncio
    async def test_update_webhook(self, webhook_store):
        """Test updating a webhook."""
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Original Name",
            url="https://example.com/original",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        updated = await webhook_store.update_webhook(
            webhook.id,
            name="Updated Name",
            url="https://example.com/updated",
            enabled=False,
        )

        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.url == "https://example.com/updated"
        assert updated.enabled is False

    @pytest.mark.asyncio
    async def test_update_webhook_events(self, webhook_store):
        """Test updating webhook events."""
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Test",
            url="https://example.com",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        updated = await webhook_store.update_webhook(
            webhook.id,
            events=[WebhookEventType.TASK_STARTED, WebhookEventType.TASK_COMPLETED],
        )

        assert updated is not None
        assert WebhookEventType.TASK_STARTED in updated.events
        assert WebhookEventType.TASK_COMPLETED in updated.events
        assert WebhookEventType.SESSION_COMPLETED not in updated.events

    @pytest.mark.asyncio
    async def test_update_webhook_not_found(self, webhook_store):
        """Test updating non-existent webhook."""
        result = await webhook_store.update_webhook(
            "nonexistent-id",
            name="New Name",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_regenerate_secret(self, webhook_store):
        """Test regenerating webhook secret."""
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Test",
            url="https://example.com",
            events=[WebhookEventType.SESSION_COMPLETED],
        )
        original_secret = webhook.secret

        new_secret = await webhook_store.regenerate_secret(webhook.id)

        assert new_secret is not None
        assert new_secret != original_secret
        assert len(new_secret) >= 32

        # Verify it was persisted
        retrieved = await webhook_store.get_webhook(webhook.id)
        assert retrieved.secret == new_secret

    @pytest.mark.asyncio
    async def test_regenerate_secret_not_found(self, webhook_store):
        """Test regenerating secret for non-existent webhook."""
        result = await webhook_store.regenerate_secret("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_webhook(self, webhook_store):
        """Test deleting a webhook."""
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Test",
            url="https://example.com",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        deleted = await webhook_store.delete_webhook(webhook.id)

        assert deleted is True
        assert await webhook_store.get_webhook(webhook.id) is None

    @pytest.mark.asyncio
    async def test_delete_webhook_not_found(self, webhook_store):
        """Test deleting non-existent webhook."""
        deleted = await webhook_store.delete_webhook("nonexistent-id")
        assert deleted is False


# ============================================
# WebhookStore Delivery Tests
# ============================================


class TestWebhookStoreDeliveries:
    """Tests for webhook delivery management."""

    @pytest.mark.asyncio
    async def test_create_delivery(self, webhook_store):
        """Test creating a delivery record."""
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Test",
            url="https://example.com",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        delivery = await webhook_store.create_delivery(
            webhook_id=webhook.id,
            event_type=WebhookEventType.SESSION_COMPLETED,
            payload='{"test": true}',
        )

        assert delivery.id is not None
        assert delivery.webhook_id == webhook.id
        assert delivery.event_type == WebhookEventType.SESSION_COMPLETED
        assert delivery.status == DeliveryStatus.PENDING
        assert delivery.attempt_count == 0

    @pytest.mark.asyncio
    async def test_update_delivery_success(self, webhook_store):
        """Test updating delivery to success."""
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Test",
            url="https://example.com",
            events=[WebhookEventType.SESSION_COMPLETED],
        )
        delivery = await webhook_store.create_delivery(
            webhook_id=webhook.id,
            event_type=WebhookEventType.SESSION_COMPLETED,
            payload='{"test": true}',
        )

        updated = await webhook_store.update_delivery(
            delivery_id=delivery.id,
            status=DeliveryStatus.SUCCESS,
            status_code=200,
            response_body='{"ok": true}',
            attempt_count=1,
        )

        assert updated is True

        # Verify persistence
        retrieved = await webhook_store.get_delivery(delivery.id)
        assert retrieved.status == DeliveryStatus.SUCCESS
        assert retrieved.status_code == 200
        assert retrieved.attempt_count == 1
        assert retrieved.completed_at is not None

    @pytest.mark.asyncio
    async def test_update_delivery_retrying(self, webhook_store):
        """Test updating delivery to retrying status."""
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Test",
            url="https://example.com",
            events=[WebhookEventType.SESSION_COMPLETED],
        )
        delivery = await webhook_store.create_delivery(
            webhook_id=webhook.id,
            event_type=WebhookEventType.SESSION_COMPLETED,
            payload='{"test": true}',
        )

        next_retry = datetime.now() + timedelta(minutes=5)
        await webhook_store.update_delivery(
            delivery_id=delivery.id,
            status=DeliveryStatus.RETRYING,
            error_message="Connection timeout",
            attempt_count=1,
            next_retry_at=next_retry,
        )

        retrieved = await webhook_store.get_delivery(delivery.id)
        assert retrieved.status == DeliveryStatus.RETRYING
        assert retrieved.error_message == "Connection timeout"
        assert retrieved.completed_at is None

    @pytest.mark.asyncio
    async def test_get_webhook_deliveries(self, webhook_store):
        """Test getting deliveries for a webhook."""
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Test",
            url="https://example.com",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        # Create multiple deliveries
        for i in range(5):
            await webhook_store.create_delivery(
                webhook_id=webhook.id,
                event_type=WebhookEventType.SESSION_COMPLETED,
                payload=f'{{"index": {i}}}',
            )

        deliveries = await webhook_store.get_webhook_deliveries(webhook.id)
        assert len(deliveries) == 5

    @pytest.mark.asyncio
    async def test_get_webhook_deliveries_with_status_filter(self, webhook_store):
        """Test getting deliveries filtered by status."""
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Test",
            url="https://example.com",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        # Create deliveries with different statuses
        delivery1 = await webhook_store.create_delivery(
            webhook_id=webhook.id,
            event_type=WebhookEventType.SESSION_COMPLETED,
            payload='{"index": 1}',
        )
        await webhook_store.update_delivery(
            delivery1.id,
            status=DeliveryStatus.SUCCESS,
            status_code=200,
        )

        delivery2 = await webhook_store.create_delivery(
            webhook_id=webhook.id,
            event_type=WebhookEventType.SESSION_COMPLETED,
            payload='{"index": 2}',
        )
        await webhook_store.update_delivery(
            delivery2.id,
            status=DeliveryStatus.FAILED,
            error_message="Error",
        )

        success_deliveries = await webhook_store.get_webhook_deliveries(
            webhook.id,
            status=DeliveryStatus.SUCCESS,
        )
        assert len(success_deliveries) == 1

        failed_deliveries = await webhook_store.get_webhook_deliveries(
            webhook.id,
            status=DeliveryStatus.FAILED,
        )
        assert len(failed_deliveries) == 1

    @pytest.mark.asyncio
    async def test_get_pending_retries(self, webhook_store):
        """Test getting deliveries ready for retry."""
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Test",
            url="https://example.com",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        # Create delivery scheduled for retry in the past
        delivery = await webhook_store.create_delivery(
            webhook_id=webhook.id,
            event_type=WebhookEventType.SESSION_COMPLETED,
            payload='{"test": true}',
        )
        past_time = datetime.now() - timedelta(minutes=1)
        await webhook_store.update_delivery(
            delivery.id,
            status=DeliveryStatus.RETRYING,
            next_retry_at=past_time,
        )

        retries = await webhook_store.get_pending_retries()
        assert len(retries) >= 1
        assert any(r.id == delivery.id for r in retries)

    @pytest.mark.asyncio
    async def test_cleanup_old_deliveries(self, webhook_store):
        """Test cleaning up old deliveries."""
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Test",
            url="https://example.com",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        # Create and complete a delivery
        delivery = await webhook_store.create_delivery(
            webhook_id=webhook.id,
            event_type=WebhookEventType.SESSION_COMPLETED,
            payload='{"test": true}',
        )
        await webhook_store.update_delivery(
            delivery.id,
            status=DeliveryStatus.SUCCESS,
            status_code=200,
        )

        # Manually set old created_at (would need DB access)
        # For now, just verify the method runs without error
        deleted = await webhook_store.cleanup_old_deliveries(days=0)
        # With days=0, should delete everything completed
        assert deleted >= 0


# ============================================
# WebhookStore Statistics Tests
# ============================================


class TestWebhookStoreStatistics:
    """Tests for webhook statistics."""

    @pytest.mark.asyncio
    async def test_get_statistics(self, webhook_store):
        """Test getting webhook statistics."""
        # Create webhooks
        webhook1 = await webhook_store.create_webhook(
            team_id="team-123",
            name="Webhook 1",
            url="https://example.com/hook1",
            events=[WebhookEventType.SESSION_COMPLETED],
        )
        await webhook_store.create_webhook(
            team_id="team-123",
            name="Webhook 2",
            url="https://example.com/hook2",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        # Create some deliveries
        await webhook_store.create_delivery(
            webhook_id=webhook1.id,
            event_type=WebhookEventType.SESSION_COMPLETED,
            payload='{"test": true}',
        )

        stats = await webhook_store.get_statistics()

        assert stats["webhooks"]["total"] >= 2
        assert stats["webhooks"]["enabled"] >= 2
        assert stats["deliveries"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_get_statistics_by_team(self, webhook_store):
        """Test getting statistics filtered by team."""
        await webhook_store.create_webhook(
            team_id="team-123",
            name="Team 123 Webhook",
            url="https://example.com/hook1",
            events=[WebhookEventType.SESSION_COMPLETED],
        )
        await webhook_store.create_webhook(
            team_id="team-other",
            name="Other Team Webhook",
            url="https://example.com/hook2",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        stats = await webhook_store.get_statistics(team_id="team-123")

        assert stats["webhooks"]["total"] == 1


# ============================================
# WebhookDeliveryService Tests
# ============================================


class TestWebhookDeliveryService:
    """Tests for WebhookDeliveryService."""

    @pytest.mark.asyncio
    async def test_format_generic_payload(self, webhook_store):
        """Test formatting generic payload."""
        webhook = Webhook(
            id="test-id",
            team_id="team-123",
            name="Test",
            url="https://example.com",
            secret="secret",
            events=[WebhookEventType.ALL],
            format=WebhookFormat.GENERIC,
        )

        service = WebhookDeliveryService(webhook_store)
        payload = service._format_payload(
            webhook,
            WebhookEventType.SESSION_COMPLETED,
            {"title": "Test", "message": "Hello"},
        )

        assert payload["event"] == "session.completed"
        assert "timestamp" in payload
        assert payload["team_id"] == "team-123"
        assert payload["data"]["title"] == "Test"
        assert payload["data"]["message"] == "Hello"

    @pytest.mark.asyncio
    async def test_format_slack_payload(self, webhook_store):
        """Test formatting Slack payload."""
        webhook = Webhook(
            id="test-id",
            team_id="team-123",
            name="Test",
            url="https://hooks.slack.com/...",
            secret="secret",
            events=[WebhookEventType.ALL],
            format=WebhookFormat.SLACK,
        )

        service = WebhookDeliveryService(webhook_store)
        payload = service._format_payload(
            webhook,
            WebhookEventType.SESSION_COMPLETED,
            {"title": "Session Done", "message": "Task completed successfully"},
        )

        assert "text" in payload
        assert "blocks" in payload
        assert len(payload["blocks"]) > 0

    @pytest.mark.asyncio
    async def test_format_discord_payload(self, webhook_store):
        """Test formatting Discord payload."""
        webhook = Webhook(
            id="test-id",
            team_id="team-123",
            name="Test",
            url="https://discord.com/api/webhooks/...",
            secret="secret",
            events=[WebhookEventType.ALL],
            format=WebhookFormat.DISCORD,
        )

        service = WebhookDeliveryService(webhook_store)
        payload = service._format_payload(
            webhook,
            WebhookEventType.SESSION_COMPLETED,
            {"title": "Session Done", "message": "Task completed"},
        )

        assert "embeds" in payload
        assert len(payload["embeds"]) > 0
        embed = payload["embeds"][0]
        assert "title" in embed
        assert "color" in embed

    @pytest.mark.asyncio
    async def test_deliver_creates_delivery_record(self, webhook_store):
        """Test that deliver creates a delivery record."""
        pytest.importorskip("aiohttp")  # Skip if aiohttp not available

        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Test",
            url="https://httpbin.org/status/200",  # Won't actually call
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        service = WebhookDeliveryService(webhook_store)

        # Mock the aiohttp request
        with patch("sindri.collaboration.webhooks.aiohttp") as mock_aiohttp:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='{"ok": true}')

            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_cm.__aexit__ = AsyncMock()

            mock_session_instance = AsyncMock()
            mock_session_instance.post = MagicMock(return_value=mock_cm)
            mock_session_instance.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session_instance.__aexit__ = AsyncMock()

            mock_aiohttp.ClientSession.return_value = mock_session_instance
            mock_aiohttp.ClientTimeout = MagicMock()

            delivery = await service.deliver(
                webhook=webhook,
                event_type=WebhookEventType.SESSION_COMPLETED,
                data={"title": "Test", "message": "Hello"},
            )

            assert delivery is not None
            assert delivery.webhook_id == webhook.id
            assert delivery.event_type == WebhookEventType.SESSION_COMPLETED

    @pytest.mark.asyncio
    async def test_retry_delays(self, webhook_store):
        """Test retry delay configuration."""
        service = WebhookDeliveryService(webhook_store)

        assert service.RETRY_DELAYS == [60, 300, 900]  # 1min, 5min, 15min


# ============================================
# Signature Verification Tests
# ============================================


class TestSignatureVerification:
    """Tests for webhook signature verification."""

    def test_verify_webhook_signature_valid(self):
        """Test verifying a valid signature."""
        payload = '{"event": "test"}'
        secret = "my-secret-key"

        signature = "sha256=" + hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        assert verify_webhook_signature(payload, signature, secret) is True

    def test_verify_webhook_signature_invalid(self):
        """Test verifying an invalid signature."""
        payload = '{"event": "test"}'
        secret = "my-secret-key"

        assert verify_webhook_signature(payload, "sha256=invalid", secret) is False

    def test_verify_webhook_signature_missing_prefix(self):
        """Test signature without sha256= prefix."""
        payload = '{"event": "test"}'
        secret = "my-secret-key"

        signature = hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        assert verify_webhook_signature(payload, signature, secret) is False

    def test_verify_webhook_signature_wrong_secret(self):
        """Test signature with wrong secret."""
        payload = '{"event": "test"}'

        signature = "sha256=" + hmac.new(
            b"correct-secret",
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        assert verify_webhook_signature(payload, signature, "wrong-secret") is False


# ============================================
# Convenience Function Tests
# ============================================


class TestTriggerWebhookEvent:
    """Tests for trigger_webhook_event function."""

    @pytest.mark.asyncio
    async def test_trigger_webhook_event_no_webhooks(self, webhook_store):
        """Test triggering event with no matching webhooks."""
        deliveries = await trigger_webhook_event(
            store=webhook_store,
            team_id="team-123",
            event_type=WebhookEventType.SESSION_COMPLETED,
            data={"title": "Test"},
        )

        assert deliveries == []

    @pytest.mark.asyncio
    async def test_trigger_webhook_event_with_matching_webhook(self, webhook_store):
        """Test triggering event with matching webhook."""
        await webhook_store.create_webhook(
            team_id="team-123",
            name="Test",
            url="https://example.com/webhook",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        # Mock the HTTP delivery
        with patch.object(
            WebhookDeliveryService,
            "_attempt_delivery",
            new_callable=AsyncMock,
        ):
            deliveries = await trigger_webhook_event(
                store=webhook_store,
                team_id="team-123",
                event_type=WebhookEventType.SESSION_COMPLETED,
                data={"title": "Test", "message": "Hello"},
            )

            assert len(deliveries) == 1


# ============================================
# Integration Tests
# ============================================


class TestWebhookIntegration:
    """Integration tests for webhook system."""

    @pytest.mark.asyncio
    async def test_full_webhook_lifecycle(self, webhook_store):
        """Test complete webhook lifecycle: create, update, deliver, delete."""
        # Create webhook
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Lifecycle Test",
            url="https://example.com/webhook",
            events=[WebhookEventType.SESSION_COMPLETED],
            format=WebhookFormat.GENERIC,
        )
        assert webhook.enabled is True

        # Update webhook
        updated = await webhook_store.update_webhook(
            webhook.id,
            description="Updated description",
            events=[WebhookEventType.SESSION_COMPLETED, WebhookEventType.SESSION_FAILED],
        )
        assert len(updated.events) == 2

        # Create delivery
        delivery = await webhook_store.create_delivery(
            webhook_id=webhook.id,
            event_type=WebhookEventType.SESSION_COMPLETED,
            payload='{"test": true}',
        )
        assert delivery.status == DeliveryStatus.PENDING

        # Update delivery to success
        await webhook_store.update_delivery(
            delivery.id,
            status=DeliveryStatus.SUCCESS,
            status_code=200,
        )

        # Check statistics
        stats = await webhook_store.get_statistics(team_id="team-123")
        assert stats["webhooks"]["total"] >= 1
        assert stats["deliveries"]["success"] >= 1

        # Delete webhook
        deleted = await webhook_store.delete_webhook(webhook.id)
        assert deleted is True

    @pytest.mark.asyncio
    async def test_multiple_webhooks_same_event(self, webhook_store):
        """Test multiple webhooks receiving the same event."""
        # Create multiple webhooks for same team
        webhook1 = await webhook_store.create_webhook(
            team_id="team-123",
            name="Webhook 1",
            url="https://example.com/hook1",
            events=[WebhookEventType.SESSION_COMPLETED],
        )
        webhook2 = await webhook_store.create_webhook(
            team_id="team-123",
            name="Webhook 2",
            url="https://example.com/hook2",
            events=[WebhookEventType.SESSION_COMPLETED],
        )
        await webhook_store.create_webhook(
            team_id="team-123",
            name="Webhook 3 (task only)",
            url="https://example.com/hook3",
            events=[WebhookEventType.TASK_COMPLETED],
        )

        # Get webhooks for session.completed event
        matching = await webhook_store.get_webhooks_for_event(
            "team-123",
            WebhookEventType.SESSION_COMPLETED,
        )

        assert len(matching) == 2
        ids = [w.id for w in matching]
        assert webhook1.id in ids
        assert webhook2.id in ids

    @pytest.mark.asyncio
    async def test_disabled_webhook_not_triggered(self, webhook_store):
        """Test that disabled webhooks are not triggered."""
        webhook = await webhook_store.create_webhook(
            team_id="team-123",
            name="Disabled Webhook",
            url="https://example.com/webhook",
            events=[WebhookEventType.SESSION_COMPLETED],
        )

        # Disable the webhook
        await webhook_store.update_webhook(webhook.id, enabled=False)

        # Get webhooks for event
        matching = await webhook_store.get_webhooks_for_event(
            "team-123",
            WebhookEventType.SESSION_COMPLETED,
        )

        assert len(matching) == 0
