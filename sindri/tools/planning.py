"""Planning tools for interactive execution planning.

Phase 7.3: Interactive Planning Mode
- ProposePlanTool creates execution plans without running them
- Plans show what agents will be used and what they'll do
- TUI can display plans for user review before execution
"""

from dataclasses import dataclass, field
from typing import Optional
from sindri.tools.base import Tool, ToolResult


@dataclass
class PlanStep:
    """A single step in an execution plan.

    Attributes:
        step_number: Step order (1-indexed)
        description: What this step accomplishes
        agent: Which agent will execute this step
        estimated_iterations: Expected iterations (rough estimate)
        dependencies: Step numbers this depends on (optional)
        tool_hints: Tools likely to be used (optional)
    """
    step_number: int
    description: str
    agent: str
    estimated_iterations: int = 5
    dependencies: list[int] = field(default_factory=list)
    tool_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "step_number": self.step_number,
            "description": self.description,
            "agent": self.agent,
            "estimated_iterations": self.estimated_iterations,
            "dependencies": self.dependencies,
            "tool_hints": self.tool_hints
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlanStep":
        """Create from dictionary."""
        return cls(
            step_number=data.get("step_number", 1),
            description=data.get("description", ""),
            agent=data.get("agent", "huginn"),
            estimated_iterations=data.get("estimated_iterations", 5),
            dependencies=data.get("dependencies", []),
            tool_hints=data.get("tool_hints", [])
        )


@dataclass
class ExecutionPlan:
    """A complete execution plan for a task.

    Attributes:
        task_summary: Brief summary of the task being planned
        steps: List of plan steps
        total_estimated_vram_gb: Expected peak VRAM usage
        rationale: Why this approach was chosen
        risks: Potential risks or challenges
    """
    task_summary: str
    steps: list[PlanStep]
    total_estimated_vram_gb: float = 0.0
    rationale: str = ""
    risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_summary": self.task_summary,
            "steps": [s.to_dict() for s in self.steps],
            "total_estimated_vram_gb": self.total_estimated_vram_gb,
            "rationale": self.rationale,
            "risks": self.risks
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionPlan":
        """Create from dictionary."""
        steps = [PlanStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            task_summary=data.get("task_summary", ""),
            steps=steps,
            total_estimated_vram_gb=data.get("total_estimated_vram_gb", 0.0),
            rationale=data.get("rationale", ""),
            risks=data.get("risks", [])
        )

    def format_display(self) -> str:
        """Format plan for display in TUI/CLI."""
        lines = []
        lines.append(f"Plan: {self.task_summary}")
        lines.append("")

        for step in self.steps:
            deps = f" (after step {', '.join(map(str, step.dependencies))})" if step.dependencies else ""
            lines.append(f"  {step.step_number}. [{step.agent}] {step.description}{deps}")
            if step.tool_hints:
                lines.append(f"     Tools: {', '.join(step.tool_hints)}")

        lines.append("")
        if self.total_estimated_vram_gb > 0:
            lines.append(f"Estimated VRAM: ~{self.total_estimated_vram_gb:.1f}GB")

        if self.rationale:
            lines.append(f"Rationale: {self.rationale}")

        if self.risks:
            lines.append("Risks:")
            for risk in self.risks:
                lines.append(f"  - {risk}")

        return "\n".join(lines)


class ProposePlanTool(Tool):
    """Tool for proposing execution plans before running tasks.

    This tool creates a plan that describes what agents will be used
    and what they will do, without actually executing anything.

    The plan can be displayed to users for review before execution.
    """

    name = "propose_plan"
    description = "Create an execution plan for a complex task. Use this before delegating to show what will happen."
    parameters = {
        "type": "object",
        "properties": {
            "task_summary": {
                "type": "string",
                "description": "Brief summary of the overall task"
            },
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "What this step accomplishes"
                        },
                        "agent": {
                            "type": "string",
                            "enum": ["huginn", "mimir", "skald", "fenrir", "odin", "ratatoskr"],
                            "description": "Agent to execute this step"
                        },
                        "dependencies": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Step numbers this depends on"
                        },
                        "tool_hints": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tools likely to be used"
                        }
                    },
                    "required": ["description", "agent"]
                },
                "description": "List of steps in the plan"
            },
            "rationale": {
                "type": "string",
                "description": "Why this approach was chosen"
            },
            "risks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Potential risks or challenges"
            }
        },
        "required": ["task_summary", "steps"]
    }

    # Agent VRAM estimates (from agent registry)
    AGENT_VRAM = {
        "brokkr": 9.0,
        "huginn": 5.0,
        "mimir": 5.0,
        "skald": 5.0,
        "fenrir": 5.0,
        "odin": 9.0,
        "ratatoskr": 3.0
    }

    async def execute(
        self,
        task_summary: str,
        steps: list[dict],
        rationale: str = "",
        risks: list[str] = None
    ) -> ToolResult:
        """Create an execution plan.

        Args:
            task_summary: Brief description of the task
            steps: List of step dictionaries
            rationale: Why this approach
            risks: List of potential risks

        Returns:
            ToolResult with formatted plan
        """
        risks = risks or []

        # Build plan steps
        plan_steps = []
        for i, step_data in enumerate(steps, 1):
            plan_steps.append(PlanStep(
                step_number=i,
                description=step_data.get("description", ""),
                agent=step_data.get("agent", "huginn"),
                estimated_iterations=step_data.get("estimated_iterations", 5),
                dependencies=step_data.get("dependencies", []),
                tool_hints=step_data.get("tool_hints", [])
            ))

        # Calculate peak VRAM (max of concurrent steps)
        # For simplicity, assume max 2 agents run in parallel
        agents_used = set(s.agent for s in plan_steps)
        max_vram = max(
            (self.AGENT_VRAM.get(a, 5.0) for a in agents_used),
            default=0.0
        )

        # If multiple agents, might run 2 in parallel
        if len(agents_used) > 1:
            agent_vrams = sorted(
                [self.AGENT_VRAM.get(a, 5.0) for a in agents_used],
                reverse=True
            )
            # Top 2 might run together
            max_vram = sum(agent_vrams[:2])

        # Create plan
        plan = ExecutionPlan(
            task_summary=task_summary,
            steps=plan_steps,
            total_estimated_vram_gb=max_vram,
            rationale=rationale,
            risks=risks
        )

        # Format output
        output = plan.format_display()

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "plan": plan.to_dict(),
                "step_count": len(plan_steps),
                "agents": list(agents_used),
                "estimated_vram_gb": max_vram
            }
        )
