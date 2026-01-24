"""Pydantic models for Triggers & Automations (ROADMAP Item 9).

Defines trigger definitions, notification hooks, and run records
for the trigger system.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field


class TriggerType(str, Enum):
    """Types of triggers."""

    CRON = "cron"  # Time-based schedule using cron expressions
    WEBHOOK = "webhook"  # External HTTP POST triggers
    EVENT = "event"  # Internal EventBus event triggers


class TriggerStatus(str, Enum):
    """Trigger status."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    PAUSED = "paused"  # Temporarily paused (e.g., too many failures)


class NotificationTarget(str, Enum):
    """Notification delivery targets."""

    DESKTOP = "desktop"  # notify-send on Linux
    LOG = "log"  # Write to log file
    WEBHOOK = "webhook"  # Outbound HTTP webhook


class NotificationHook(BaseModel):
    """Notification configuration for trigger outcomes."""

    target: NotificationTarget
    on_success: bool = True
    on_failure: bool = True

    # Desktop notification settings
    urgency: str = Field(default="normal")  # low, normal, critical

    # Log target settings
    log_path: Optional[str] = None  # Defaults to ~/.sindri/triggers.log

    # Webhook target settings (for outbound notifications)
    webhook_url: Optional[str] = None
    webhook_headers: dict[str, str] = Field(default_factory=dict)


class TriggerDefinition(BaseModel):
    """Trigger definition persisted to database."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="")
    trigger_type: TriggerType
    status: TriggerStatus = TriggerStatus.ENABLED

    # Task configuration
    task_description: str = Field(..., min_length=1)
    agent: str = Field(default="brokkr")
    max_iterations: int = Field(default=30, ge=1, le=100)
    work_dir: Optional[str] = None

    # Scheduling (for CRON type)
    cron_expression: Optional[str] = None  # e.g., "0 2 * * *" (2 AM daily)
    timezone: str = Field(default="UTC")

    # Webhook config (for WEBHOOK type)
    webhook_secret: Optional[str] = None  # For signature verification
    rate_limit_per_minute: int = Field(default=10, ge=1, le=100)

    # Event config (for EVENT type)
    event_types: list[str] = Field(default_factory=list)  # EventType names
    event_filters: dict[str, Any] = Field(default_factory=dict)  # JSON filter

    # Notification hooks
    notifications: list[NotificationHook] = Field(default_factory=list)

    # Tracking
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None  # Calculated for CRON
    run_count: int = Field(default=0)
    failure_count: int = Field(default=0)
    consecutive_failures: int = Field(default=0)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger_type": self.trigger_type.value,
            "status": self.status.value,
            "task_description": self.task_description,
            "agent": self.agent,
            "max_iterations": self.max_iterations,
            "work_dir": self.work_dir,
            "cron_expression": self.cron_expression,
            "timezone": self.timezone,
            "webhook_secret": self.webhook_secret,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "event_types": self.event_types,
            "event_filters": self.event_filters,
            "notifications": [n.model_dump() for n in self.notifications],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "run_count": self.run_count,
            "failure_count": self.failure_count,
            "consecutive_failures": self.consecutive_failures,
        }


class TriggerRun(BaseModel):
    """Record of a trigger execution."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trigger_id: str
    trigger_name: str = Field(default="")
    task_id: Optional[str] = None  # Link to created task
    session_id: Optional[str] = None

    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None

    success: bool = False
    error: Optional[str] = None
    result_summary: Optional[str] = None

    # For webhook triggers
    webhook_payload: Optional[dict] = None
    webhook_headers: Optional[dict] = None

    # For event triggers
    event_type: Optional[str] = None
    event_data: Optional[dict] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "trigger_id": self.trigger_id,
            "trigger_name": self.trigger_name,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "result_summary": self.result_summary,
            "webhook_payload": self.webhook_payload,
            "webhook_headers": self.webhook_headers,
            "event_type": self.event_type,
            "event_data": self.event_data,
        }
