"""Tests for Policy + Guardrails feature."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from sindri.core.policy import (
    AgentPolicy,
    EscalationMode,
    PolicyState,
    PolicyEnforcer,
    PolicyCheckResult,
)


class TestAgentPolicy:
    """Test AgentPolicy dataclass."""

    def test_default_policy_allows_everything(self):
        """Default policy has no restrictions."""
        policy = AgentPolicy()
        assert policy.max_tool_calls is None
        assert policy.max_files_touched is None
        assert policy.max_runtime_seconds is None
        assert policy.file_scope == []
        assert policy.escalation_mode == EscalationMode.DENY

    def test_file_scope_allowlist(self, tmp_path):
        """Test file scope with allowlist mode."""
        policy = AgentPolicy(
            file_scope=[str(tmp_path / "src/*"), str(tmp_path / "tests/*")],
            file_scope_mode="allowlist",
        )

        assert policy.allows_file(tmp_path / "src/main.py")
        assert policy.allows_file(tmp_path / "tests/test_main.py")
        assert not policy.allows_file(tmp_path / "config.yaml")
        assert not policy.allows_file("/etc/passwd")

    def test_file_scope_blocklist(self, tmp_path):
        """Test file scope with blocklist mode."""
        policy = AgentPolicy(
            file_scope=["/etc/*", "/root/*", str(tmp_path / ".env")],
            file_scope_mode="blocklist",
        )

        assert policy.allows_file(tmp_path / "src/main.py")
        assert not policy.allows_file("/etc/passwd")
        assert not policy.allows_file(tmp_path / ".env")

    def test_empty_file_scope_allows_all(self):
        """Empty file scope allows all files."""
        policy = AgentPolicy(file_scope=[])
        assert policy.allows_file("/any/path/file.txt")
        assert policy.allows_file("/etc/passwd")

    def test_escalation_mode_values(self):
        """Test EscalationMode enum values."""
        assert EscalationMode.DENY.value == "deny"
        assert EscalationMode.WARN.value == "warn"
        assert EscalationMode.ESCALATE.value == "escalate"


class TestPolicyState:
    """Test PolicyState tracking."""

    def test_record_tool_calls(self):
        """Test tool call recording."""
        state = PolicyState(
            task_id="test-task",
            agent_name="test-agent",
            policy=AgentPolicy(),
        )

        state.record_tool_call("read_file")
        state.record_tool_call("write_file")
        state.record_tool_call("read_file")

        assert state.tool_calls == 3
        assert state.tool_calls_by_name["read_file"] == 2
        assert state.tool_calls_by_name["write_file"] == 1

    def test_record_file_access(self, tmp_path):
        """Test file access recording."""
        state = PolicyState(
            task_id="test-task",
            agent_name="test-agent",
            policy=AgentPolicy(),
        )

        state.record_file_access(tmp_path / "a.py")
        state.record_file_access(tmp_path / "b.py")
        state.record_file_access(tmp_path / "a.py")  # Duplicate

        assert len(state.files_touched) == 2

    def test_elapsed_seconds(self):
        """Test elapsed time calculation."""
        state = PolicyState(
            task_id="test-task",
            agent_name="test-agent",
            policy=AgentPolicy(),
        )
        # Elapsed time should be very small immediately after creation
        assert state.elapsed_seconds < 1.0


class TestPolicyEnforcer:
    """Test PolicyEnforcer checks."""

    def test_max_tool_calls_allowed(self):
        """Test tool calls within limit are allowed."""
        policy = AgentPolicy(max_tool_calls=3)
        state = PolicyState(task_id="t", agent_name="a", policy=policy)
        enforcer = PolicyEnforcer(state)

        # First call should be allowed
        result = enforcer.check_tool_call("shell")
        assert result.allowed
        assert result.reason == "Tool call allowed"

    def test_max_tool_calls_enforced(self):
        """Test max tool calls limit enforcement."""
        policy = AgentPolicy(max_tool_calls=3)
        state = PolicyState(task_id="t", agent_name="a", policy=policy)
        enforcer = PolicyEnforcer(state)

        # Record 3 calls
        state.record_tool_call("shell")
        state.record_tool_call("shell")
        state.record_tool_call("shell")

        # Fourth call should be blocked
        result = enforcer.check_tool_call("shell")
        assert not result.allowed
        assert result.violation_type == "max_tool_calls"
        assert result.current_value == 3
        assert result.limit_value == 3
        assert result.escalation_mode == EscalationMode.DENY

    def test_tool_budget_enforced(self):
        """Test per-tool budget limits."""
        policy = AgentPolicy(tool_budget={"shell": 2, "write_file": 5})
        state = PolicyState(task_id="t", agent_name="a", policy=policy)
        enforcer = PolicyEnforcer(state)

        # Shell limited to 2
        state.record_tool_call("shell")
        state.record_tool_call("shell")

        result = enforcer.check_tool_call("shell")
        assert not result.allowed
        assert result.violation_type == "tool_budget"
        assert "shell" in result.reason

        # write_file still allowed (hasn't reached limit)
        result = enforcer.check_tool_call("write_file")
        assert result.allowed

    def test_max_files_allowed(self, tmp_path):
        """Test file access within limit is allowed."""
        policy = AgentPolicy(max_files_touched=3)
        state = PolicyState(task_id="t", agent_name="a", policy=policy)
        enforcer = PolicyEnforcer(state)

        # First file should be allowed
        result = enforcer.check_file_access(str(tmp_path / "a.py"))
        assert result.allowed

    def test_max_files_enforced(self, tmp_path):
        """Test max files touched limit."""
        policy = AgentPolicy(max_files_touched=2)
        state = PolicyState(task_id="t", agent_name="a", policy=policy)
        enforcer = PolicyEnforcer(state)

        # First 2 files allowed
        state.record_file_access(tmp_path / "a.py")
        state.record_file_access(tmp_path / "b.py")

        # Third file blocked
        result = enforcer.check_file_access(str(tmp_path / "c.py"))
        assert not result.allowed
        assert result.violation_type == "max_files_touched"
        assert result.current_value == 2
        assert result.limit_value == 2

    def test_same_file_not_counted_twice(self, tmp_path):
        """Test that accessing same file multiple times doesn't count twice."""
        policy = AgentPolicy(max_files_touched=2)
        state = PolicyState(task_id="t", agent_name="a", policy=policy)
        enforcer = PolicyEnforcer(state)

        # Access same file twice
        state.record_file_access(tmp_path / "a.py")
        state.record_file_access(tmp_path / "a.py")

        # Should still allow another file (only 1 unique file touched)
        result = enforcer.check_file_access(str(tmp_path / "b.py"))
        assert result.allowed

    def test_file_scope_enforced(self, tmp_path):
        """Test file scope restrictions."""
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()

        policy = AgentPolicy(
            file_scope=[str(allowed_dir / "*")],
            file_scope_mode="allowlist",
        )
        state = PolicyState(task_id="t", agent_name="a", policy=policy)
        enforcer = PolicyEnforcer(state)

        # Allowed path
        result = enforcer.check_file_access(str(allowed_dir / "test.py"))
        assert result.allowed

        # Blocked path
        result = enforcer.check_file_access(str(tmp_path / "forbidden.py"))
        assert not result.allowed
        assert result.violation_type == "file_scope"
        assert "outside allowed scope" in result.reason

    def test_runtime_allowed(self):
        """Test runtime within limit is allowed."""
        policy = AgentPolicy(max_runtime_seconds=60)
        state = PolicyState(task_id="t", agent_name="a", policy=policy)
        enforcer = PolicyEnforcer(state)

        result = enforcer.check_runtime()
        assert result.allowed
        assert result.reason == "Runtime within limits"

    def test_runtime_enforced(self):
        """Test runtime limit enforcement."""
        policy = AgentPolicy(max_runtime_seconds=0.1)
        state = PolicyState(task_id="t", agent_name="a", policy=policy)
        # Backdate start time to simulate time passing
        state.start_time = datetime.now() - timedelta(seconds=1)
        enforcer = PolicyEnforcer(state)

        result = enforcer.check_runtime()
        assert not result.allowed
        assert result.violation_type == "max_runtime"
        assert result.current_value >= 1.0
        assert result.limit_value == 0.1

    def test_no_limits_allows_everything(self):
        """Test that no limits means everything is allowed."""
        policy = AgentPolicy()  # All limits are None
        state = PolicyState(task_id="t", agent_name="a", policy=policy)
        enforcer = PolicyEnforcer(state)

        # Record many operations
        for i in range(100):
            state.record_tool_call("shell")
            state.record_file_access(f"/path/file{i}.txt")

        # All checks should still pass
        assert enforcer.check_tool_call("shell").allowed
        assert enforcer.check_file_access("/new/file.txt").allowed
        assert enforcer.check_runtime().allowed


