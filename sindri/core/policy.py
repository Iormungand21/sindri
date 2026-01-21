"""Agent policy enforcement for Sindri.

This module provides policy constraints and guardrails for agent execution,
including limits on tool calls, files touched, runtime, and file scope.

Phase: Policy + Guardrails (ROADMAP item 6)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Set
import fnmatch
import structlog

log = structlog.get_logger()


class EscalationMode(str, Enum):
    """How to handle policy violations."""

    DENY = "deny"  # Block the operation, fail the task
    WARN = "warn"  # Log warning but allow
    ESCALATE = "escalate"  # Escalate to supervised mode for approval


@dataclass
class AgentPolicy:
    """Policy constraints for an agent.

    Defines what an agent can and cannot do during task execution.
    All limits are optional - None means unlimited.
    """

    # Resource limits
    max_tool_calls: Optional[int] = None  # Max tool invocations (None = unlimited)
    max_files_touched: Optional[int] = None  # Max unique files read/written
    max_runtime_seconds: Optional[float] = None  # Max wall-clock time

    # File scope constraints
    file_scope: list[str] = field(default_factory=list)  # Glob patterns
    file_scope_mode: str = "allowlist"  # "allowlist" or "blocklist"

    # Tool constraints (in addition to global tool permissions)
    tool_budget: dict[str, int] = field(default_factory=dict)  # Per-tool call limits

    # Escalation behavior
    escalation_mode: EscalationMode = EscalationMode.DENY

    def allows_file(self, path: str | Path) -> bool:
        """Check if a file path is allowed by the file scope.

        Args:
            path: File path to check

        Returns:
            True if file access is allowed, False otherwise
        """
        if not self.file_scope:
            return True  # No scope = all files allowed

        path_str = str(Path(path).resolve())
        matches = any(fnmatch.fnmatch(path_str, pattern) for pattern in self.file_scope)

        if self.file_scope_mode == "allowlist":
            return matches
        else:  # blocklist
            return not matches


@dataclass
class PolicyState:
    """Runtime state for tracking policy compliance.

    Tracks current usage against policy limits during task execution.
    """

    task_id: str
    agent_name: str
    policy: AgentPolicy

    # Counters
    tool_calls: int = 0
    tool_calls_by_name: dict[str, int] = field(default_factory=dict)
    files_touched: Set[str] = field(default_factory=set)
    start_time: datetime = field(default_factory=datetime.now)

    def record_tool_call(self, tool_name: str) -> None:
        """Record a tool call.

        Args:
            tool_name: Name of the tool being called
        """
        self.tool_calls += 1
        self.tool_calls_by_name[tool_name] = (
            self.tool_calls_by_name.get(tool_name, 0) + 1
        )

    def record_file_access(self, path: str) -> None:
        """Record a file being accessed.

        Args:
            path: Path to the file being accessed
        """
        self.files_touched.add(str(Path(path).resolve()))

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time since task start."""
        return (datetime.now() - self.start_time).total_seconds()


@dataclass
class PolicyCheckResult:
    """Result of a policy check."""

    allowed: bool
    reason: str
    violation_type: Optional[str] = None  # e.g., "max_tool_calls", "file_scope"
    escalation_mode: Optional[EscalationMode] = None
    current_value: Optional[int | float] = None
    limit_value: Optional[int | float] = None


class PolicyEnforcer:
    """Enforces policy constraints during task execution."""

    def __init__(self, state: PolicyState):
        """Initialize the policy enforcer.

        Args:
            state: Policy state to track compliance
        """
        self.state = state

    def check_tool_call(self, tool_name: str) -> PolicyCheckResult:
        """Check if a tool call is allowed.

        Args:
            tool_name: Name of the tool to call

        Returns:
            PolicyCheckResult indicating if the call is allowed
        """
        policy = self.state.policy

        # Check global tool call limit
        if policy.max_tool_calls is not None:
            if self.state.tool_calls >= policy.max_tool_calls:
                return PolicyCheckResult(
                    allowed=False,
                    reason=f"Max tool calls exceeded ({self.state.tool_calls}/{policy.max_tool_calls})",
                    violation_type="max_tool_calls",
                    escalation_mode=policy.escalation_mode,
                    current_value=self.state.tool_calls,
                    limit_value=policy.max_tool_calls,
                )

        # Check per-tool budget
        if tool_name in policy.tool_budget:
            current = self.state.tool_calls_by_name.get(tool_name, 0)
            limit = policy.tool_budget[tool_name]
            if current >= limit:
                return PolicyCheckResult(
                    allowed=False,
                    reason=f"Tool '{tool_name}' budget exceeded ({current}/{limit})",
                    violation_type="tool_budget",
                    escalation_mode=policy.escalation_mode,
                    current_value=current,
                    limit_value=limit,
                )

        return PolicyCheckResult(allowed=True, reason="Tool call allowed")

    def check_file_access(self, path: str) -> PolicyCheckResult:
        """Check if file access is allowed.

        Args:
            path: Path to the file to access

        Returns:
            PolicyCheckResult indicating if access is allowed
        """
        policy = self.state.policy

        # Check file scope
        if not policy.allows_file(path):
            return PolicyCheckResult(
                allowed=False,
                reason=f"File '{path}' outside allowed scope",
                violation_type="file_scope",
                escalation_mode=policy.escalation_mode,
            )

        # Check max files limit
        if policy.max_files_touched is not None:
            # If this is a new file, check limit
            resolved = str(Path(path).resolve())
            if resolved not in self.state.files_touched:
                if len(self.state.files_touched) >= policy.max_files_touched:
                    return PolicyCheckResult(
                        allowed=False,
                        reason=f"Max files exceeded ({len(self.state.files_touched)}/{policy.max_files_touched})",
                        violation_type="max_files_touched",
                        escalation_mode=policy.escalation_mode,
                        current_value=len(self.state.files_touched),
                        limit_value=policy.max_files_touched,
                    )

        return PolicyCheckResult(allowed=True, reason="File access allowed")

    def check_runtime(self) -> PolicyCheckResult:
        """Check if runtime limit has been exceeded.

        Returns:
            PolicyCheckResult indicating if runtime is within limits
        """
        policy = self.state.policy

        if policy.max_runtime_seconds is not None:
            elapsed = self.state.elapsed_seconds
            if elapsed >= policy.max_runtime_seconds:
                return PolicyCheckResult(
                    allowed=False,
                    reason=f"Max runtime exceeded ({elapsed:.1f}s/{policy.max_runtime_seconds}s)",
                    violation_type="max_runtime",
                    escalation_mode=policy.escalation_mode,
                    current_value=elapsed,
                    limit_value=policy.max_runtime_seconds,
                )

        return PolicyCheckResult(allowed=True, reason="Runtime within limits")
