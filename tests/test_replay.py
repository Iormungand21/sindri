"""Tests for Reproducible Sessions feature."""

import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from click.testing import CliRunner

from sindri.persistence.snapshots import (
    EnvironmentSnapshot,
    InferenceParams,
    ModelMetadata,
    SnapshotStore,
    ToolOutput,
    ToolOutputStore,
)
from sindri.replay.snapshot import SnapshotCapture
from sindri.replay.engine import ReplayEngine, ReplayMode, ReplayResult, RecordedToolExecutor
from sindri.replay.comparator import (
    SessionComparator,
    SessionComparison,
    TurnDiff,
    EnvironmentDiff,
)
from sindri.persistence.state import Session, Turn


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def model_metadata():
    """Sample model metadata."""
    return ModelMetadata(
        name="qwen2.5-coder:7b",
        digest="sha256:abc123def456",
        family="qwen2",
        parameter_size="7B",
        quantization_level="Q4_K_M",
        format="gguf",
        modified_at="2026-01-01T00:00:00Z",
    )


@pytest.fixture
def inference_params():
    """Sample inference parameters."""
    return InferenceParams(
        temperature=0.7,
        top_p=0.9,
        top_k=40,
        seed=42,
        repeat_penalty=1.1,
        num_ctx=4096,
    )


@pytest.fixture
def environment_snapshot(model_metadata, inference_params):
    """Sample environment snapshot."""
    return EnvironmentSnapshot(
        sindri_version="1.0.0",
        sindri_git_commit="abc1234",
        python_version="3.11.5",
        ollama_version="0.5.1",
        ollama_host="http://localhost:11434",
        model_metadata=model_metadata,
        inference_params=inference_params,
        config_snapshot={"total_vram_gb": 16.0, "default_model": "qwen2.5-coder:7b"},
        captured_at=datetime.now(),
    )


@pytest.fixture
def sample_session():
    """Sample session for testing."""
    session = Session(
        id="test-session-12345678",
        task="Write hello world",
        model="qwen2.5-coder:7b",
        status="completed",
        iterations=5,
    )
    session.turns = [
        Turn(role="user", content="Write hello world"),
        Turn(
            role="assistant",
            content="I'll create a hello world file.",
            tool_calls=[{"function": {"name": "write_file", "arguments": {"path": "hello.py"}}}],
        ),
        Turn(role="tool", content="File written successfully"),
        Turn(role="assistant", content="Done! Created hello.py"),
    ]
    return session


@pytest.fixture
def sample_tool_outputs():
    """Sample tool outputs for testing."""
    return [
        ToolOutput(
            session_id="test-session-12345678",
            turn_index=1,
            tool_index=0,
            tool_name="write_file",
            arguments={"path": "hello.py", "content": "print('hello')"},
            output="File written successfully",
            output_hash="sha256:abc",
            duration_ms=50,
            success=True,
        ),
    ]


# ==============================================================================
# ModelMetadata Tests
# ==============================================================================


class TestModelMetadata:
    """Tests for ModelMetadata dataclass."""

    def test_to_dict(self, model_metadata):
        """Test serialization to dict."""
        d = model_metadata.to_dict()
        assert d["name"] == "qwen2.5-coder:7b"
        assert d["digest"] == "sha256:abc123def456"
        assert d["family"] == "qwen2"
        assert d["quantization_level"] == "Q4_K_M"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "name": "llama3:8b",
            "digest": "sha256:xyz",
            "family": "llama",
            "parameter_size": "8B",
            "quantization_level": "Q8_0",
            "format": "gguf",
        }
        meta = ModelMetadata.from_dict(data)
        assert meta.name == "llama3:8b"
        assert meta.family == "llama"
        assert meta.quantization_level == "Q8_0"

    def test_from_dict_with_defaults(self):
        """Test deserialization with missing fields."""
        data = {"name": "test-model"}
        meta = ModelMetadata.from_dict(data)
        assert meta.name == "test-model"
        assert meta.family == "unknown"
        assert meta.quantization_level == "unknown"


# ==============================================================================
# InferenceParams Tests
# ==============================================================================


