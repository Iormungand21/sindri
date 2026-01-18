"""Webhooks system for external integrations.

This module provides webhook functionality for team collaboration:
- Webhook registration and management
- Event types: activity, notifications, sessions, teams
- Secure delivery with HMAC-SHA256 signatures
- Retry logic for failed deliveries
- Support for Slack, Discord, and generic HTTP endpoints
"""

import asyncio
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

import structlog

if TYPE_CHECKING:
    from sindri.persistence.database import Database

log = structlog.get_logger()


def generate_webhook_id() -> str:
    """Generate a unique webhook ID."""
    return secrets.token_hex(16)


def generate_webhook_secret() -> str:
    """Generate a secure webhook secret for HMAC signing."""
    return secrets.token_urlsafe(32)


def generate_delivery_id() -> str:
    """Generate a unique delivery ID."""
    return secrets.token_hex(16)


class WebhookEventType(str, Enum):
    """Types of events that can trigger webhooks."""

    # Session events
    SESSION_CREATED = "session.created"
    SESSION_COMPLETED = "session.completed"
    SESSION_FAILED = "session.failed"
    SESSION_RESUMED = "session.resumed"

    # Task events
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_DELEGATED = "task.delegated"

    # Team events
    TEAM_MEMBER_JOINED = "team.member_joined"
    TEAM_MEMBER_LEFT = "team.member_left"
    TEAM_ROLE_CHANGED = "team.role_changed"
    TEAM_SETTINGS_CHANGED = "team.settings_changed"

    # Comment events
    COMMENT_ADDED = "comment.added"
    COMMENT_RESOLVED = "comment.resolved"

    # Share events
    SESSION_SHARED = "session.shared"
    SHARE_REVOKED = "session.share_revoked"

    # Notification forwarding
    NOTIFICATION_CREATED = "notification.created"

    # Activity feed
    ACTIVITY_LOGGED = "activity.logged"

    # Wildcard - receive all events
    ALL = "*"


class WebhookFormat(str, Enum):
    """Payload format for webhook delivery."""

    GENERIC = "generic"  # Standard JSON payload
    SLACK = "slack"  # Slack-compatible payload
    DISCORD = "discord"  # Discord-compatible payload


