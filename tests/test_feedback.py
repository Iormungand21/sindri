"""Tests for Sindri feedback collection and training export.

Phase 9.4: Agent Fine-Tuning Infrastructure
"""

import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path

from sindri.persistence.database import Database
from sindri.persistence.state import SessionState, Session
from sindri.persistence.feedback import (
    SessionFeedback,
    FeedbackStore,
    QualityTag,
)
from sindri.persistence.training_export import (
    TrainingDataExporter,
    ExportFormat,
    ExportStats,
    generate_modelfile,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path, auto_backup=False)
        yield db


@pytest.fixture
def feedback_store(temp_db):
    """Create a feedback store with temporary database."""
    return FeedbackStore(temp_db)


@pytest.fixture
def session_state(temp_db):
    """Create a session state with temporary database."""
    return SessionState(temp_db)


async def create_sample_session(session_state) -> Session:
    """Create a sample session with turns (helper function)."""
    session = await session_state.create_session("Test coding task", "qwen2.5-coder:7b")
    session.add_turn("user", "Write a function to add two numbers")
    session.add_turn("assistant", "Here's a function:\n```python\ndef add(a, b):\n    return a + b\n```")
    session.add_turn("user", "Thanks!")
    session.iterations = 2
    await session_state.save_session(session)
    return session


# ============================================================
# SessionFeedback Tests
# ============================================================


class TestSessionFeedback:
    """Tests for SessionFeedback dataclass."""

    def test_create_feedback(self):
        """Test creating basic feedback."""
        fb = SessionFeedback(
            session_id="test-session-123",
            rating=5,
        )
        assert fb.session_id == "test-session-123"
        assert fb.rating == 5
        assert fb.include_in_training is True
        assert fb.quality_tags == []

    def test_create_feedback_with_tags(self):
        """Test creating feedback with quality tags."""
        fb = SessionFeedback(
            session_id="test-session-123",
            rating=4,
            quality_tags=["correct", "efficient"],
            notes="Good solution",
        )
        assert fb.quality_tags == ["correct", "efficient"]
        assert fb.notes == "Good solution"

    def test_rating_validation_too_low(self):
        """Test that rating below 1 raises error."""
        with pytest.raises(ValueError, match="Rating must be between 1 and 5"):
            SessionFeedback(session_id="test", rating=0)

    def test_rating_validation_too_high(self):
        """Test that rating above 5 raises error."""
        with pytest.raises(ValueError, match="Rating must be between 1 and 5"):
            SessionFeedback(session_id="test", rating=6)

    def test_is_positive(self):
        """Test is_positive property."""
        assert SessionFeedback(session_id="test", rating=5).is_positive is True
        assert SessionFeedback(session_id="test", rating=4).is_positive is True
        assert SessionFeedback(session_id="test", rating=3).is_positive is False

    def test_is_negative(self):
        """Test is_negative property."""
        assert SessionFeedback(session_id="test", rating=1).is_negative is True
        assert SessionFeedback(session_id="test", rating=2).is_negative is True
        assert SessionFeedback(session_id="test", rating=3).is_negative is False

    def test_to_dict(self):
        """Test dictionary conversion."""
        fb = SessionFeedback(
            session_id="test-session-123",
            rating=4,
            turn_index=2,
            quality_tags=["correct"],
            notes="Good",
        )
        d = fb.to_dict()
        assert d["session_id"] == "test-session-123"
        assert d["rating"] == 4
        assert d["turn_index"] == 2
        assert d["quality_tags"] == ["correct"]
        assert d["notes"] == "Good"


class TestQualityTag:
    """Tests for QualityTag enum."""

    def test_positive_tags(self):
        """Test positive quality tags."""
        assert QualityTag.CORRECT.value == "correct"
        assert QualityTag.EFFICIENT.value == "efficient"
        assert QualityTag.WELL_EXPLAINED.value == "well_explained"

    def test_negative_tags(self):
        """Test negative quality tags."""
        assert QualityTag.INCORRECT.value == "incorrect"
        assert QualityTag.HALLUCINATED.value == "hallucinated"

    def test_neutral_tags(self):
        """Test neutral quality tags."""
        assert QualityTag.PARTIAL.value == "partial"
        assert QualityTag.NEEDED_GUIDANCE.value == "needed_guidance"


# ============================================================
# FeedbackStore Tests
# ============================================================


