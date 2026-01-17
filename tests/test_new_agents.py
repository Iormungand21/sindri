"""Tests for Phase 9 Agent Expansion (2026-01-16).

Verifies that the 4 new agents are properly configured:
- Heimdall (Security Guardian)
- Baldr (Debugger)
- Idunn (Documentation)
- Vidar (Multi-language Coder)

Also tests Odin upgrade to deepseek-r1:14b.
"""

from sindri.agents.prompts import (
    HEIMDALL_PROMPT,
    BALDR_PROMPT,
    IDUNN_PROMPT,
    VIDAR_PROMPT,
)
from sindri.agents.registry import AGENTS, get_agent, list_agents


class TestNewAgentsExist:
    """Verify all new agents are registered."""

    def test_heimdall_exists(self):
        """Heimdall agent is registered."""
        assert "heimdall" in AGENTS
        agent = get_agent("heimdall")
        assert agent.name == "heimdall"

    def test_baldr_exists(self):
        """Baldr agent is registered."""
        assert "baldr" in AGENTS
        agent = get_agent("baldr")
        assert agent.name == "baldr"

    def test_idunn_exists(self):
        """Idunn agent is registered."""
        assert "idunn" in AGENTS
        agent = get_agent("idunn")
        assert agent.name == "idunn"

    def test_vidar_exists(self):
        """Vidar agent is registered."""
        assert "vidar" in AGENTS
        agent = get_agent("vidar")
        assert agent.name == "vidar"

    def test_total_agent_count(self):
        """Total agent count is 11 (7 original + 4 new)."""
        agents = list_agents()
        assert len(agents) == 11


class TestHeimdallAgent:
    """Tests for Heimdall (Security Guardian)."""

    def test_heimdall_role(self):
        """Heimdall has security-focused role."""
        agent = get_agent("heimdall")
        assert "security" in agent.role.lower()

    def test_heimdall_model(self):
        """Heimdall uses qwen3:14b for reasoning."""
        agent = get_agent("heimdall")
        assert "qwen3:14b" in agent.model

    def test_heimdall_vram_estimate(self):
        """Heimdall VRAM estimate is reasonable for 14b model."""
        agent = get_agent("heimdall")
        assert agent.estimated_vram_gb >= 9.0
        assert agent.estimated_vram_gb <= 12.0

    def test_heimdall_has_security_tools(self):
        """Heimdall has tools needed for security analysis."""
        agent = get_agent("heimdall")
        assert "read_file" in agent.tools
        assert "search_code" in agent.tools
        assert "lint_code" in agent.tools

    def test_heimdall_can_delegate(self):
        """Heimdall can delegate to Mimir."""
        agent = get_agent("heimdall")
        assert agent.can_delegate
        assert "mimir" in agent.delegate_to

    def test_heimdall_prompt_contains_owasp(self):
        """Heimdall prompt contains OWASP Top 10."""
        assert "owasp" in HEIMDALL_PROMPT.lower()
        assert "injection" in HEIMDALL_PROMPT.lower()
        assert "access control" in HEIMDALL_PROMPT.lower()

    def test_heimdall_prompt_contains_secrets_detection(self):
        """Heimdall prompt contains secrets detection patterns."""
        assert "secret" in HEIMDALL_PROMPT.lower()
        assert "api" in HEIMDALL_PROMPT.lower() and "key" in HEIMDALL_PROMPT.lower()

    def test_heimdall_has_fallback(self):
        """Heimdall has fallback model configured."""
        agent = get_agent("heimdall")
        assert agent.fallback_model is not None
        assert agent.fallback_vram_gb is not None