class TestEscalationModes:
    """Test different escalation modes."""

    def test_deny_mode_in_result(self):
        """Test DENY escalation mode is in result."""
        policy = AgentPolicy(
            max_tool_calls=1,
            escalation_mode=EscalationMode.DENY,
        )
        state = PolicyState(task_id="t", agent_name="a", policy=policy)
        state.record_tool_call("shell")
        enforcer = PolicyEnforcer(state)

        result = enforcer.check_tool_call("shell")
        assert not result.allowed
        assert result.escalation_mode == EscalationMode.DENY

    def test_warn_mode_in_result(self):
        """Test WARN escalation mode is in result."""
        policy = AgentPolicy(
            max_tool_calls=1,
            escalation_mode=EscalationMode.WARN,
        )
        state = PolicyState(task_id="t", agent_name="a", policy=policy)
        state.record_tool_call("shell")
        enforcer = PolicyEnforcer(state)

        result = enforcer.check_tool_call("shell")
        assert not result.allowed  # Check still fails
        assert result.escalation_mode == EscalationMode.WARN  # But mode is WARN

    def test_escalate_mode_in_result(self):
        """Test ESCALATE escalation mode is in result."""
        policy = AgentPolicy(
            max_tool_calls=1,
            escalation_mode=EscalationMode.ESCALATE,
        )
        state = PolicyState(task_id="t", agent_name="a", policy=policy)
        state.record_tool_call("shell")
        enforcer = PolicyEnforcer(state)

        result = enforcer.check_tool_call("shell")
        assert not result.allowed
        assert result.escalation_mode == EscalationMode.ESCALATE