class TestInferenceParams:
    """Tests for InferenceParams dataclass."""

    def test_to_dict(self, inference_params):
        """Test serialization to dict."""
        d = inference_params.to_dict()
        assert d["temperature"] == 0.7
        assert d["top_p"] == 0.9
        assert d["seed"] == 42

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {"temperature": 0.5, "top_p": 0.8, "seed": 123}
        params = InferenceParams.from_dict(data)
        assert params.temperature == 0.5
        assert params.top_p == 0.8
        assert params.seed == 123

    def test_defaults(self):
        """Test default values."""
        params = InferenceParams()
        assert params.temperature == 0.7
        assert params.top_p == 0.9
        assert params.seed is None


# ==============================================================================
# EnvironmentSnapshot Tests
# ==============================================================================


class TestEnvironmentSnapshot:
    """Tests for EnvironmentSnapshot dataclass."""

    def test_to_dict(self, environment_snapshot):
        """Test serialization to dict."""
        d = environment_snapshot.to_dict()
        assert d["sindri_version"] == "1.0.0"
        assert d["python_version"] == "3.11.5"
        assert d["ollama_version"] == "0.5.1"
        assert "model_metadata" in d
        assert "inference_params" in d
        assert "config_snapshot" in d

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "sindri_version": "2.0.0",
            "python_version": "3.12.0",
            "ollama_host": "http://localhost:11434",
            "model_metadata": {"name": "test-model"},
            "config_snapshot": {},
        }
        snapshot = EnvironmentSnapshot.from_dict(data)
        assert snapshot.sindri_version == "2.0.0"
        assert snapshot.python_version == "3.12.0"
        assert snapshot.model_metadata.name == "test-model"


# ==============================================================================
# SnapshotStore Tests
# ==============================================================================


class TestSnapshotStore:
    """Tests for SnapshotStore persistence."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = MagicMock()
        db.initialize = AsyncMock()

        # Mock connection context manager
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.commit = AsyncMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=None)

        db.get_connection = MagicMock(return_value=conn)
        return db

    @pytest.mark.asyncio
    async def test_save_snapshot(self, mock_db, environment_snapshot):
        """Test saving a snapshot."""
        store = SnapshotStore(database=mock_db)
        await store.save_snapshot("session-123", environment_snapshot)

        mock_db.initialize.assert_called_once()
        conn = mock_db.get_connection.return_value
        conn.execute.assert_called_once()
        conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_has_snapshot_true(self, mock_db):
        """Test checking if snapshot exists (true case)."""
        store = SnapshotStore(database=mock_db)

        # Mock cursor
        cursor = MagicMock()
        cursor.fetchone = AsyncMock(return_value=(1,))
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock(return_value=None)

        conn = mock_db.get_connection.return_value
        conn.execute = MagicMock(return_value=cursor)

        result = await store.has_snapshot("session-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_has_snapshot_false(self, mock_db):
        """Test checking if snapshot exists (false case)."""
        store = SnapshotStore(database=mock_db)

        # Mock cursor returning None
        cursor = MagicMock()
        cursor.fetchone = AsyncMock(return_value=None)
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock(return_value=None)

        conn = mock_db.get_connection.return_value
        conn.execute = MagicMock(return_value=cursor)

        result = await store.has_snapshot("session-123")
        assert result is False


# ==============================================================================
# ToolOutputStore Tests
# ==============================================================================


class TestToolOutputStore:
    """Tests for ToolOutputStore persistence."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = MagicMock()
        db.initialize = AsyncMock()

        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.commit = AsyncMock()
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=None)

        db.get_connection = MagicMock(return_value=conn)
        return db

    @pytest.mark.asyncio
    async def test_save_tool_output(self, mock_db):
        """Test saving a tool output."""
        store = ToolOutputStore(database=mock_db)

        await store.save_tool_output(
            session_id="session-123",
            turn_index=1,
            tool_index=0,
            tool_name="write_file",
            arguments={"path": "test.py"},
            output="File written",
            success=True,
            duration_ms=50,
        )

        mock_db.initialize.assert_called_once()
        conn = mock_db.get_connection.return_value
        conn.execute.assert_called_once()
        conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_output_count(self, mock_db):
        """Test getting output count."""
        store = ToolOutputStore(database=mock_db)

        # Mock cursor
        cursor = MagicMock()
        cursor.fetchone = AsyncMock(return_value=(5,))
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock(return_value=None)

        conn = mock_db.get_connection.return_value
        conn.execute = MagicMock(return_value=cursor)

        count = await store.get_output_count("session-123")
        assert count == 5


