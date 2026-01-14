"""Test crash recovery system."""

import pytest
import json
from datetime import datetime
from pathlib import Path


def test_checkpoint_save_load(recovery_manager):
    """Checkpoints should save and load correctly."""

    state = {
        "task": "test task",
        "iteration": 5,
        "agent": "brokkr",
        "messages": [{"role": "user", "content": "test"}]
    }

    session_id = "session-123"
    recovery_manager.save_checkpoint(session_id, state)

    assert recovery_manager.has_checkpoint(session_id)

    loaded = recovery_manager.load_checkpoint(session_id)
    assert loaded == state
    assert loaded["iteration"] == 5


def test_checkpoint_not_exists(recovery_manager):
    """Loading non-existent checkpoint returns None."""

    loaded = recovery_manager.load_checkpoint("non-existent-session")
    assert loaded is None
    assert not recovery_manager.has_checkpoint("non-existent-session")


def test_checkpoint_atomic_write(recovery_manager, temp_dir):
    """Checkpoints should be written atomically."""

    session_id = "session-atomic"
    state = {"test": "data"}

    recovery_manager.save_checkpoint(session_id, state)

    # Check that temp file was cleaned up
    checkpoint_dir = temp_dir / "state"
    temp_files = list(checkpoint_dir.glob("*.tmp"))
    assert len(temp_files) == 0, "Temporary files should be cleaned up"

    # Check final file exists
    checkpoint_file = checkpoint_dir / f"{session_id}.checkpoint.json"
    assert checkpoint_file.exists()

    # Verify content
    data = json.loads(checkpoint_file.read_text())
    assert data["session_id"] == session_id
    assert data["state"] == state
    assert "timestamp" in data


def test_clear_checkpoint(recovery_manager):
    """Clearing checkpoint should remove the file."""

    session_id = "session-clear"
    recovery_manager.save_checkpoint(session_id, {"test": "data"})

    assert recovery_manager.has_checkpoint(session_id)

    recovery_manager.clear_checkpoint(session_id)

    assert not recovery_manager.has_checkpoint(session_id)


def test_list_recoverable_sessions(recovery_manager):
    """Listing recoverable sessions should return all checkpoints."""

    # Create multiple checkpoints
    sessions = [
        ("session-1", {"task": "Task 1"}),
        ("session-2", {"task": "Task 2"}),
        ("session-3", {"task": "Task 3"}),
    ]

    for session_id, state in sessions:
        recovery_manager.save_checkpoint(session_id, state)

    recoverable = recovery_manager.list_recoverable_sessions()

    assert len(recoverable) == 3

    # Should be sorted by timestamp (most recent first)
    assert all("session_id" in s for s in recoverable)
    assert all("timestamp" in s for s in recoverable)
    assert all("task" in s for s in recoverable)

    session_ids = {s["session_id"] for s in recoverable}
    assert session_ids == {"session-1", "session-2", "session-3"}


def test_checkpoint_corrupted_json(recovery_manager, temp_dir):
    """Loading corrupted checkpoint should return None."""

    session_id = "session-corrupted"
    checkpoint_dir = temp_dir / "state"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_file = checkpoint_dir / f"{session_id}.checkpoint.json"
    checkpoint_file.write_text("{ invalid json }")

    loaded = recovery_manager.load_checkpoint(session_id)
    assert loaded is None


def test_checkpoint_overwrite(recovery_manager):
    """Overwriting checkpoint should update the data."""

    session_id = "session-overwrite"

    # Save initial checkpoint
    recovery_manager.save_checkpoint(session_id, {"iteration": 1})
    first_load = recovery_manager.load_checkpoint(session_id)
    assert first_load["iteration"] == 1

    # Overwrite
    recovery_manager.save_checkpoint(session_id, {"iteration": 5})
    second_load = recovery_manager.load_checkpoint(session_id)
    assert second_load["iteration"] == 5


def test_cleanup_old_checkpoints(recovery_manager):
    """Old checkpoints should be cleaned up."""

    # Create multiple checkpoints
    for i in range(15):
        recovery_manager.save_checkpoint(f"session-{i}", {"index": i})

    # Cleanup keeping only 5 most recent
    recovery_manager.cleanup_old_checkpoints(keep=5)

    recoverable = recovery_manager.list_recoverable_sessions()
    assert len(recoverable) <= 5

    # Most recent should still exist
    assert recovery_manager.has_checkpoint("session-14")
    assert recovery_manager.has_checkpoint("session-13")

    # Oldest should be gone
    assert not recovery_manager.has_checkpoint("session-0")
    assert not recovery_manager.has_checkpoint("session-1")


def test_checkpoint_directory_creation(temp_dir):
    """Checkpoint directory should be created if it doesn't exist."""

    from sindri.core.recovery import RecoveryManager

    state_dir = temp_dir / "new_state_dir"
    assert not state_dir.exists()

    recovery = RecoveryManager(str(state_dir))

    # Directory should be created
    assert state_dir.exists()
    assert state_dir.is_dir()


def test_checkpoint_with_complex_state(recovery_manager):
    """Checkpoints should handle complex nested state."""

    session_id = "session-complex"
    state = {
        "task": "complex task",
        "iteration": 10,
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi", "tool_calls": [
                {"name": "read_file", "args": {"path": "/test"}}
            ]},
        ],
        "context": {
            "project_id": "test",
            "files": ["file1.py", "file2.py"],
            "metadata": {"nested": {"data": [1, 2, 3]}}
        }
    }

    recovery_manager.save_checkpoint(session_id, state)
    loaded = recovery_manager.load_checkpoint(session_id)

    assert loaded == state
    assert loaded["messages"][1]["tool_calls"][0]["name"] == "read_file"
    assert loaded["context"]["metadata"]["nested"]["data"] == [1, 2, 3]
