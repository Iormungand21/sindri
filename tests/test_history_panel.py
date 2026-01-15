"""Tests for Task History Panel widget.

Phase 5.5: Task History Panel implementation tests.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from sindri.tui.widgets.history import (
    TaskHistoryPanel,
    SessionItem,
    SessionItemContent,
    SessionSelected,
)


class TestSessionItemContent:
    """Tests for SessionItemContent rendering."""

    def test_render_completed_session(self):
        """Test rendering a completed session."""
        content = SessionItemContent(
            session_id="abc12345-1234-5678-abcd-123456789012",
            task="Create a hello world function",
            status="completed",
            created_at="2026-01-15T10:30:00",
            iterations=5,
            model="qwen2.5-coder:14b",
        )

        rendered = content.render()
        text = rendered.plain

        # Check status icon is displayed
        assert "[OK]" in text
        # Check task is displayed
        assert "hello world" in text
        # Check iteration count
        assert "5 iter" in text
        # Check model name (truncated to 12 chars)
        assert "qwen2.5-code" in text

    def test_render_failed_session(self):
        """Test rendering a failed session."""
        content = SessionItemContent(
            session_id="fail1234-1234-5678-abcd-123456789012",
            task="Task that failed",
            status="failed",
            created_at="2026-01-15T11:00:00",
            iterations=3,
            model="llama3.1:8b",
        )

        rendered = content.render()
        text = rendered.plain

        assert "[!!]" in text
        assert "failed" in text.lower() or "Task" in text

    def test_render_active_session(self):
        """Test rendering an active session."""
        content = SessionItemContent(
            session_id="active12-1234-5678-abcd-123456789012",
            task="Currently running task",
            status="active",
            created_at="2026-01-15T12:00:00",
            iterations=10,
            model="qwen2.5:3b",
        )

        rendered = content.render()
        text = rendered.plain

        assert "[~~]" in text

    def test_render_cancelled_session(self):
        """Test rendering a cancelled session."""
        content = SessionItemContent(
            session_id="cancel12-1234-5678-abcd-123456789012",
            task="Cancelled task",
            status="cancelled",
            created_at="2026-01-15T13:00:00",
            iterations=2,
            model="qwen2.5-coder:7b",
        )

        rendered = content.render()
        text = rendered.plain

        assert "[--]" in text

    def test_render_unknown_status(self):
        """Test rendering a session with unknown status."""
        content = SessionItemContent(
            session_id="unknown1-1234-5678-abcd-123456789012",
            task="Unknown status task",
            status="weird_status",
            created_at="2026-01-15T14:00:00",
            iterations=1,
            model="custom:model",
        )

        rendered = content.render()
        text = rendered.plain

        assert "[??]" in text

    def test_render_long_task_truncation(self):
        """Test that long task descriptions are truncated."""
        long_task = "This is a very long task description that should be truncated at some point because it exceeds the maximum length"
        content = SessionItemContent(
            session_id="long1234-1234-5678-abcd-123456789012",
            task=long_task,
            status="completed",
            created_at="2026-01-15T15:00:00",
            iterations=5,
            model="qwen2.5:14b",
        )

        rendered = content.render()
        text = rendered.plain

        # Task should be truncated with "..."
        assert "..." in text
        # Should not contain the full task
        assert long_task not in text

    def test_render_timestamp_formatting(self):
        """Test that timestamps are formatted correctly."""
        content = SessionItemContent(
            session_id="time1234-1234-5678-abcd-123456789012",
            task="Test task",
            status="completed",
            created_at="2026-03-25T14:30:00",
            iterations=3,
            model="test:model",
        )

        rendered = content.render()
        text = rendered.plain

        # Should format as MM/DD HH:MM
        assert "03/25" in text or "14:30" in text


class TestSessionItem:
    """Tests for SessionItem widget."""

    def test_session_item_stores_data(self):
        """Test that SessionItem stores session data."""
        item = SessionItem(
            session_id="store123-1234-5678-abcd-123456789012",
            task="Test task storage",
            status="completed",
            created_at="2026-01-15T10:00:00",
            iterations=7,
            model="qwen2.5-coder:14b",
        )

        assert item.session_id == "store123-1234-5678-abcd-123456789012"
        assert item.task_description == "Test task storage"
        assert item.status == "completed"
        assert item.iterations == 7
        assert item.model == "qwen2.5-coder:14b"


class TestTaskHistoryPanel:
    """Tests for TaskHistoryPanel widget."""

    def test_panel_init(self):
        """Test panel initializes correctly."""
        panel = TaskHistoryPanel()
        assert panel._session_items == []
        assert panel.visible is True

    def test_add_session(self):
        """Test adding a single session."""
        panel = TaskHistoryPanel()
        panel._session_items = []  # Reset for testing

        panel.add_session(
            session_id="add12345-1234-5678-abcd-123456789012",
            task="Added task",
            status="completed",
            created_at="2026-01-15T10:00:00",
            iterations=5,
            model="qwen2.5:14b",
        )

        assert len(panel._session_items) == 1
        assert panel._session_items[0]["task"] == "Added task"
        assert panel._session_items[0]["status"] == "completed"

    def test_add_multiple_sessions(self):
        """Test adding multiple sessions."""
        panel = TaskHistoryPanel()
        panel._session_items = []

        for i in range(5):
            panel.add_session(
                session_id=f"multi{i:04d}-1234-5678-abcd-123456789012",
                task=f"Task number {i}",
                status="completed" if i % 2 == 0 else "failed",
                created_at=f"2026-01-15T{10+i:02d}:00:00",
                iterations=i + 1,
                model="qwen2.5:14b",
            )

        assert len(panel._session_items) == 5

    def test_clear_sessions(self):
        """Test clearing all sessions."""
        panel = TaskHistoryPanel()
        panel._session_items = []

        # Add some sessions
        panel.add_session(
            session_id="clear123-1234-5678-abcd-123456789012",
            task="Task to clear",
            status="completed",
            created_at="2026-01-15T10:00:00",
            iterations=3,
            model="qwen2.5:14b",
        )
        panel.add_session(
            session_id="clear456-1234-5678-abcd-123456789012",
            task="Another task",
            status="failed",
            created_at="2026-01-15T11:00:00",
            iterations=2,
            model="qwen2.5:7b",
        )

        assert len(panel._session_items) == 2

        # Clear sessions
        panel.clear_sessions()

        assert len(panel._session_items) == 0

    def test_set_sessions(self):
        """Test setting sessions from a list."""
        panel = TaskHistoryPanel()

        sessions = [
            {
                "id": "set12345-1234-5678-abcd-123456789012",
                "task": "First task",
                "status": "completed",
                "created_at": "2026-01-15T10:00:00",
                "iterations": 5,
                "model": "qwen2.5:14b",
            },
            {
                "id": "set67890-1234-5678-abcd-123456789012",
                "task": "Second task",
                "status": "failed",
                "created_at": "2026-01-15T11:00:00",
                "iterations": 3,
                "model": "llama3.1:8b",
            },
        ]

        panel.set_sessions(sessions)

        assert len(panel._session_items) == 2
        assert panel._session_items[0]["task"] == "First task"
        assert panel._session_items[1]["task"] == "Second task"

    def test_set_sessions_replaces_existing(self):
        """Test that set_sessions replaces existing sessions."""
        panel = TaskHistoryPanel()

        # Add initial session
        panel.add_session(
            session_id="old12345-1234-5678-abcd-123456789012",
            task="Old task",
            status="completed",
            created_at="2026-01-15T09:00:00",
            iterations=2,
            model="qwen2.5:3b",
        )

        # Set new sessions
        new_sessions = [
            {
                "id": "new12345-1234-5678-abcd-123456789012",
                "task": "New task",
                "status": "completed",
                "created_at": "2026-01-15T10:00:00",
                "iterations": 5,
                "model": "qwen2.5:14b",
            },
        ]

        panel.set_sessions(new_sessions)

        # Should only have the new session
        assert len(panel._session_items) == 1
        assert panel._session_items[0]["task"] == "New task"

    def test_get_session_count(self):
        """Test getting session count."""
        panel = TaskHistoryPanel()
        panel._session_items = []

        assert panel.get_session_count() == 0

        panel.add_session(
            session_id="count123-1234-5678-abcd-123456789012",
            task="Task 1",
            status="completed",
            created_at="2026-01-15T10:00:00",
            iterations=3,
            model="qwen2.5:14b",
        )

        assert panel.get_session_count() == 1

        panel.add_session(
            session_id="count456-1234-5678-abcd-123456789012",
            task="Task 2",
            status="failed",
            created_at="2026-01-15T11:00:00",
            iterations=2,
            model="qwen2.5:7b",
        )

        assert panel.get_session_count() == 2

    def test_get_session_ids(self):
        """Test getting list of session IDs."""
        panel = TaskHistoryPanel()
        panel._session_items = []

        assert panel.get_session_ids() == []

        panel.add_session(
            session_id="ids12345-1234-5678-abcd-123456789012",
            task="Task 1",
            status="completed",
            created_at="2026-01-15T10:00:00",
            iterations=3,
            model="qwen2.5:14b",
        )

        panel.add_session(
            session_id="ids67890-1234-5678-abcd-123456789012",
            task="Task 2",
            status="failed",
            created_at="2026-01-15T11:00:00",
            iterations=2,
            model="qwen2.5:7b",
        )

        ids = panel.get_session_ids()

        assert len(ids) == 2
        assert "ids12345-1234-5678-abcd-123456789012" in ids
        assert "ids67890-1234-5678-abcd-123456789012" in ids


class TestSessionSelectedMessage:
    """Tests for SessionSelected message."""

    def test_message_creation(self):
        """Test creating SessionSelected message."""
        message = SessionSelected(
            session_id="msg12345-1234-5678-abcd-123456789012",
            task="Selected task",
        )

        assert message.session_id == "msg12345-1234-5678-abcd-123456789012"
        assert message.task == "Selected task"

    def test_message_with_long_task(self):
        """Test message with long task description."""
        long_task = "This is a very long task description " * 10
        message = SessionSelected(
            session_id="long1234-1234-5678-abcd-123456789012",
            task=long_task,
        )

        assert message.task == long_task


class TestTaskHistoryPanelAsync:
    """Async tests for TaskHistoryPanel."""

    @pytest.mark.asyncio
    async def test_load_sessions_from_database(self):
        """Test loading sessions from database."""
        panel = TaskHistoryPanel()

        # Mock the SessionState
        mock_sessions = [
            {
                "id": "db123456-1234-5678-abcd-123456789012",
                "task": "Database task 1",
                "status": "completed",
                "created_at": "2026-01-15T10:00:00",
                "iterations": 5,
                "model": "qwen2.5-coder:14b",
            },
            {
                "id": "db789012-1234-5678-abcd-123456789012",
                "task": "Database task 2",
                "status": "failed",
                "created_at": "2026-01-15T11:00:00",
                "iterations": 3,
                "model": "llama3.1:8b",
            },
        ]

        with patch('sindri.persistence.state.SessionState') as MockState:
            mock_state_instance = AsyncMock()
            mock_state_instance.list_sessions = AsyncMock(return_value=mock_sessions)
            MockState.return_value = mock_state_instance

            await panel.load_sessions(limit=20)

            # Verify sessions were set
            assert len(panel._session_items) == 2
            assert panel._session_items[0]["task"] == "Database task 1"
            assert panel._session_items[1]["task"] == "Database task 2"

    @pytest.mark.asyncio
    async def test_load_sessions_empty_database(self):
        """Test loading from empty database."""
        panel = TaskHistoryPanel()

        with patch('sindri.persistence.state.SessionState') as MockState:
            mock_state_instance = AsyncMock()
            mock_state_instance.list_sessions = AsyncMock(return_value=[])
            MockState.return_value = mock_state_instance

            await panel.load_sessions(limit=20)

            assert len(panel._session_items) == 0

    @pytest.mark.asyncio
    async def test_load_sessions_respects_limit(self):
        """Test that limit parameter is passed correctly."""
        panel = TaskHistoryPanel()

        with patch('sindri.persistence.state.SessionState') as MockState:
            mock_state_instance = AsyncMock()
            mock_state_instance.list_sessions = AsyncMock(return_value=[])
            MockState.return_value = mock_state_instance

            await panel.load_sessions(limit=5)

            mock_state_instance.list_sessions.assert_called_once_with(limit=5)


class TestHistoryPanelEdgeCases:
    """Edge case tests for history panel."""

    def test_empty_task_description(self):
        """Test handling empty task description."""
        content = SessionItemContent(
            session_id="empty123-1234-5678-abcd-123456789012",
            task="",
            status="completed",
            created_at="2026-01-15T10:00:00",
            iterations=1,
            model="qwen2.5:14b",
        )

        # Should not raise
        rendered = content.render()
        assert rendered is not None

    def test_zero_iterations(self):
        """Test handling zero iterations."""
        content = SessionItemContent(
            session_id="zero1234-1234-5678-abcd-123456789012",
            task="Task with zero iterations",
            status="completed",
            created_at="2026-01-15T10:00:00",
            iterations=0,
            model="qwen2.5:14b",
        )

        rendered = content.render()
        text = rendered.plain

        assert "0 iter" in text

    def test_invalid_timestamp_format(self):
        """Test handling invalid timestamp format."""
        content = SessionItemContent(
            session_id="time1234-1234-5678-abcd-123456789012",
            task="Task with bad timestamp",
            status="completed",
            created_at="not-a-valid-timestamp",
            iterations=3,
            model="qwen2.5:14b",
        )

        # Should not raise, should use fallback formatting
        rendered = content.render()
        assert rendered is not None

    def test_special_characters_in_task(self):
        """Test handling special characters in task description."""
        special_task = "Task with <special> & 'chars' \"quoted\" stuff"
        content = SessionItemContent(
            session_id="spec1234-1234-5678-abcd-123456789012",
            task=special_task,
            status="completed",
            created_at="2026-01-15T10:00:00",
            iterations=3,
            model="qwen2.5:14b",
        )

        rendered = content.render()
        text = rendered.plain

        # Should contain some part of the task
        assert "special" in text or "chars" in text

    def test_model_without_version(self):
        """Test model name without version tag."""
        content = SessionItemContent(
            session_id="model123-1234-5678-abcd-123456789012",
            task="Test task",
            status="completed",
            created_at="2026-01-15T10:00:00",
            iterations=3,
            model="custommodel",  # No :version suffix
        )

        rendered = content.render()
        text = rendered.plain

        assert "custommodel" in text

    def test_set_sessions_with_missing_fields(self):
        """Test set_sessions with missing optional fields."""
        panel = TaskHistoryPanel()

        sessions = [
            {
                "id": "partial1-1234-5678-abcd-123456789012",
                # Missing: task, status, created_at, iterations, model
            },
        ]

        # Should not raise, should use defaults
        panel.set_sessions(sessions)

        assert len(panel._session_items) == 1
        assert panel._session_items[0]["task"] == "Unknown task"
        assert panel._session_items[0]["status"] == "unknown"
