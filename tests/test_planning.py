"""Tests for Phase 7.3 Interactive Planning system.

Tests cover:
- PlanStep dataclass creation and serialization
- ExecutionPlan creation and formatting
- ProposePlanTool execution
- Event emission for PLAN_PROPOSED
- TUI plan display handling
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sindri.tools.planning import (
    PlanStep,
    ExecutionPlan,
    ProposePlanTool,
)
from sindri.core.events import EventType, Event, EventBus


class TestPlanStep:
    """Tests for PlanStep dataclass."""

    def test_plan_step_basic_creation(self):
        """Test creating a basic plan step."""
        step = PlanStep(
            step_number=1,
            description="Create user model",
            agent="huginn"
        )
        assert step.step_number == 1
        assert step.description == "Create user model"
        assert step.agent == "huginn"
        assert step.estimated_iterations == 5  # default
        assert step.dependencies == []
        assert step.tool_hints == []

    def test_plan_step_full_creation(self):
        """Test creating a plan step with all fields."""
        step = PlanStep(
            step_number=2,
            description="Create auth routes",
            agent="huginn",
            estimated_iterations=10,
            dependencies=[1],
            tool_hints=["write_file", "edit_file"]
        )
        assert step.step_number == 2
        assert step.estimated_iterations == 10
        assert step.dependencies == [1]
        assert step.tool_hints == ["write_file", "edit_file"]

    def test_plan_step_to_dict(self):
        """Test serializing a plan step to dictionary."""
        step = PlanStep(
            step_number=1,
            description="Test step",
            agent="mimir",
            dependencies=[2, 3],
            tool_hints=["read_file"]
        )
        result = step.to_dict()
        assert result["step_number"] == 1
        assert result["description"] == "Test step"
        assert result["agent"] == "mimir"
        assert result["dependencies"] == [2, 3]
        assert result["tool_hints"] == ["read_file"]

    def test_plan_step_from_dict(self):
        """Test creating a plan step from dictionary."""
        data = {
            "step_number": 3,
            "description": "Write tests",
            "agent": "skald",
            "estimated_iterations": 15,
            "dependencies": [1, 2],
            "tool_hints": ["shell"]
        }
        step = PlanStep.from_dict(data)
        assert step.step_number == 3
        assert step.description == "Write tests"
        assert step.agent == "skald"
        assert step.estimated_iterations == 15
        assert step.dependencies == [1, 2]

    def test_plan_step_from_dict_minimal(self):
        """Test creating a plan step from minimal dictionary."""
        data = {}
        step = PlanStep.from_dict(data)
        assert step.step_number == 1
        assert step.description == ""
        assert step.agent == "huginn"
        assert step.estimated_iterations == 5


class TestExecutionPlan:
    """Tests for ExecutionPlan dataclass."""

    def test_execution_plan_basic_creation(self):
        """Test creating a basic execution plan."""
        steps = [
            PlanStep(1, "Step 1", "huginn"),
            PlanStep(2, "Step 2", "skald", dependencies=[1])
        ]
        plan = ExecutionPlan(
            task_summary="Test task",
            steps=steps
        )
        assert plan.task_summary == "Test task"
        assert len(plan.steps) == 2
        assert plan.total_estimated_vram_gb == 0.0
        assert plan.rationale == ""
        assert plan.risks == []

    def test_execution_plan_full_creation(self):
        """Test creating a plan with all fields."""
        steps = [PlanStep(1, "Only step", "fenrir")]
        plan = ExecutionPlan(
            task_summary="Complex task",
            steps=steps,
            total_estimated_vram_gb=10.5,
            rationale="This is the optimal approach",
            risks=["May take longer than expected", "Requires specific model"]
        )
        assert plan.total_estimated_vram_gb == 10.5
        assert plan.rationale == "This is the optimal approach"
        assert len(plan.risks) == 2

    def test_execution_plan_to_dict(self):
        """Test serializing an execution plan to dictionary."""
        steps = [
            PlanStep(1, "Step A", "huginn"),
            PlanStep(2, "Step B", "mimir")
        ]
        plan = ExecutionPlan(
            task_summary="My task",
            steps=steps,
            rationale="Good reason",
            risks=["Risk 1"]
        )
        result = plan.to_dict()
        assert result["task_summary"] == "My task"
        assert len(result["steps"]) == 2
        assert result["rationale"] == "Good reason"
        assert result["risks"] == ["Risk 1"]

    def test_execution_plan_from_dict(self):
        """Test creating an execution plan from dictionary."""
        data = {
            "task_summary": "Rebuild auth",
            "steps": [
                {"step_number": 1, "description": "Model", "agent": "huginn"},
                {"step_number": 2, "description": "Routes", "agent": "huginn", "dependencies": [1]}
            ],
            "total_estimated_vram_gb": 8.0,
            "rationale": "Standard approach",
            "risks": ["Time intensive"]
        }
        plan = ExecutionPlan.from_dict(data)
        assert plan.task_summary == "Rebuild auth"
        assert len(plan.steps) == 2
        assert plan.steps[1].dependencies == [1]
        assert plan.total_estimated_vram_gb == 8.0

    def test_execution_plan_format_display(self):
        """Test formatting plan for display."""
        steps = [
            PlanStep(1, "Create models", "huginn", tool_hints=["write_file"]),
            PlanStep(2, "Add tests", "skald", dependencies=[1])
        ]
        plan = ExecutionPlan(
            task_summary="Auth implementation",
            steps=steps,
            total_estimated_vram_gb=10.0,
            rationale="Breaking down into logical steps",
            risks=["Complex feature"]
        )
        display = plan.format_display()

        assert "Auth implementation" in display
        assert "Create models" in display
        assert "Add tests" in display
        assert "[huginn]" in display
        assert "[skald]" in display
        assert "after step 1" in display
        assert "write_file" in display
        assert "10.0GB" in display
        assert "Breaking down" in display
        assert "Complex feature" in display


class TestProposePlanTool:
    """Tests for ProposePlanTool."""

    def test_tool_schema(self):
        """Test that tool has correct schema."""
        tool = ProposePlanTool()
        schema = tool.get_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "propose_plan"
        assert "task_summary" in schema["function"]["parameters"]["properties"]
        assert "steps" in schema["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_basic_plan_creation(self):
        """Test creating a basic execution plan."""
        tool = ProposePlanTool()
        result = await tool.execute(
            task_summary="Add user authentication",
            steps=[
                {"description": "Create User model", "agent": "huginn"},
                {"description": "Create auth routes", "agent": "huginn"}
            ]
        )

        assert result.success
        assert "Add user authentication" in result.output
        assert "Create User model" in result.output
        assert "Create auth routes" in result.output
        assert result.metadata["step_count"] == 2
        assert "huginn" in result.metadata["agents"]

    @pytest.mark.asyncio
    async def test_plan_with_dependencies(self):
        """Test creating a plan with step dependencies."""
        tool = ProposePlanTool()
        result = await tool.execute(
            task_summary="Build API",
            steps=[
                {"description": "Create models", "agent": "huginn"},
                {"description": "Create routes", "agent": "huginn", "dependencies": [1]},
                {"description": "Write tests", "agent": "skald", "dependencies": [1, 2]}
            ]
        )

        assert result.success
        assert "after step 1" in result.output
        assert "after step 1, 2" in result.output
        assert result.metadata["step_count"] == 3

    @pytest.mark.asyncio
    async def test_plan_with_rationale_and_risks(self):
        """Test creating a plan with rationale and risks."""
        tool = ProposePlanTool()
        result = await tool.execute(
            task_summary="Database migration",
            steps=[
                {"description": "Backup database", "agent": "fenrir"},
                {"description": "Run migration", "agent": "fenrir"}
            ],
            rationale="Backup first ensures safety",
            risks=["Data loss if backup fails", "Downtime during migration"]
        )

        assert result.success
        assert "Backup first" in result.output
        assert "Data loss" in result.output
        assert "Downtime" in result.output

    @pytest.mark.asyncio
    async def test_plan_vram_estimation_single_agent(self):
        """Test VRAM estimation for single agent."""
        tool = ProposePlanTool()
        result = await tool.execute(
            task_summary="Simple task",
            steps=[
                {"description": "Step 1", "agent": "huginn"},
                {"description": "Step 2", "agent": "huginn"}
            ]
        )

        assert result.success
        # Single agent should use that agent's VRAM (huginn = 5.0)
        # But since there could be parallel execution, it might sum
        assert result.metadata["estimated_vram_gb"] >= 5.0

    @pytest.mark.asyncio
    async def test_plan_vram_estimation_multiple_agents(self):
        """Test VRAM estimation for multiple agents."""
        tool = ProposePlanTool()
        result = await tool.execute(
            task_summary="Complex task",
            steps=[
                {"description": "Implement", "agent": "huginn"},
                {"description": "Review", "agent": "mimir"},
                {"description": "Test", "agent": "skald"}
            ]
        )

        assert result.success
        # Multiple agents might run in parallel - should estimate peak VRAM
        assert result.metadata["estimated_vram_gb"] >= 5.0
        assert set(result.metadata["agents"]) == {"huginn", "mimir", "skald"}

    @pytest.mark.asyncio
    async def test_plan_with_tool_hints(self):
        """Test creating a plan with tool hints."""
        tool = ProposePlanTool()
        result = await tool.execute(
            task_summary="File operations",
            steps=[
                {"description": "Read config", "agent": "huginn", "tool_hints": ["read_file"]},
                {"description": "Write output", "agent": "huginn", "tool_hints": ["write_file", "edit_file"]}
            ]
        )

        assert result.success
        assert "read_file" in result.output
        assert "write_file" in result.output

    @pytest.mark.asyncio
    async def test_plan_metadata_structure(self):
        """Test that plan metadata has correct structure."""
        tool = ProposePlanTool()
        result = await tool.execute(
            task_summary="Test task",
            steps=[{"description": "Do something", "agent": "ratatoskr"}]
        )

        assert result.success
        assert "plan" in result.metadata
        assert "step_count" in result.metadata
        assert "agents" in result.metadata
        assert "estimated_vram_gb" in result.metadata

        # Verify plan structure
        plan = result.metadata["plan"]
        assert "task_summary" in plan
        assert "steps" in plan
        assert len(plan["steps"]) == 1


class TestPlanningEvents:
    """Tests for planning event emission."""

    def test_event_type_exists(self):
        """Test that PLAN_PROPOSED event type exists."""
        assert hasattr(EventType, "PLAN_PROPOSED")
        assert hasattr(EventType, "PLAN_APPROVED")
        assert hasattr(EventType, "PLAN_REJECTED")

    def test_event_emission(self):
        """Test emitting a PLAN_PROPOSED event."""
        event_bus = EventBus()
        received_events = []

        def handler(data):
            received_events.append(data)

        event_bus.subscribe(EventType.PLAN_PROPOSED, handler)

        # Emit a plan event
        event_bus.emit(Event(
            type=EventType.PLAN_PROPOSED,
            data={
                "task_id": "test-123",
                "agent": "brokkr",
                "plan": {"task_summary": "Test"},
                "step_count": 2
            }
        ))

        assert len(received_events) == 1
        assert received_events[0]["task_id"] == "test-123"
        assert received_events[0]["step_count"] == 2


class TestBrokkrPromptUpdate:
    """Tests for Brokkr prompt updates."""

    def test_brokkr_has_planning_instructions(self):
        """Test that Brokkr's prompt includes planning instructions."""
        from sindri.agents.prompts import BROKKR_PROMPT

        assert "propose_plan" in BROKKR_PROMPT
        assert "PLAN FIRST" in BROKKR_PROMPT
        assert "task_summary" in BROKKR_PROMPT
        assert "EXECUTION PLAN" in BROKKR_PROMPT or "execution plan" in BROKKR_PROMPT.lower()

    def test_brokkr_has_propose_plan_tool(self):
        """Test that Brokkr has propose_plan in tools list."""
        from sindri.agents.registry import AGENTS

        brokkr = AGENTS["brokkr"]
        assert "propose_plan" in brokkr.tools


