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
