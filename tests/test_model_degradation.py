"""Tests for model degradation fallback functionality."""

from sindri.agents.definitions import AgentDefinition
from sindri.agents.registry import AGENTS


class TestAgentDefinitionFallback:
    """Test AgentDefinition fallback fields."""

    def test_fallback_fields_exist(self):
        """AgentDefinition should have fallback fields."""
        agent = AgentDefinition(
            name="test",
            role="test agent",
            model="test:7b",
            system_prompt="test",
            tools=["read_file"],
            fallback_model="test:3b",
            fallback_vram_gb=3.0,
        )
        assert agent.fallback_model == "test:3b"
        assert agent.fallback_vram_gb == 3.0

    def test_fallback_fields_optional(self):
        """Fallback fields should be optional (default None)."""
        agent = AgentDefinition(
            name="test",
            role="test agent",
            model="test:7b",
            system_prompt="test",
            tools=["read_file"],
        )
        assert agent.fallback_model is None
        assert agent.fallback_vram_gb is None


class TestAgentRegistryFallbacks:
    """Test that agent registry has proper fallback configurations."""

    def test_brokkr_has_fallback(self):
        """Brokkr should have a fallback model configured."""
        agent = AGENTS["brokkr"]
        assert agent.fallback_model is not None
        assert agent.fallback_vram_gb is not None
        assert agent.fallback_vram_gb < agent.estimated_vram_gb

    def test_huginn_has_fallback(self):
        """Huginn should have a fallback model configured."""
        agent = AGENTS["huginn"]
        assert agent.fallback_model is not None
        assert agent.fallback_vram_gb is not None
        assert agent.fallback_vram_gb < agent.estimated_vram_gb

    def test_mimir_has_fallback(self):
        """Mimir should have a fallback model configured."""
        agent = AGENTS["mimir"]
        assert agent.fallback_model is not None
        assert agent.fallback_vram_gb is not None

    def test_ratatoskr_no_fallback(self):
        """Ratatoskr (smallest) should not have a fallback."""
        agent = AGENTS["ratatoskr"]
        assert agent.fallback_model is None

    def test_skald_has_fallback(self):
        """Skald should have a fallback model configured."""
        agent = AGENTS["skald"]
        assert agent.fallback_model is not None
        assert agent.fallback_vram_gb is not None

    def test_fenrir_no_fallback(self):
        """Fenrir (specialized SQL) should not have a fallback."""
        agent = AGENTS["fenrir"]
        assert agent.fallback_model is None

    def test_odin_has_fallback(self):
        """Odin should have a fallback model configured."""
        agent = AGENTS["odin"]
        assert agent.fallback_model is not None
        assert agent.fallback_vram_gb is not None

    def test_fallback_vram_less_than_primary(self):
        """Fallback models should require less VRAM than primary."""
        for name, agent in AGENTS.items():
            if agent.fallback_model:
                assert (
                    agent.fallback_vram_gb < agent.estimated_vram_gb
                ), f"{name}: fallback should require less VRAM"


# ==============================================================================
# Fallback Recording in Session Metadata Tests
# ==============================================================================

import pytest
from sindri.persistence.snapshots import EnvironmentSnapshot, ModelMetadata
from sindri.replay.snapshot import SnapshotCapture


