"""Tests for Phase 7.1 Enhanced Agent Specialization.

Verifies that agent prompts contain:
- Specialized patterns and examples
- Domain-specific knowledge
- Proper structure and sections
"""

import pytest
from sindri.agents.prompts import (
    BROKKR_PROMPT,
    HUGINN_PROMPT,
    MIMIR_PROMPT,
    RATATOSKR_PROMPT,
    SKALD_PROMPT,
    FENRIR_PROMPT,
    ODIN_PROMPT,
)
from sindri.agents.registry import AGENTS, get_agent


class TestAgentPromptsExist:
    """Verify all agent prompts are non-empty and substantial."""

    def test_brokkr_prompt_substantial(self):
        """Brokkr prompt contains orchestration guidance."""
        assert len(BROKKR_PROMPT) > 500
        assert "orchestrator" in BROKKR_PROMPT.lower()
        assert "delegate" in BROKKR_PROMPT.lower()

    def test_huginn_prompt_substantial(self):
        """Huginn prompt contains code implementation patterns."""
        assert len(HUGINN_PROMPT) > 2000  # Enhanced with patterns
        assert "implementation" in HUGINN_PROMPT.lower()

    def test_mimir_prompt_substantial(self):
        """Mimir prompt contains review guidance."""
        assert len(MIMIR_PROMPT) > 2000  # Enhanced with security patterns
        assert "review" in MIMIR_PROMPT.lower()

    def test_skald_prompt_substantial(self):
        """Skald prompt contains testing patterns."""
        assert len(SKALD_PROMPT) > 2000  # Enhanced with pytest patterns
        assert "test" in SKALD_PROMPT.lower()

    def test_fenrir_prompt_substantial(self):
        """Fenrir prompt contains SQL patterns."""
        assert len(FENRIR_PROMPT) > 2000  # Enhanced with SQL patterns
        assert "sql" in FENRIR_PROMPT.lower()

    def test_odin_prompt_substantial(self):
        """Odin prompt contains reasoning patterns."""
        assert len(ODIN_PROMPT) > 1000  # Enhanced with planning
        assert "reasoning" in ODIN_PROMPT.lower() or "planning" in ODIN_PROMPT.lower()

    def test_ratatoskr_prompt_exists(self):
        """Ratatoskr prompt exists for simple tasks."""
        assert len(RATATOSKR_PROMPT) > 100
        assert "executor" in RATATOSKR_PROMPT.lower() or "swift" in RATATOSKR_PROMPT.lower()


class TestHuginnSpecialization:
    """Verify Huginn has code implementation expertise."""

    def test_contains_python_patterns(self):
        """Huginn prompt includes Python best practices."""
        assert "type hints" in HUGINN_PROMPT.lower() or "type_hints" in HUGINN_PROMPT.lower()
        assert "docstring" in HUGINN_PROMPT.lower()
        assert "async" in HUGINN_PROMPT.lower()

    def test_contains_typescript_patterns(self):
        """Huginn prompt includes TypeScript patterns."""
        assert "typescript" in HUGINN_PROMPT.lower()
        assert "interface" in HUGINN_PROMPT.lower()

    def test_contains_refactoring_patterns(self):
        """Huginn prompt includes refactoring guidance."""
        assert "refactor" in HUGINN_PROMPT.lower()
        assert "extract" in HUGINN_PROMPT.lower()

    def test_contains_error_handling_guidance(self):
        """Huginn prompt includes error handling patterns."""
        assert "error" in HUGINN_PROMPT.lower()
        assert "exception" in HUGINN_PROMPT.lower() or "try" in HUGINN_PROMPT.lower()

    def test_contains_code_examples(self):
        """Huginn prompt includes code examples."""
        assert "```python" in HUGINN_PROMPT
        assert "def " in HUGINN_PROMPT