class TestFeedbackStore:
    """Tests for FeedbackStore persistence."""

    @pytest.mark.asyncio
    async def test_add_feedback(self, feedback_store, session_state):
        """Test adding feedback to database."""
        sample_session = await create_sample_session(session_state)
        fb = SessionFeedback(
            session_id=sample_session.id,
            rating=5,
            notes="Excellent response",
        )
        result = await feedback_store.add_feedback(fb)

        assert result.id is not None
        assert result.rating == 5

    @pytest.mark.asyncio
    async def test_get_feedback(self, feedback_store, session_state):
        """Test retrieving feedback for a session."""
        sample_session = await create_sample_session(session_state)
        # Add multiple feedback entries
        await feedback_store.add_feedback(
            SessionFeedback(session_id=sample_session.id, rating=5)
        )
        await feedback_store.add_feedback(
            SessionFeedback(session_id=sample_session.id, rating=4, turn_index=1)
        )

        feedback_list = await feedback_store.get_feedback(sample_session.id)
        assert len(feedback_list) == 2
        assert feedback_list[0].rating == 5
        assert feedback_list[1].rating == 4

    @pytest.mark.asyncio
    async def test_get_feedback_by_id(self, feedback_store, session_state):
        """Test retrieving specific feedback by ID."""
        sample_session = await create_sample_session(session_state)
        fb = await feedback_store.add_feedback(
            SessionFeedback(session_id=sample_session.id, rating=4)
        )

        loaded = await feedback_store.get_feedback_by_id(fb.id)
        assert loaded is not None
        assert loaded.rating == 4

    @pytest.mark.asyncio
    async def test_get_feedback_by_id_not_found(self, feedback_store):
        """Test get_feedback_by_id returns None for missing ID."""
        result = await feedback_store.get_feedback_by_id(99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_update_feedback(self, feedback_store, session_state):
        """Test updating feedback."""
        sample_session = await create_sample_session(session_state)
        fb = await feedback_store.add_feedback(
            SessionFeedback(session_id=sample_session.id, rating=3)
        )

        fb.rating = 5
        fb.quality_tags = ["correct", "efficient"]
        success = await feedback_store.update_feedback(fb)

        assert success is True

        loaded = await feedback_store.get_feedback_by_id(fb.id)
        assert loaded.rating == 5
        assert "correct" in loaded.quality_tags

    @pytest.mark.asyncio
    async def test_update_feedback_no_id(self, feedback_store, session_state):
        """Test update fails without ID."""
        sample_session = await create_sample_session(session_state)
        fb = SessionFeedback(session_id=sample_session.id, rating=3)

        with pytest.raises(ValueError, match="must have an ID"):
            await feedback_store.update_feedback(fb)

    @pytest.mark.asyncio
    async def test_delete_feedback(self, feedback_store, session_state):
        """Test deleting feedback."""
        sample_session = await create_sample_session(session_state)
        fb = await feedback_store.add_feedback(
            SessionFeedback(session_id=sample_session.id, rating=4)
        )

        success = await feedback_store.delete_feedback(fb.id)
        assert success is True

        loaded = await feedback_store.get_feedback_by_id(fb.id)
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_feedback_not_found(self, feedback_store):
        """Test delete returns False for missing ID."""
        success = await feedback_store.delete_feedback(99999)
        assert success is False

    @pytest.mark.asyncio
    async def test_list_rated_sessions(self, feedback_store, session_state):
        """Test listing rated sessions."""
        # Create multiple sessions with feedback
        session1 = await session_state.create_session("Task 1", "model1")
        session2 = await session_state.create_session("Task 2", "model2")

        await feedback_store.add_feedback(
            SessionFeedback(session_id=session1.id, rating=5)
        )
        await feedback_store.add_feedback(
            SessionFeedback(session_id=session2.id, rating=3)
        )

        sessions = await feedback_store.list_rated_sessions()
        assert len(sessions) == 2
        # Should be sorted by rating (5 first)
        assert sessions[0]["avg_rating"] == 5.0

    @pytest.mark.asyncio
    async def test_list_rated_sessions_with_filter(self, feedback_store, session_state):
        """Test filtering rated sessions by rating."""
        session1 = await session_state.create_session("Task 1", "model1")
        session2 = await session_state.create_session("Task 2", "model2")

        await feedback_store.add_feedback(
            SessionFeedback(session_id=session1.id, rating=5)
        )
        await feedback_store.add_feedback(
            SessionFeedback(session_id=session2.id, rating=2)
        )

        # Filter for high ratings only
        sessions = await feedback_store.list_rated_sessions(min_rating=4)
        assert len(sessions) == 1
        assert sessions[0]["avg_rating"] == 5.0

    @pytest.mark.asyncio
    async def test_get_training_candidates(self, feedback_store, session_state):
        """Test getting training candidate session IDs."""
        session1 = await session_state.create_session("Good task", "model1")
        session2 = await session_state.create_session("Bad task", "model2")

        await feedback_store.add_feedback(
            SessionFeedback(session_id=session1.id, rating=5)
        )
        await feedback_store.add_feedback(
            SessionFeedback(session_id=session2.id, rating=2)
        )

        candidates = await feedback_store.get_training_candidates(min_rating=4)
        assert len(candidates) == 1
        assert candidates[0] == session1.id

    @pytest.mark.asyncio
    async def test_get_training_candidates_excludes_non_training(
        self, feedback_store, session_state
    ):
        """Test that sessions excluded from training aren't returned."""
        session1 = await session_state.create_session("Task 1", "model1")
        session2 = await session_state.create_session("Task 2", "model2")

        await feedback_store.add_feedback(
            SessionFeedback(session_id=session1.id, rating=5, include_in_training=True)
        )
        await feedback_store.add_feedback(
            SessionFeedback(session_id=session2.id, rating=5, include_in_training=False)
        )

        candidates = await feedback_store.get_training_candidates(min_rating=4)
        assert len(candidates) == 1
        assert candidates[0] == session1.id

    @pytest.mark.asyncio
    async def test_get_feedback_stats_empty(self, feedback_store):
        """Test stats with no feedback."""
        stats = await feedback_store.get_feedback_stats()
        assert stats["total_feedback"] == 0
        assert stats["sessions_with_feedback"] == 0
        assert stats["average_rating"] is None

    @pytest.mark.asyncio
    async def test_get_feedback_stats(self, feedback_store, session_state):
        """Test feedback statistics."""
        session1 = await session_state.create_session("Task 1", "model1")
        session2 = await session_state.create_session("Task 2", "model2")

        await feedback_store.add_feedback(
            SessionFeedback(
                session_id=session1.id, rating=5, quality_tags=["correct", "efficient"]
            )
        )
        await feedback_store.add_feedback(
            SessionFeedback(session_id=session2.id, rating=4, quality_tags=["correct"])
        )

        stats = await feedback_store.get_feedback_stats()

        assert stats["total_feedback"] == 2
        assert stats["sessions_with_feedback"] == 2
        assert stats["average_rating"] == 4.5
        assert stats["training_candidates"] == 2
        assert "correct" in stats["top_quality_tags"]
        assert stats["top_quality_tags"]["correct"] == 2


# ============================================================
# TrainingDataExporter Tests
# ============================================================


class TestTrainingDataExporter:
    """Tests for training data export."""

    @pytest.mark.asyncio
    async def test_export_jsonl(self, temp_db, session_state, feedback_store):
        """Test JSONL export format."""
        # Create session with feedback
        session = await session_state.create_session("Test task", "model1")
        session.add_turn("user", "Hello")
        session.add_turn("assistant", "Hi there!")
        await session_state.save_session(session)

        await feedback_store.add_feedback(
            SessionFeedback(session_id=session.id, rating=5)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training.jsonl"

            exporter = TrainingDataExporter(
                database=temp_db,
                session_state=session_state,
                feedback_store=feedback_store,
            )

            stats = await exporter.export_training_data(
                output_path=output_path,
                format=ExportFormat.JSONL,
                min_rating=4,
            )

            assert stats.sessions_exported == 1
            assert stats.turns_exported >= 2
            assert output_path.exists()

            # Verify JSONL format
            content = output_path.read_text()
            data = json.loads(content.strip())
            assert "messages" in data
            assert len(data["messages"]) >= 2  # At least user + assistant

    @pytest.mark.asyncio
    async def test_export_chatml(self, temp_db, session_state, feedback_store):
        """Test ChatML export format."""
        session = await session_state.create_session("Test task", "model1")
        session.add_turn("user", "Write code")
        session.add_turn("assistant", "Here is code")
        await session_state.save_session(session)

        await feedback_store.add_feedback(
            SessionFeedback(session_id=session.id, rating=5)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training.chatml"

            exporter = TrainingDataExporter(
                database=temp_db,
                session_state=session_state,
                feedback_store=feedback_store,
            )

            stats = await exporter.export_training_data(
                output_path=output_path,
                format=ExportFormat.CHATML,
            )

            assert stats.sessions_exported == 1
            content = output_path.read_text()
            assert "<|im_start|>" in content
            assert "<|im_end|>" in content
            assert "<|end_of_conversation|>" in content

    @pytest.mark.asyncio
    async def test_export_ollama(self, temp_db, session_state, feedback_store):
        """Test Ollama Modelfile export format."""
        session = await session_state.create_session("Test task", "model1")
        session.add_turn("user", "Help me")
        session.add_turn("assistant", "Sure thing")
        await session_state.save_session(session)

        await feedback_store.add_feedback(
            SessionFeedback(session_id=session.id, rating=5)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training.ollama"

            exporter = TrainingDataExporter(
                database=temp_db,
                session_state=session_state,
                feedback_store=feedback_store,
            )

            stats = await exporter.export_training_data(
                output_path=output_path,
                format=ExportFormat.OLLAMA,
            )

            assert stats.sessions_exported == 1
            content = output_path.read_text()
            assert "MESSAGE user" in content
            assert "MESSAGE assistant" in content

    @pytest.mark.asyncio
    async def test_export_no_candidates(self, temp_db, session_state, feedback_store):
        """Test export with no training candidates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training.jsonl"

            exporter = TrainingDataExporter(
                database=temp_db,
                session_state=session_state,
                feedback_store=feedback_store,
            )

            stats = await exporter.export_training_data(
                output_path=output_path,
                format=ExportFormat.JSONL,
                min_rating=4,
            )

            assert stats.sessions_exported == 0
            assert stats.sessions_skipped == 0

    @pytest.mark.asyncio
    async def test_export_filters_low_ratings(
        self, temp_db, session_state, feedback_store
    ):
        """Test that low-rated sessions are filtered out."""
        session1 = await session_state.create_session("Good task", "model1")
        session1.add_turn("user", "Good")
        session1.add_turn("assistant", "Response")
        await session_state.save_session(session1)

        session2 = await session_state.create_session("Bad task", "model2")
        session2.add_turn("user", "Bad")
        session2.add_turn("assistant", "Response")
        await session_state.save_session(session2)

        await feedback_store.add_feedback(
            SessionFeedback(session_id=session1.id, rating=5)
        )
        await feedback_store.add_feedback(
            SessionFeedback(session_id=session2.id, rating=2)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training.jsonl"

            exporter = TrainingDataExporter(
                database=temp_db,
                session_state=session_state,
                feedback_store=feedback_store,
            )

            stats = await exporter.export_training_data(
                output_path=output_path,
                format=ExportFormat.JSONL,
                min_rating=4,
            )

            assert stats.sessions_exported == 1

    @pytest.mark.asyncio
    async def test_export_with_tool_calls(
        self, temp_db, session_state, feedback_store
    ):
        """Test export includes tool calls when enabled."""
        session = await session_state.create_session("Test task", "model1")
        session.add_turn("user", "Read file")
        session.add_turn(
            "assistant",
            "Reading file",
            tool_calls=[{"function": {"name": "read_file", "arguments": {"path": "test.py"}}}],
        )
        session.add_turn("tool", "File contents here")
        await session_state.save_session(session)

        await feedback_store.add_feedback(
            SessionFeedback(session_id=session.id, rating=5)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training.jsonl"

            exporter = TrainingDataExporter(
                database=temp_db,
                session_state=session_state,
                feedback_store=feedback_store,
            )

            stats = await exporter.export_training_data(
                output_path=output_path,
                format=ExportFormat.JSONL,
                include_tool_calls=True,
            )

            content = output_path.read_text()
            data = json.loads(content.strip())
            # Find assistant message with tool calls
            assistant_msg = next(
                (m for m in data["messages"] if m["role"] == "assistant"),
                None,
            )
            assert assistant_msg is not None
            assert "tool_calls" in assistant_msg

    @pytest.mark.asyncio
    async def test_export_without_tool_calls(
        self, temp_db, session_state, feedback_store
    ):
        """Test export excludes tool calls when disabled."""
        session = await session_state.create_session("Test task", "model1")
        session.add_turn("user", "Read file")
        session.add_turn(
            "assistant",
            "Reading file",
            tool_calls=[{"function": {"name": "read_file", "arguments": {}}}],
        )
        session.add_turn("tool", "File contents here")
        await session_state.save_session(session)

        await feedback_store.add_feedback(
            SessionFeedback(session_id=session.id, rating=5)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training.jsonl"

            exporter = TrainingDataExporter(
                database=temp_db,
                session_state=session_state,
                feedback_store=feedback_store,
            )

            stats = await exporter.export_training_data(
                output_path=output_path,
                format=ExportFormat.JSONL,
                include_tool_calls=False,
            )

            content = output_path.read_text()
            data = json.loads(content.strip())
            # Tool role should be excluded
            roles = [m["role"] for m in data["messages"]]
            assert "tool" not in roles


class TestExportStats:
    """Tests for ExportStats dataclass."""

    def test_default_values(self):
        """Test default values."""
        stats = ExportStats()
        assert stats.sessions_exported == 0
        assert stats.turns_exported == 0
        assert stats.export_path is None

    def test_to_dict(self):
        """Test dictionary conversion."""
        stats = ExportStats(
            sessions_exported=5,
            turns_exported=100,
            export_path=Path("/tmp/test.jsonl"),
        )
        d = stats.to_dict()
        assert d["sessions_exported"] == 5
        assert d["export_path"] == "/tmp/test.jsonl"


class TestGenerateModelfile:
    """Tests for Modelfile generation."""

    def test_generate_modelfile(self):
        """Test basic Modelfile generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            training_path = Path(tmpdir) / "training.ollama"
            training_path.write_text('MESSAGE user "test"')

            output_path = Path(tmpdir) / "Modelfile"

            result = generate_modelfile(
                base_model="qwen2.5-coder:7b",
                training_data_path=training_path,
                output_path=output_path,
                model_name="test-model",
            )

            assert result == output_path
            content = output_path.read_text()
            assert "FROM qwen2.5-coder:7b" in content
            assert "PARAMETER temperature" in content
            assert 'MESSAGE user "test"' in content


# ============================================================
# Integration Tests
# ============================================================


class TestFeedbackIntegration:
    """Integration tests for feedback workflow."""

    @pytest.mark.asyncio
    async def test_full_feedback_workflow(self, temp_db):
        """Test complete feedback collection and export workflow."""
        session_state = SessionState(temp_db)
        feedback_store = FeedbackStore(temp_db)

        # 1. Create sessions
        good_session = await session_state.create_session("Good task", "model1")
        good_session.add_turn("user", "Write a function")
        good_session.add_turn("assistant", "def func():\n    pass")
        await session_state.save_session(good_session)

        bad_session = await session_state.create_session("Bad task", "model2")
        bad_session.add_turn("user", "Help")
        bad_session.add_turn("assistant", "Error")
        await session_state.save_session(bad_session)

        # 2. Add feedback
        await feedback_store.add_feedback(
            SessionFeedback(
                session_id=good_session.id,
                rating=5,
                quality_tags=["correct", "efficient"],
                notes="Perfect solution",
            )
        )
        await feedback_store.add_feedback(
            SessionFeedback(
                session_id=bad_session.id,
                rating=1,
                quality_tags=["incorrect"],
                notes="Didn't work",
            )
        )

        # 3. Check stats
        stats = await feedback_store.get_feedback_stats()
        assert stats["total_feedback"] == 2
        assert stats["training_candidates"] == 1

        # 4. Export training data
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training.jsonl"

            exporter = TrainingDataExporter(
                database=temp_db,
                session_state=session_state,
                feedback_store=feedback_store,
            )

            export_stats = await exporter.export_training_data(
                output_path=output_path,
                format=ExportFormat.JSONL,
                min_rating=4,
            )

            # Only good session should be exported
            assert export_stats.sessions_exported == 1
            assert export_stats.turns_exported >= 2

    @pytest.mark.asyncio
    async def test_feedback_persistence_across_loads(self, temp_db):
        """Test that feedback persists correctly in database."""
        session_state = SessionState(temp_db)

        # Create session
        session = await session_state.create_session("Test", "model1")

        # Add feedback with first store instance
        store1 = FeedbackStore(temp_db)
        fb = await store1.add_feedback(
            SessionFeedback(
                session_id=session.id,
                rating=4,
                quality_tags=["correct"],
            )
        )

        # Load with new store instance
        store2 = FeedbackStore(temp_db)
        loaded = await store2.get_feedback_by_id(fb.id)

        assert loaded is not None
        assert loaded.rating == 4
        assert "correct" in loaded.quality_tags