# ==============================================================================
# SnapshotCapture Tests
# ==============================================================================


class TestSnapshotCapture:
    """Tests for SnapshotCapture."""

    def test_get_sindri_version(self):
        """Test getting Sindri version."""
        capture = SnapshotCapture()
        version = capture._get_sindri_version()
        # Should return a version string or "unknown"
        assert isinstance(version, str)

    @pytest.mark.asyncio
    async def test_capture_without_client(self):
        """Test capture without Ollama client."""
        capture = SnapshotCapture(ollama_client=None)
        snapshot = await capture.capture("test-model")

        assert snapshot.model_metadata.name == "test-model"
        assert snapshot.python_version is not None
        assert snapshot.ollama_version is None

    @pytest.mark.asyncio
    async def test_capture_with_inference_params(self):
        """Test capture with custom inference params."""
        params = InferenceParams(temperature=0.5, seed=42)
        capture = SnapshotCapture(ollama_client=None)
        snapshot = await capture.capture("test-model", inference_params=params)

        assert snapshot.inference_params.temperature == 0.5
        assert snapshot.inference_params.seed == 42


# ==============================================================================
# RecordedToolExecutor Tests
# ==============================================================================


class TestRecordedToolExecutor:
    """Tests for RecordedToolExecutor."""

    def test_get_output_exists(self, sample_tool_outputs):
        """Test getting existing output."""
        executor = RecordedToolExecutor(sample_tool_outputs)
        output = executor.get_output(1, 0)

        assert output is not None
        assert output.tool_name == "write_file"

    def test_get_output_not_exists(self, sample_tool_outputs):
        """Test getting non-existent output."""
        executor = RecordedToolExecutor(sample_tool_outputs)
        output = executor.get_output(99, 0)

        assert output is None

    def test_has_output(self, sample_tool_outputs):
        """Test checking if output exists."""
        executor = RecordedToolExecutor(sample_tool_outputs)

        assert executor.has_output(1, 0) is True
        assert executor.has_output(99, 0) is False

    def test_total_outputs(self, sample_tool_outputs):
        """Test total outputs count."""
        executor = RecordedToolExecutor(sample_tool_outputs)
        assert executor.total_outputs == 1


# ==============================================================================
# ReplayEngine Tests
# ==============================================================================


