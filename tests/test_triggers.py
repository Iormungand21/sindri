"""Tests for Triggers & Automations (ROADMAP Item 9)."""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sindri.triggers.models import (
    TriggerDefinition,
    TriggerRun,
    TriggerType,
    TriggerStatus,
    NotificationHook,
    NotificationTarget,
)
from sindri.triggers.store import TriggerStore
from sindri.triggers.scheduler import TriggerScheduler, SchedulerConfig
from sindri.triggers.executor import TriggerExecutor
from sindri.triggers.notifications import NotificationService
from sindri.persistence.database import Database
from sindri.core.events import EventType


# ==============================================================================
# Model Tests
# ==============================================================================


class TestTriggerModels:
    """Tests for Pydantic trigger models."""

    def test_trigger_definition_defaults(self):
        """Test TriggerDefinition with minimal required fields."""
        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
        )

        assert trigger.name == "test-trigger"
        assert trigger.trigger_type == TriggerType.CRON
        assert trigger.status == TriggerStatus.ENABLED
        assert trigger.agent == "brokkr"
        assert trigger.max_iterations == 30
        assert trigger.run_count == 0
        assert trigger.failure_count == 0
        assert len(trigger.id) == 36  # UUID

    def test_trigger_definition_cron_fields(self):
        """Test TriggerDefinition with cron-specific fields."""
        trigger = TriggerDefinition(
            name="cron-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Run at 2 AM daily",
            cron_expression="0 2 * * *",
            timezone="UTC",
        )

        assert trigger.cron_expression == "0 2 * * *"
        assert trigger.timezone == "UTC"

    def test_trigger_definition_webhook_fields(self):
        """Test TriggerDefinition with webhook-specific fields."""
        trigger = TriggerDefinition(
            name="webhook-trigger",
            trigger_type=TriggerType.WEBHOOK,
            task_description="Handle webhook",
            webhook_secret="my-secret",
            rate_limit_per_minute=5,
        )

        assert trigger.webhook_secret == "my-secret"
        assert trigger.rate_limit_per_minute == 5

    def test_trigger_definition_event_fields(self):
        """Test TriggerDefinition with event-specific fields."""
        trigger = TriggerDefinition(
            name="event-trigger",
            trigger_type=TriggerType.EVENT,
            task_description="React to failures",
            event_types=["TASK_STATUS_CHANGED"],
            event_filters={"status": "failed"},
        )

        assert trigger.event_types == ["TASK_STATUS_CHANGED"]
        assert trigger.event_filters == {"status": "failed"}

    def test_trigger_definition_notifications(self):
        """Test TriggerDefinition with notification hooks."""
        trigger = TriggerDefinition(
            name="notify-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Notify on completion",
            notifications=[
                NotificationHook(target=NotificationTarget.DESKTOP),
                NotificationHook(
                    target=NotificationTarget.LOG,
                    on_success=False,
                    on_failure=True,
                ),
            ],
        )

        assert len(trigger.notifications) == 2
        assert trigger.notifications[0].target == NotificationTarget.DESKTOP
        assert trigger.notifications[1].on_success is False

    def test_trigger_definition_to_dict(self):
        """Test TriggerDefinition serialization."""
        trigger = TriggerDefinition(
            name="serialize-test",
            trigger_type=TriggerType.CRON,
            task_description="Test serialization",
            cron_expression="* * * * *",
        )

        data = trigger.to_dict()

        assert data["name"] == "serialize-test"
        assert data["trigger_type"] == "cron"
        assert data["cron_expression"] == "* * * * *"
        assert "id" in data
        assert "created_at" in data

    def test_trigger_run_defaults(self):
        """Test TriggerRun with minimal fields."""
        run = TriggerRun(trigger_id="abc123")

        assert run.trigger_id == "abc123"
        assert run.success is False
        assert run.error is None
        assert len(run.id) == 36

    def test_trigger_run_complete(self):
        """Test TriggerRun with all fields."""
        now = datetime.now(timezone.utc)
        run = TriggerRun(
            trigger_id="abc123",
            trigger_name="test-trigger",
            task_id="task-456",
            session_id="session-789",
            started_at=now,
            completed_at=now + timedelta(seconds=5),
            duration_ms=5000.0,
            success=True,
            result_summary="Task completed",
        )

        assert run.task_id == "task-456"
        assert run.success is True
        assert run.duration_ms == 5000.0

    def test_trigger_run_to_dict(self):
        """Test TriggerRun serialization."""
        run = TriggerRun(
            trigger_id="abc123",
            success=True,
            duration_ms=1000.0,
        )

        data = run.to_dict()

        assert data["trigger_id"] == "abc123"
        assert data["success"] is True
        assert data["duration_ms"] == 1000.0

    def test_notification_hook_desktop(self):
        """Test NotificationHook for desktop notifications."""
        hook = NotificationHook(
            target=NotificationTarget.DESKTOP,
            urgency="critical",
        )

        assert hook.target == NotificationTarget.DESKTOP
        assert hook.urgency == "critical"
        assert hook.on_success is True
        assert hook.on_failure is True

    def test_notification_hook_log(self):
        """Test NotificationHook for log notifications."""
        hook = NotificationHook(
            target=NotificationTarget.LOG,
            log_path="/var/log/sindri-triggers.log",
        )

        assert hook.target == NotificationTarget.LOG
        assert hook.log_path == "/var/log/sindri-triggers.log"

    def test_notification_hook_webhook(self):
        """Test NotificationHook for webhook notifications."""
        hook = NotificationHook(
            target=NotificationTarget.WEBHOOK,
            webhook_url="https://example.com/notify",
            webhook_headers={"Authorization": "Bearer token"},
        )

        assert hook.target == NotificationTarget.WEBHOOK
        assert hook.webhook_url == "https://example.com/notify"
        assert "Authorization" in hook.webhook_headers


