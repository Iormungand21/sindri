"""Agent definition dataclass for Sindri."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentDefinition:
    """Defines an agent's capabilities and configuration."""

    # Identity
    name: str  # Unique identifier (e.g., "brokkr")
    role: str  # Human description
    model: str  # Ollama model name
    system_prompt: str  # Role-specific prompt
    tools: list[str]  # Allowed tool names

    # Context management
    max_context_tokens: int = 16384
    temperature: float = 0.3

    # Delegation
    can_delegate: bool = False
    delegate_to: list[str] = field(default_factory=list)

    # Resource hints
    estimated_vram_gb: float = 8.0
    priority: int = 1  # Lower = higher priority
    max_iterations: int = 30

    # Phase 5.6: Model degradation fallback
    fallback_model: Optional[str] = None  # Smaller model to use if primary fails
    fallback_vram_gb: Optional[float] = None  # VRAM requirement for fallback model

    def can_delegate_to(self, agent_name: str) -> bool:
        """Check if this agent can delegate to the specified agent."""
        return self.can_delegate and agent_name in self.delegate_to

    def has_tool(self, tool_name: str) -> bool:
        """Check if agent has access to a tool."""
        return tool_name in self.tools