class TestReplayEngine:
    """Tests for ReplayEngine."""

    @pytest.fixture
    def mock_stores(self, sample_session, environment_snapshot, sample_tool_outputs):
        """Create mock stores."""
        session_state = MagicMock()
        session_state.load_session = AsyncMock(return_value=sample_session)

        snapshot_store = MagicMock()
        snapshot_store.load_snapshot = AsyncMock(return_value=environment_snapshot)

        tool_output_store = MagicMock()
        tool_output_store.get_session_outputs = AsyncMock(return_value=sample_tool_outputs)

        return session_state, snapshot_store, tool_output_store

    @pytest.mark.asyncio
    async def test_replay_tool_only_success(self, mock_stores):
        """Test successful tool-only replay."""
        session_state, snapshot_store, tool_output_store = mock_stores

        engine = ReplayEngine(
            session_state=session_state,
            snapshot_store=snapshot_store,
            tool_output_store=tool_output_store,
        )

        result = await engine.replay("session-123", mode=ReplayMode.TOOL_ONLY)

        assert result.status == "completed"
        assert result.tool_outputs_replayed == 1
        assert result.tool_outputs_total == 1

    @pytest.mark.asyncio
    async def test_replay_session_not_found(self):
        """Test replay with non-existent session."""
        session_state = MagicMock()
        session_state.load_session = AsyncMock(return_value=None)

        engine = ReplayEngine(session_state=session_state)
        result = await engine.replay("nonexistent")

        assert result.status == "failed"
        assert "not found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_replay_no_snapshot(self, sample_session):
        """Test replay without snapshot."""
        session_state = MagicMock()
        session_state.load_session = AsyncMock(return_value=sample_session)

        snapshot_store = MagicMock()
        snapshot_store.load_snapshot = AsyncMock(return_value=None)

        engine = ReplayEngine(
            session_state=session_state,
            snapshot_store=snapshot_store,
        )
        result = await engine.replay("session-123")

        assert result.status == "failed"
        assert "No snapshot" in result.errors[0]

    @pytest.mark.asyncio
    async def test_replay_no_outputs(self, sample_session, environment_snapshot):
        """Test replay without tool outputs."""
        session_state = MagicMock()
        session_state.load_session = AsyncMock(return_value=sample_session)

        snapshot_store = MagicMock()
        snapshot_store.load_snapshot = AsyncMock(return_value=environment_snapshot)

        tool_output_store = MagicMock()
        tool_output_store.get_session_outputs = AsyncMock(return_value=[])

        engine = ReplayEngine(
            session_state=session_state,
            snapshot_store=snapshot_store,
            tool_output_store=tool_output_store,
        )
        result = await engine.replay("session-123")

        assert result.status == "no_outputs"

    @pytest.mark.asyncio
    async def test_get_replay_info(self, mock_stores, environment_snapshot):
        """Test getting replay info."""
        session_state, snapshot_store, tool_output_store = mock_stores
        tool_output_store.get_output_count = AsyncMock(return_value=5)

        engine = ReplayEngine(
            session_state=session_state,
            snapshot_store=snapshot_store,
            tool_output_store=tool_output_store,
        )

        info = await engine.get_replay_info("session-123")

        assert info["has_snapshot"] is True
        assert info["has_tool_outputs"] is True
        assert info["tool_output_count"] == 5
        assert info["replayable"] is True


# ==============================================================================
# SessionComparator Tests
# ==============================================================================


class TestSessionComparator:
    """Tests for SessionComparator."""

    @pytest.fixture
    def two_sessions(self, sample_session):
        """Create two sessions for comparison."""
        session1 = sample_session

        session2 = Session(
            id="test-session-87654321",
            task="Write hello world",
            model="qwen2.5-coder:7b",
            status="completed",
            iterations=5,
        )
        session2.turns = [
            Turn(role="user", content="Write hello world"),
            Turn(
                role="assistant",
                content="I'll create a hello world file.",
                tool_calls=[{"function": {"name": "write_file", "arguments": {"path": "hello.py"}}}],
            ),
            Turn(role="tool", content="File written successfully"),
            Turn(role="assistant", content="Done! Created hello.py"),
        ]

        return session1, session2

    @pytest.mark.asyncio
    async def test_compare_identical_sessions(self, two_sessions, environment_snapshot):
        """Test comparing identical sessions."""
        session1, session2 = two_sessions

        session_state = MagicMock()
        session_state.load_session = AsyncMock(side_effect=[session1, session2])

        snapshot_store = MagicMock()
        snapshot_store.load_snapshot = AsyncMock(return_value=environment_snapshot)

        comparator = SessionComparator(
            snapshot_store=snapshot_store,
            session_state=session_state,
        )

        comparison = await comparator.compare("session-1", "session-2")

        assert comparison.overall_similarity == 1.0
        assert comparison.turns_identical == 4
        assert comparison.are_identical is True

    @pytest.mark.asyncio
    async def test_compare_different_content(self, environment_snapshot):
        """Test comparing sessions with different content."""
        session1 = Session(
            id="session-1",
            task="Task 1",
            model="qwen2.5-coder:7b",
            status="completed",
        )
        session1.turns = [Turn(role="assistant", content="Response A")]

        session2 = Session(
            id="session-2",
            task="Task 2",
            model="qwen2.5-coder:7b",
            status="completed",
        )
        session2.turns = [Turn(role="assistant", content="Response B")]

        session_state = MagicMock()
        session_state.load_session = AsyncMock(side_effect=[session1, session2])

        snapshot_store = MagicMock()
        snapshot_store.load_snapshot = AsyncMock(return_value=environment_snapshot)

        comparator = SessionComparator(
            snapshot_store=snapshot_store,
            session_state=session_state,
        )

        comparison = await comparator.compare("session-1", "session-2")

        assert comparison.overall_similarity < 1.0
        assert comparison.turns_identical == 0
        assert len(comparison.turn_diffs) == 1
        assert comparison.turn_diffs[0].content_match is False

    @pytest.mark.asyncio
    async def test_compare_session_not_found(self):
        """Test comparing with non-existent session."""
        session_state = MagicMock()
        session_state.load_session = AsyncMock(return_value=None)

        comparator = SessionComparator(session_state=session_state)

        with pytest.raises(ValueError, match="not found"):
            await comparator.compare("nonexistent", "session-2")


