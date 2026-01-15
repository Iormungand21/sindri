"""
The Ralph-style agent loop - heart of Sindri.

Iterates until:
- Completion marker detected
- Max iterations reached
- Unrecoverable error
"""

from dataclasses import dataclass
import structlog

from sindri.llm.client import OllamaClient
from sindri.tools.registry import ToolRegistry
from sindri.persistence.state import SessionState
from sindri.core.completion import CompletionDetector
from sindri.core.context import ContextBuilder

log = structlog.get_logger()


@dataclass
class LoopConfig:
    max_iterations: int = 50
    completion_marker: str = "<sindri:complete/>"
    stuck_threshold: int = 3
    checkpoint_interval: int = 5
    # Phase 5.6: Enhanced stuck detection
    max_nudges: int = 3  # Maximum nudges before escalating to failure
    similarity_threshold: float = 0.8  # Word overlap ratio for similarity detection
    # Phase 6.3: Streaming output
    streaming: bool = True  # Enable streaming responses by default


@dataclass
class LoopResult:
    success: bool
    iterations: int
    reason: str = ""
    final_output: str = ""


class AgentLoop:
    """Core iteration loop."""

    def __init__(
        self,
        client: OllamaClient,
        tools: ToolRegistry,
        state: SessionState,
        config: LoopConfig = None
    ):
        self.client = client
        self.tools = tools
        self.state = state
        self.config = config or LoopConfig()
        self.completion = CompletionDetector(self.config.completion_marker)
        self.context = ContextBuilder()

    async def run(self, task: str, model: str) -> LoopResult:
        """Execute the loop until completion."""

        session = await self.state.create_session(task, model)
        recent_responses = []

        for iteration in range(self.config.max_iterations):
            log.info("iteration_start", iteration=iteration + 1, session=session.id)

            # 1. Build messages
            messages = self.context.build(
                task=task,
                history=session.turns,
                tools=self.tools.get_schemas()
            )

            # 2. Call LLM
            response = await self.client.chat(
                model=model,
                messages=messages,
                tools=self.tools.get_schemas()
            )

            assistant_content = response.message.content
            log.info("llm_response", content=assistant_content[:200], has_tool_calls=response.message.tool_calls is not None)

            # 3. Execute tool calls FIRST (before checking completion)
            # This ensures tools execute even if agent prematurely marks complete
            tool_results = []
            calls_to_execute = []

            # Check for native tool calls first
            if response.message.tool_calls:
                log.info("tool_calls_detected", count=len(response.message.tool_calls))
                calls_to_execute = response.message.tool_calls
            else:
                # Try parsing tool calls from text
                from sindri.llm.tool_parser import ToolCallParser
                parser = ToolCallParser()
                parsed_calls = parser.parse(assistant_content)
                if parsed_calls:
                    log.info("parsed_tool_calls_from_text", count=len(parsed_calls))
                    # Convert to native format
                    class CallWrapper:
                        def __init__(self, name, arguments):
                            self.function = type('obj', (object,), {
                                'name': name,
                                'arguments': arguments
                            })()
                    calls_to_execute = [CallWrapper(c.name, c.arguments) for c in parsed_calls]

            # Execute all tool calls
            for call in calls_to_execute:
                log.info("executing_tool", tool=call.function.name, args=call.function.arguments)
                result = await self.tools.execute(
                    call.function.name,
                    call.function.arguments
                )
                tool_results.append({
                    "tool": call.function.name,
                    "result": result.output if result.success else f"ERROR: {result.error}"
                })
                log.info("tool_executed", tool=call.function.name, success=result.success)

            # 4. Check completion (after tool execution)
            if self.completion.is_complete(assistant_content):
                # Only complete if no tools were just executed
                if not tool_results:
                    await self.state.complete_session(session.id)
                    return LoopResult(
                        success=True,
                        iterations=iteration + 1,
                        reason="completion_marker",
                        final_output=assistant_content
                    )
                else:
                    # Tools executed - continue to show agent the results
                    log.warning("completion_marker_with_tools", message="Agent marked complete but tools executed - continuing")

            # 5. Check stuck
            recent_responses.append(assistant_content)
            if len(recent_responses) > self.config.stuck_threshold:
                recent_responses.pop(0)

            if self._is_stuck(recent_responses):
                log.warning("stuck_detected")
                # Add nudge
                session.add_turn("user", "You seem stuck. Try a different approach or ask for clarification.")
                recent_responses.clear()
                continue

            # 6. Update session
            session.add_turn("assistant", assistant_content, tool_calls=response.message.tool_calls)
            if tool_results:
                session.add_turn("tool", str(tool_results))

            # 7. Checkpoint
            session.iterations = iteration + 1
            if iteration % self.config.checkpoint_interval == 0:
                await self.state.save_session(session)

        return LoopResult(
            success=False,
            iterations=self.config.max_iterations,
            reason="max_iterations_reached"
        )

    def _is_stuck(self, responses: list[str]) -> bool:
        """Detect if we're getting the same response repeatedly."""
        if len(responses) < self.config.stuck_threshold:
            return False
        return len(set(responses)) == 1