class TestEnvironmentSnapshotFallback:
    """Test EnvironmentSnapshot fallback tracking fields."""

    def test_fallback_fields_exist(self):
        """EnvironmentSnapshot should have fallback tracking fields."""
        snapshot = EnvironmentSnapshot(
            sindri_version="1.0.0",
            python_version="3.11.0",
            ollama_host="http://localhost:11434",
            model_metadata=ModelMetadata(name="qwen2.5-coder:7b"),
            config_snapshot={},
            primary_model="qwen2.5-coder:14b",
            fallback_model_used="qwen2.5-coder:7b",
            degradation_reason="insufficient_vram",
        )
        assert snapshot.primary_model == "qwen2.5-coder:14b"
        assert snapshot.fallback_model_used == "qwen2.5-coder:7b"
        assert snapshot.degradation_reason == "insufficient_vram"

    def test_fallback_fields_optional(self):
        """Fallback fields should be optional (default None)."""
        snapshot = EnvironmentSnapshot(
            sindri_version="1.0.0",
            python_version="3.11.0",
            ollama_host="http://localhost:11434",
            model_metadata=ModelMetadata(name="qwen2.5-coder:14b"),
            config_snapshot={},
        )
        assert snapshot.primary_model is None
        assert snapshot.fallback_model_used is None
        assert snapshot.degradation_reason is None

    def test_to_dict_with_fallback(self):
        """to_dict should include fallback fields when set."""
        snapshot = EnvironmentSnapshot(
            sindri_version="1.0.0",
            python_version="3.11.0",
            ollama_host="http://localhost:11434",
            model_metadata=ModelMetadata(name="qwen2.5-coder:7b"),
            config_snapshot={},
            primary_model="qwen2.5-coder:14b",
            fallback_model_used="qwen2.5-coder:7b",
            degradation_reason="insufficient_vram",
        )
        d = snapshot.to_dict()
        assert d["primary_model"] == "qwen2.5-coder:14b"
        assert d["fallback_model_used"] == "qwen2.5-coder:7b"
        assert d["degradation_reason"] == "insufficient_vram"

    def test_to_dict_without_fallback(self):
        """to_dict should omit fallback fields when not set."""
        snapshot = EnvironmentSnapshot(
            sindri_version="1.0.0",
            python_version="3.11.0",
            ollama_host="http://localhost:11434",
            model_metadata=ModelMetadata(name="qwen2.5-coder:14b"),
            config_snapshot={},
        )
        d = snapshot.to_dict()
        assert "primary_model" not in d
        assert "fallback_model_used" not in d
        assert "degradation_reason" not in d

    def test_from_dict_with_fallback(self):
        """from_dict should restore fallback fields."""
        data = {
            "sindri_version": "1.0.0",
            "python_version": "3.11.0",
            "ollama_host": "http://localhost:11434",
            "model_metadata": {"name": "qwen2.5-coder:7b"},
            "config_snapshot": {},
            "primary_model": "qwen2.5-coder:14b",
            "fallback_model_used": "qwen2.5-coder:7b",
            "degradation_reason": "insufficient_vram",
        }
        snapshot = EnvironmentSnapshot.from_dict(data)
        assert snapshot.primary_model == "qwen2.5-coder:14b"
        assert snapshot.fallback_model_used == "qwen2.5-coder:7b"
        assert snapshot.degradation_reason == "insufficient_vram"

    def test_from_dict_backward_compatible(self):
        """from_dict should handle old data without fallback fields."""
        data = {
            "sindri_version": "1.0.0",
            "python_version": "3.11.0",
            "ollama_host": "http://localhost:11434",
            "model_metadata": {"name": "qwen2.5-coder:14b"},
            "config_snapshot": {},
        }
        snapshot = EnvironmentSnapshot.from_dict(data)
        assert snapshot.primary_model is None
        assert snapshot.fallback_model_used is None
        assert snapshot.degradation_reason is None


class TestSnapshotCaptureFallback:
    """Test SnapshotCapture with fallback parameters."""

    @pytest.mark.asyncio
    async def test_capture_without_fallback(self):
        """Capture without degradation should not set fallback fields."""
        capture = SnapshotCapture(ollama_client=None)
        snapshot = await capture.capture("qwen2.5-coder:14b")

        assert snapshot.model_metadata.name == "qwen2.5-coder:14b"
        assert snapshot.primary_model is None
        assert snapshot.fallback_model_used is None
        assert snapshot.degradation_reason is None

    @pytest.mark.asyncio
    async def test_capture_with_fallback(self):
        """Capture with degradation should set fallback fields."""
        capture = SnapshotCapture(ollama_client=None)
        snapshot = await capture.capture(
            "qwen2.5-coder:7b",
            primary_model="qwen2.5-coder:14b",
            fallback_model_used="qwen2.5-coder:7b",
            degradation_reason="insufficient_vram",
        )

        assert snapshot.model_metadata.name == "qwen2.5-coder:7b"
        assert snapshot.primary_model == "qwen2.5-coder:14b"
        assert snapshot.fallback_model_used == "qwen2.5-coder:7b"
        assert snapshot.degradation_reason == "insufficient_vram"

    @pytest.mark.asyncio
    async def test_capture_roundtrip(self):
        """Snapshot should survive serialization roundtrip with fallback info."""
        capture = SnapshotCapture(ollama_client=None)
        original = await capture.capture(
            "qwen2.5-coder:7b",
            primary_model="qwen2.5-coder:14b",
            fallback_model_used="qwen2.5-coder:7b",
            degradation_reason="insufficient_vram",
        )

        # Serialize and deserialize
        data = original.to_dict()
        restored = EnvironmentSnapshot.from_dict(data)

        assert restored.primary_model == original.primary_model
        assert restored.fallback_model_used == original.fallback_model_used
        assert restored.degradation_reason == original.degradation_reason


