"""Tests for Sindri persistence."""

import pytest
import tempfile
from pathlib import Path

from sindri.persistence.database import Database
from sindri.persistence.state import SessionState


@pytest.mark.asyncio
async def test_database_initialization():
    """Test database initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)

        await db.initialize()

        assert db_path.exists()


@pytest.mark.asyncio
async def test_session_creation():
    """Test creating a session."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        state = SessionState(db)

        session = await state.create_session("Test task", "test-model")

        assert session.id is not None
        assert session.task == "Test task"
        assert session.model == "test-model"
        assert session.status == "active"


@pytest.mark.asyncio
async def test_session_save_and_load():
    """Test saving and loading a session."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        state = SessionState(db)

        # Create and modify session
        session = await state.create_session("Test task", "test-model")
        session.add_turn("user", "Do something")
        session.add_turn("assistant", "I'll do it")
        session.iterations = 5

        # Save
        await state.save_session(session)

        # Load
        loaded = await state.load_session(session.id)

        assert loaded is not None
        assert loaded.task == "Test task"
        assert loaded.iterations == 5
        assert len(loaded.turns) == 2
        assert loaded.turns[0].role == "user"
        assert loaded.turns[1].content == "I'll do it"


@pytest.mark.asyncio
async def test_session_completion():
    """Test completing a session."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        state = SessionState(db)

        session = await state.create_session("Test task", "test-model")
        await state.complete_session(session.id)

        loaded = await state.load_session(session.id)

        assert loaded.status == "completed"
        assert loaded.completed_at is not None


@pytest.mark.asyncio
async def test_fail_session_with_error():
    """Test failing a session with an error message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        state = SessionState(db)

        session = await state.create_session("Test task", "test-model")
        await state.fail_session(session.id, "Something went wrong")

        loaded = await state.load_session(session.id)

        assert loaded.status == "failed"
        assert loaded.completed_at is not None
        assert loaded.error == "Something went wrong"


@pytest.mark.asyncio
async def test_fail_session_without_error():
    """Test failing a session without an error message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        state = SessionState(db)

        session = await state.create_session("Test task", "test-model")
        await state.fail_session(session.id)

        loaded = await state.load_session(session.id)

        assert loaded.status == "failed"
        assert loaded.completed_at is not None
        assert loaded.error is None


@pytest.mark.asyncio
async def test_cancel_session_with_reason():
    """Test cancelling a session with a reason."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        state = SessionState(db)

        session = await state.create_session("Test task", "test-model")
        await state.cancel_session(session.id, "User requested cancellation")

        loaded = await state.load_session(session.id)

        assert loaded.status == "cancelled"
        assert loaded.completed_at is not None
        assert loaded.error == "User requested cancellation"


@pytest.mark.asyncio
async def test_cancel_session_default_reason():
    """Test cancelling a session uses default reason if none provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        state = SessionState(db)

        session = await state.create_session("Test task", "test-model")
        await state.cancel_session(session.id)

        loaded = await state.load_session(session.id)

        assert loaded.status == "cancelled"
        assert loaded.completed_at is not None
        assert loaded.error == "Cancelled by user"


@pytest.mark.asyncio
async def test_cleanup_stale_ignores_cancelled_sessions():
    """Test that cleanup_stale_sessions ignores already cancelled sessions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        state = SessionState(db)

        # Create and cancel a session
        session = await state.create_session("Test task", "test-model")
        await state.cancel_session(session.id)

        # Cleanup with 0 max age (would mark active sessions as failed)
        cleaned = await state.cleanup_stale_sessions(max_age_hours=0.0)

        # Should not have cleaned any - session was already cancelled
        assert cleaned == 0

        # Verify session is still cancelled
        loaded = await state.load_session(session.id)
        assert loaded.status == "cancelled"


@pytest.mark.asyncio
async def test_cleanup_stale_ignores_failed_sessions():
    """Test that cleanup_stale_sessions ignores already failed sessions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        state = SessionState(db)

        # Create and fail a session
        session = await state.create_session("Test task", "test-model")
        await state.fail_session(session.id, "Test failure")

        # Cleanup with 0 max age
        cleaned = await state.cleanup_stale_sessions(max_age_hours=0.0)

        # Should not have cleaned any - session was already failed
        assert cleaned == 0

        # Verify session is still failed with original error
        loaded = await state.load_session(session.id)
        assert loaded.status == "failed"
        assert loaded.error == "Test failure"
