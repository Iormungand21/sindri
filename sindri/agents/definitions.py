"""Agent definition dataclass for Sindri."""

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sindri.core.policy import AgentPolicy, EscalationMode


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

    # Policy + Guardrails: Agent-level constraints
    policy: Optional["AgentPolicy"] = None  # Full policy object (takes precedence)
    max_tool_calls: Optional[int] = None  # Convenience: max tool calls per task
    max_files_touched: Optional[int] = None  # Convenience: max files accessed
    max_runtime_seconds: Optional[float] = None  # Convenience: max runtime
    file_scope: list[str] = field(default_factory=list)  # Convenience: allowed paths
    escalation_mode: str = "deny"  # Convenience: deny, warn, escalate

    def can_delegate_to(self, agent_name: str) -> bool:
        """Check if this agent can delegate to the specified agent."""
        return self.can_delegate and agent_name in self.delegate_to

    def has_tool(self, tool_name: str) -> bool:
        """Check if agent has access to a tool."""
        return tool_name in self.tools

    def get_effective_policy(
        self, default_policy: Optional["AgentPolicy"] = None
    ) -> "AgentPolicy":
        """Get the effective policy for this agent.

        Priority: agent.policy > agent convenience fields > default_policy > no limits

        Args:
            default_policy: Fallback policy if no agent-specific settings

        Returns:
            AgentPolicy to use for this agent
        """
        from sindri.core.policy import AgentPolicy, EscalationMode

        # If explicit policy object is set, use it
        if self.policy is not None:
            return self.policy

        # Build from convenience fields if any are set
        if any(
            [
                self.max_tool_calls is not None,
                self.max_files_touched is not None,
                self.max_runtime_seconds is not None,
                self.file_scope,
            ]
        ):
            return AgentPolicy(
                max_tool_calls=self.max_tool_calls,
                max_files_touched=self.max_files_touched,
                max_runtime_seconds=self.max_runtime_seconds,
                file_scope=self.file_scope,
                escalation_mode=EscalationMode(self.escalation_mode),
            )

        # Use default if provided
        if default_policy is not None:
            return default_policy

        # No limits
        return AgentPolicy()
