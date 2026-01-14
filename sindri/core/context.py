"""Context building for Sindri."""

import structlog

log = structlog.get_logger()


class ContextBuilder:
    """Builds message context for LLM calls."""

    def build(
        self,
        task: str,
        history: list,
        tools: list[dict]
    ) -> list[dict]:
        """Build messages array for Ollama."""

        messages = []

        # System message
        system_prompt = self._build_system_prompt(task, tools)
        messages.append({
            "role": "system",
            "content": system_prompt
        })

        # Add conversation history
        for turn in history:
            message = {
                "role": turn.role,
                "content": turn.content
            }
            # Include tool_calls if present
            if turn.tool_calls:
                message["tool_calls"] = turn.tool_calls
            messages.append(message)

        log.info("context_built", num_messages=len(messages))
        return messages

    def _build_system_prompt(self, task: str, tools: list[dict]) -> str:
        """Build the system prompt."""

        tool_descriptions = "\n".join([
            f"- {tool['function']['name']}: {tool['function']['description']}"
            for tool in tools
        ])

        return f"""You are Sindri, a local LLM orchestration agent.

Your task: {task}

Available tools:
{tool_descriptions}

Instructions:
1. Break down the task into steps
2. Use the available tools to complete each step
3. When the task is fully complete, output: <sindri:complete/>
4. If you get stuck, explain what you need

Be direct and efficient. Execute tools as needed to accomplish the task.
"""