class TestBaldrAgent:
    """Tests for Baldr (Debugger)."""

    def test_baldr_role(self):
        """Baldr has debugging-focused role."""
        agent = get_agent("baldr")
        assert "debug" in agent.role.lower() or "problem" in agent.role.lower()

    def test_baldr_model(self):
        """Baldr uses deepseek-r1:14b for reasoning."""
        agent = get_agent("baldr")
        assert "deepseek-r1:14b" in agent.model

    def test_baldr_vram_estimate(self):
        """Baldr VRAM estimate is reasonable for 14b model."""
        agent = get_agent("baldr")
        assert agent.estimated_vram_gb >= 8.0
        assert agent.estimated_vram_gb <= 11.0

    def test_baldr_has_debugging_tools(self):
        """Baldr has tools needed for debugging."""
        agent = get_agent("baldr")
        assert "read_file" in agent.tools
        assert "search_code" in agent.tools
        assert "git_diff" in agent.tools
        assert "run_tests" in agent.tools

    def test_baldr_can_delegate_to_huginn(self):
        """Baldr can delegate fixes to Huginn."""
        agent = get_agent("baldr")
        assert agent.can_delegate
        assert "huginn" in agent.delegate_to

    def test_baldr_prompt_contains_methodology(self):
        """Baldr prompt contains debugging methodology."""
        assert "hypothesis" in BALDR_PROMPT.lower() or "observe" in BALDR_PROMPT.lower()
        assert "root cause" in BALDR_PROMPT.lower()

    def test_baldr_prompt_contains_stack_trace(self):
        """Baldr prompt contains stack trace interpretation."""
        assert "stack" in BALDR_PROMPT.lower() or "traceback" in BALDR_PROMPT.lower()

    def test_baldr_prompt_contains_bug_patterns(self):
        """Baldr prompt contains common bug patterns."""
        assert "off-by-one" in BALDR_PROMPT.lower() or "none" in BALDR_PROMPT.lower()

    def test_baldr_has_fallback(self):
        """Baldr has fallback model configured."""
        agent = get_agent("baldr")
        assert agent.fallback_model == "deepseek-r1:8b"


class TestIdunnAgent:
    """Tests for Idunn (Documentation)."""

    def test_idunn_role(self):
        """Idunn has documentation-focused role."""
        agent = get_agent("idunn")
        assert "documentation" in agent.role.lower() or "doc" in agent.role.lower()

    def test_idunn_model(self):
        """Idunn uses llama3.1:8b (shares with Mimir)."""
        agent = get_agent("idunn")
        assert "llama3.1:8b" in agent.model

    def test_idunn_vram_estimate(self):
        """Idunn VRAM estimate is efficient (shared model)."""
        agent = get_agent("idunn")
        assert agent.estimated_vram_gb <= 6.0

    def test_idunn_has_writing_tools(self):
        """Idunn has tools needed for documentation."""
        agent = get_agent("idunn")
        assert "read_file" in agent.tools
        assert "write_file" in agent.tools
        assert "list_directory" in agent.tools
        assert "read_tree" in agent.tools

    def test_idunn_cannot_delegate(self):
        """Idunn does not delegate (focused specialist)."""
        agent = get_agent("idunn")
        assert not agent.can_delegate

    def test_idunn_prompt_contains_docstring_styles(self):
        """Idunn prompt contains docstring style guidance."""
        assert "google" in IDUNN_PROMPT.lower() or "numpy" in IDUNN_PROMPT.lower()
        assert "docstring" in IDUNN_PROMPT.lower()

    def test_idunn_prompt_contains_readme_template(self):
        """Idunn prompt contains README structure."""
        assert "readme" in IDUNN_PROMPT.lower()
        assert "installation" in IDUNN_PROMPT.lower()

    def test_idunn_prompt_contains_changelog(self):
        """Idunn prompt contains changelog guidance."""
        assert "changelog" in IDUNN_PROMPT.lower()

    def test_idunn_has_fallback(self):
        """Idunn has fallback model configured."""
        agent = get_agent("idunn")
        assert agent.fallback_model is not None


class TestVidarAgent:
    """Tests for Vidar (Multi-language Coder)."""

    def test_vidar_role(self):
        """Vidar has multi-language coding role."""
        agent = get_agent("vidar")
        assert (
            "multi-language" in agent.role.lower() or "language" in agent.role.lower()
        )

    def test_vidar_model(self):
        """Vidar uses codestral for multi-language support."""
        agent = get_agent("vidar")
        assert "codestral" in agent.model

    def test_vidar_vram_estimate(self):
        """Vidar VRAM estimate is reasonable for 22b model."""
        agent = get_agent("vidar")
        assert agent.estimated_vram_gb >= 12.0
        assert agent.estimated_vram_gb <= 16.0

    def test_vidar_has_coding_tools(self):
        """Vidar has tools needed for code generation."""
        agent = get_agent("vidar")
        assert "read_file" in agent.tools
        assert "write_file" in agent.tools
        assert "edit_file" in agent.tools
        assert "check_syntax" in agent.tools

    def test_vidar_can_delegate_to_skald(self):
        """Vidar can delegate test writing to Skald."""
        agent = get_agent("vidar")
        assert agent.can_delegate
        assert "skald" in agent.delegate_to

    def test_vidar_prompt_contains_multiple_languages(self):
        """Vidar prompt contains multiple programming languages."""
        # Check for tier 1 languages
        prompt_lower = VIDAR_PROMPT.lower()
        assert "python" in prompt_lower
        assert "javascript" in prompt_lower or "typescript" in prompt_lower
        assert "rust" in prompt_lower
        assert "go" in prompt_lower

    def test_vidar_prompt_contains_language_patterns(self):
        """Vidar prompt contains language-specific patterns."""
        assert "```rust" in VIDAR_PROMPT or "```go" in VIDAR_PROMPT
        assert "```typescript" in VIDAR_PROMPT or "```java" in VIDAR_PROMPT

    def test_vidar_has_fallback(self):
        """Vidar has fallback model configured."""
        agent = get_agent("vidar")
        assert agent.fallback_model == "qwen2.5-coder:7b"