class TestEnvironmentDiff:
    """Tests for EnvironmentDiff."""

    def test_has_differences_true(self):
        """Test has_differences when there are differences."""
        diff = EnvironmentDiff(sindri_version=("1.0.0", "2.0.0"))
        assert diff.has_differences is True

    def test_has_differences_false(self):
        """Test has_differences when there are no differences."""
        diff = EnvironmentDiff()
        assert diff.has_differences is False

    def test_to_dict(self):
        """Test conversion to dict."""
        diff = EnvironmentDiff(
            sindri_version=("1.0.0", "2.0.0"),
            python_version=("3.11", "3.12"),
        )
        d = diff.to_dict()
        assert d["sindri_version"] == ("1.0.0", "2.0.0")
        assert d["python_version"] == ("3.11", "3.12")
        assert "model_name" not in d  # Not set


class TestTurnDiff:
    """Tests for TurnDiff."""

    def test_is_identical_true(self):
        """Test is_identical when turn is identical."""
        diff = TurnDiff(
            turn_index=0,
            role="assistant",
            content_match=True,
            tool_calls_match=True,
        )
        assert diff.is_identical is True

    def test_is_identical_false_content(self):
        """Test is_identical when content differs."""
        diff = TurnDiff(
            turn_index=0,
            role="assistant",
            content_match=False,
            tool_calls_match=True,
        )
        assert diff.is_identical is False

    def test_is_identical_false_tools(self):
        """Test is_identical when tool calls differ."""
        diff = TurnDiff(
            turn_index=0,
            role="assistant",
            content_match=True,
            tool_calls_match=False,
        )
        assert diff.is_identical is False


# ==============================================================================
# CLI Tests
# ==============================================================================