# ==============================================================================
# Store Tests
# ==============================================================================


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    os.environ["SINDRI_DB_PATH"] = str(db_path)
    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()
    del os.environ["SINDRI_DB_PATH"]


@pytest.fixture
def trigger_store(temp_db):
    """Create a TriggerStore with temporary database."""
    return TriggerStore(Database(db_path=temp_db))


class TestTriggerStore:
    """Tests for TriggerStore persistence."""

    @pytest.mark.asyncio
    async def test_save_and_load_trigger(self, trigger_store):
        """Test saving and loading a trigger."""
        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
            cron_expression="0 * * * *",
        )

        trigger_id = await trigger_store.save_trigger(trigger)
        assert trigger_id == trigger.id

        loaded = await trigger_store.load_trigger(trigger_id)
        assert loaded is not None
        assert loaded.name == "test-trigger"
        assert loaded.trigger_type == TriggerType.CRON
        assert loaded.cron_expression == "0 * * * *"

    @pytest.mark.asyncio
    async def test_load_nonexistent_trigger(self, trigger_store):
        """Test loading a trigger that doesn't exist."""
        loaded = await trigger_store.load_trigger("nonexistent-id")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_update_trigger(self, trigger_store):
        """Test updating trigger fields."""
        trigger = TriggerDefinition(
            name="original-name",
            trigger_type=TriggerType.CRON,
            task_description="Original task",
        )

        await trigger_store.save_trigger(trigger)

        result = await trigger_store.update_trigger(
            trigger.id, {"name": "updated-name"}
        )
        assert result is True

        loaded = await trigger_store.load_trigger(trigger.id)
        assert loaded.name == "updated-name"

    @pytest.mark.asyncio
    async def test_update_trigger_status(self, trigger_store):
        """Test updating trigger status."""
        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
        )

        await trigger_store.save_trigger(trigger)

        await trigger_store.update_trigger(
            trigger.id, {"status": TriggerStatus.DISABLED}
        )

        loaded = await trigger_store.load_trigger(trigger.id)
        assert loaded.status == TriggerStatus.DISABLED

    @pytest.mark.asyncio
    async def test_delete_trigger(self, trigger_store):
        """Test deleting a trigger."""
        trigger = TriggerDefinition(
            name="delete-me",
            trigger_type=TriggerType.CRON,
            task_description="Delete test",
        )

        await trigger_store.save_trigger(trigger)

        result = await trigger_store.delete_trigger(trigger.id)
        assert result is True

        loaded = await trigger_store.load_trigger(trigger.id)
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_trigger(self, trigger_store):
        """Test deleting a trigger that doesn't exist."""
        result = await trigger_store.delete_trigger("nonexistent-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_triggers(self, trigger_store):
        """Test listing all triggers."""
        for i in range(3):
            trigger = TriggerDefinition(
                name=f"trigger-{i}",
                trigger_type=TriggerType.CRON,
                task_description=f"Task {i}",
            )
            await trigger_store.save_trigger(trigger)

        triggers = await trigger_store.list_triggers()
        assert len(triggers) == 3

    @pytest.mark.asyncio
    async def test_list_triggers_by_type(self, trigger_store):
        """Test filtering triggers by type."""
        trigger1 = TriggerDefinition(
            name="cron-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Cron task",
        )
        trigger2 = TriggerDefinition(
            name="webhook-trigger",
            trigger_type=TriggerType.WEBHOOK,
            task_description="Webhook task",
        )

        await trigger_store.save_trigger(trigger1)
        await trigger_store.save_trigger(trigger2)

        cron_triggers = await trigger_store.list_triggers(
            trigger_type=TriggerType.CRON
        )
        assert len(cron_triggers) == 1
        assert cron_triggers[0].name == "cron-trigger"

    @pytest.mark.asyncio
    async def test_list_triggers_by_status(self, trigger_store):
        """Test filtering triggers by status."""
        trigger1 = TriggerDefinition(
            name="enabled-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Enabled task",
            status=TriggerStatus.ENABLED,
        )
        trigger2 = TriggerDefinition(
            name="disabled-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Disabled task",
            status=TriggerStatus.DISABLED,
        )

        await trigger_store.save_trigger(trigger1)
        await trigger_store.save_trigger(trigger2)

        enabled_triggers = await trigger_store.list_triggers(
            status=TriggerStatus.ENABLED
        )
        assert len(enabled_triggers) == 1
        assert enabled_triggers[0].name == "enabled-trigger"

    @pytest.mark.asyncio
    async def test_get_due_triggers(self, trigger_store):
        """Test getting due cron triggers."""
        now = datetime.now(timezone.utc)
        past = now - timedelta(minutes=5)
        future = now + timedelta(hours=1)

        trigger1 = TriggerDefinition(
            name="past-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Past task",
            cron_expression="* * * * *",
            next_run_at=past,
        )
        trigger2 = TriggerDefinition(
            name="future-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Future task",
            cron_expression="* * * * *",
            next_run_at=future,
        )

        await trigger_store.save_trigger(trigger1)
        await trigger_store.save_trigger(trigger2)

        due = await trigger_store.get_due_triggers(now)
        assert len(due) == 1
        assert due[0].name == "past-trigger"

    @pytest.mark.asyncio
    async def test_update_next_run(self, trigger_store):
        """Test updating next run time."""
        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
        )

        await trigger_store.save_trigger(trigger)

        next_run = datetime.now(timezone.utc) + timedelta(hours=1)
        await trigger_store.update_next_run(trigger.id, next_run)

        loaded = await trigger_store.load_trigger(trigger.id)
        # Compare with tolerance for floating point
        assert abs((loaded.next_run_at - next_run).total_seconds()) < 1

    @pytest.mark.asyncio
    async def test_increment_run_count_success(self, trigger_store):
        """Test incrementing run count for successful run."""
        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
        )

        await trigger_store.save_trigger(trigger)

        now = datetime.now(timezone.utc)
        await trigger_store.increment_run_count(trigger.id, success=True, last_run=now)

        loaded = await trigger_store.load_trigger(trigger.id)
        assert loaded.run_count == 1
        assert loaded.failure_count == 0
        assert loaded.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_increment_run_count_failure(self, trigger_store):
        """Test incrementing run count for failed run."""
        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
        )

        await trigger_store.save_trigger(trigger)

        now = datetime.now(timezone.utc)
        await trigger_store.increment_run_count(trigger.id, success=False, last_run=now)

        loaded = await trigger_store.load_trigger(trigger.id)
        assert loaded.run_count == 1
        assert loaded.failure_count == 1
        assert loaded.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_auto_pause_after_failures(self, trigger_store):
        """Test auto-pausing after consecutive failures."""
        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
        )

        await trigger_store.save_trigger(trigger)

        now = datetime.now(timezone.utc)
        for _ in range(3):
            await trigger_store.increment_run_count(
                trigger.id, success=False, last_run=now
            )

        loaded = await trigger_store.load_trigger(trigger.id)
        assert loaded.status == TriggerStatus.PAUSED
        assert loaded.consecutive_failures == 3

    @pytest.mark.asyncio
    async def test_save_and_load_run(self, trigger_store):
        """Test saving and loading a trigger run."""
        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
        )
        await trigger_store.save_trigger(trigger)

        run = TriggerRun(
            trigger_id=trigger.id,
            trigger_name=trigger.name,
            success=True,
            duration_ms=1000.0,
            result_summary="Success",
        )

        run_id = await trigger_store.save_run(run)
        assert run_id == run.id

        loaded = await trigger_store.load_run(run_id)
        assert loaded is not None
        assert loaded.success is True
        assert loaded.duration_ms == 1000.0

    @pytest.mark.asyncio
    async def test_list_runs(self, trigger_store):
        """Test listing runs for a trigger."""
        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
        )
        await trigger_store.save_trigger(trigger)

        for i in range(5):
            run = TriggerRun(
                trigger_id=trigger.id,
                success=i % 2 == 0,
            )
            await trigger_store.save_run(run)

        runs = await trigger_store.list_runs(trigger.id)
        assert len(runs) == 5

    @pytest.mark.asyncio
    async def test_get_run_stats(self, trigger_store):
        """Test getting aggregate run statistics."""
        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
        )
        await trigger_store.save_trigger(trigger)

        # 3 successful, 2 failed
        for i in range(5):
            run = TriggerRun(
                trigger_id=trigger.id,
                success=i < 3,
                duration_ms=100.0 * (i + 1),
            )
            await trigger_store.save_run(run)

        stats = await trigger_store.get_run_stats(trigger.id)
        assert stats["total_runs"] == 5
        assert stats["successful_runs"] == 3
        assert stats["failed_runs"] == 2
        assert stats["success_rate"] == 0.6

    @pytest.mark.asyncio
    async def test_rate_limiting(self, trigger_store):
        """Test webhook rate limiting."""
        trigger_id = "test-trigger-id"

        # Should be within limit
        within_limit = await trigger_store.check_rate_limit(trigger_id, limit_per_minute=5)
        assert within_limit is True

        # Increment 5 times
        for _ in range(5):
            await trigger_store.increment_rate_limit(trigger_id)

        # Should now be rate limited
        within_limit = await trigger_store.check_rate_limit(trigger_id, limit_per_minute=5)
        assert within_limit is False

    @pytest.mark.asyncio
    async def test_cleanup_rate_limits(self, trigger_store):
        """Test cleaning up old rate limit entries."""
        trigger_id = "test-trigger-id"

        await trigger_store.increment_rate_limit(trigger_id)

        # Cleanup entries older than 0 minutes (should delete all)
        deleted = await trigger_store.cleanup_rate_limits(older_than_minutes=0)
        # Entry is in current minute, so shouldn't be deleted
        assert deleted == 0