class TestMimirSpecialization:
    """Verify Mimir has security and review expertise."""

    def test_contains_owasp_references(self):
        """Mimir prompt includes OWASP security patterns."""
        assert "owasp" in MIMIR_PROMPT.lower()
        # Check for at least some OWASP categories
        assert "injection" in MIMIR_PROMPT.lower()
        assert "access control" in MIMIR_PROMPT.lower()

    def test_contains_code_smell_detection(self):
        """Mimir prompt includes code smell guidance."""
        assert "smell" in MIMIR_PROMPT.lower() or "complexity" in MIMIR_PROMPT.lower()

    def test_contains_review_checklist(self):
        """Mimir prompt includes systematic review checklist."""
        assert "checklist" in MIMIR_PROMPT.lower()
        assert "correctness" in MIMIR_PROMPT.lower()
        assert "security" in MIMIR_PROMPT.lower()

    def test_contains_vulnerability_examples(self):
        """Mimir prompt includes vulnerability examples."""
        # SQL injection example
        assert "sql" in MIMIR_PROMPT.lower() and "injection" in MIMIR_PROMPT.lower()
        # XSS example
        assert "xss" in MIMIR_PROMPT.lower()

    def test_contains_review_output_format(self):
        """Mimir prompt includes structured output format."""
        assert "critical" in MIMIR_PROMPT.lower()
        assert "warning" in MIMIR_PROMPT.lower()
        assert "suggestion" in MIMIR_PROMPT.lower()


class TestSkaldSpecialization:
    """Verify Skald has testing expertise."""

    def test_contains_pytest_patterns(self):
        """Skald prompt includes pytest-specific patterns."""
        assert "pytest" in SKALD_PROMPT.lower()
        assert "fixture" in SKALD_PROMPT.lower()
        assert "parametrize" in SKALD_PROMPT.lower()

    def test_contains_mocking_patterns(self):
        """Skald prompt includes mocking guidance."""
        assert "mock" in SKALD_PROMPT.lower()
        assert "patch" in SKALD_PROMPT.lower()

    def test_contains_test_conventions(self):
        """Skald prompt includes test file conventions."""
        assert "test_" in SKALD_PROMPT
        assert "conftest" in SKALD_PROMPT.lower()

    def test_contains_edge_case_guidance(self):
        """Skald prompt includes edge case testing guidance."""
        assert "edge case" in SKALD_PROMPT.lower() or "edge cases" in SKALD_PROMPT.lower()
        assert "empty" in SKALD_PROMPT.lower()
        assert "none" in SKALD_PROMPT.lower() or "null" in SKALD_PROMPT.lower()

    def test_contains_test_quality_checklist(self):
        """Skald prompt includes test quality criteria."""
        assert "checklist" in SKALD_PROMPT.lower()
        assert "independent" in SKALD_PROMPT.lower()

    def test_contains_fixture_examples(self):
        """Skald prompt includes fixture code examples."""
        assert "@pytest.fixture" in SKALD_PROMPT


class TestFenrirSpecialization:
    """Verify Fenrir has SQL and database expertise."""

    def test_contains_schema_design_patterns(self):
        """Fenrir prompt includes schema design guidance."""
        assert "schema" in FENRIR_PROMPT.lower()
        assert "normalization" in FENRIR_PROMPT.lower() or "normalize" in FENRIR_PROMPT.lower()
        assert "foreign key" in FENRIR_PROMPT.lower()

    def test_contains_query_optimization(self):
        """Fenrir prompt includes query optimization guidance."""
        assert "optimization" in FENRIR_PROMPT.lower() or "optimize" in FENRIR_PROMPT.lower()
        assert "index" in FENRIR_PROMPT.lower()
        assert "explain" in FENRIR_PROMPT.lower()

    def test_contains_cte_patterns(self):
        """Fenrir prompt includes CTE (Common Table Expression) patterns."""
        assert "cte" in FENRIR_PROMPT.lower() or "common table expression" in FENRIR_PROMPT.lower()
        assert "with " in FENRIR_PROMPT.lower() or "WITH " in FENRIR_PROMPT

    def test_contains_window_functions(self):
        """Fenrir prompt includes window function patterns."""
        assert "window" in FENRIR_PROMPT.lower()
        assert "over" in FENRIR_PROMPT.lower() or "OVER" in FENRIR_PROMPT

    def test_contains_migration_patterns(self):
        """Fenrir prompt includes migration guidance."""
        assert "migration" in FENRIR_PROMPT.lower()
        assert "alembic" in FENRIR_PROMPT.lower()

    def test_contains_database_specific_features(self):
        """Fenrir prompt covers multiple database systems."""
        assert "sqlite" in FENRIR_PROMPT.lower()
        assert "postgresql" in FENRIR_PROMPT.lower()
        assert "mysql" in FENRIR_PROMPT.lower()

    def test_contains_sql_examples(self):
        """Fenrir prompt includes SQL code examples."""
        assert "```sql" in FENRIR_PROMPT
        assert "SELECT" in FENRIR_PROMPT
        assert "CREATE TABLE" in FENRIR_PROMPT


