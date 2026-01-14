"""Summarize conversations for episodic memory."""

from sindri.llm.client import OllamaClient
import structlog

log = structlog.get_logger()


SUMMARIZE_PROMPT = """Summarize this completed task conversation into a brief episodic memory.

Task: {task}

Conversation:
{conversation}

Provide a concise summary (2-3 sentences) capturing:
1. What was accomplished
2. Key decisions made
3. Any important lessons/errors

Summary:"""


class ConversationSummarizer:
    """Compress conversations into episodic memories."""

    def __init__(
        self,
        client: OllamaClient,
        model: str = "qwen2.5:3b-instruct-q8_0"  # Small, fast model for summarization
    ):
        self.client = client
        self.model = model
        log.info("summarizer_initialized", model=model)

    async def summarize(
        self,
        task: str,
        conversation: list[dict]
    ) -> str:
        """Summarize a completed task conversation."""

        # Format conversation (truncate long messages)
        conv_text = "\n".join(
            f"{msg['role']}: {msg.get('content', '')[:500]}"
            for msg in conversation
            if msg.get('content')
        )

        prompt = SUMMARIZE_PROMPT.format(
            task=task,
            conversation=conv_text
        )

        try:
            response = await self.client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            summary = response.message.content.strip()
            log.info("conversation_summarized", length=len(summary))
            return summary

        except Exception as e:
            log.error("summarization_failed", error=str(e))
            # Fallback: return truncated task description
            return f"Completed: {task[:200]}"
