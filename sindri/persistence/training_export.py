"""Training data export for Sindri fine-tuning.

This module exports high-quality sessions to formats suitable for
fine-tuning local LLMs via Ollama. Supported formats:

- JSONL: Standard format for OpenAI-style fine-tuning
- ChatML: Chat Markup Language format
- Ollama: Format for Ollama Modelfile creation

The exporter filters sessions by feedback rating to ensure only
high-quality interactions are used for training.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any, TextIO
import structlog

from sindri.persistence.database import Database
from sindri.persistence.state import SessionState, Session
from sindri.persistence.feedback import FeedbackStore

log = structlog.get_logger()


class ExportFormat(str, Enum):
    """Supported export formats for training data."""

    JSONL = "jsonl"  # OpenAI-style JSONL format
    CHATML = "chatml"  # Chat Markup Language format
    OLLAMA = "ollama"  # Ollama Modelfile format


@dataclass
class ExportStats:
    """Statistics about an export operation."""

    sessions_exported: int = 0
    conversations_exported: int = 0
    turns_exported: int = 0
    sessions_skipped: int = 0
    total_tokens_estimate: int = 0
    export_path: Optional[Path] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sessions_exported": self.sessions_exported,
            "conversations_exported": self.conversations_exported,
            "turns_exported": self.turns_exported,
            "sessions_skipped": self.sessions_skipped,
            "total_tokens_estimate": self.total_tokens_estimate,
            "export_path": str(self.export_path) if self.export_path else None,
        }


class TrainingDataExporter:
    """Exports session data to formats suitable for LLM fine-tuning.

    The exporter can:
    - Export sessions with positive feedback (4-5 stars)
    - Filter by quality tags
    - Generate JSONL, ChatML, or Ollama Modelfile formats
    - Estimate token counts for training cost estimation
    """

    def __init__(
        self,
        database: Optional[Database] = None,
        session_state: Optional[SessionState] = None,
        feedback_store: Optional[FeedbackStore] = None,
    ):
        """Initialize the exporter.

        Args:
            database: Database instance (uses default if not provided)
            session_state: SessionState instance for loading sessions
            feedback_store: FeedbackStore instance for feedback queries
        """
        self.db = database or Database()
        self.session_state = session_state or SessionState(self.db)
        self.feedback_store = feedback_store or FeedbackStore(self.db)

    async def export_training_data(
        self,
        output_path: Path,
        format: ExportFormat = ExportFormat.JSONL,
        min_rating: int = 4,
        session_ids: Optional[list[str]] = None,
        include_system_prompt: bool = True,
        include_tool_calls: bool = True,
        max_sessions: int = 1000,
    ) -> ExportStats:
        """Export training data to a file.

        Args:
            output_path: Path to the output file
            format: Export format (jsonl, chatml, ollama)
            min_rating: Minimum feedback rating to include (default 4)
            session_ids: Specific session IDs to export (None = auto-select)
            include_system_prompt: Include system prompts in training data
            include_tool_calls: Include tool calls and results
            max_sessions: Maximum number of sessions to export

        Returns:
            ExportStats with information about the export
        """
        stats = ExportStats(export_path=output_path)

        # Get session IDs to export
        if session_ids is None:
            session_ids = await self.feedback_store.get_training_candidates(
                min_rating=min_rating,
                limit=max_sessions,
            )

        if not session_ids:
            log.warning("no_training_candidates", min_rating=min_rating)
            return stats

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Export based on format
        with open(output_path, "w", encoding="utf-8") as f:
            for session_id in session_ids:
                session = await self.session_state.load_session(session_id)
                if not session:
                    stats.sessions_skipped += 1
                    continue

                # Skip sessions with no turns
                if not session.turns:
                    stats.sessions_skipped += 1
                    continue

                if format == ExportFormat.JSONL:
                    self._export_jsonl(
                        f,
                        session,
                        include_system_prompt,
                        include_tool_calls,
                        stats,
                    )
                elif format == ExportFormat.CHATML:
                    self._export_chatml(
                        f,
                        session,
                        include_system_prompt,
                        include_tool_calls,
                        stats,
                    )
                elif format == ExportFormat.OLLAMA:
                    self._export_ollama(
                        f,
                        session,
                        include_system_prompt,
                        include_tool_calls,
                        stats,
                    )

                stats.sessions_exported += 1
                stats.conversations_exported += 1

        log.info(
            "training_data_exported",
            format=format.value,
            sessions=stats.sessions_exported,
            turns=stats.turns_exported,
            path=str(output_path),
        )

        return stats

    def _export_jsonl(
        self,
        f: TextIO,
        session: Session,
        include_system_prompt: bool,
        include_tool_calls: bool,
        stats: ExportStats,
    ) -> None:
        """Export session in JSONL format (OpenAI fine-tuning format).

        Each conversation is a single JSON line with "messages" array.
        """
        messages = []

        # Add system prompt if requested
        if include_system_prompt:
            system_prompt = self._get_system_prompt(session.model)
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

        # Process turns
        for turn in session.turns:
            # Skip tool results unless including tool calls
            if turn.role == "tool" and not include_tool_calls:
                continue

            message: dict[str, Any] = {
                "role": turn.role,
                "content": turn.content or "",
            }

            # Add tool calls if present and requested
            if include_tool_calls and turn.tool_calls:
                message["tool_calls"] = self._format_tool_calls(turn.tool_calls)

            messages.append(message)
            stats.turns_exported += 1

            # Rough token estimate (4 chars per token)
            stats.total_tokens_estimate += len(turn.content or "") // 4

        # Write as single JSONL line
        if messages:
            json_line = json.dumps({"messages": messages}, ensure_ascii=False)
            f.write(json_line + "\n")

    def _export_chatml(
        self,
        f: TextIO,
        session: Session,
        include_system_prompt: bool,
        include_tool_calls: bool,
        stats: ExportStats,
    ) -> None:
        """Export session in ChatML format.

        ChatML uses special tokens: <|im_start|>role, <|im_end|>
        """
        # Add system prompt if requested
        if include_system_prompt:
            system_prompt = self._get_system_prompt(session.model)
            if system_prompt:
                f.write(f"<|im_start|>system\n{system_prompt}<|im_end|>\n")

        # Process turns
        for turn in session.turns:
            # Skip tool results unless including tool calls
            if turn.role == "tool" and not include_tool_calls:
                continue

            content = turn.content or ""

            # Include tool calls in content if present
            if include_tool_calls and turn.tool_calls:
                tool_str = json.dumps(
                    self._format_tool_calls(turn.tool_calls),
                    indent=2,
                    ensure_ascii=False,
                )
                content = f"{content}\n\nTool calls:\n{tool_str}"

            f.write(f"<|im_start|>{turn.role}\n{content}<|im_end|>\n")
            stats.turns_exported += 1
            stats.total_tokens_estimate += len(content) // 4

        # End of conversation marker
        f.write("<|end_of_conversation|>\n\n")

    def _export_ollama(
        self,
        f: TextIO,
        session: Session,
        include_system_prompt: bool,
        include_tool_calls: bool,
        stats: ExportStats,
    ) -> None:
        """Export session in Ollama Modelfile MESSAGE format.

        Uses MESSAGE directives for conversation history.
        """
        # Add system message
        if include_system_prompt:
            system_prompt = self._get_system_prompt(session.model)
            if system_prompt:
                # Escape quotes in content for Modelfile
                escaped = system_prompt.replace('"', '\\"')
                f.write(f'MESSAGE system "{escaped}"\n')

        # Process turns
        for turn in session.turns:
            # Skip tool results for Ollama format
            if turn.role == "tool":
                continue

            content = turn.content or ""

            # Include tool calls in content if present (simplified for Ollama)
            if include_tool_calls and turn.tool_calls:
                tool_names = [
                    tc.get("function", {}).get("name", "unknown")
                    for tc in turn.tool_calls
                    if isinstance(tc, dict)
                ]
                if tool_names:
                    content = f"{content}\n[Used tools: {', '.join(tool_names)}]"

            # Escape quotes and newlines
            escaped = (
                content.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            )
            f.write(f'MESSAGE {turn.role} "{escaped}"\n')
            stats.turns_exported += 1
            stats.total_tokens_estimate += len(content) // 4

        f.write("\n")  # Separator between sessions

    def _format_tool_calls(self, tool_calls: list) -> list[dict[str, Any]]:
        """Format tool calls for export."""
        formatted = []
        for call in tool_calls:
            if isinstance(call, dict):
                func = call.get("function", call)
                formatted.append(
                    {
                        "type": "function",
                        "function": {
                            "name": func.get("name", "unknown"),
                            "arguments": func.get("arguments", {}),
                        },
                    }
                )
        return formatted

    def _get_system_prompt(self, model: str) -> Optional[str]:
        """Get appropriate system prompt for the model.

        Returns a generic system prompt suitable for fine-tuning.
        The actual agent prompts may be more specific.
        """
        return (
            "You are a helpful AI coding assistant. You help users with software engineering tasks "
            "including writing code, debugging, refactoring, and explaining concepts. "
            "You use available tools when appropriate and provide clear, concise responses."
        )

    async def export_for_specific_agent(
        self,
        output_path: Path,
        agent_name: str,
        format: ExportFormat = ExportFormat.JSONL,
        min_rating: int = 4,
        max_sessions: int = 500,
    ) -> ExportStats:
        """Export training data for a specific agent.

        This filters sessions by the agent/model that was used,
        useful for fine-tuning specific agent roles.

        Args:
            output_path: Path to the output file
            agent_name: Name of the agent to export data for
            format: Export format
            min_rating: Minimum feedback rating
            max_sessions: Maximum sessions to export

        Returns:
            ExportStats with export information
        """
        # First get training candidates
        all_candidates = await self.feedback_store.get_training_candidates(
            min_rating=min_rating,
            limit=max_sessions * 2,  # Over-fetch to allow filtering
        )

        # Filter by agent model
        filtered_ids = []
        for session_id in all_candidates:
            session = await self.session_state.load_session(session_id)
            if session and agent_name.lower() in session.model.lower():
                filtered_ids.append(session_id)
                if len(filtered_ids) >= max_sessions:
                    break

        return await self.export_training_data(
            output_path=output_path,
            format=format,
            session_ids=filtered_ids,
        )


def generate_modelfile(
    base_model: str,
    training_data_path: Path,
    output_path: Path,
    model_name: str = "sindri-custom",
    temperature: float = 0.7,
    context_length: int = 4096,
) -> Path:
    """Generate an Ollama Modelfile for fine-tuning.

    Args:
        base_model: Base model to build from (e.g., "qwen2.5-coder:7b")
        training_data_path: Path to exported training data
        output_path: Where to save the Modelfile
        model_name: Name for the custom model
        temperature: Default temperature
        context_length: Context window size

    Returns:
        Path to the generated Modelfile
    """
    modelfile_content = f"""# Sindri Fine-tuned Model
# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# Training data: {training_data_path}

FROM {base_model}

# Model parameters
PARAMETER temperature {temperature}
PARAMETER num_ctx {context_length}

# System prompt
SYSTEM "You are a helpful AI coding assistant fine-tuned on successful coding interactions. You help users with software engineering tasks including writing code, debugging, refactoring, and explaining concepts. You use available tools when appropriate and provide clear, concise responses."

# Training messages are appended below by 'ollama create'
# Use: ollama create {model_name} -f {output_path}
"""

    # Read training data and append as MESSAGE directives
    if training_data_path.exists():
        with open(training_data_path, "r") as f:
            modelfile_content += "\n# Training conversations\n"
            modelfile_content += f.read()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(modelfile_content, encoding="utf-8")

    log.info("modelfile_generated", path=str(output_path), base_model=base_model)

    return output_path
