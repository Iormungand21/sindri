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
        tools=["read_file", "write_file", "edit_file", "list_directory", "read_tree", "search_code", "find_symbol", "git_status", "git_diff", "git_log", "git_branch", "shell", "delegate", "propose_plan"],
        can_delegate=True,
        delegate_to=["huginn", "mimir", "skald", "fenrir", "odin"],  # Removed ratatoskr - brokkr can handle simple tasks
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
        tools=["read_file", "write_file", "edit_file", "list_directory", "read_tree", "search_code", "find_symbol", "git_status", "git_diff", "git_log", "shell", "delegate"],
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
        tools=["read_file", "search_code", "git_diff", "git_log", "shell"],
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
        tools=["read_file", "write_file", "shell"],
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
        tools=["read_file", "write_file", "shell"],
        can_delegate=False,
        estimated_vram_gb=5.0,
        priority=1,
        max_iterations=20,
        # No fallback - sqlcoder is specialized, no smaller equivalent
    ),

    "odin": AgentDefinition(
        name="odin",
        role="Deep reasoning and planning specialist",
        model="deepseek-r1:8b",  # Reasoning model
        system_prompt=ODIN_PROMPT,
        tools=["read_file", "search_code", "git_status", "git_log", "delegate"],
        can_delegate=True,
        delegate_to=["huginn", "skald", "fenrir"],
        estimated_vram_gb=6.0,
        priority=0,
        max_iterations=15,
        temperature=0.7,  # Higher temp for creative thinking
        # Phase 5.6: Fallback to smaller model when VRAM is insufficient
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
