"""Hierarchical agent loop with delegation support."""

from datetime import datetime
import os
import structlog

from sindri.llm.client import OllamaClient
from sindri.llm.tool_parser import ToolCallParser
from sindri.tools.registry import ToolRegistry
from sindri.tools.delegation import DelegateTool
from sindri.persistence.state import SessionState
from sindri.core.loop import LoopConfig, LoopResult
from sindri.core.completion import CompletionDetector
from sindri.core.context import ContextBuilder
from sindri.core.tasks import Task, TaskStatus
from sindri.core.scheduler import TaskScheduler
from sindri.core.delegation import DelegationManager
from sindri.agents.registry import AGENTS
from sindri.memory.system import MuninnMemory
from sindri.memory.summarizer import ConversationSummarizer
from sindri.core.events import EventBus, Event, EventType
from typing import Optional

log = structlog.get_logger()


class HierarchicalAgentLoop:
    """Agent loop with delegation support."""

    def __init__(
        self,
        client: OllamaClient,
        tools: ToolRegistry,
        state: SessionState,
        scheduler: TaskScheduler,
        delegation: DelegationManager,
        config: LoopConfig = None,
        memory: Optional[MuninnMemory] = None,
        summarizer: Optional[ConversationSummarizer] = None,
        event_bus: Optional[EventBus] = None
    ):
        self.client = client
        self.tools = tools
        self.state = state
        self.scheduler = scheduler
        self.delegation = delegation
        self.config = config or LoopConfig()
        self.context_builder = ContextBuilder()
        self.memory = memory
        self.summarizer = summarizer
        self.event_bus = event_bus or EventBus()
        self._indexed_projects = set()  # Track indexed projects

    async def run_task(self, task: Task) -> LoopResult:
        """Run a specific task with its assigned agent."""

        agent = AGENTS.get(task.assigned_agent)
        if not agent:
            return LoopResult(
                success=False,
                iterations=0,
                reason=f"Unknown agent: {task.assigned_agent}"
            )

        # Ensure model is loaded
        loaded = await self.scheduler.model_manager.ensure_loaded(
            agent.model, agent.estimated_vram_gb
        )
        if not loaded:
            return LoopResult(
                success=False,
                iterations=0,
                reason=f"Could not load model {agent.model}"
            )

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()

        # Emit task status event
        self.event_bus.emit(Event(
            type=EventType.TASK_STATUS_CHANGED,
            data={"task_id": task.id, "status": TaskStatus.RUNNING}
        ))

        log.info("task_started",
                 task_id=task.id,
                 agent=agent.name,
                 description=task.description[:50])

        # Add delegate tool if agent can delegate
        task_tools = ToolRegistry()
        for tool_name in agent.tools:
            if tool_name == "delegate":
                # Add delegation tool with task context
                task_tools.register(DelegateTool(self.delegation, task))
            else:
                # Copy from global registry
                tool = self.tools.get_tool(tool_name)
                if tool:
                    task_tools.register(tool)

        result = await self._run_loop(task, agent, task_tools)

        if result.success:
            task.status = TaskStatus.COMPLETE
            task.completed_at = datetime.now()
            task.result = {"output": result.final_output}
            await self.delegation.child_completed(task)

            # Emit completion event
            self.event_bus.emit(Event(
                type=EventType.TASK_STATUS_CHANGED,
                data={"task_id": task.id, "status": TaskStatus.COMPLETE}
            ))

            log.info("task_completed", task_id=task.id, iterations=result.iterations)
        else:
            task.status = TaskStatus.FAILED
            task.error = result.reason
            await self.delegation.child_failed(task)

            # Emit failure event
            self.event_bus.emit(Event(
                type=EventType.TASK_STATUS_CHANGED,
                data={"task_id": task.id, "status": TaskStatus.FAILED}
            ))

            log.error("task_failed",
                      task_id=task.id,
                      reason=result.reason,
                      iterations=result.iterations)

        return result

    async def _run_loop(self, task: Task, agent, task_tools: ToolRegistry) -> LoopResult:
        """Execute the agent loop for a task."""

        session = await self.state.create_session(
            task.description,
            agent.model
        )

        # Store session_id on task for later retrieval
        task.session_id = session.id

        # Index project if memory available and not yet indexed
        project_id = f"project_{os.getcwd().replace('/', '_')}"
        if self.memory and project_id not in self._indexed_projects:
            log.info("indexing_project", path=os.getcwd())
            indexed = self.memory.index_project(os.getcwd(), project_id)
            self._indexed_projects.add(project_id)
            log.info("project_indexed", files=indexed, project_id=project_id)

        recent_responses = []
        completion_detector = CompletionDetector(self.config.completion_marker)
        tool_parser = ToolCallParser()

        for iteration in range(agent.max_iterations):
            log.info("iteration_start",
                     task_id=task.id,
                     iteration=iteration + 1,
                     agent=agent.name)

            # Emit iteration start event
            self.event_bus.emit(Event(
                type=EventType.ITERATION_START,
                data={
                    "task_id": task.id,
                    "iteration": iteration + 1,
                    "agent": agent.name
                }
            ))

            # Build messages with memory-augmented context if available
            if self.memory:
                # Convert session turns to message format
                conversation = [
                    {"role": turn.role, "content": turn.content}
                    for turn in session.turns
                ]

                # Get memory-augmented context
                memory_messages = self.memory.build_context(
                    project_id=project_id,
                    current_task=task.description,
                    conversation=conversation,
                    max_tokens=agent.max_context_tokens
                )

                # Add system prompt with task info
                system_msg = self._build_system_message(
                    agent.system_prompt,
                    task.description,
                    task.context,
                    task_tools.get_schemas()
                )

                messages = [system_msg] + memory_messages
            else:
                # Fallback to simple message building
                messages = self._build_messages(
                    agent.system_prompt,
                    task.description,
                    task.context,
                    session.turns,
                    task_tools.get_schemas()
                )

            # Call LLM
            response = await self.client.chat(
                model=agent.model,
                messages=messages,
                tools=task_tools.get_schemas()
            )

            assistant_content = response.message.content
            log.info("llm_response",
                     task_id=task.id,
                     content=assistant_content[:200],
                     has_tool_calls=response.message.tool_calls is not None)

            # Emit agent output event
            self.event_bus.emit(Event(
                type=EventType.AGENT_OUTPUT,
                data={
                    "task_id": task.id,
                    "agent": agent.name,
                    "text": assistant_content
                }
            ))

            # Check completion
            if completion_detector.is_complete(assistant_content):
                await self.state.complete_session(session.id)

                # Store episode if memory available
                if self.memory and self.summarizer:
                    try:
                        # Summarize the conversation
                        conversation = [
                            {"role": turn.role, "content": turn.content}
                            for turn in session.turns
                        ]
                        summary = await self.summarizer.summarize(task.description, conversation)

                        # Store episode
                        self.memory.store_episode(
                            project_id=project_id,
                            event_type="task_complete",
                            content=summary,
                            metadata={
                                "task_id": task.id,
                                "agent": agent.name,
                                "iterations": iteration + 1
                            }
                        )
                        log.info("episode_stored", task_id=task.id)
                    except Exception as e:
                        log.warning("episode_storage_failed", error=str(e))

                return LoopResult(
                    success=True,
                    iterations=iteration + 1,
                    reason="completion_marker",
                    final_output=assistant_content
                )

            # Check stuck
            recent_responses.append(assistant_content)
            if len(recent_responses) > self.config.stuck_threshold:
                recent_responses.pop(0)

            if self._is_stuck(recent_responses):
                log.warning("stuck_detected", task_id=task.id)
                session.add_turn("user", "You seem stuck. Try a different approach or ask for clarification.")
                recent_responses.clear()
                continue

            # Execute tool calls (native or parsed from text)
            tool_results = []
            calls_to_execute = []

            # Check for native tool calls first
            if response.message.tool_calls:
                log.info("native_tool_calls_detected",
                         task_id=task.id,
                         count=len(response.message.tool_calls))
                calls_to_execute = response.message.tool_calls
            else:
                # Try parsing tool calls from text
                parsed_calls = tool_parser.parse(assistant_content)
                if parsed_calls:
                    log.info("parsed_tool_calls_from_text",
                             task_id=task.id,
                             count=len(parsed_calls))
                    # Convert parsed calls to native format
                    class CallWrapper:
                        def __init__(self, name, arguments):
                            self.function = type('obj', (object,), {
                                'name': name,
                                'arguments': arguments
                            })()
                    calls_to_execute = [CallWrapper(c.name, c.arguments) for c in parsed_calls]

            # Execute all calls
            for call in calls_to_execute:
                log.info("executing_tool",
                         task_id=task.id,
                         tool=call.function.name,
                         args=call.function.arguments)

                result = await task_tools.execute(
                    call.function.name,
                    call.function.arguments
                )

                tool_results.append({
                    "tool": call.function.name,
                    "result": result.output if result.success else f"ERROR: {result.error}"
                })

                log.info("tool_executed",
                         task_id=task.id,
                         tool=call.function.name,
                         success=result.success)

                # Emit tool called event
                self.event_bus.emit(Event(
                    type=EventType.TOOL_CALLED,
                    data={
                        "task_id": task.id,
                        "name": call.function.name,
                        "success": result.success,
                        "result": result.output if result.success else result.error
                    }
                ))

                # If delegation occurred, pause this task
                if call.function.name == "delegate" and result.success:
                    log.info("delegation_in_progress",
                             task_id=task.id,
                             pausing="waiting for child")
                    # Task will resume when child completes

            # Update session
            session.add_turn("assistant", assistant_content, tool_calls=response.message.tool_calls)
            if tool_results:
                session.add_turn("tool", str(tool_results))

            # Checkpoint
            session.iterations = iteration + 1
            if iteration % self.config.checkpoint_interval == 0:
                await self.state.save_session(session)

        return LoopResult(
            success=False,
            iterations=agent.max_iterations,
            reason="max_iterations_reached"
        )

    def _build_messages(
        self,
        system_prompt: str,
        task_description: str,
        task_context: dict,
        history: list,
        tools: list[dict]
    ) -> list[dict]:
        """Build messages for the LLM."""

        messages = []

        # System message with agent-specific prompt
        full_prompt = f"{system_prompt}\n\nYour current task: {task_description}"

        # Add context if present
        if task_context:
            context_str = "\n".join([f"- {k}: {v}" for k, v in task_context.items()])
            full_prompt += f"\n\nContext:\n{context_str}"

        # Add tool descriptions
        if tools:
            tool_descriptions = "\n".join([
                f"- {tool['function']['name']}: {tool['function']['description']}"
                for tool in tools
            ])
            full_prompt += f"\n\nAvailable tools:\n{tool_descriptions}"

        messages.append({
            "role": "system",
            "content": full_prompt
        })

        # Add conversation history
        for turn in history:
            message = {
                "role": turn.role,
                "content": turn.content
            }
            if turn.tool_calls:
                message["tool_calls"] = turn.tool_calls
            messages.append(message)

        return messages

    def _is_stuck(self, responses: list[str]) -> bool:
        """Detect if we're getting the same response repeatedly."""
        if len(responses) < self.config.stuck_threshold:
            return False
        return len(set(responses)) == 1

    def _build_system_message(
        self,
        system_prompt: str,
        task_description: str,
        task_context: dict,
        tools: list[dict]
    ) -> dict:
        """Build system message for memory-augmented context."""

        full_prompt = f"{system_prompt}\n\nYour current task: {task_description}"

        # Add context if present
        if task_context:
            context_str = "\n".join([f"- {k}: {v}" for k, v in task_context.items()])
            full_prompt += f"\n\nContext:\n{context_str}"

        # Add tool descriptions
        if tools:
            tool_descriptions = "\n".join([
                f"- {tool['function']['name']}: {tool['function']['description']}"
                for tool in tools
            ])
            full_prompt += f"\n\nAvailable tools:\n{tool_descriptions}"

        return {
            "role": "system",
            "content": full_prompt
        }