class TestOdinSpecialization:
    """Verify Odin has reasoning and planning expertise."""

    def test_contains_reasoning_framework(self):
        """Odin prompt includes structured reasoning guidance."""
        assert "reasoning" in ODIN_PROMPT.lower()
        assert "<think>" in ODIN_PROMPT

    def test_contains_architecture_patterns(self):
        """Odin prompt includes architecture decision patterns."""
        assert "architecture" in ODIN_PROMPT.lower()
        assert "trade-off" in ODIN_PROMPT.lower() or "tradeoff" in ODIN_PROMPT.lower()

    def test_contains_planning_checklist(self):
        """Odin prompt includes planning verification."""
        assert "checklist" in ODIN_PROMPT.lower()
        assert "risk" in ODIN_PROMPT.lower()
        assert "dependencies" in ODIN_PROMPT.lower() or "dependency" in ODIN_PROMPT.lower()

    def test_contains_delegation_guidance(self):
        """Odin prompt includes delegation to specialists."""
        assert "delegate" in ODIN_PROMPT.lower()
        assert "huginn" in ODIN_PROMPT.lower()
        assert "skald" in ODIN_PROMPT.lower()


class TestAgentRegistry:
    """Verify agents in registry have correct prompts."""

    def test_all_agents_have_prompts(self):
        """All registered agents have non-empty system prompts."""
        for name, agent in AGENTS.items():
            assert agent.system_prompt, f"Agent {name} has no system prompt"
            assert len(agent.system_prompt) > 50, f"Agent {name} has minimal prompt"

    def test_get_agent_returns_correct_prompts(self):
        """get_agent returns agents with enhanced prompts."""
        huginn = get_agent("huginn")
        assert "type hints" in huginn.system_prompt.lower() or "python" in huginn.system_prompt.lower()

        mimir = get_agent("mimir")
        assert "security" in mimir.system_prompt.lower() or "review" in mimir.system_prompt.lower()

        skald = get_agent("skald")
        assert "test" in skald.system_prompt.lower()

        fenrir = get_agent("fenrir")
        assert "sql" in fenrir.system_prompt.lower()

    def test_agent_tools_match_specialization(self):
        """Agent tools are appropriate for their specialization."""
        huginn = get_agent("huginn")
        assert "write_file" in huginn.tools
        assert "edit_file" in huginn.tools
        assert "shell" in huginn.tools

        mimir = get_agent("mimir")
        assert "read_file" in mimir.tools
        assert "shell" in mimir.tools  # For running tests

        skald = get_agent("skald")
        assert "write_file" in skald.tools  # Write test files
        assert "shell" in skald.tools  # Run pytest

        fenrir = get_agent("fenrir")
        assert "write_file" in fenrir.tools  # Write SQL files


class TestToolExecutionFlowInPrompts:
    """Verify all prompts include tool execution flow guidance."""

    def test_huginn_has_tool_flow(self):
        """Huginn prompt includes tool execution flow."""
        assert "WAIT FOR" in HUGINN_PROMPT
        assert "<sindri:complete/>" in HUGINN_PROMPT

    def test_mimir_has_tool_flow(self):
        """Mimir prompt includes tool execution flow."""
        assert "WAIT FOR" in MIMIR_PROMPT
        assert "<sindri:complete/>" in MIMIR_PROMPT

    def test_skald_has_tool_flow(self):
        """Skald prompt includes tool execution flow."""
        assert "WAIT FOR" in SKALD_PROMPT
        assert "<sindri:complete/>" in SKALD_PROMPT

    def test_fenrir_has_tool_flow(self):
        """Fenrir prompt includes tool execution flow."""
        assert "WAIT FOR" in FENRIR_PROMPT
        assert "<sindri:complete/>" in FENRIR_PROMPT

    def test_odin_has_tool_flow(self):
        """Odin prompt includes tool execution flow."""
        assert "WAIT FOR" in ODIN_PROMPT
        assert "<sindri:complete/>" in ODIN_PROMPT

    def test_brokkr_has_tool_flow(self):
        """Brokkr prompt includes tool execution flow."""
        assert "WAIT FOR" in BROKKR_PROMPT
        assert "<sindri:complete/>" in BROKKR_PROMPT