class DeliveryStatus(str, Enum):
    """Status of a webhook delivery attempt."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class Webhook:
    """A webhook configuration.

    Attributes:
        id: Unique webhook identifier
        team_id: Team this webhook belongs to
        name: Human-readable name
        url: Endpoint URL to deliver to
        secret: Secret key for HMAC signature
        events: List of event types to trigger on
        format: Payload format (generic, slack, discord)
        enabled: Whether webhook is active
        created_at: When webhook was created
        created_by: User who created it
        description: Optional description
        headers: Custom headers to include
        retry_count: Number of retries on failure (default 3)
        timeout_seconds: Request timeout in seconds (default 30)
    """

    id: str
    team_id: str
    name: str
    url: str
    secret: str
    events: list[WebhookEventType]
    format: WebhookFormat = WebhookFormat.GENERIC
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    created_by: Optional[str] = None
    description: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    retry_count: int = 3
    timeout_seconds: int = 30

    def to_dict(self, include_secret: bool = False) -> dict:
        """Convert to dictionary for serialization.

        Args:
            include_secret: Whether to include the secret

        Returns:
            Dictionary representation
        """
        result = {
            "id": self.id,
            "team_id": self.team_id,
            "name": self.name,
            "url": self.url,
            "events": [e.value for e in self.events],
            "format": self.format.value,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "description": self.description,
            "headers": self.headers,
            "retry_count": self.retry_count,
            "timeout_seconds": self.timeout_seconds,
        }
        if include_secret:
            result["secret"] = self.secret
        return result

    def matches_event(self, event_type: WebhookEventType) -> bool:
        """Check if this webhook should receive an event type.

        Args:
            event_type: Event type to check

        Returns:
            True if webhook should receive this event
        """
        if not self.enabled:
            return False
        if WebhookEventType.ALL in self.events:
            return True
        return event_type in self.events

    def compute_signature(self, payload: str) -> str:
        """Compute HMAC-SHA256 signature for a payload.

        Args:
            payload: JSON payload string

        Returns:
            Hex-encoded signature
        """
        return hmac.new(
            self.secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


@dataclass
class WebhookDelivery:
    """Record of a webhook delivery attempt.

    Attributes:
        id: Unique delivery identifier
        webhook_id: Webhook that was triggered
        event_type: Event type that triggered delivery
        payload: JSON payload that was sent
        status: Delivery status
        status_code: HTTP response status code
        response_body: Response body (truncated)
        error_message: Error message if failed
        attempt_count: Number of delivery attempts
        created_at: When delivery was initiated
        completed_at: When delivery completed (success or final failure)
        next_retry_at: When next retry is scheduled
    """

    id: str
    webhook_id: str
    event_type: WebhookEventType
    payload: str
    status: DeliveryStatus = DeliveryStatus.PENDING
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    attempt_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "webhook_id": self.webhook_id,
            "event_type": self.event_type.value,
            "payload": self.payload,
            "status": self.status.value,
            "status_code": self.status_code,
            "response_body": self.response_body,
            "error_message": self.error_message,
            "attempt_count": self.attempt_count,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
        }


class WebhookStore:
    """Persistent storage for webhooks and deliveries."""

    def __init__(self, database: Optional["Database"] = None):
        """Initialize the webhook store.

        Args:
            database: Database instance (creates default if not provided)
        """
        from sindri.persistence.database import Database

        self.db = database or Database()

    async def _ensure_tables(self) -> None:
        """Ensure webhook tables exist."""
        await self.db.initialize()
        async with self.db.get_connection() as conn:
            # Webhooks table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    id TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    secret TEXT NOT NULL,
                    events TEXT NOT NULL,
                    format TEXT DEFAULT 'generic',
                    enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT,
                    description TEXT DEFAULT '',
                    headers TEXT DEFAULT '{}',
                    retry_count INTEGER DEFAULT 3,
                    timeout_seconds INTEGER DEFAULT 30
                )
            """)

            # Webhook deliveries table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS webhook_deliveries (
                    id TEXT PRIMARY KEY,
                    webhook_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    status_code INTEGER,
                    response_body TEXT,
                    error_message TEXT,
                    attempt_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    next_retry_at TIMESTAMP,
                    FOREIGN KEY (webhook_id) REFERENCES webhooks(id) ON DELETE CASCADE
                )
            """)

            # Indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_webhooks_team_id
                ON webhooks(team_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook_id
                ON webhook_deliveries(webhook_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_status
                ON webhook_deliveries(status)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_next_retry
                ON webhook_deliveries(next_retry_at)
            """)

            await conn.commit()

    async def create_webhook(
        self,
        team_id: str,
        name: str,
        url: str,
        events: list[WebhookEventType],
        format: WebhookFormat = WebhookFormat.GENERIC,
        created_by: Optional[str] = None,
        description: str = "",
        headers: Optional[dict[str, str]] = None,
        retry_count: int = 3,
        timeout_seconds: int = 30,
    ) -> Webhook:
        """Create a new webhook.

        Args:
            team_id: Team ID
            name: Webhook name
            url: Endpoint URL
            events: Event types to subscribe to
            format: Payload format
            created_by: User creating the webhook
            description: Optional description
            headers: Custom headers
            retry_count: Number of retries
            timeout_seconds: Request timeout

        Returns:
            Created Webhook
        """
        await self._ensure_tables()

        webhook_id = generate_webhook_id()
        secret = generate_webhook_secret()

        webhook = Webhook(
            id=webhook_id,
            team_id=team_id,
            name=name,
            url=url,
            secret=secret,
            events=events,
            format=format,
            created_by=created_by,
            description=description,
            headers=headers or {},
            retry_count=retry_count,
            timeout_seconds=timeout_seconds,
        )

        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO webhooks (
                    id, team_id, name, url, secret, events, format,
                    enabled, created_at, created_by, description,
                    headers, retry_count, timeout_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    webhook.id,
                    webhook.team_id,
                    webhook.name,
                    webhook.url,
                    webhook.secret,
                    json.dumps([e.value for e in webhook.events]),
                    webhook.format.value,
                    1 if webhook.enabled else 0,
                    webhook.created_at.isoformat(),
                    webhook.created_by,
                    webhook.description,
                    json.dumps(webhook.headers),
                    webhook.retry_count,
                    webhook.timeout_seconds,
                ),
            )
            await conn.commit()

        log.info(
            "webhook_created",
            webhook_id=webhook_id,
            team_id=team_id,
            name=name,
            events=[e.value for e in events],
        )
        return webhook

    async def get_webhook(self, webhook_id: str) -> Optional[Webhook]:
        """Get a webhook by ID.

        Args:
            webhook_id: Webhook ID

        Returns:
            Webhook if found, None otherwise
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM webhooks WHERE id = ?",
                (webhook_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_webhook(row)

    async def get_team_webhooks(
        self,
        team_id: str,
        enabled_only: bool = False,
    ) -> list[Webhook]:
        """Get all webhooks for a team.

        Args:
            team_id: Team ID
            enabled_only: Only return enabled webhooks

        Returns:
            List of Webhook objects
        """
        await self._ensure_tables()

        query = "SELECT * FROM webhooks WHERE team_id = ?"
        params: list = [team_id]

        if enabled_only:
            query += " AND enabled = 1"

        query += " ORDER BY created_at DESC"

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

        return [self._row_to_webhook(row) for row in rows]

    async def get_webhooks_for_event(
        self,
        team_id: str,
        event_type: WebhookEventType,
    ) -> list[Webhook]:
        """Get all enabled webhooks that should receive an event.

        Args:
            team_id: Team ID
            event_type: Event type

        Returns:
            List of matching Webhook objects
        """
        webhooks = await self.get_team_webhooks(team_id, enabled_only=True)
        return [w for w in webhooks if w.matches_event(event_type)]

    async def update_webhook(
        self,
        webhook_id: str,
        name: Optional[str] = None,
        url: Optional[str] = None,
        events: Optional[list[WebhookEventType]] = None,
        format: Optional[WebhookFormat] = None,
        enabled: Optional[bool] = None,
        description: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
        retry_count: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
    ) -> Optional[Webhook]:
        """Update a webhook.

        Args:
            webhook_id: Webhook ID
            name: New name
            url: New URL
            events: New event list
            format: New format
            enabled: Enable/disable
            description: New description
            headers: New custom headers
            retry_count: New retry count
            timeout_seconds: New timeout

        Returns:
            Updated Webhook, or None if not found
        """
        await self._ensure_tables()

        webhook = await self.get_webhook(webhook_id)
        if not webhook:
            return None

        # Build update query dynamically
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
            webhook.name = name

        if url is not None:
            updates.append("url = ?")
            params.append(url)
            webhook.url = url

        if events is not None:
            updates.append("events = ?")
            params.append(json.dumps([e.value for e in events]))
            webhook.events = events

        if format is not None:
            updates.append("format = ?")
            params.append(format.value)
            webhook.format = format

        if enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if enabled else 0)
            webhook.enabled = enabled

        if description is not None:
            updates.append("description = ?")
            params.append(description)
            webhook.description = description

        if headers is not None:
            updates.append("headers = ?")
            params.append(json.dumps(headers))
            webhook.headers = headers

        if retry_count is not None:
            updates.append("retry_count = ?")
            params.append(retry_count)
            webhook.retry_count = retry_count

        if timeout_seconds is not None:
            updates.append("timeout_seconds = ?")
            params.append(timeout_seconds)
            webhook.timeout_seconds = timeout_seconds

        if not updates:
            return webhook

        params.append(webhook_id)
        query = f"UPDATE webhooks SET {', '.join(updates)} WHERE id = ?"

        async with self.db.get_connection() as conn:
            await conn.execute(query, params)
            await conn.commit()

        log.info("webhook_updated", webhook_id=webhook_id)
        return webhook

    async def regenerate_secret(self, webhook_id: str) -> Optional[str]:
        """Regenerate the secret for a webhook.

        Args:
            webhook_id: Webhook ID

        Returns:
            New secret, or None if webhook not found
        """
        await self._ensure_tables()

        new_secret = generate_webhook_secret()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "UPDATE webhooks SET secret = ? WHERE id = ?",
                (new_secret, webhook_id),
            )
            await conn.commit()

            if cursor.rowcount == 0:
                return None

        log.info("webhook_secret_regenerated", webhook_id=webhook_id)
        return new_secret

    async def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook.

        Args:
            webhook_id: Webhook ID

        Returns:
            True if webhook was deleted
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM webhooks WHERE id = ?",
                (webhook_id,),
            )
            await conn.commit()

        deleted = cursor.rowcount > 0
        if deleted:
            log.info("webhook_deleted", webhook_id=webhook_id)
        return deleted

    async def create_delivery(
        self,
        webhook_id: str,
        event_type: WebhookEventType,
        payload: str,
    ) -> WebhookDelivery:
        """Create a delivery record.

        Args:
            webhook_id: Webhook ID
            event_type: Event type
            payload: JSON payload

        Returns:
            Created WebhookDelivery
        """
        await self._ensure_tables()

        delivery_id = generate_delivery_id()
        delivery = WebhookDelivery(
            id=delivery_id,
            webhook_id=webhook_id,
            event_type=event_type,
            payload=payload,
        )

        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO webhook_deliveries (
                    id, webhook_id, event_type, payload, status,
                    attempt_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery.id,
                    delivery.webhook_id,
                    delivery.event_type.value,
                    delivery.payload,
                    delivery.status.value,
                    delivery.attempt_count,
                    delivery.created_at.isoformat(),
                ),
            )
            await conn.commit()

        return delivery

    async def update_delivery(
        self,
        delivery_id: str,
        status: DeliveryStatus,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        error_message: Optional[str] = None,
        attempt_count: Optional[int] = None,
        next_retry_at: Optional[datetime] = None,
    ) -> bool:
        """Update a delivery record.

        Args:
            delivery_id: Delivery ID
            status: New status
            status_code: HTTP status code
            response_body: Response body (truncated)
            error_message: Error message
            attempt_count: Attempt count
            next_retry_at: Next retry time

        Returns:
            True if updated
        """
        await self._ensure_tables()

        completed_at = None
        if status in (DeliveryStatus.SUCCESS, DeliveryStatus.FAILED):
            completed_at = datetime.now()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE webhook_deliveries SET
                    status = ?,
                    status_code = ?,
                    response_body = ?,
                    error_message = ?,
                    attempt_count = COALESCE(?, attempt_count),
                    completed_at = ?,
                    next_retry_at = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    status_code,
                    response_body[:1000] if response_body else None,
                    error_message,
                    attempt_count,
                    completed_at.isoformat() if completed_at else None,
                    next_retry_at.isoformat() if next_retry_at else None,
                    delivery_id,
                ),
            )
            await conn.commit()

        return cursor.rowcount > 0

    async def get_delivery(self, delivery_id: str) -> Optional[WebhookDelivery]:
        """Get a delivery by ID.

        Args:
            delivery_id: Delivery ID

        Returns:
            WebhookDelivery if found
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM webhook_deliveries WHERE id = ?",
                (delivery_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_delivery(row)

    async def get_webhook_deliveries(
        self,
        webhook_id: str,
        status: Optional[DeliveryStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WebhookDelivery]:
        """Get deliveries for a webhook.

        Args:
            webhook_id: Webhook ID
            status: Filter by status
            limit: Maximum results
            offset: Results to skip

        Returns:
            List of WebhookDelivery objects
        """
        await self._ensure_tables()

        query = "SELECT * FROM webhook_deliveries WHERE webhook_id = ?"
        params: list = [webhook_id]

        if status:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

        return [self._row_to_delivery(row) for row in rows]

    async def get_pending_retries(self) -> list[WebhookDelivery]:
        """Get deliveries that need to be retried.

        Returns:
            List of deliveries ready for retry
        """
        await self._ensure_tables()

        now = datetime.now().isoformat()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM webhook_deliveries
                WHERE status = 'retrying' AND next_retry_at <= ?
                ORDER BY next_retry_at ASC
                LIMIT 100
                """,
                (now,),
            )
            rows = await cursor.fetchall()

        return [self._row_to_delivery(row) for row in rows]

    async def cleanup_old_deliveries(self, days: int = 7) -> int:
        """Delete old delivery records.

        Args:
            days: Delete deliveries older than this many days

        Returns:
            Number of deliveries deleted
        """
        await self._ensure_tables()

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                DELETE FROM webhook_deliveries
                WHERE created_at < ? AND status IN ('success', 'failed')
                """,
                (cutoff,),
            )
            await conn.commit()

        deleted = cursor.rowcount
        if deleted > 0:
            log.info("webhook_deliveries_cleaned", deleted=deleted, days=days)
        return deleted

    async def get_statistics(
        self,
        team_id: Optional[str] = None,
        webhook_id: Optional[str] = None,
    ) -> dict:
        """Get webhook statistics.

        Args:
            team_id: Filter by team
            webhook_id: Filter by webhook

        Returns:
            Dictionary with statistics
        """
        await self._ensure_tables()

        async with self.db.get_connection() as conn:
            # Webhook counts
            webhook_query = "SELECT COUNT(*), SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END) FROM webhooks"
            webhook_params: list = []

            if team_id:
                webhook_query += " WHERE team_id = ?"
                webhook_params.append(team_id)

            cursor = await conn.execute(webhook_query, webhook_params)
            webhook_row = await cursor.fetchone()

            # Delivery counts
            delivery_query = """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'retrying' THEN 1 ELSE 0 END) as retrying
                FROM webhook_deliveries
            """
            delivery_params: list = []

            if webhook_id:
                delivery_query += " WHERE webhook_id = ?"
                delivery_params.append(webhook_id)
            elif team_id:
                delivery_query += " WHERE webhook_id IN (SELECT id FROM webhooks WHERE team_id = ?)"
                delivery_params.append(team_id)

            cursor = await conn.execute(delivery_query, delivery_params)
            delivery_row = await cursor.fetchone()

        return {
            "webhooks": {
                "total": webhook_row[0] or 0,
                "enabled": webhook_row[1] or 0,
            },
            "deliveries": {
                "total": delivery_row[0] or 0,
                "success": delivery_row[1] or 0,
                "failed": delivery_row[2] or 0,
                "pending": delivery_row[3] or 0,
                "retrying": delivery_row[4] or 0,
            },
        }

    def _row_to_webhook(self, row) -> Webhook:
        """Convert a database row to a Webhook object."""
        events_json = row[5]
        try:
            events = [WebhookEventType(e) for e in json.loads(events_json)]
        except (json.JSONDecodeError, ValueError):
            events = []

        headers = {}
        if row[11]:
            try:
                headers = json.loads(row[11])
            except json.JSONDecodeError:
                pass

        return Webhook(
            id=row[0],
            team_id=row[1],
            name=row[2],
            url=row[3],
            secret=row[4],
            events=events,
            format=WebhookFormat(row[6]) if row[6] else WebhookFormat.GENERIC,
            enabled=bool(row[7]),
            created_at=datetime.fromisoformat(row[8]) if row[8] else datetime.now(),
            created_by=row[9],
            description=row[10] or "",
            headers=headers,
            retry_count=row[12] if row[12] else 3,
            timeout_seconds=row[13] if row[13] else 30,
        )

    def _row_to_delivery(self, row) -> WebhookDelivery:
        """Convert a database row to a WebhookDelivery object."""
        return WebhookDelivery(
            id=row[0],
            webhook_id=row[1],
            event_type=WebhookEventType(row[2]),
            payload=row[3],
            status=DeliveryStatus(row[4]) if row[4] else DeliveryStatus.PENDING,
            status_code=row[5],
            response_body=row[6],
            error_message=row[7],
            attempt_count=row[8] or 0,
            created_at=datetime.fromisoformat(row[9]) if row[9] else datetime.now(),
            completed_at=datetime.fromisoformat(row[10]) if row[10] else None,
            next_retry_at=datetime.fromisoformat(row[11]) if row[11] else None,
        )


class WebhookDeliveryService:
    """Service for delivering webhooks."""

    # Retry delays in seconds (exponential backoff)
    RETRY_DELAYS = [60, 300, 900]  # 1 min, 5 min, 15 min

    def __init__(self, store: WebhookStore):
        """Initialize the delivery service.

        Args:
            store: WebhookStore instance
        """
        self.store = store

    async def deliver(
        self,
        webhook: Webhook,
        event_type: WebhookEventType,
        data: dict[str, Any],
    ) -> WebhookDelivery:
        """Deliver a webhook event.

        Args:
            webhook: Webhook to deliver to
            event_type: Event type
            data: Event data

        Returns:
            WebhookDelivery record
        """
        # Format payload based on webhook format
        payload = self._format_payload(webhook, event_type, data)
        payload_json = json.dumps(payload, default=str)

        # Create delivery record
        delivery = await self.store.create_delivery(
            webhook_id=webhook.id,
            event_type=event_type,
            payload=payload_json,
        )

        # Attempt delivery
        await self._attempt_delivery(webhook, delivery, payload_json)

        return delivery

    async def _attempt_delivery(
        self,
        webhook: Webhook,
        delivery: WebhookDelivery,
        payload_json: str,
    ) -> None:
        """Attempt to deliver a webhook.

        Args:
            webhook: Webhook configuration
            delivery: Delivery record
            payload_json: JSON payload string
        """
        import aiohttp

        attempt = delivery.attempt_count + 1

        # Compute signature
        signature = webhook.compute_signature(payload_json)

        # Build headers
        headers = {
            "Content-Type": "application/json",
            "X-Sindri-Webhook-Id": webhook.id,
            "X-Sindri-Delivery-Id": delivery.id,
            "X-Sindri-Event": delivery.event_type.value,
            "X-Sindri-Signature": f"sha256={signature}",
            "X-Sindri-Timestamp": datetime.now().isoformat(),
            **webhook.headers,
        }

        try:
            timeout = aiohttp.ClientTimeout(total=webhook.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    webhook.url,
                    data=payload_json,
                    headers=headers,
                ) as response:
                    status_code = response.status
                    response_body = await response.text()

                    if 200 <= status_code < 300:
                        # Success
                        await self.store.update_delivery(
                            delivery_id=delivery.id,
                            status=DeliveryStatus.SUCCESS,
                            status_code=status_code,
                            response_body=response_body,
                            attempt_count=attempt,
                        )
                        log.info(
                            "webhook_delivered",
                            webhook_id=webhook.id,
                            delivery_id=delivery.id,
                            status_code=status_code,
                        )
                    else:
                        # Server error - may retry
                        await self._handle_failure(
                            webhook,
                            delivery,
                            attempt,
                            status_code,
                            response_body,
                            f"HTTP {status_code}",
                        )

        except asyncio.TimeoutError:
            await self._handle_failure(
                webhook,
                delivery,
                attempt,
                None,
                None,
                "Request timed out",
            )
        except aiohttp.ClientError as e:
            await self._handle_failure(
                webhook,
                delivery,
                attempt,
                None,
                None,
                str(e),
            )
        except Exception as e:
            await self._handle_failure(
                webhook,
                delivery,
                attempt,
                None,
                None,
                f"Unexpected error: {e}",
            )

    async def _handle_failure(
        self,
        webhook: Webhook,
        delivery: WebhookDelivery,
        attempt: int,
        status_code: Optional[int],
        response_body: Optional[str],
        error_message: str,
    ) -> None:
        """Handle a failed delivery attempt.

        Args:
            webhook: Webhook configuration
            delivery: Delivery record
            attempt: Current attempt number
            status_code: HTTP status code (if any)
            response_body: Response body (if any)
            error_message: Error message
        """
        if attempt < webhook.retry_count:
            # Schedule retry
            delay_index = min(attempt - 1, len(self.RETRY_DELAYS) - 1)
            delay = self.RETRY_DELAYS[delay_index]
            next_retry = datetime.now() + timedelta(seconds=delay)

            await self.store.update_delivery(
                delivery_id=delivery.id,
                status=DeliveryStatus.RETRYING,
                status_code=status_code,
                response_body=response_body,
                error_message=error_message,
                attempt_count=attempt,
                next_retry_at=next_retry,
            )
            log.warning(
                "webhook_delivery_retry_scheduled",
                webhook_id=webhook.id,
                delivery_id=delivery.id,
                attempt=attempt,
                next_retry=next_retry.isoformat(),
            )
        else:
            # Final failure
            await self.store.update_delivery(
                delivery_id=delivery.id,
                status=DeliveryStatus.FAILED,
                status_code=status_code,
                response_body=response_body,
                error_message=error_message,
                attempt_count=attempt,
            )
            log.error(
                "webhook_delivery_failed",
                webhook_id=webhook.id,
                delivery_id=delivery.id,
                attempts=attempt,
                error=error_message,
            )

    async def process_pending_retries(self) -> int:
        """Process all pending retries.

        Returns:
            Number of retries processed
        """
        deliveries = await self.store.get_pending_retries()
        processed = 0

        for delivery in deliveries:
            webhook = await self.store.get_webhook(delivery.webhook_id)
            if not webhook or not webhook.enabled:
                # Mark as failed if webhook is gone or disabled
                await self.store.update_delivery(
                    delivery_id=delivery.id,
                    status=DeliveryStatus.FAILED,
                    error_message="Webhook no longer available",
                    attempt_count=delivery.attempt_count,
                )
                continue

            await self._attempt_delivery(webhook, delivery, delivery.payload)
            processed += 1

        return processed

    def _format_payload(
        self,
        webhook: Webhook,
        event_type: WebhookEventType,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Format the webhook payload based on format type.

        Args:
            webhook: Webhook configuration
            event_type: Event type
            data: Event data

        Returns:
            Formatted payload
        """
        if webhook.format == WebhookFormat.SLACK:
            return self._format_slack_payload(event_type, data)
        elif webhook.format == WebhookFormat.DISCORD:
            return self._format_discord_payload(event_type, data)
        else:
            return self._format_generic_payload(webhook, event_type, data)

    def _format_generic_payload(
        self,
        webhook: Webhook,
        event_type: WebhookEventType,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Format a generic JSON payload.

        Args:
            webhook: Webhook configuration
            event_type: Event type
            data: Event data

        Returns:
            Generic payload
        """
        return {
            "event": event_type.value,
            "timestamp": datetime.now().isoformat(),
            "team_id": webhook.team_id,
            "data": data,
        }

    def _format_slack_payload(
        self,
        event_type: WebhookEventType,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Format a Slack-compatible payload.

        Args:
            event_type: Event type
            data: Event data

        Returns:
            Slack payload
        """
        # Build message text
        title = data.get("title", event_type.value)
        message = data.get("message", "")

        # Build blocks for rich formatting
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Sindri: {title}",
                },
            },
        ]

        if message:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message,
                },
            })

        # Add context
        context_elements = [
            {
                "type": "mrkdwn",
                "text": f"*Event:* `{event_type.value}`",
            },
        ]

        if "session_id" in data:
            context_elements.append({
                "type": "mrkdwn",
                "text": f"*Session:* `{data['session_id']}`",
            })

        if "user" in data:
            context_elements.append({
                "type": "mrkdwn",
                "text": f"*User:* {data['user']}",
            })

        blocks.append({
            "type": "context",
            "elements": context_elements,
        })

        return {
            "text": f"Sindri: {title}",
            "blocks": blocks,
        }

    def _format_discord_payload(
        self,
        event_type: WebhookEventType,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Format a Discord-compatible payload.

        Args:
            event_type: Event type
            data: Event data

        Returns:
            Discord payload
        """
        title = data.get("title", event_type.value)
        message = data.get("message", "")

        # Color based on event type
        color_map = {
            "session.completed": 0x00FF00,  # Green
            "session.failed": 0xFF0000,  # Red
            "task.completed": 0x00FF00,  # Green
            "comment.added": 0x0000FF,  # Blue
        }
        color = color_map.get(event_type.value, 0x808080)  # Default grey

        # Build embed
        embed = {
            "title": f"Sindri: {title}",
            "description": message,
            "color": color,
            "timestamp": datetime.now().isoformat(),
            "footer": {
                "text": f"Event: {event_type.value}",
            },
            "fields": [],
        }

        # Add fields
        if "session_id" in data:
            embed["fields"].append({
                "name": "Session",
                "value": f"`{data['session_id']}`",
                "inline": True,
            })

        if "user" in data:
            embed["fields"].append({
                "name": "User",
                "value": data["user"],
                "inline": True,
            })

        if "duration" in data:
            embed["fields"].append({
                "name": "Duration",
                "value": data["duration"],
                "inline": True,
            })

        return {
            "embeds": [embed],
        }


# Convenience functions


async def trigger_webhook_event(
    store: WebhookStore,
    team_id: str,
    event_type: WebhookEventType,
    data: dict[str, Any],
) -> list[WebhookDelivery]:
    """Trigger webhooks for an event.

    Args:
        store: WebhookStore instance
        team_id: Team ID
        event_type: Event type
        data: Event data

    Returns:
        List of delivery records
    """
    webhooks = await store.get_webhooks_for_event(team_id, event_type)
    if not webhooks:
        return []

    service = WebhookDeliveryService(store)
    deliveries = []

    for webhook in webhooks:
        try:
            delivery = await service.deliver(webhook, event_type, data)
            deliveries.append(delivery)
        except Exception as e:
            log.error(
                "webhook_trigger_error",
                webhook_id=webhook.id,
                event_type=event_type.value,
                error=str(e),
            )

    return deliveries


def verify_webhook_signature(
    payload: str,
    signature: str,
    secret: str,
) -> bool:
    """Verify a webhook signature.

    Args:
        payload: JSON payload string
        signature: Signature header value (sha256=...)
        secret: Webhook secret

    Returns:
        True if signature is valid
    """
    if not signature.startswith("sha256="):
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    provided = signature[7:]  # Remove "sha256=" prefix

    return hmac.compare_digest(expected, provided)