# ==============================================================================
# Scheduler Tests
# ==============================================================================


class TestTriggerScheduler:
    """Tests for TriggerScheduler."""

    def test_validate_cron_expression_valid(self):
        """Test validating a valid cron expression."""
        store = MagicMock()
        scheduler = TriggerScheduler(store, MagicMock())

        valid, error = scheduler.validate_cron_expression("0 * * * *")
        assert valid is True
        assert error is None

    def test_validate_cron_expression_invalid(self):
        """Test validating an invalid cron expression."""
        store = MagicMock()
        scheduler = TriggerScheduler(store, MagicMock())

        valid, error = scheduler.validate_cron_expression("invalid")
        assert valid is False
        assert error is not None

    def test_get_next_runs(self):
        """Test calculating next run times."""
        store = MagicMock()
        scheduler = TriggerScheduler(store, MagicMock())

        runs = scheduler.get_next_runs("* * * * *", count=3)
        assert len(runs) == 3

        # Each run should be 1 minute apart
        for i in range(1, len(runs)):
            diff = (runs[i] - runs[i - 1]).total_seconds()
            assert diff == 60

    def test_calculate_next_run(self):
        """Test calculating next run for a trigger."""
        store = MagicMock()
        scheduler = TriggerScheduler(store, MagicMock())

        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
            cron_expression="0 * * * *",  # Every hour
        )

        next_run = scheduler._calculate_next_run(trigger)
        assert next_run is not None
        assert next_run > datetime.now(timezone.utc)

    def test_calculate_next_run_no_expression(self):
        """Test calculating next run without cron expression."""
        store = MagicMock()
        scheduler = TriggerScheduler(store, MagicMock())

        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.WEBHOOK,
            task_description="Test task",
        )

        next_run = scheduler._calculate_next_run(trigger)
        assert next_run is None

    @pytest.mark.asyncio
    async def test_start_and_stop(self, trigger_store):
        """Test starting and stopping the scheduler."""
        executor = MagicMock()
        scheduler = TriggerScheduler(
            trigger_store, executor,
            config=SchedulerConfig(tick_interval_seconds=60),
        )

        # Start
        started = await scheduler.start()
        assert started is True
        assert scheduler.status.value == "running"

        # Don't start again
        started_again = await scheduler.start()
        assert started_again is False

        # Stop
        stopped = await scheduler.stop()
        assert stopped is True
        assert scheduler.status.value == "stopped"


