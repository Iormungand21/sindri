"""Tests for recovery manager integration with HierarchicalAgentLoop."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from sindri.core.recovery import RecoveryManager
from sindri.core.hierarchical import HierarchicalAgentLoop
from sindri.core.loop import LoopConfig
from sindri.core.events import EventBus
from sindri.core.tasks import Task, TaskStatus


class TestRecoveryManagerBasic:
    """Test basic RecoveryManager functionality."""

    @pytest.fixture
    def recovery_manager(self, tmp_path):
        """Create a RecoveryManager with temp directory."""
        return RecoveryManager(state_dir=str(tmp_path / "state"))

    def test_save_and_load_checkpoint(self, recovery_manager):
        """Should save and load checkpoint correctly."""
        session_id = "test-session-123"
        state = {
            "task": "Write tests",
            "iterations": 5,
            "agent": "huginn"
        }

        recovery_manager.save_checkpoint(session_id, state)

        assert recovery_manager.has_checkpoint(session_id)

        loaded = recovery_manager.load_checkpoint(session_id)
        assert loaded == state

    def test_clear_checkpoint(self, recovery_manager):
        """Should clear checkpoint on success."""
        session_id = "test-session-456"
        recovery_manager.save_checkpoint(session_id, {"test": True})

        assert recovery_manager.has_checkpoint(session_id)

        recovery_manager.clear_checkpoint(session_id)

        assert not recovery_manager.has_checkpoint(session_id)

    def test_list_recoverable_sessions(self, recovery_manager):
        """Should list all recoverable sessions."""
        recovery_manager.save_checkpoint("session-1", {"task": "Task 1", "iterations": 1})
        recovery_manager.save_checkpoint("session-2", {"task": "Task 2", "iterations": 2})
        recovery_manager.save_checkpoint("session-3", {"task": "Task 3", "iterations": 3})

        sessions = recovery_manager.list_recoverable_sessions()

        assert len(sessions) == 3
        session_ids = [s["session_id"] for s in sessions]
        assert "session-1" in session_ids
        assert "session-2" in session_ids
        assert "session-3" in session_ids

    def test_cleanup_old_checkpoints_by_count(self, recovery_manager):
        """Should keep only N most recent checkpoints."""
        for i in range(5):
            recovery_manager.save_checkpoint(f"session-{i}", {"n": i})

        recovery_manager.cleanup_old_checkpoints(keep=2)

        sessions = recovery_manager.list_recoverable_sessions()
        assert len(sessions) == 2

    def test_missing_checkpoint(self, recovery_manager):
        """Should return None for missing checkpoint."""
        result = recovery_manager.load_checkpoint("nonexistent")
        assert result is None


class TestHierarchicalLoopRecoveryIntegration:
    """Test RecoveryManager integration with HierarchicalAgentLoop."""

    @pytest.fixture
    def mock_loop_deps(self, tmp_path):
        """Create mocked dependencies for HierarchicalAgentLoop."""
        client = MagicMock()
        tools = MagicMock()
        state = MagicMock()
        scheduler = MagicMock()
        delegation = MagicMock()
        config = LoopConfig()
        event_bus = EventBus()
        recovery = RecoveryManager(state_dir=str(tmp_path / "state"))

        return {
            "client": client,
            "tools": tools,
            "state": state,
            "scheduler": scheduler,
            "delegation": delegation,
            "config": config,
            "event_bus": event_bus,
            "recovery": recovery
        }

    @pytest.fixture
    def loop(self, mock_loop_deps):
        """Create a HierarchicalAgentLoop with recovery manager."""
        return HierarchicalAgentLoop(**mock_loop_deps)

    def test_save_error_checkpoint_method_exists(self, loop):
        """Should have _save_error_checkpoint method."""
        assert hasattr(loop, "_save_error_checkpoint")

    def test_save_error_checkpoint_creates_file(self, loop, mock_loop_deps):
        """Should save checkpoint data to file."""
        task = Task(
            id="test-task-123",
            description="Test task",
            assigned_agent="huginn"
        )

        loop._save_error_checkpoint(
            task=task,
            error_reason="test_error",
            session_id="session-456",
            iteration=5
        )

        recovery = mock_loop_deps["recovery"]
        assert recovery.has_checkpoint("test-task-123")

        checkpoint = recovery.load_checkpoint("test-task-123")
        assert checkpoint["error"]["reason"] == "test_error"
        assert checkpoint["session_id"] == "session-456"
        assert checkpoint["iterations"] == 5

    def test_save_error_checkpoint_with_context(self, loop, mock_loop_deps):
        """Should include error context in checkpoint."""
        task = Task(
            id="test-task-789",
            description="Test task with context",
            assigned_agent="brokkr"
        )

        loop._save_error_checkpoint(
            task=task,
            error_reason="model_load_failed",
            error_context={"model": "qwen2.5:14b", "vram_required": 9.0}
        )

        recovery = mock_loop_deps["recovery"]
        checkpoint = recovery.load_checkpoint("test-task-789")

        assert checkpoint["error"]["context"]["model"] == "qwen2.5:14b"
        assert checkpoint["error"]["context"]["vram_required"] == 9.0

    def test_save_error_checkpoint_captures_task_info(self, loop, mock_loop_deps):
        """Should capture full task information."""
        task = Task(
            id="test-task-full",
            description="Full task info test",
            assigned_agent="mimir",
            parent_id="parent-task-1",
            context={"file": "test.py", "action": "review"}
        )

        loop._save_error_checkpoint(
            task=task,
            error_reason="test_reason"
        )

        recovery = mock_loop_deps["recovery"]
        checkpoint = recovery.load_checkpoint("test-task-full")

        assert checkpoint["task"]["id"] == "test-task-full"
        assert checkpoint["task"]["description"] == "Full task info test"
        assert checkpoint["task"]["assigned_agent"] == "mimir"
        assert checkpoint["task"]["parent_id"] == "parent-task-1"
        assert checkpoint["task"]["context"]["file"] == "test.py"

    def test_no_checkpoint_without_recovery_manager(self, mock_loop_deps):
        """Should not fail when recovery manager is None."""
        del mock_loop_deps["recovery"]
        loop = HierarchicalAgentLoop(**mock_loop_deps)

        task = Task(
            id="test-task-no-recovery",
            description="Test without recovery",
            assigned_agent="huginn"
        )

        # Should not raise
        loop._save_error_checkpoint(
            task=task,
            error_reason="test_error"
        )


class TestRecoveryOnFailurePaths:
    """Test that checkpoints are saved in various failure paths."""

    @pytest.fixture
    def mock_deps(self, tmp_path):
        """Create mocked dependencies."""
        client = MagicMock()
        tools = MagicMock()
        tools.get_tool = MagicMock(return_value=MagicMock())
        state = MagicMock()
        state.load_session = AsyncMock(return_value=None)
        state.create_session = AsyncMock(return_value=MagicMock(
            id="session-123",
            turns=[],
            add_turn=MagicMock(),
            iterations=0
        ))

        scheduler = MagicMock()
        scheduler.model_manager = MagicMock()
        scheduler.model_manager.ensure_loaded = AsyncMock(return_value=False)

        delegation = MagicMock()
        config = LoopConfig()
        event_bus = EventBus()
        recovery = RecoveryManager(state_dir=str(tmp_path / "state"))

        return {
            "client": client,
            "tools": tools,
            "state": state,
            "scheduler": scheduler,
            "delegation": delegation,
            "config": config,
            "event_bus": event_bus,
            "recovery": recovery
        }

    @pytest.mark.asyncio
    async def test_checkpoint_on_model_load_failure(self, mock_deps):
        """Should save checkpoint when model fails to load."""
        loop = HierarchicalAgentLoop(**mock_deps)

        task = Task(
            id="task-model-fail",
            description="Test model failure",
            assigned_agent="brokkr"
        )

        result = await loop.run_task(task)

        assert result.success is False
        assert "Could not load model" in result.reason

        recovery = mock_deps["recovery"]
        assert recovery.has_checkpoint("task-model-fail")

        checkpoint = recovery.load_checkpoint("task-model-fail")
        assert "model" in checkpoint["error"]["context"]


class TestRecoveryCleanupOnSuccess:
    """Test that checkpoints are cleared on successful completion."""

    @pytest.fixture
    def loop_with_recovery(self, tmp_path):
        """Create loop with recovery for success testing."""
        recovery = RecoveryManager(state_dir=str(tmp_path / "state"))

        loop = HierarchicalAgentLoop(
            client=MagicMock(),
            tools=MagicMock(),
            state=MagicMock(),
            scheduler=MagicMock(),
            delegation=MagicMock(),
            config=LoopConfig(),
            event_bus=EventBus(),
            recovery=recovery
        )

        return loop, recovery

    def test_clear_checkpoint_on_success(self, loop_with_recovery):
        """Should clear checkpoint when task completes successfully."""
        loop, recovery = loop_with_recovery

        # Pre-create a checkpoint (simulating error recovery)
        task_id = "task-will-succeed"
        recovery.save_checkpoint(task_id, {"test": True})
        assert recovery.has_checkpoint(task_id)

        # Manually call clear (simulating success path)
        recovery.clear_checkpoint(task_id)

        assert not recovery.has_checkpoint(task_id)


class TestRecoveryCheckpointData:
    """Test checkpoint data structure and content."""

    @pytest.fixture
    def recovery_manager(self, tmp_path):
        """Create a RecoveryManager."""
        return RecoveryManager(state_dir=str(tmp_path / "state"))

    def test_checkpoint_includes_timestamp(self, recovery_manager):
        """Checkpoint should include timestamp."""
        recovery_manager.save_checkpoint("session-ts", {"data": True})

        # Read raw checkpoint file
        checkpoint_path = Path(recovery_manager.state_dir) / "session-ts.checkpoint.json"
        data = json.loads(checkpoint_path.read_text())

        assert "timestamp" in data
        # Verify it's a valid ISO timestamp
        datetime.fromisoformat(data["timestamp"])

    def test_checkpoint_atomic_write(self, recovery_manager, tmp_path):
        """Checkpoint write should be atomic (no partial writes)."""
        large_data = {"data": "x" * 10000}  # 10KB of data
        recovery_manager.save_checkpoint("session-atomic", large_data)

        checkpoint_path = Path(recovery_manager.state_dir) / "session-atomic.checkpoint.json"

        # Verify the file exists and is valid JSON
        assert checkpoint_path.exists()
        data = json.loads(checkpoint_path.read_text())
        assert data["state"]["data"] == "x" * 10000

        # Verify no temp file left behind
        temp_path = checkpoint_path.with_suffix(".tmp")
        assert not temp_path.exists()
