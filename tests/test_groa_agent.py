"""Tests for Groa (Document/Vision) agent (Phase 12 Tier 3).

Tests for agent registration, configuration, tool assignments,
prompt quality, and delegation from Brokkr.
"""

import pytest

from sindri.agents.registry import get_agent, list_agents, AGENTS
from sindri.agents.prompts import GROA_PROMPT


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Registration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGroaAgentExists:
    """Test that Groa agent is properly registered."""

    def test_groa_in_agents_dict(self):
        """Groa agent is in AGENTS dict."""
        assert "groa" in AGENTS

    def test_groa_in_list_agents(self):
        """Groa agent appears in list_agents()."""
        assert "groa" in list_agents()

    def test_get_groa_agent(self):
        """Can retrieve Groa agent via get_agent()."""
        agent = get_agent("groa")
        assert agent is not None
        assert agent.name == "groa"


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Configuration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGroaAgentConfiguration:
    """Test Groa agent configuration settings."""

    def test_groa_role(self):
        """Groa has correct role description."""
        agent = get_agent("groa")
        assert "document" in agent.role.lower()
        assert "vision" in agent.role.lower() or "seeress" in agent.role.lower()

    def test_groa_model(self):
        """Groa uses vision model."""
        agent = get_agent("groa")
        assert "granite" in agent.model.lower() or "vision" in agent.model.lower()

    def test_groa_vram_estimate(self):
        """Groa VRAM estimate is reasonable for vision model."""
        agent = get_agent("groa")
        # granite3.2-vision:2b is ~2GB
        assert agent.estimated_vram_gb >= 1.5
        assert agent.estimated_vram_gb <= 4.0

    def test_groa_priority(self):
        """Groa has Tier 2/3 specialist priority."""
        agent = get_agent("groa")
        assert agent.priority == 2  # Tier 2 specialist

    def test_groa_cannot_delegate(self):
        """Groa does not delegate (leaf agent)."""
        agent = get_agent("groa")
        assert agent.can_delegate is False
        assert len(agent.delegate_to) == 0

    def test_groa_temperature(self):
        """Groa has low temperature for precise document analysis."""
        agent = get_agent("groa")
        assert agent.temperature <= 0.5

    def test_groa_fallback_model(self):
        """Groa has a fallback model defined."""
        agent = get_agent("groa")
        assert agent.fallback_model is not None
        assert "qwen" in agent.fallback_model.lower() or "coder" in agent.fallback_model.lower()

    def test_groa_max_iterations(self):
        """Groa has reasonable max iterations."""
        agent = get_agent("groa")
        assert agent.max_iterations >= 10
        assert agent.max_iterations <= 30


# ═══════════════════════════════════════════════════════════════════════════════
# Tool Assignment Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGroaAgentTools:
    """Test Groa agent tool assignments."""

    def test_groa_has_vision_tools(self):
        """Groa has vision-based document tools."""
        agent = get_agent("groa")
        assert "document_describe" in agent.tools
        assert "document_extract_structured" in agent.tools
        assert "document_summarize" in agent.tools

    def test_groa_has_traditional_document_tools(self):
        """Groa has traditional document processing tools."""
        agent = get_agent("groa")
        assert "pdf_extract_text" in agent.tools
        assert "pdf_to_markdown" in agent.tools
        assert "pdf_merge" in agent.tools
        assert "pdf_split" in agent.tools
        assert "ocr_image" in agent.tools
        assert "spreadsheet_read" in agent.tools
        assert "spreadsheet_write" in agent.tools

    def test_groa_has_file_tools(self):
        """Groa has basic file operation tools."""
        agent = get_agent("groa")
        assert "read_file" in agent.tools
        assert "write_file" in agent.tools
        assert "list_directory" in agent.tools
        assert "read_tree" in agent.tools

    def test_groa_no_shell_execution(self):
        """Groa does not have shell execution (security)."""
        agent = get_agent("groa")
        assert "shell" not in agent.tools

    def test_groa_no_git_tools(self):
        """Groa does not have git tools (not needed for document processing)."""
        agent = get_agent("groa")
        assert "git_status" not in agent.tools
        assert "git_commit" not in agent.tools

    def test_groa_no_service_tools(self):
        """Groa does not have service management tools."""
        agent = get_agent("groa")
        assert "service_start" not in agent.tools
        assert "service_stop" not in agent.tools

    def test_groa_tool_count(self):
        """Groa has expected number of tools."""
        agent = get_agent("groa")
        # 4 file ops + 3 vision + 7 traditional = 14 tools
        assert len(agent.tools) >= 14
        assert len(agent.tools) <= 20