# ==============================================================================
# Executor Tests
# ==============================================================================


class TestTriggerExecutor:
    """Tests for TriggerExecutor."""

    @pytest.mark.asyncio
    async def test_execute_trigger(self, trigger_store):
        """Test executing a trigger."""
        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
        )
        await trigger_store.save_trigger(trigger)

        executor = TriggerExecutor(trigger_store)

        # Mock the orchestrator at the source module
        with patch("sindri.core.orchestrator.Orchestrator") as MockOrchestrator:
            mock_instance = AsyncMock()
            mock_instance.run.return_value = {
                "success": True,
                "task_id": "task-123",
                "result": "Task completed",
            }
            MockOrchestrator.return_value = mock_instance

            run = await executor.execute_trigger(trigger)

            assert run.success is True
            assert run.task_id == "task-123"
            assert run.duration_ms > 0

    @pytest.mark.asyncio
    async def test_execute_trigger_failure(self, trigger_store):
        """Test executing a trigger that fails."""
        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
        )
        await trigger_store.save_trigger(trigger)

        executor = TriggerExecutor(trigger_store)

        # Mock the orchestrator to raise an exception at the source module
        with patch("sindri.core.orchestrator.Orchestrator") as MockOrchestrator:
            mock_instance = AsyncMock()
            mock_instance.run.side_effect = Exception("Task failed")
            MockOrchestrator.return_value = mock_instance

            run = await executor.execute_trigger(trigger)

            assert run.success is False
            assert "Task failed" in run.error