class TestSnapshotStoreFallbackPersistence:
    """Test SnapshotStore persistence of fallback fields."""

    @pytest.mark.asyncio
    async def test_fallback_fields_persist_roundtrip(self, tmp_path):
        """Fallback fields should survive database persistence roundtrip."""
        from sindri.persistence.database import Database
        from sindri.persistence.snapshots import SnapshotStore
        from sindri.persistence.state import SessionState

        db = Database(db_path=tmp_path / "test.db")
        await db.initialize()

        # Create a session first (required for foreign key)
        state = SessionState(database=db)
        session = await state.create_session("Test task", "qwen2.5-coder:7b")

        # Create snapshot with fallback fields
        snapshot = EnvironmentSnapshot(
            sindri_version="1.0.0",
            python_version="3.11.0",
            ollama_host="http://localhost:11434",
            model_metadata=ModelMetadata(name="qwen2.5-coder:7b"),
            config_snapshot={"total_vram_gb": 16.0},
            primary_model="qwen2.5-coder:14b",
            fallback_model_used="qwen2.5-coder:7b",
            degradation_reason="insufficient_vram",
        )

        # Save and load
        store = SnapshotStore(database=db)
        await store.save_snapshot(session.id, snapshot)
        loaded = await store.load_snapshot(session.id)

        # Verify fallback fields were persisted
        assert loaded is not None
        assert loaded.primary_model == "qwen2.5-coder:14b"
        assert loaded.fallback_model_used == "qwen2.5-coder:7b"
        assert loaded.degradation_reason == "insufficient_vram"
        # Also verify config_snapshot is clean (no internal _fallback_ keys)
        assert "_fallback_primary_model" not in loaded.config_snapshot
        assert "_fallback_model_used" not in loaded.config_snapshot
        assert "_fallback_degradation_reason" not in loaded.config_snapshot
        assert loaded.config_snapshot.get("total_vram_gb") == 16.0

    @pytest.mark.asyncio
    async def test_no_fallback_fields_persist_roundtrip(self, tmp_path):
        """Snapshot without fallback should persist cleanly."""
        from sindri.persistence.database import Database
        from sindri.persistence.snapshots import SnapshotStore
        from sindri.persistence.state import SessionState

        db = Database(db_path=tmp_path / "test.db")
        await db.initialize()

        # Create a session first
        state = SessionState(database=db)
        session = await state.create_session("Test task", "qwen2.5-coder:14b")

        # Create snapshot without fallback fields
        snapshot = EnvironmentSnapshot(
            sindri_version="1.0.0",
            python_version="3.11.0",
            ollama_host="http://localhost:11434",
            model_metadata=ModelMetadata(name="qwen2.5-coder:14b"),
            config_snapshot={"total_vram_gb": 16.0},
        )

        # Save and load
        store = SnapshotStore(database=db)
        await store.save_snapshot(session.id, snapshot)
        loaded = await store.load_snapshot(session.id)

        # Verify no fallback fields
        assert loaded is not None
        assert loaded.primary_model is None
        assert loaded.fallback_model_used is None
        assert loaded.degradation_reason is None
        assert loaded.config_snapshot.get("total_vram_gb") == 16.0
