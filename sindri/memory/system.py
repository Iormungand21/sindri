"""Unified memory system - Muninn, Odin's raven of memory."""

from dataclasses import dataclass
from typing import Optional
import tiktoken
import structlog

from sindri.memory.episodic import EpisodicMemory
from sindri.memory.semantic import SemanticMemory
from sindri.memory.embedder import LocalEmbedder
from sindri.persistence.vectors import VectorStore

log = structlog.get_logger()


@dataclass
class MemoryConfig:
    """Configuration for memory system."""
    episodic_limit: int = 5
    semantic_limit: int = 10
    max_context_tokens: int = 16384
    working_memory_ratio: float = 0.6  # 60% for conversation


class MuninnMemory:
    """The complete memory system - Odin's raven of memory.

    Three-tier architecture:
    - Working: Immediate context (recent conversation)
    - Episodic: Project history (past tasks/decisions)
    - Semantic: Codebase index (code embeddings)
    """

    def __init__(
        self,
        db_path: str,
        config: Optional[MemoryConfig] = None
    ):
        self.config = config or MemoryConfig()
        self.embedder = LocalEmbedder()
        self.vectors = VectorStore(db_path, self.embedder.dimension)
        self.episodic = EpisodicMemory(db_path, self.embedder)
        self.semantic = SemanticMemory(self.vectors, self.embedder)
        self._tokenizer = tiktoken.get_encoding("cl100k_base")
        log.info("muninn_memory_initialized", db_path=db_path)

    def build_context(
        self,
        project_id: str,
        current_task: str,
        conversation: list[dict],
        max_tokens: Optional[int] = None
    ) -> list[dict]:
        """Build complete context for an agent invocation.

        Allocates token budget across three memory tiers:
        - 60% working memory (recent conversation)
        - 20% episodic memory (past tasks)
        - 20% semantic memory (codebase)
        """

        max_tokens = max_tokens or self.config.max_context_tokens

        # Budget allocation
        working_budget = int(max_tokens * self.config.working_memory_ratio)
        episodic_budget = int(max_tokens * 0.2)
        semantic_budget = int(max_tokens * 0.2)

        context_parts = []

        # 1. Semantic memory (codebase context)
        try:
            semantic_results = self.semantic.search(
                namespace=project_id,
                query=current_task,
                limit=self.config.semantic_limit
            )
            if semantic_results:
                semantic_text = self._format_semantic(semantic_results)
                semantic_text = self._truncate_to_tokens(semantic_text, semantic_budget)
                context_parts.append({
                    "role": "user",
                    "content": f"[Relevant code from codebase]\n{semantic_text}"
                })
                log.debug("semantic_context_added", chunks=len(semantic_results))
        except Exception as e:
            log.warning("semantic_context_failed", error=str(e))

        # 2. Episodic memory (past decisions)
        try:
            episodes = self.episodic.retrieve_relevant(
                project_id=project_id,
                query=current_task,
                limit=self.config.episodic_limit
            )
            if episodes:
                episodic_text = self._format_episodic(episodes)
                episodic_text = self._truncate_to_tokens(episodic_text, episodic_budget)
                context_parts.append({
                    "role": "user",
                    "content": f"[Relevant past context]\n{episodic_text}"
                })
                log.debug("episodic_context_added", episodes=len(episodes))
        except Exception as e:
            log.warning("episodic_context_failed", error=str(e))

        # 3. Working memory (recent conversation)
        working_conv = self._fit_conversation(conversation, working_budget)
        log.debug(
            "context_built",
            working_messages=len(working_conv),
            total_parts=len(context_parts) + len(working_conv)
        )

        return context_parts + working_conv

    def _format_semantic(self, results: list[tuple[str, dict, float]]) -> str:
        """Format semantic search results."""
        parts = []
        for content, meta, score in results:
            path = meta.get('path', 'unknown')
            start = meta.get('start_line', '?')
            end = meta.get('end_line', '?')
            parts.append(f"# {path} (lines {start}-{end}, relevance: {score:.2f})\n{content}")
        return "\n\n".join(parts)

    def _format_episodic(self, episodes: list) -> str:
        """Format episodic memories."""
        parts = []
        for ep in episodes:
            parts.append(f"[{ep.event_type}] {ep.content}")
        return "\n".join(parts)

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self._tokenizer.encode(text))

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit token budget."""
        tokens = self._tokenizer.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self._tokenizer.decode(tokens[:max_tokens])

    def _fit_conversation(self, conv: list[dict], max_tokens: int) -> list[dict]:
        """Fit conversation into token budget, keeping most recent."""
        result = []
        used = 0

        for msg in reversed(conv):
            content = msg.get("content", "")
            if not content:
                continue

            msg_tokens = self._count_tokens(content)
            if used + msg_tokens > max_tokens:
                break
            result.insert(0, msg)
            used += msg_tokens

        return result

    # Storage operations

    def store_episode(
        self,
        project_id: str,
        event_type: str,
        content: str,
        metadata: Optional[dict] = None
    ) -> int:
        """Store a new episode."""
        return self.episodic.store(project_id, event_type, content, metadata)

    def index_project(self, project_path: str, project_id: str, force: bool = False) -> int:
        """Index a project's codebase.

        Returns: Number of files indexed
        """
        return self.semantic.index_directory(project_path, project_id, force)

    def clear_project(self, project_id: str):
        """Clear all memory for a project."""
        self.semantic.clear_index(project_id)
        log.info("project_memory_cleared", project_id=project_id)