# ==============================================================================
# Notification Tests
# ==============================================================================


class TestNotificationService:
    """Tests for NotificationService."""

    @pytest.mark.asyncio
    async def test_notify_log(self):
        """Test log notification."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            log_path = Path(f.name)

        try:
            service = NotificationService(default_log_path=log_path)

            trigger = TriggerDefinition(
                name="test-trigger",
                trigger_type=TriggerType.CRON,
                task_description="Test task",
                notifications=[
                    NotificationHook(target=NotificationTarget.LOG),
                ],
            )

            run = TriggerRun(
                trigger_id=trigger.id,
                trigger_name=trigger.name,
                success=True,
                result_summary="Success",
            )

            results = await service.notify(trigger, run)

            assert len(results) == 1
            assert results[0]["target"] == "log"
            assert results[0]["success"] is True

            # Check log file contents
            with open(log_path) as f:
                content = f.read()
                assert "test-trigger" in content
                assert '"success": true' in content

        finally:
            if log_path.exists():
                log_path.unlink()

    @pytest.mark.asyncio
    async def test_notify_skip_based_on_status(self):
        """Test that notifications are skipped based on success/failure config."""
        service = NotificationService()

        trigger = TriggerDefinition(
            name="test-trigger",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
            notifications=[
                NotificationHook(
                    target=NotificationTarget.LOG,
                    on_success=False,  # Only notify on failure
                    on_failure=True,
                ),
            ],
        )

        # Successful run should not trigger notification
        run = TriggerRun(
            trigger_id=trigger.id,
            trigger_name=trigger.name,
            success=True,
        )

        results = await service.notify(trigger, run)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_notify_on_failure(self):
        """Test that failure notifications are sent."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            log_path = Path(f.name)

        try:
            service = NotificationService(default_log_path=log_path)

            trigger = TriggerDefinition(
                name="test-trigger",
                trigger_type=TriggerType.CRON,
                task_description="Test task",
                notifications=[
                    NotificationHook(
                        target=NotificationTarget.LOG,
                        on_success=False,
                        on_failure=True,
                    ),
                ],
            )

            # Failed run should trigger notification
            run = TriggerRun(
                trigger_id=trigger.id,
                trigger_name=trigger.name,
                success=False,
                error="Something went wrong",
            )

            results = await service.notify(trigger, run)
            assert len(results) == 1
            assert results[0]["success"] is True

            # Check log file
            with open(log_path) as f:
                content = f.read()
                assert '"success": false' in content
                assert "Something went wrong" in content

        finally:
            if log_path.exists():
                log_path.unlink()