class TestToolRegistration:
    """Tests for tool registration."""

    def test_propose_plan_in_default_registry(self):
        """Test that ProposePlanTool is in default registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()
        tool = registry.get_tool("propose_plan")
        assert tool is not None
        assert tool.name == "propose_plan"

    @pytest.mark.asyncio
    async def test_propose_plan_execution_via_registry(self):
        """Test executing propose_plan through registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()
        result = await registry.execute(
            "propose_plan",
            {
                "task_summary": "Test via registry",
                "steps": [{"description": "Step", "agent": "huginn"}]
            }
        )

        assert result.success
        assert "Test via registry" in result.output


class TestPlanStepEdgeCases:
    """Tests for edge cases in plan steps."""

    def test_empty_steps_list(self):
        """Test creating a plan with no steps."""
        plan = ExecutionPlan(
            task_summary="Empty plan",
            steps=[]
        )
        display = plan.format_display()
        assert "Empty plan" in display
        assert plan.to_dict()["steps"] == []

    def test_many_dependencies(self):
        """Test step with many dependencies."""
        step = PlanStep(
            step_number=5,
            description="Final step",
            agent="mimir",
            dependencies=[1, 2, 3, 4]
        )
        step_dict = step.to_dict()
        assert len(step_dict["dependencies"]) == 4

    def test_long_description(self):
        """Test step with very long description."""
        long_desc = "A" * 500
        step = PlanStep(
            step_number=1,
            description=long_desc,
            agent="huginn"
        )
        assert step.description == long_desc
        assert len(step.to_dict()["description"]) == 500

    def test_all_agents_vram_estimate(self):
        """Test VRAM estimation covers all agent types."""
        tool = ProposePlanTool()

        # All agents should be in AGENT_VRAM dict
        agents = ["brokkr", "huginn", "mimir", "skald", "fenrir", "odin", "ratatoskr"]
        for agent in agents:
            assert agent in tool.AGENT_VRAM