class TestOdinUpgrade:
    """Tests for Odin upgrade to deepseek-r1:14b."""

    def test_odin_uses_14b_model(self):
        """Odin now uses deepseek-r1:14b instead of 8b."""
        agent = get_agent("odin")
        assert "deepseek-r1:14b" in agent.model

    def test_odin_vram_updated(self):
        """Odin VRAM estimate updated for 14b model."""
        agent = get_agent("odin")
        assert agent.estimated_vram_gb >= 8.0

    def test_odin_fallback_to_8b(self):
        """Odin falls back to deepseek-r1:8b when needed."""
        agent = get_agent("odin")
        assert agent.fallback_model == "deepseek-r1:8b"


class TestBrokkrDelegation:
    """Tests for Brokkr's updated delegation list."""

    def test_brokkr_can_delegate_to_new_agents(self):
        """Brokkr can delegate to all new agents."""
        agent = get_agent("brokkr")
        assert "heimdall" in agent.delegate_to
        assert "baldr" in agent.delegate_to
        assert "idunn" in agent.delegate_to
        assert "vidar" in agent.delegate_to

    def test_brokkr_delegation_count(self):
        """Brokkr can delegate to 9 agents (5 original + 4 new)."""
        agent = get_agent("brokkr")
        assert len(agent.delegate_to) == 9


class TestPromptQuality:
    """Verify new prompts meet quality standards."""

    def test_heimdall_prompt_length(self):
        """Heimdall prompt is substantial."""
        assert len(HEIMDALL_PROMPT) > 3000

    def test_baldr_prompt_length(self):
        """Baldr prompt is substantial."""
        assert len(BALDR_PROMPT) > 3000

    def test_idunn_prompt_length(self):
        """Idunn prompt is substantial."""
        assert len(IDUNN_PROMPT) > 3000

    def test_vidar_prompt_length(self):
        """Vidar prompt is substantial."""
        assert len(VIDAR_PROMPT) > 3000

    def test_all_prompts_have_tool_flow(self):
        """All new prompts include tool execution flow."""
        for prompt in [HEIMDALL_PROMPT, BALDR_PROMPT, IDUNN_PROMPT, VIDAR_PROMPT]:
            assert "tool execution flow" in prompt.lower()
            assert "sindri:complete" in prompt.lower()

    def test_all_prompts_have_core_capabilities(self):
        """All new prompts include core capabilities section."""
        for prompt in [HEIMDALL_PROMPT, BALDR_PROMPT, IDUNN_PROMPT, VIDAR_PROMPT]:
            assert "core capabilities" in prompt.lower()

    def test_prompts_contain_code_examples(self):
        """New prompts contain code examples where appropriate."""
        # Heimdall should have security code examples
        assert "```python" in HEIMDALL_PROMPT
        # Baldr should have debugging examples
        assert "```python" in BALDR_PROMPT
        # Vidar should have multi-language examples
        assert "```rust" in VIDAR_PROMPT
        assert "```go" in VIDAR_PROMPT


class TestAgentModelsAvailability:
    """Test that agent models are correctly configured."""

    def test_models_for_new_agents(self):
        """New agents use appropriate models."""
        heimdall = get_agent("heimdall")
        baldr = get_agent("baldr")
        idunn = get_agent("idunn")
        vidar = get_agent("vidar")

        # Heimdall uses reasoning model
        assert "qwen3" in heimdall.model or "deepseek" in heimdall.model

        # Baldr uses reasoning model (same as upgraded Odin)
        assert "deepseek-r1:14b" in baldr.model

        # Idunn shares model with Mimir
        mimir = get_agent("mimir")
        assert idunn.model == mimir.model

        # Vidar uses dedicated code model
        assert "codestral" in vidar.model

    def test_fallback_models_are_smaller(self):
        """Fallback models have lower VRAM requirements."""
        for name in ["heimdall", "baldr", "idunn", "vidar"]:
            agent = get_agent(name)
            if agent.fallback_model and agent.fallback_vram_gb:
                assert agent.fallback_vram_gb < agent.estimated_vram_gb