# ═══════════════════════════════════════════════════════════════════════════════
# Prompt Quality Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGroaPromptQuality:
    """Test Groa agent prompt quality and content."""

    def test_groa_prompt_exists(self):
        """GROA_PROMPT is defined."""
        assert GROA_PROMPT is not None
        assert len(GROA_PROMPT) > 0

    def test_groa_prompt_length(self):
        """Groa prompt is substantial."""
        assert len(GROA_PROMPT) > 2000

    def test_groa_prompt_has_identity(self):
        """Groa prompt establishes Norse identity."""
        prompt_lower = GROA_PROMPT.lower()
        assert "groa" in prompt_lower
        assert "seeress" in prompt_lower or "völva" in prompt_lower or "document" in prompt_lower

    def test_groa_prompt_has_capabilities(self):
        """Groa prompt lists core capabilities."""
        prompt_lower = GROA_PROMPT.lower()
        assert "capabilities" in prompt_lower
        assert "vision" in prompt_lower or "describe" in prompt_lower
        assert "extract" in prompt_lower
        assert "summarize" in prompt_lower

    def test_groa_prompt_has_tools_section(self):
        """Groa prompt has tools documentation."""
        prompt_lower = GROA_PROMPT.lower()
        assert "document_describe" in prompt_lower
        assert "document_extract_structured" in prompt_lower
        assert "document_summarize" in prompt_lower

    def test_groa_prompt_has_execution_flow(self):
        """Groa prompt has tool execution flow instructions."""
        prompt_lower = GROA_PROMPT.lower()
        assert "wait for" in prompt_lower or "tool results" in prompt_lower
        assert "<sindri:complete/>" in GROA_PROMPT

    def test_groa_prompt_distinguishes_vision_vs_traditional(self):
        """Groa prompt explains when to use vision vs traditional tools."""
        prompt_lower = GROA_PROMPT.lower()
        assert "when to use" in prompt_lower or "vision vs" in prompt_lower


# ═══════════════════════════════════════════════════════════════════════════════
# Brokkr Delegation Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrokkrDelegation:
    """Test that Brokkr can delegate to Groa."""

    def test_brokkr_can_delegate_to_groa(self):
        """Brokkr has Groa in delegate_to list."""
        brokkr = get_agent("brokkr")
        assert "groa" in brokkr.delegate_to

    def test_brokkr_delegation_count_updated(self):
        """Brokkr delegation count includes Groa (19 agents)."""
        brokkr = get_agent("brokkr")
        # Should be 19 agents after adding Groa
        assert len(brokkr.delegate_to) >= 19

    def test_groa_accessible_from_hierarchy(self):
        """Groa is accessible in the agent hierarchy."""
        brokkr = get_agent("brokkr")
        groa = get_agent("groa")

        assert brokkr.can_delegate is True
        assert groa.name in brokkr.delegate_to


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Count Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentCount:
    """Test total agent count after adding Groa."""

    def test_total_agent_count(self):
        """Total agent count is correct after adding Groa."""
        all_agents = list_agents()
        # Should be 22 agents after adding Groa
        # (21 before + 1 groa)
        assert len(all_agents) >= 22

    def test_all_expected_agents_exist(self):
        """All expected agents are registered."""
        expected_agents = [
            "brokkr",
            "huginn",
            "mimir",
            "ratatoskr",
            "skald",
            "fenrir",
            "odin",
            "heimdall",
            "baldr",
            "idunn",
            "vidar",
            "skuld",
            "kvasir",
            "volundr",
            "saga",
            "vor",
            "ran",
            "sif",
            "nidhogg",
            "tyr",
            "groa",  # NEW
            "sindri_admin",
        ]

        all_agents = list_agents()
        for agent_name in expected_agents:
            assert agent_name in all_agents, f"Missing agent: {agent_name}"


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGroaAgentIntegration:
    """Integration tests for Groa agent."""

    def test_groa_tools_exist_in_registry(self):
        """All tools assigned to Groa exist in tool registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()
        groa = get_agent("groa")
        tool_names = list(registry._tools.keys())

        for tool_name in groa.tools:
            assert tool_name in tool_names, f"Tool not found: {tool_name}"

    def test_groa_can_get_tool_schemas(self):
        """Can get tool schemas for all Groa's tools."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()
        groa = get_agent("groa")

        for tool_name in groa.tools:
            tool = registry.get_tool(tool_name)
            assert tool is not None, f"Tool not found: {tool_name}"
            schema = tool.get_schema()
            assert "function" in schema
            assert schema["function"]["name"] == tool_name