# ==============================================================================
# Event Schema Tests
# ==============================================================================


class TestTriggerEventSchemas:
    """Tests for trigger event schemas."""

    def test_trigger_event_types_exist(self):
        """Test that trigger event types are defined."""
        from sindri.core.events import EventType

        assert hasattr(EventType, "TRIGGER_CREATED")
        assert hasattr(EventType, "TRIGGER_STARTED")
        assert hasattr(EventType, "TRIGGER_COMPLETED")
        assert hasattr(EventType, "TRIGGER_FAILED")
        assert hasattr(EventType, "TRIGGER_SCHEDULER_STARTED")

    def test_trigger_event_schemas_registered(self):
        """Test that trigger event schemas are in the payload models."""
        from sindri.core.event_schemas import EVENT_PAYLOAD_MODELS

        assert "TRIGGER_CREATED" in EVENT_PAYLOAD_MODELS
        assert "TRIGGER_STARTED" in EVENT_PAYLOAD_MODELS
        assert "TRIGGER_COMPLETED" in EVENT_PAYLOAD_MODELS
        assert "TRIGGER_FAILED" in EVENT_PAYLOAD_MODELS

    def test_trigger_started_data_schema(self):
        """Test TriggerStartedData schema."""
        from sindri.core.event_schemas import TriggerStartedData

        data = TriggerStartedData(
            trigger_id="abc123",
            trigger_name="test-trigger",
            trigger_type="cron",
            run_id="run-456",
        )

        assert data.trigger_id == "abc123"
        assert data.trigger_type == "cron"

    def test_trigger_completed_data_schema(self):
        """Test TriggerCompletedData schema."""
        from sindri.core.event_schemas import TriggerCompletedData

        data = TriggerCompletedData(
            trigger_id="abc123",
            trigger_name="test-trigger",
            run_id="run-456",
            task_id="task-789",
            success=True,
            duration_ms=1000.0,
        )

        assert data.success is True
        assert data.duration_ms == 1000.0