class TestReplayCLI:
    """Tests for replay CLI commands."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_replay_info_session_not_found(self, runner):
        """Test replay info with non-existent session."""
        from sindri.cli import cli

        with patch("sindri.cli.asyncio.run") as mock_run:
            # Simulate session not found
            mock_run.return_value = (None, None, "No session found")
            result = runner.invoke(cli, ["replay", "info", "nonexistent"])
            # The error should be handled gracefully
            assert result.exit_code == 0 or "not found" in result.output.lower()

    def test_replay_list_empty(self, runner):
        """Test replay list with no sessions."""
        from sindri.cli import cli

        with patch("sindri.cli.asyncio.run") as mock_run:
            mock_run.return_value = []
            result = runner.invoke(cli, ["replay", "list"])
            assert result.exit_code == 0

    def test_replay_help(self, runner):
        """Test replay help command."""
        from sindri.cli import cli

        result = runner.invoke(cli, ["replay", "--help"])
        assert result.exit_code == 0
        assert "Replay and compare" in result.output

    def test_replay_info_help(self, runner):
        """Test replay info help."""
        from sindri.cli import cli

        result = runner.invoke(cli, ["replay", "info", "--help"])
        assert result.exit_code == 0
        assert "environment snapshot" in result.output.lower()

    def test_replay_run_help(self, runner):
        """Test replay run help."""
        from sindri.cli import cli

        result = runner.invoke(cli, ["replay", "run", "--help"])
        assert result.exit_code == 0
        assert "tool-only" in result.output

    def test_replay_compare_help(self, runner):
        """Test replay compare help."""
        from sindri.cli import cli

        result = runner.invoke(cli, ["replay", "compare", "--help"])
        assert result.exit_code == 0
        assert "Compare two sessions" in result.output


# ==============================================================================
# Integration Tests (Database Schema)
# ==============================================================================


class TestDatabaseSchema:
    """Tests for database schema changes."""

    @pytest.mark.asyncio
    async def test_schema_version_7(self, tmp_path):
        """Test that schema version 7 creates new tables."""
        from sindri.persistence.database import Database, SCHEMA_VERSION

        assert SCHEMA_VERSION == 7

        db = Database(db_path=tmp_path / "test.db")
        await db.initialize()

        # Verify new tables exist
        import aiosqlite
        async with aiosqlite.connect(tmp_path / "test.db") as conn:
            # Check session_snapshots table
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='session_snapshots'"
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, "session_snapshots table not created"

            # Check session_tool_outputs table
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='session_tool_outputs'"
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, "session_tool_outputs table not created"

            # Verify schema version
            async with conn.execute("PRAGMA user_version") as cursor:
                row = await cursor.fetchone()
                assert row[0] == 7


# ==============================================================================
# End-to-End Tests
# ==============================================================================


class TestReplayEndToEnd:
    """End-to-end tests for replay functionality."""

    @pytest.mark.asyncio
    async def test_snapshot_save_and_load(self, tmp_path, environment_snapshot):
        """Test saving and loading a snapshot."""
        from sindri.persistence.database import Database
        from sindri.persistence.snapshots import SnapshotStore

        db = Database(db_path=tmp_path / "test.db")
        await db.initialize()

        store = SnapshotStore(database=db)

        # First create a session
        from sindri.persistence.state import SessionState
        state = SessionState(database=db)
        session = await state.create_session("Test task", "test-model")

        # Save snapshot
        await store.save_snapshot(session.id, environment_snapshot)

        # Load snapshot
        loaded = await store.load_snapshot(session.id)

        assert loaded is not None
        assert loaded.sindri_version == environment_snapshot.sindri_version
        assert loaded.python_version == environment_snapshot.python_version
        assert loaded.model_metadata.name == environment_snapshot.model_metadata.name

    @pytest.mark.asyncio
    async def test_tool_output_save_and_load(self, tmp_path):
        """Test saving and loading tool outputs."""
        from sindri.persistence.database import Database
        from sindri.persistence.snapshots import ToolOutputStore
        from sindri.persistence.state import SessionState

        db = Database(db_path=tmp_path / "test.db")
        await db.initialize()

        # Create a session first
        state = SessionState(database=db)
        session = await state.create_session("Test task", "test-model")

        store = ToolOutputStore(database=db)

        # Save tool output
        await store.save_tool_output(
            session_id=session.id,
            turn_index=1,
            tool_index=0,
            tool_name="write_file",
            arguments={"path": "test.py", "content": "print('hello')"},
            output="File written successfully",
            success=True,
            duration_ms=50,
        )

        # Load outputs
        outputs = await store.get_session_outputs(session.id)

        assert len(outputs) == 1
        assert outputs[0].tool_name == "write_file"
        assert outputs[0].success is True
        assert outputs[0].output == "File written successfully"

    @pytest.mark.asyncio
    async def test_replay_info_integration(self, tmp_path, environment_snapshot):
        """Test replay info with real database."""
        from sindri.persistence.database import Database
        from sindri.persistence.snapshots import SnapshotStore, ToolOutputStore
        from sindri.persistence.state import SessionState
        from sindri.replay.engine import ReplayEngine

        db = Database(db_path=tmp_path / "test.db")
        await db.initialize()

        # Create session
        state = SessionState(database=db)
        session = await state.create_session("Test task", "test-model")

        # Save snapshot
        snapshot_store = SnapshotStore(database=db)
        await snapshot_store.save_snapshot(session.id, environment_snapshot)

        # Save tool output
        tool_store = ToolOutputStore(database=db)
        await tool_store.save_tool_output(
            session_id=session.id,
            turn_index=1,
            tool_index=0,
            tool_name="test_tool",
            arguments={},
            output="output",
            success=True,
        )

        # Check replay info
        engine = ReplayEngine(
            session_state=state,
            snapshot_store=snapshot_store,
            tool_output_store=tool_store,
        )

        info = await engine.get_replay_info(session.id)

        assert info["has_snapshot"] is True
        assert info["has_tool_outputs"] is True
        assert info["tool_output_count"] == 1
        assert info["replayable"] is True