class TestPolicyCheckResult:
    """Test PolicyCheckResult dataclass."""

    def test_allowed_result(self):
        """Test allowed result has correct fields."""
        result = PolicyCheckResult(allowed=True, reason="Operation allowed")
        assert result.allowed
        assert result.violation_type is None
        assert result.escalation_mode is None

    def test_denied_result(self):
        """Test denied result has correct fields."""
        result = PolicyCheckResult(
            allowed=False,
            reason="Limit exceeded",
            violation_type="max_tool_calls",
            escalation_mode=EscalationMode.DENY,
            current_value=10,
            limit_value=5,
        )
        assert not result.allowed
        assert result.violation_type == "max_tool_calls"
        assert result.escalation_mode == EscalationMode.DENY
        assert result.current_value == 10
        assert result.limit_value == 5


class TestAgentDefinitionPolicy:
    """Test AgentDefinition policy integration."""

    def test_get_effective_policy_from_policy_object(self):
        """Test that agent.policy takes precedence."""
        from sindri.agents.definitions import AgentDefinition

        custom_policy = AgentPolicy(max_tool_calls=10)
        agent = AgentDefinition(
            name="test",
            role="Test Agent",
            model="test:7b",
            system_prompt="Test prompt",
            tools=["read_file"],
            policy=custom_policy,
            max_tool_calls=5,  # Should be ignored
        )

        effective = agent.get_effective_policy()
        assert effective.max_tool_calls == 10  # From policy object, not convenience field

    def test_get_effective_policy_from_convenience_fields(self):
        """Test that convenience fields are used if no policy object."""
        from sindri.agents.definitions import AgentDefinition

        agent = AgentDefinition(
            name="test",
            role="Test Agent",
            model="test:7b",
            system_prompt="Test prompt",
            tools=["read_file"],
            max_tool_calls=5,
            max_files_touched=20,
            escalation_mode="warn",
        )

        effective = agent.get_effective_policy()
        assert effective.max_tool_calls == 5
        assert effective.max_files_touched == 20
        assert effective.escalation_mode == EscalationMode.WARN

    def test_get_effective_policy_uses_default(self):
        """Test that default policy is used if no agent-specific settings."""
        from sindri.agents.definitions import AgentDefinition

        agent = AgentDefinition(
            name="test",
            role="Test Agent",
            model="test:7b",
            system_prompt="Test prompt",
            tools=["read_file"],
        )

        default = AgentPolicy(max_tool_calls=100)
        effective = agent.get_effective_policy(default)
        assert effective.max_tool_calls == 100

    def test_get_effective_policy_no_limits(self):
        """Test that no limits returns empty policy."""
        from sindri.agents.definitions import AgentDefinition

        agent = AgentDefinition(
            name="test",
            role="Test Agent",
            model="test:7b",
            system_prompt="Test prompt",
            tools=["read_file"],
        )

        effective = agent.get_effective_policy()
        assert effective.max_tool_calls is None
        assert effective.max_files_touched is None
        assert effective.max_runtime_seconds is None
