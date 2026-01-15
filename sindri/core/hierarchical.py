"""Hierarchical agent loop with delegation support."""

from datetime import datetime
import os
import structlog

from sindri.llm.client import OllamaClient
from sindri.llm.tool_parser import ToolCallParser
from sindri.llm.streaming import StreamingBuffer
from sindri.tools.registry import ToolRegistry
from sindri.tools.delegation import DelegateTool
from sindri.persistence.state import SessionState
from sindri.core.loop import LoopConfig, LoopResult
from sindri.core.completion import CompletionDetector
from sindri.core.context import ContextBuilder
from sindri.core.tasks import Task, TaskStatus
from sindri.core.scheduler import TaskScheduler
from sindri.core.delegation import DelegationManager
from sindri.core.recovery import RecoveryManager
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
        event_bus: Optional[EventBus] = None,
        recovery: Optional[RecoveryManager] = None
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
        self.recovery = recovery  # Phase 5.6: Recovery manager for error checkpoints
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

        # Ensure model is loaded (Phase 5.6: with fallback support)
        loaded = await self.scheduler.model_manager.ensure_loaded(
            agent.model, agent.estimated_vram_gb
        )

        # Phase 5.6: Try fallback model if primary fails and fallback is available
        active_model = agent.model
        if not loaded and agent.fallback_model:
            log.warning("model_degradation_attempt",
                       task_id=task.id,
                       agent=agent.name,
                       primary_model=agent.model,
                       fallback_model=agent.fallback_model)

            loaded = await self.scheduler.model_manager.ensure_loaded(
                agent.fallback_model, agent.fallback_vram_gb or 3.0
            )

            if loaded:
                active_model = agent.fallback_model
                log.info("model_degradation_success",
                        task_id=task.id,
                        agent=agent.name,
                        using_model=active_model)

                # Emit degradation event for TUI
                self.event_bus.emit(Event(
                    type=EventType.MODEL_DEGRADED,
                    data={
                        "task_id": task.id,
                        "agent": agent.name,
                        "primary_model": agent.model,
                        "fallback_model": agent.fallback_model,
                        "reason": "insufficient_vram"
                    },
                    task_id=task.id
                ))

        if not loaded:
            fallback_info = f" (fallback {agent.fallback_model} also failed)" if agent.fallback_model else ""
            error_reason = f"Could not load model {agent.model}{fallback_info}"

            # Phase 5.6: Save checkpoint on model load failure
            self._save_error_checkpoint(
                task=task,
                error_reason=error_reason,
                error_context={"model": agent.model, "fallback_model": agent.fallback_model}
            )

            return LoopResult(
                success=False,
                iterations=0,
                reason=error_reason
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

        result = await self._run_loop(task, agent, task_tools, active_model=active_model)

        if result.success:
            task.status = TaskStatus.COMPLETE
            task.completed_at = datetime.now()
            task.result = {"output": result.final_output}
            await self.delegation.child_completed(task)

            # Phase 5.6: Clear checkpoint on successful completion
            if self.recovery:
                self.recovery.clear_checkpoint(task.id)

            # Emit completion event
            self.event_bus.emit(Event(
                type=EventType.TASK_STATUS_CHANGED,
                data={"task_id": task.id, "status": TaskStatus.COMPLETE}
            ))

            log.info("task_completed", task_id=task.id, iterations=result.iterations)
        elif task.status != TaskStatus.CANCELLED:
            # Only mark as FAILED if not already CANCELLED
            task.status = TaskStatus.FAILED
            task.error = result.reason
            await self.delegation.child_failed(task)

            # Emit failure event
            self.event_bus.emit(Event(
                type=EventType.TASK_STATUS_CHANGED,
                data={"task_id": task.id, "status": TaskStatus.FAILED}
            ))

            # Emit error event for TUI
            self.event_bus.emit(Event(
                type=EventType.ERROR,
                data={
                    "task_id": task.id,
                    "error": result.reason or "Task failed",
                    "error_type": "task_failure",
                    "agent": agent.name,
                    "description": task.description[:100]
                }
            ))

            log.error("task_failed",
                      task_id=task.id,
                      reason=result.reason,
                      iterations=result.iterations)

        return result

    async def _run_loop(
        self,
        task: Task,
        agent,
        task_tools: ToolRegistry,
        active_model: str = None
    ) -> LoopResult:
        """Execute the agent loop for a task.

        Args:
            task: The task to execute
            agent: Agent definition
            task_tools: Tool registry for this task
            active_model: Model to use (may differ from agent.model if degraded)
        """
        # Phase 5.6: Use active_model if provided, otherwise agent.model
        model_to_use = active_model or agent.model

        # Resume existing session if available, otherwise create new one
        # Note: Use model_to_use for session (may be fallback model)
        if task.session_id:
            log.info("resuming_session", task_id=task.id, session_id=task.session_id, model=model_to_use)
            session = await self.state.load_session(task.session_id)
            if not session:
                log.warning("session_not_found", session_id=task.session_id)
                # Fallback: create new session
                session = await self.state.create_session(task.description, model_to_use)
                task.session_id = session.id
        else:
            # Create new session for new task
            log.info("creating_new_session", task_id=task.id)
            session = await self.state.create_session(task.description, agent.model)
            task.session_id = session.id

        # Index project if memory available and not yet indexed
        project_id = f"project_{os.getcwd().replace('/', '_')}"
        if self.memory and project_id not in self._indexed_projects:
            log.info("indexing_project", path=os.getcwd())
            indexed = self.memory.index_project(os.getcwd(), project_id)
            self._indexed_projects.add(project_id)
            log.info("project_indexed", files=indexed, project_id=project_id)

        recent_responses = []
        tool_call_history = []  # Phase 5.6: Track tool calls for repetition detection
        nudge_count = 0         # Phase 5.6: Track nudges for escalation
        completion_detector = CompletionDetector(self.config.completion_marker)
        tool_parser = ToolCallParser()

        for iteration in range(agent.max_iterations):
            # Check for cancellation
            if task.cancel_requested:
                log.info("task_cancelled_in_loop", task_id=task.id, iteration=iteration + 1)
                task.status = TaskStatus.CANCELLED
                task.error = "Task cancelled by user"
                self.event_bus.emit(Event(
                    type=EventType.TASK_STATUS_CHANGED,
                    data={"task_id": task.id, "status": TaskStatus.CANCELLED}
                ))

                # Phase 5.6: Save checkpoint on cancellation
                self._save_error_checkpoint(
                    task=task,
                    error_reason="cancelled_by_user",
                    session_id=session.id if session else None,
                    iteration=iteration + 1
                )

                return LoopResult(
                    success=False,
                    iterations=iteration + 1
                )

            # Phase 5.6: Warn agent about remaining iterations
            iterations_remaining = agent.max_iterations - iteration
            if iterations_remaining in [5, 3, 1]:
                if iterations_remaining == 1:
                    warning_msg = (
                        "WARNING: This is your FINAL iteration. "
                        "Please complete the task or summarize what you've accomplished and what remains."
                    )
                else:
                    warning_msg = (
                        f"WARNING: Only {iterations_remaining} iterations remaining. "
                        "Please prioritize completing the task or marking blockers."
                    )

                log.warning("iteration_warning",
                           task_id=task.id,
                           remaining=iterations_remaining)

                # Emit warning event for TUI
                self.event_bus.emit(Event(
                    type=EventType.ITERATION_WARNING,
                    data={
                        "task_id": task.id,
                        "remaining": iterations_remaining,
                        "message": warning_msg
                    },
                    task_id=task.id
                ))

                # Inject warning into session so agent sees it
                session.add_turn("system", warning_msg)

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

            # Call LLM (Phase 5.6: use model_to_use for potential fallback)
            # Phase 6.3: Support streaming mode
            if self.config.streaming:
                response, assistant_content = await self._call_llm_streaming(
                    model=model_to_use,
                    messages=messages,
                    tools=task_tools.get_schemas(),
                    task=task,
                    agent=agent
                )
            else:
                response = await self.client.chat(
                    model=model_to_use,
                    messages=messages,
                    tools=task_tools.get_schemas()
                )
                assistant_content = response.message.content

            # Check for cancellation after LLM call (in case it was requested during call)
            if task.cancel_requested:
                log.info("task_cancelled_after_llm", task_id=task.id)
                task.status = TaskStatus.CANCELLED
                task.error = "Task cancelled by user"
                self.event_bus.emit(Event(
                    type=EventType.TASK_STATUS_CHANGED,
                    data={"task_id": task.id, "status": TaskStatus.CANCELLED}
                ))

                # Phase 5.6: Save checkpoint on cancellation
                self._save_error_checkpoint(
                    task=task,
                    error_reason="cancelled_after_llm",
                    session_id=session.id,
                    iteration=iteration + 1
                )

                return LoopResult(
                    success=False,
                    iterations=iteration + 1
                )

            # assistant_content is already set by streaming or non-streaming path
            log.info("llm_response",
                     task_id=task.id,
                     content=assistant_content[:200] if assistant_content else "",
                     has_tool_calls=response.message.tool_calls is not None)

            # Emit agent output event (only if not streaming - streaming emits tokens directly)
            if not self.config.streaming:
                self.event_bus.emit(Event(
                    type=EventType.AGENT_OUTPUT,
                    data={
                        "task_id": task.id,
                        "agent": agent.name,
                        "text": assistant_content
                    }
                ))

            # Execute tool calls FIRST (before checking completion)
            # This ensures tools are executed even if agent prematurely marks complete
            tool_results = []
            calls_to_execute = []

            # Check for native tool calls first
            log.info("tool_check", native_tool_calls=response.message.tool_calls,
                     content_has_json="{" in assistant_content)
            if response.message.tool_calls:
                log.info("native_tool_calls_detected",
                         task_id=task.id,
                         count=len(response.message.tool_calls))
                calls_to_execute = response.message.tool_calls
            else:
                # Try parsing tool calls from text
                log.info("attempting_tool_parse", content_preview=assistant_content[:200])
                parsed_calls = tool_parser.parse(assistant_content)
                log.info("parse_result", parsed_count=len(parsed_calls) if parsed_calls else 0)
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

                # Phase 5.6: Track tool calls for stuck detection
                args_hash = hash(str(call.function.arguments))
                tool_call_history.append((call.function.name, args_hash))
                if len(tool_call_history) > 10:  # Keep only recent history
                    tool_call_history.pop(0)

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

                    # Update session with delegation result
                    session.add_turn("assistant", assistant_content, tool_calls=response.message.tool_calls)
                    if tool_results:
                        session.add_turn("tool", str(tool_results))
                    session.iterations = iteration + 1
                    await self.state.save_session(session)

                    # RETURN from loop - parent will resume when child completes
                    # (DelegationManager sets parent status to WAITING and will
                    # set it back to PENDING + re-add to queue when child finishes)
                    log.info("parent_paused_for_delegation",
                            task_id=task.id,
                            iterations=iteration + 1)
                    return LoopResult(
                        success=None,  # Not complete yet, waiting for child
                        iterations=iteration + 1,
                        reason="delegation_waiting",
                        final_output="Waiting for delegated child task to complete"
                    )

            # Update session
            session.add_turn("assistant", assistant_content, tool_calls=response.message.tool_calls)
            if tool_results:
                session.add_turn("tool", str(tool_results))

            # Checkpoint
            session.iterations = iteration + 1
            if iteration % self.config.checkpoint_interval == 0:
                await self.state.save_session(session)

            # NOW check completion (after tools executed)
            if completion_detector.is_complete(assistant_content):
                # Only complete if no tools were just executed (tools need results first)
                if not tool_results:
                    # Validate that completion is legitimate (work was actually done)
                    if self._validate_completion(session, task, assistant_content):
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
                    else:
                        # Completion marker found but validation failed
                        log.warning("invalid_completion_rejected",
                                   task_id=task.id,
                                   reason="No evidence of work done",
                                   message="Agent marked complete but validation failed - continuing")
                        session.add_turn("user",
                                       "You marked the task complete, but I don't see evidence that you performed the requested work. Please actually complete the task before marking it done.")
                else:
                    # Tools were executed - agent marked complete prematurely
                    # Continue to next iteration to let agent see tool results
                    log.warning("completion_marker_with_tools",
                               task_id=task.id,
                               message="Agent marked complete but tools were just executed - continuing")

            # Check stuck (Phase 5.6: Enhanced detection with escalation)
            recent_responses.append(assistant_content)
            if len(recent_responses) > self.config.stuck_threshold:
                recent_responses.pop(0)

            is_stuck, stuck_reason = self._is_stuck(recent_responses, tool_call_history)
            if is_stuck:
                nudge_count += 1
                log.warning("stuck_detected",
                           task_id=task.id,
                           reason=stuck_reason,
                           nudge_count=nudge_count,
                           max_nudges=self.config.max_nudges)

                # Check if we should escalate (fail) instead of nudging
                if nudge_count >= self.config.max_nudges:
                    # Emit error event for TUI
                    self.event_bus.emit(Event(
                        type=EventType.ERROR,
                        data={
                            "task_id": task.id,
                            "error_type": "agent_stuck",
                            "reason": stuck_reason,
                            "nudge_count": nudge_count,
                            "suggestion": "Consider switching agent or replanning the task"
                        },
                        task_id=task.id
                    ))

                    task.status = TaskStatus.FAILED
                    task.error = f"Agent stuck after {nudge_count} nudges (reason: {stuck_reason})"

                    # Phase 5.6: Save checkpoint on stuck escalation
                    self._save_error_checkpoint(
                        task=task,
                        error_reason=f"stuck_after_nudges:{stuck_reason}",
                        session_id=session.id,
                        iteration=iteration + 1,
                        error_context={"nudge_count": nudge_count, "stuck_reason": stuck_reason}
                    )

                    return LoopResult(
                        success=False,
                        iterations=iteration + 1,
                        reason=f"stuck_after_nudges:{stuck_reason}"
                    )

                # Generate context-specific nudge message
                nudge_messages = {
                    "exact_repeat": "You're repeating the same response. Try a different approach or use a different tool.",
                    "high_similarity": "Your responses are very similar. Consider breaking down the problem differently.",
                    "repeated_tool_calls": "You're calling the same tool repeatedly with the same arguments. Check if it's working or try something else.",
                    "clarification_loop": "You've asked for clarification multiple times. Please proceed with your best interpretation of the task."
                }
                nudge_msg = nudge_messages.get(stuck_reason, "You seem stuck. Try a different approach.")
                nudge_msg += f" ({self.config.max_nudges - nudge_count} nudge(s) remaining before task fails)"

                session.add_turn("user", nudge_msg)
                recent_responses.clear()
                continue

        # Phase 5.6: Save checkpoint when max iterations reached
        self._save_error_checkpoint(
            task=task,
            error_reason="max_iterations_reached",
            session_id=session.id,
            iteration=agent.max_iterations,
            error_context={"max_iterations": agent.max_iterations}
        )

        return LoopResult(
            success=False,
            iterations=agent.max_iterations,
            reason="max_iterations_reached"
        )

    async def _call_llm_streaming(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        task: Task,
        agent
    ) -> tuple:
        """Call LLM with streaming, emitting tokens to event bus.

        Phase 6.3: Enables real-time token display in TUI.

        Args:
            model: Model to use
            messages: Conversation messages
            tools: Tool schemas
            task: Current task
            agent: Agent definition

        Returns:
            (Response, content) - Response object and full content string
        """
        streaming_buffer = StreamingBuffer()

        # Emit streaming start event
        self.event_bus.emit(Event(
            type=EventType.STREAMING_START,
            data={
                "task_id": task.id,
                "agent": agent.name,
                "model": model
            },
            task_id=task.id
        ))

        def on_token(token: str):
            """Callback for each token."""
            displayable, is_tool = streaming_buffer.add_token(token)

            # Only emit displayable tokens (not tool call JSON)
            if displayable and not is_tool:
                self.event_bus.emit(Event(
                    type=EventType.STREAMING_TOKEN,
                    data={
                        "task_id": task.id,
                        "agent": agent.name,
                        "token": displayable
                    },
                    task_id=task.id
                ))

        try:
            # Use streaming chat
            streaming_response = await self.client.chat_stream(
                model=model,
                messages=messages,
                tools=tools,
                on_token=on_token
            )

            # Convert to standard Response
            response = streaming_response.to_response()

            # Emit streaming end event
            self.event_bus.emit(Event(
                type=EventType.STREAMING_END,
                data={
                    "task_id": task.id,
                    "agent": agent.name,
                    "content_length": len(streaming_response.content)
                },
                task_id=task.id
            ))

            # Check for tool calls detected from text (if not native)
            if not response.message.tool_calls:
                detected_calls = streaming_buffer.get_tool_calls()
                if detected_calls:
                    # Convert to the expected format
                    class CallWrapper:
                        def __init__(self, name, arguments):
                            self.function = type('obj', (object,), {
                                'name': name,
                                'arguments': arguments
                            })()

                    # Note: We don't modify response.message.tool_calls as it's
                    # already handled by ToolCallParser later in the flow
                    log.info("streaming_detected_tool_calls",
                            task_id=task.id,
                            count=len(detected_calls))

            return response, streaming_response.content

        except Exception as e:
            log.error("streaming_error", task_id=task.id, error=str(e))
            # Fallback to non-streaming
            response = await self.client.chat(
                model=model,
                messages=messages,
                tools=tools
            )
            return response, response.message.content

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

    def _is_stuck(self, responses: list[str], tool_history: list[tuple] = None) -> tuple[bool, str]:
        """Enhanced stuck detection with multiple heuristics.

        Phase 5.6: Improved detection beyond exact string matching.

        Args:
            responses: Recent assistant responses
            tool_history: Recent tool calls as (name, args_hash) tuples

        Returns:
            (is_stuck: bool, reason: str) - reason explains why stuck
        """
        if len(responses) < self.config.stuck_threshold:
            return False, ""

        recent = responses[-self.config.stuck_threshold:]

        # 1. Exact match detection (existing behavior)
        if len(set(recent)) == 1:
            return True, "exact_repeat"

        # 2. High similarity detection (word overlap)
        if self._high_similarity(recent):
            return True, "high_similarity"

        # 3. Tool call repetition (same tool with same args 3+ times)
        if tool_history and self._repeated_tool_calls(tool_history):
            return True, "repeated_tool_calls"

        # 4. Clarification loop (agent keeps asking for clarification)
        clarification_patterns = [
            "what would you like",
            "please clarify",
            "could you specify",
            "can you provide more",
            "i need more information",
            "please provide",
        ]
        if all(any(p in r.lower() for p in clarification_patterns) for r in recent):
            return True, "clarification_loop"

        return False, ""

    def _high_similarity(self, responses: list[str]) -> bool:
        """Check if responses have high word overlap (>80%).

        Args:
            responses: List of response strings

        Returns:
            True if all responses are highly similar
        """
        if len(responses) < 2:
            return False

        # Tokenize into words
        word_sets = [set(r.lower().split()) for r in responses]

        # Remove very common words that don't indicate real similarity
        common_words = {"the", "a", "an", "is", "are", "to", "for", "and", "or", "i"}
        word_sets = [words - common_words for words in word_sets]

        # Check overlap between consecutive responses
        base = word_sets[0]
        for other in word_sets[1:]:
            if not base or not other:
                return False
            overlap = len(base & other) / max(len(base | other), 1)
            if overlap < self.config.similarity_threshold:
                return False

        return True

    def _repeated_tool_calls(self, tool_history: list[tuple]) -> bool:
        """Check if the same tool is called with same args repeatedly.

        Args:
            tool_history: List of (tool_name, args_hash) tuples

        Returns:
            True if same tool call repeated 3+ times consecutively
        """
        if len(tool_history) < 3:
            return False

        recent = tool_history[-3:]
        return len(set(recent)) == 1

    def _validate_completion(self, session, task, final_response: str) -> bool:
        """Validate that a completion marker is legitimate.

        Returns True if the agent actually did work, False if it's a false completion.
        """
        # Check 1: Were any tools executed during this session?
        tool_turns = [turn for turn in session.turns if turn.role == "tool"]
        if tool_turns:
            log.info("completion_validation_passed",
                    reason="tools_executed",
                    tool_count=len(tool_turns))
            return True

        # Check 2: Is there substantive output in the final response?
        # (More than just the completion marker)
        response_without_marker = final_response.replace("<sindri:complete/>", "").strip()
        if len(response_without_marker) > 100:
            log.info("completion_validation_passed",
                    reason="substantive_output",
                    output_length=len(response_without_marker))
            return True

        # Check 3: For action-oriented tasks, require evidence of action
        action_keywords = [
            "create", "write", "edit", "modify", "update", "delete", "remove",
            "implement", "build", "refactor", "review", "analyze", "fix"
        ]
        task_lower = task.description.lower()
        requires_action = any(keyword in task_lower for keyword in action_keywords)

        if requires_action:
            log.warning("completion_validation_failed",
                       reason="action_required_but_no_tools",
                       task_preview=task.description[:100])
            return False

        # Check 4: Very short sessions (< 3 turns) with no tools are suspicious
        if len(session.turns) < 3 and not tool_turns:
            log.warning("completion_validation_failed",
                       reason="suspiciously_short_session",
                       turn_count=len(session.turns))
            return False

        # If none of the above checks failed, accept completion
        log.info("completion_validation_passed",
                reason="default",
                turn_count=len(session.turns))
        return True

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

    def _save_error_checkpoint(
        self,
        task: Task,
        error_reason: str,
        session_id: str = None,
        iteration: int = 0,
        error_context: dict = None
    ):
        """Save checkpoint on error for recovery.

        Phase 5.6: Save state when errors occur for crash recovery.

        Args:
            task: The task that failed
            error_reason: Why the task failed
            session_id: Session ID if available
            iteration: Current iteration number
            error_context: Additional error context
        """
        if not self.recovery:
            return

        try:
            checkpoint_data = {
                "task": {
                    "id": task.id,
                    "description": task.description,
                    "assigned_agent": task.assigned_agent,
                    "parent_id": task.parent_id,
                    "context": task.context
                },
                "error": {
                    "reason": error_reason,
                    "context": error_context or {}
                },
                "session_id": session_id,
                "iterations": iteration,
                "timestamp": datetime.now().isoformat()
            }

            self.recovery.save_checkpoint(task.id, checkpoint_data)
            log.info("error_checkpoint_saved",
                    task_id=task.id,
                    error_reason=error_reason)

        except Exception as e:
            log.warning("error_checkpoint_failed",
                       task_id=task.id,
                       error=str(e))