# ==============================================================================
# Config Tests
# ==============================================================================


class TestTriggerConfig:
    """Tests for TriggerConfig."""

    def test_trigger_config_defaults(self):
        """Test TriggerConfig default values."""
        from sindri.config import TriggerConfig

        config = TriggerConfig()

        assert config.enabled is True
        assert config.auto_start is False
        assert config.tick_interval_seconds == 30
        assert config.max_concurrent_triggers == 5
        assert config.auto_pause_after_failures == 3

    def test_trigger_config_in_sindri_config(self):
        """Test TriggerConfig is included in SindriConfig."""
        from sindri.config import SindriConfig

        config = SindriConfig()

        assert hasattr(config, "triggers")
        assert config.triggers.enabled is True

    def test_trigger_config_validation(self):
        """Test TriggerConfig field validation."""
        from sindri.config import TriggerConfig

        # Valid config
        config = TriggerConfig(
            tick_interval_seconds=60,
            max_concurrent_triggers=10,
        )
        assert config.tick_interval_seconds == 60

        # Invalid tick interval (too low)
        with pytest.raises(ValueError):
            TriggerConfig(tick_interval_seconds=5)

        # Invalid max concurrent (too high)
        with pytest.raises(ValueError):
            TriggerConfig(max_concurrent_triggers=50)


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestTriggersIntegration:
    """Integration tests for the triggers system."""

    @pytest.mark.asyncio
    async def test_full_trigger_lifecycle(self, trigger_store):
        """Test complete trigger lifecycle: create, run, update, delete."""
        # Create trigger
        trigger = TriggerDefinition(
            name="lifecycle-test",
            trigger_type=TriggerType.CRON,
            task_description="Test lifecycle",
            cron_expression="0 * * * *",
        )

        trigger_id = await trigger_store.save_trigger(trigger)
        assert trigger_id is not None

        # Load and verify
        loaded = await trigger_store.load_trigger(trigger_id)
        assert loaded.name == "lifecycle-test"

        # Update
        await trigger_store.update_trigger(trigger_id, {"name": "updated-name"})
        loaded = await trigger_store.load_trigger(trigger_id)
        assert loaded.name == "updated-name"

        # Simulate a run
        run = TriggerRun(
            trigger_id=trigger_id,
            trigger_name=loaded.name,
            success=True,
            duration_ms=500.0,
        )
        await trigger_store.save_run(run)
        await trigger_store.increment_run_count(
            trigger_id, success=True, last_run=datetime.now(timezone.utc)
        )

        # Verify run count
        loaded = await trigger_store.load_trigger(trigger_id)
        assert loaded.run_count == 1

        # Get run history
        runs = await trigger_store.list_runs(trigger_id)
        assert len(runs) == 1

        # Delete
        deleted = await trigger_store.delete_trigger(trigger_id)
        assert deleted is True

        # Verify deleted
        loaded = await trigger_store.load_trigger(trigger_id)
        assert loaded is None
