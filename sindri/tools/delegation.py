"""Delegation tool for agent hierarchy."""

import structlog

from sindri.tools.base import Tool, ToolResult
from sindri.core.delegation import DelegationManager, DelegationRequest
from sindri.core.tasks import Task

log = structlog.get_logger()


class DelegateTool(Tool):
    """Delegate a task to another agent."""

    name = "delegate"
    description = "Delegate a subtask to another specialized agent"
    parameters = {
        "type": "object",
        "properties": {
            "agent": {
                "type": "string",
                "description": "Target agent name",
                "enum": ["huginn", "mimir", "ratatoskr", "skald", "fenrir", "odin"]
            },
            "task": {
                "type": "string",
                "description": "Description of the task to delegate"
            },
            "context": {
                "type": "object",
                "description": "Additional context for the delegated task",
                "default": {}
            },
            "constraints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Constraints or requirements for the task",
                "default": []
            },
            "criteria": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Success criteria for the task",
                "default": []
            }
        },
        "required": ["agent", "task"]
    }

    def __init__(self, delegation_manager: DelegationManager, current_task: Task):
        self.delegation_manager = delegation_manager
        self.current_task = current_task

    async def execute(
        self,
        agent: str,
        task: str,
        context: dict = None,
        constraints: list[str] = None,
        criteria: list[str] = None
    ) -> ToolResult:
        """Execute delegation to another agent."""

        try:
            request = DelegationRequest(
                target_agent=agent,
                task_description=task,
                context=context or {},
                constraints=constraints or [],
                success_criteria=criteria or []
            )

            child_task = await self.delegation_manager.delegate(
                self.current_task,
                request
            )

            log.info("delegation_executed",
                     parent=self.current_task.id,
                     child=child_task.id,
                     agent=agent)

            return ToolResult(
                success=True,
                output=f"Delegated to {agent}: task {child_task.id}",
                metadata={
                    "child_task_id": child_task.id,
                    "agent": agent
                }
            )

        except ValueError as e:
            log.error("delegation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Delegation failed: {str(e)}"
            )
        except Exception as e:
            log.error("delegation_error", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Unexpected error during delegation: {str(e)}"
            )
