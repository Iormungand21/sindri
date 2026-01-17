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
