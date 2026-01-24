"""Tests for Sindri Web API - Triggers Endpoints.

Tests for the /api/triggers/* REST API endpoints.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from sindri.web.server import create_app
from sindri.triggers.models import (
    TriggerDefinition,
    TriggerRun,
    TriggerType,
    TriggerStatus,
    NotificationHook,
    NotificationTarget,
)


# ===== Fixtures =====


@pytest.fixture
def app():
    """Create test application."""
    return create_app(vram_gb=16.0)


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_trigger():
    """Create a sample trigger for testing."""
    return TriggerDefinition(
        id="test-trigger-123",
        name="Test Trigger",
        description="A test trigger",
        trigger_type=TriggerType.CRON,
        status=TriggerStatus.ENABLED,
        task_description="Run tests",
        agent="brokkr",
        max_iterations=30,
        cron_expression="0 2 * * *",
        timezone="UTC",
        run_count=5,
        failure_count=1,
    )


@pytest.fixture
def sample_run():
    """Create a sample trigger run for testing."""
    return TriggerRun(
        id="run-123",
        trigger_id="test-trigger-123",
        trigger_name="Test Trigger",
        task_id="task-456",
        session_id="session-789",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_ms=1500.5,
        success=True,
        result_summary="Tests passed",
    )


# ===== List Triggers Tests =====


class TestListTriggers:
    """Tests for GET /api/triggers."""

    def test_list_triggers_empty(self, client):
        """Test listing triggers when empty."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.list_triggers = AsyncMock(return_value=[])
            MockStore.return_value = mock_instance

            response = client.get("/api/triggers")
            assert response.status_code == 200
            assert response.json() == []

    def test_list_triggers_with_data(self, client, sample_trigger):
        """Test listing triggers with data."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.list_triggers = AsyncMock(return_value=[sample_trigger])
            MockStore.return_value = mock_instance

            response = client.get("/api/triggers")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["name"] == "Test Trigger"
            assert data[0]["trigger_type"] == "cron"

    def test_list_triggers_with_type_filter(self, client):
        """Test listing triggers with type filter."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.list_triggers = AsyncMock(return_value=[])
            MockStore.return_value = mock_instance

            response = client.get("/api/triggers?trigger_type=cron")
            assert response.status_code == 200

            # Verify filter was passed
            mock_instance.list_triggers.assert_called_once()
            call_kwargs = mock_instance.list_triggers.call_args[1]
            assert call_kwargs["trigger_type"] == TriggerType.CRON

    def test_list_triggers_invalid_type(self, client):
        """Test listing triggers with invalid type filter."""
        response = client.get("/api/triggers?trigger_type=invalid")
        assert response.status_code == 400
        assert "Invalid trigger_type" in response.json()["detail"]

    def test_list_triggers_with_status_filter(self, client):
        """Test listing triggers with status filter."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.list_triggers = AsyncMock(return_value=[])
            MockStore.return_value = mock_instance

            response = client.get("/api/triggers?status=enabled")
            assert response.status_code == 200

            # Verify filter was passed
            call_kwargs = mock_instance.list_triggers.call_args[1]
            assert call_kwargs["status"] == TriggerStatus.ENABLED

    def test_list_triggers_invalid_status(self, client):
        """Test listing triggers with invalid status filter."""
        response = client.get("/api/triggers?status=invalid")
        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]


# ===== Get Trigger Tests =====


class TestGetTrigger:
    """Tests for GET /api/triggers/{trigger_id}."""

    def test_get_trigger_success(self, client, sample_trigger):
        """Test getting a trigger by ID."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(return_value=sample_trigger)
            MockStore.return_value = mock_instance

            response = client.get("/api/triggers/test-trigger-123")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "test-trigger-123"
            assert data["name"] == "Test Trigger"

    def test_get_trigger_not_found(self, client):
        """Test 404 for non-existent trigger."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(return_value=None)
            MockStore.return_value = mock_instance

            response = client.get("/api/triggers/nonexistent")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]


# ===== Create Trigger Tests =====


class TestCreateTrigger:
    """Tests for POST /api/triggers."""

    def test_create_cron_trigger(self, client):
        """Test creating a cron trigger."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.save_trigger = AsyncMock(return_value="new-id")
            MockStore.return_value = mock_instance

            with patch("sindri.triggers.scheduler.TriggerScheduler") as MockScheduler:
                mock_scheduler = MagicMock()
                mock_scheduler.validate_cron_expression.return_value = (True, None)
                mock_scheduler._calculate_next_run.return_value = datetime.now(
                    timezone.utc
                )
                MockScheduler.return_value = mock_scheduler

                response = client.post(
                    "/api/triggers",
                    json={
                        "name": "New Cron Trigger",
                        "trigger_type": "cron",
                        "task_description": "Run daily tests",
                        "cron_expression": "0 2 * * *",
                    },
                )

                assert response.status_code == 200
                data = response.json()
                assert data["name"] == "New Cron Trigger"
                assert data["trigger_type"] == "cron"
                assert data["cron_expression"] == "0 2 * * *"

    def test_create_webhook_trigger(self, client):
        """Test creating a webhook trigger."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.save_trigger = AsyncMock(return_value="new-id")
            MockStore.return_value = mock_instance

            response = client.post(
                "/api/triggers",
                json={
                    "name": "Webhook Trigger",
                    "trigger_type": "webhook",
                    "task_description": "Handle webhook",
                    "webhook_secret": "secret123",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["trigger_type"] == "webhook"

    def test_create_event_trigger(self, client):
        """Test creating an event trigger."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.save_trigger = AsyncMock(return_value="new-id")
            MockStore.return_value = mock_instance

            response = client.post(
                "/api/triggers",
                json={
                    "name": "Event Trigger",
                    "trigger_type": "event",
                    "task_description": "Handle event",
                    "event_types": ["TASK_COMPLETED"],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["trigger_type"] == "event"
            assert "TASK_COMPLETED" in data["event_types"]

    def test_create_trigger_invalid_type(self, client):
        """Test validation for invalid trigger type."""
        response = client.post(
            "/api/triggers",
            json={
                "name": "Bad Trigger",
                "trigger_type": "invalid",
                "task_description": "Do something",
            },
        )

        assert response.status_code == 400
        assert "Invalid trigger type" in response.json()["detail"]

    def test_create_cron_trigger_invalid_expression(self, client):
        """Test validation for invalid cron expression."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            MockStore.return_value = mock_instance

            with patch("sindri.triggers.scheduler.TriggerScheduler") as MockScheduler:
                mock_scheduler = MagicMock()
                mock_scheduler.validate_cron_expression.return_value = (
                    False,
                    "Invalid syntax",
                )
                MockScheduler.return_value = mock_scheduler

                response = client.post(
                    "/api/triggers",
                    json={
                        "name": "Bad Cron",
                        "trigger_type": "cron",
                        "task_description": "Run tests",
                        "cron_expression": "invalid cron",
                    },
                )

                assert response.status_code == 400
                assert "Invalid cron expression" in response.json()["detail"]

    def test_create_cron_trigger_missing_expression(self, client):
        """Test cron trigger requires expression."""
        response = client.post(
            "/api/triggers",
            json={
                "name": "Missing Cron",
                "trigger_type": "cron",
                "task_description": "Run tests",
            },
        )

        assert response.status_code == 400
        assert "cron_expression is required" in response.json()["detail"]


# ===== Update Trigger Tests =====


class TestUpdateTrigger:
    """Tests for PUT /api/triggers/{trigger_id}."""

    def test_update_trigger_name(self, client, sample_trigger):
        """Test updating trigger name."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(return_value=sample_trigger)
            mock_instance.update_trigger = AsyncMock(return_value=True)

            # Return updated trigger after update
            updated_trigger = TriggerDefinition(
                **{**sample_trigger.model_dump(), "name": "Updated Name"}
            )
            mock_instance.load_trigger = AsyncMock(
                side_effect=[sample_trigger, updated_trigger]
            )
            MockStore.return_value = mock_instance

            response = client.put(
                "/api/triggers/test-trigger-123",
                json={"name": "Updated Name"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Updated Name"

    def test_update_trigger_not_found(self, client):
        """Test updating non-existent trigger."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(return_value=None)
            MockStore.return_value = mock_instance

            response = client.put(
                "/api/triggers/nonexistent",
                json={"name": "Updated Name"},
            )

            assert response.status_code == 404

    def test_update_trigger_no_fields(self, client, sample_trigger):
        """Test updating with no fields."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(return_value=sample_trigger)
            MockStore.return_value = mock_instance

            response = client.put(
                "/api/triggers/test-trigger-123",
                json={},
            )

            assert response.status_code == 400
            assert "No fields to update" in response.json()["detail"]


# ===== Delete Trigger Tests =====


class TestDeleteTrigger:
    """Tests for DELETE /api/triggers/{trigger_id}."""

    def test_delete_trigger_success(self, client, sample_trigger):
        """Test deleting a trigger."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(return_value=sample_trigger)
            mock_instance.delete_trigger = AsyncMock(return_value=True)
            MockStore.return_value = mock_instance

            response = client.delete("/api/triggers/test-trigger-123")

            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Trigger deleted"
            assert data["trigger_id"] == "test-trigger-123"

    def test_delete_trigger_not_found(self, client):
        """Test deleting non-existent trigger."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(return_value=None)
            MockStore.return_value = mock_instance

            response = client.delete("/api/triggers/nonexistent")
            assert response.status_code == 404


# ===== Enable/Disable Trigger Tests =====


class TestEnableDisableTrigger:
    """Tests for POST /api/triggers/{trigger_id}/enable and /disable."""

    def test_enable_trigger(self, client, sample_trigger):
        """Test enabling a trigger."""
        disabled_trigger = TriggerDefinition(
            **{**sample_trigger.model_dump(), "status": TriggerStatus.DISABLED}
        )
        enabled_trigger = TriggerDefinition(
            **{**sample_trigger.model_dump(), "status": TriggerStatus.ENABLED}
        )

        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(
                side_effect=[disabled_trigger, enabled_trigger]
            )
            mock_instance.update_trigger = AsyncMock(return_value=True)
            MockStore.return_value = mock_instance

            response = client.post("/api/triggers/test-trigger-123/enable")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "enabled"

    def test_disable_trigger(self, client, sample_trigger):
        """Test disabling a trigger."""
        disabled_trigger = TriggerDefinition(
            **{**sample_trigger.model_dump(), "status": TriggerStatus.DISABLED}
        )

        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(
                side_effect=[sample_trigger, disabled_trigger]
            )
            mock_instance.update_trigger = AsyncMock(return_value=True)
            MockStore.return_value = mock_instance

            response = client.post("/api/triggers/test-trigger-123/disable")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "disabled"

    def test_enable_trigger_not_found(self, client):
        """Test enabling non-existent trigger."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(return_value=None)
            MockStore.return_value = mock_instance

            response = client.post("/api/triggers/nonexistent/enable")
            assert response.status_code == 404


# ===== Run Trigger Tests =====


class TestRunTrigger:
    """Tests for POST /api/triggers/{trigger_id}/run."""

    def test_run_trigger_success(self, client, sample_trigger, sample_run):
        """Test manually running a trigger."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load_trigger = AsyncMock(return_value=sample_trigger)
            MockStore.return_value = mock_store

            with patch("sindri.triggers.executor.TriggerExecutor") as MockExecutor:
                mock_executor = MagicMock()
                mock_executor.execute_trigger = AsyncMock(return_value=sample_run)
                MockExecutor.return_value = mock_executor

                response = client.post("/api/triggers/test-trigger-123/run")

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["trigger_id"] == "test-trigger-123"

    def test_run_trigger_with_context(self, client, sample_trigger, sample_run):
        """Test running trigger with context."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load_trigger = AsyncMock(return_value=sample_trigger)
            MockStore.return_value = mock_store

            with patch("sindri.triggers.executor.TriggerExecutor") as MockExecutor:
                mock_executor = MagicMock()
                mock_executor.execute_trigger = AsyncMock(return_value=sample_run)
                MockExecutor.return_value = mock_executor

                response = client.post(
                    "/api/triggers/test-trigger-123/run",
                    json={"context": {"key": "value"}},
                )

                assert response.status_code == 200
                # Verify context was passed
                mock_executor.execute_trigger.assert_called_once()
                call_kwargs = mock_executor.execute_trigger.call_args[1]
                assert call_kwargs["context"] == {"key": "value"}

    def test_run_trigger_not_found(self, client):
        """Test running non-existent trigger."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_store = MagicMock()
            mock_store.load_trigger = AsyncMock(return_value=None)
            MockStore.return_value = mock_store

            response = client.post("/api/triggers/nonexistent/run")
            assert response.status_code == 404


# ===== Run History Tests =====


class TestTriggerRuns:
    """Tests for GET /api/triggers/{trigger_id}/runs and /runs/{run_id}."""

    def test_get_trigger_runs(self, client, sample_trigger, sample_run):
        """Test getting run history."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(return_value=sample_trigger)
            mock_instance.list_runs = AsyncMock(return_value=[sample_run])
            MockStore.return_value = mock_instance

            response = client.get("/api/triggers/test-trigger-123/runs")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == "run-123"
            assert data[0]["success"] is True

    def test_get_trigger_runs_trigger_not_found(self, client):
        """Test getting runs for non-existent trigger."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(return_value=None)
            MockStore.return_value = mock_instance

            response = client.get("/api/triggers/nonexistent/runs")
            assert response.status_code == 404

    def test_get_single_run(self, client, sample_trigger, sample_run):
        """Test getting a specific run."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(return_value=sample_trigger)
            mock_instance.load_run = AsyncMock(return_value=sample_run)
            MockStore.return_value = mock_instance

            response = client.get("/api/triggers/test-trigger-123/runs/run-123")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "run-123"

    def test_get_single_run_not_found(self, client, sample_trigger):
        """Test getting non-existent run."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.load_trigger = AsyncMock(return_value=sample_trigger)
            mock_instance.load_run = AsyncMock(return_value=None)
            MockStore.return_value = mock_instance

            response = client.get("/api/triggers/test-trigger-123/runs/nonexistent")
            assert response.status_code == 404


# ===== Stats Tests =====


class TestTriggerStats:
    """Tests for GET /api/triggers/stats."""

    def test_get_trigger_stats(self, client, sample_trigger):
        """Test getting aggregate statistics."""
        triggers = [
            sample_trigger,
            TriggerDefinition(
                name="Trigger 2",
                trigger_type=TriggerType.WEBHOOK,
                task_description="Task 2",
                status=TriggerStatus.DISABLED,
                run_count=10,
                failure_count=2,
            ),
            TriggerDefinition(
                name="Trigger 3",
                trigger_type=TriggerType.EVENT,
                task_description="Task 3",
                status=TriggerStatus.PAUSED,
                run_count=3,
                failure_count=3,
            ),
        ]

        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.list_triggers = AsyncMock(return_value=triggers)
            MockStore.return_value = mock_instance

            response = client.get("/api/triggers/stats")

            assert response.status_code == 200
            data = response.json()

            assert data["total_triggers"] == 3
            assert data["enabled_triggers"] == 1
            assert data["disabled_triggers"] == 1
            assert data["paused_triggers"] == 1
            assert data["total_runs"] == 18  # 5 + 10 + 3
            assert data["failed_runs"] == 6  # 1 + 2 + 3
            assert data["successful_runs"] == 12
            assert data["by_type"]["cron"] == 1
            assert data["by_type"]["webhook"] == 1
            assert data["by_type"]["event"] == 1

    def test_get_trigger_stats_empty(self, client):
        """Test stats with no triggers."""
        with patch("sindri.triggers.store.TriggerStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.list_triggers = AsyncMock(return_value=[])
            MockStore.return_value = mock_instance

            response = client.get("/api/triggers/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["total_triggers"] == 0
            assert data["success_rate"] == 0.0
