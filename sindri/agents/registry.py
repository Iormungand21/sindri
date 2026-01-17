"""Agent registry for Sindri."""

from sindri.agents.definitions import AgentDefinition
from sindri.agents.prompts import (
    BROKKR_PROMPT,
    HUGINN_PROMPT,
    MIMIR_PROMPT,
    RATATOSKR_PROMPT,
    SKALD_PROMPT,
    FENRIR_PROMPT,
    ODIN_PROMPT,
    # Phase 9: New agents (2026-01-16)
    HEIMDALL_PROMPT,
    BALDR_PROMPT,
    IDUNN_PROMPT,
    VIDAR_PROMPT,
)

# Agent Registry
# All agents available in the Sindri system
AGENTS: dict[str, AgentDefinition] = {
    # Core orchestration agents
    "brokkr": AgentDefinition(
        name="brokkr",
        role="Master orchestrator - handles simple tasks, delegates complex work",
        model="qwen2.5-coder:14b",  # Using available model
        system_prompt=BROKKR_PROMPT,
        tools=["read_file", "write_file", "edit_file", "list_directory", "read_tree", "search_code", "find_symbol", "git_status", "git_diff", "git_log", "git_branch", "http_request", "run_tests", "check_syntax", "format_code", "lint_code", "rename_symbol", "extract_function", "inline_variable", "move_file", "batch_rename", "split_file", "merge_files", "shell", "delegate", "propose_plan"],
        can_delegate=True,
        # Phase 9: Added heimdall, baldr, idunn, vidar to delegation targets
        delegate_to=["huginn", "mimir", "skald", "fenrir", "odin", "heimdall", "baldr", "idunn", "vidar"],
        estimated_vram_gb=9.0,
        priority=0,
        max_iterations=15,  # Reduced since simple tasks won't take many iterations
        # Phase 5.6: Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5-coder:7b",
        fallback_vram_gb=5.0,
    ),

    "huginn": AgentDefinition(
        name="huginn",
        role="Code implementation specialist",
        model="qwen2.5-coder:7b",  # Using available model
        system_prompt=HUGINN_PROMPT,
        tools=["read_file", "write_file", "edit_file", "list_directory", "read_tree", "search_code", "find_symbol", "git_status", "git_diff", "git_log", "http_request", "run_tests", "check_syntax", "format_code", "lint_code", "rename_symbol", "extract_function", "inline_variable", "move_file", "batch_rename", "split_file", "merge_files", "shell", "delegate"],
        can_delegate=True,
        delegate_to=["ratatoskr", "skald"],
        estimated_vram_gb=5.0,
        priority=1,
        max_iterations=30,
        # Phase 5.6: Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),

    "mimir": AgentDefinition(
        name="mimir",
        role="Code reviewer and quality checker",
        model="llama3.1:8b",  # Using available model
        system_prompt=MIMIR_PROMPT,
        tools=["read_file", "search_code", "git_diff", "git_log", "run_tests", "check_syntax", "lint_code", "shell"],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=1,
        max_iterations=20,
        # Phase 5.6: Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),

    "ratatoskr": AgentDefinition(
        name="ratatoskr",
        role="Fast executor for simple tasks",
        model="qwen2.5:3b-instruct-q8_0",
        system_prompt=RATATOSKR_PROMPT,
        tools=["shell", "read_file", "write_file"],
        can_delegate=False,
        estimated_vram_gb=3.0,
        priority=2,
        max_iterations=10,
        # No fallback - already the smallest model
    ),

    # Specialized agents
    "skald": AgentDefinition(
        name="skald",
        role="Test writer and quality guardian",
        model="qwen2.5-coder:7b",  # Good for test generation
        system_prompt=SKALD_PROMPT,
        tools=["read_file", "write_file", "http_request", "run_tests", "check_syntax", "shell"],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=1,
        max_iterations=25,
        # Phase 5.6: Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),

    "fenrir": AgentDefinition(
        name="fenrir",
        role="SQL and data specialist",
        model="sqlcoder:7b",  # Specialized SQL model
        system_prompt=FENRIR_PROMPT,
        tools=["read_file", "write_file", "http_request", "execute_query", "describe_schema", "explain_query", "shell"],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=1,
        max_iterations=20,
        # No fallback - sqlcoder is specialized, no smaller equivalent
    ),

    "odin": AgentDefinition(
        name="odin",
        role="Deep reasoning and planning specialist",
        model="deepseek-r1:14b",  # Upgraded to 14b for better reasoning (already pulled!)
        system_prompt=ODIN_PROMPT,
        tools=["read_file", "search_code", "git_status", "git_log", "delegate"],
        can_delegate=True,
        delegate_to=["huginn", "skald", "fenrir"],
        estimated_vram_gb=9.0,  # Updated for 14b model
        priority=0,
        max_iterations=15,
        temperature=0.7,  # Higher temp for creative thinking
        # Phase 5.6: Fallback to smaller model when VRAM is insufficient
        fallback_model="deepseek-r1:8b",  # Fall back to 8b version
        fallback_vram_gb=5.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════════════
    # Phase 9: New Specialized Agents (2026-01-16)
    # ═══════════════════════════════════════════════════════════════════════════════

    "heimdall": AgentDefinition(
        name="heimdall",
        role="Security guardian - vulnerability detection and OWASP analysis",
        model="qwen3:14b",  # Reasoning model with thinking mode for security analysis
        system_prompt=HEIMDALL_PROMPT,
        tools=["read_file", "search_code", "git_diff", "git_log", "lint_code", "shell"],
        can_delegate=True,
        delegate_to=["mimir"],  # Can escalate to code reviewer
        estimated_vram_gb=10.0,
        priority=1,
        max_iterations=20,
        temperature=0.3,  # Lower temp for precise security analysis
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5-coder:7b",
        fallback_vram_gb=5.0,
    ),

    "baldr": AgentDefinition(
        name="baldr",
        role="Debugger and problem solver - root cause analysis",
        model="deepseek-r1:14b",  # Already pulled! Great for reasoning about bugs
        system_prompt=BALDR_PROMPT,
        tools=["read_file", "search_code", "git_diff", "git_log", "run_tests", "shell", "delegate"],
        can_delegate=True,
        delegate_to=["huginn"],  # Can delegate fixes to coder
        estimated_vram_gb=9.0,
        priority=1,
        max_iterations=25,
        temperature=0.5,  # Balanced for hypothesis exploration
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="deepseek-r1:8b",
        fallback_vram_gb=5.0,
    ),

    "idunn": AgentDefinition(
        name="idunn",
        role="Documentation specialist - docstrings, READMEs, API docs",
        model="llama3.1:8b",  # Shares model with Mimir for VRAM efficiency
        system_prompt=IDUNN_PROMPT,
        tools=["read_file", "write_file", "list_directory", "read_tree", "search_code", "edit_file"],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=2,
        max_iterations=20,
        temperature=0.4,  # Moderate creativity for documentation
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5:3b-instruct-q8_0",
        fallback_vram_gb=3.0,
    ),

    "vidar": AgentDefinition(
        name="vidar",
        role="Multi-language code specialist - 80+ programming languages",
        model="codestral:22b-v0.1-q4_K_M",  # Mistral's dedicated code model
        system_prompt=VIDAR_PROMPT,
        tools=["read_file", "write_file", "edit_file", "search_code", "check_syntax", "shell", "delegate"],
        can_delegate=True,
        delegate_to=["skald"],  # Can delegate test writing
        estimated_vram_gb=14.0,
        priority=1,
        max_iterations=30,
        temperature=0.3,  # Lower temp for precise code generation
        # Fallback to smaller model when VRAM is insufficient
        fallback_model="qwen2.5-coder:7b",
        fallback_vram_gb=5.0,
    ),
}


def get_agent(name: str) -> AgentDefinition:
    """Get an agent by name."""
    agent = AGENTS.get(name)
    if not agent:
        raise ValueError(f"Unknown agent: {name}")
    return agent


def list_agents() -> list[str]:
    """List all agent names."""
    return list(AGENTS.keys())
