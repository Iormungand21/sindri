"""Unified memory system - Muninn, Odin's raven of memory."""

from dataclasses import dataclass
from typing import Optional, List, TYPE_CHECKING
import tiktoken
import structlog

from sindri.memory.episodic import EpisodicMemory
from sindri.memory.semantic import SemanticMemory
from sindri.memory.embedder import LocalEmbedder
from sindri.memory.patterns import PatternStore, Pattern
from sindri.memory.learner import PatternLearner, LearningConfig
from sindri.memory.codebase import CodebaseAnalyzer, CodebaseAnalysisStore
from sindri.persistence.vectors import VectorStore

if TYPE_CHECKING:
    from sindri.core.tasks import Task

log = structlog.get_logger()


@dataclass
class MemoryConfig:
    """Configuration for memory system."""
    episodic_limit: int = 5
    semantic_limit: int = 10
    pattern_limit: int = 3  # Max patterns to include in context
    max_context_tokens: int = 16384
    working_memory_ratio: float = 0.6  # 60% for conversation
    enable_learning: bool = True  # Whether to learn from completions
    enable_codebase_analysis: bool = True  # Phase 7.4: Codebase understanding


class MuninnMemory:
    """The complete memory system - Odin's raven of memory.

    Five-tier architecture:
    - Working: Immediate context (recent conversation)
    - Episodic: Project history (past tasks/decisions)
    - Semantic: Codebase index (code embeddings)
    - Patterns: Learned successful approaches (Phase 7.2)
    - Analysis: Codebase structure understanding (Phase 7.4)
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

        # Phase 7.2: Pattern learning system
        self.patterns = PatternStore(db_path)
        self.learner = PatternLearner(
            self.patterns,
            LearningConfig()
        ) if self.config.enable_learning else None

        # Phase 7.4: Codebase analysis system
        self.codebase_analyzer = CodebaseAnalyzer(db_path) if self.config.enable_codebase_analysis else None

        log.info("muninn_memory_initialized",
                db_path=db_path,
                learning_enabled=self.config.enable_learning,
                analysis_enabled=self.config.enable_codebase_analysis)

    def build_context(
        self,
        project_id: str,
        current_task: str,
        conversation: list[dict],
        max_tokens: Optional[int] = None
    ) -> list[dict]:
        """Build complete context for an agent invocation.

        Allocates token budget across five memory tiers:
        - 50% working memory (recent conversation)
        - 18% episodic memory (past tasks)
        - 18% semantic memory (codebase)
        - 5% patterns (learned approaches)
        - 9% codebase analysis (Phase 7.4)
        """

        max_tokens = max_tokens or self.config.max_context_tokens

        # Budget allocation (adjusted for codebase analysis)
        working_budget = int(max_tokens * 0.50)
        episodic_budget = int(max_tokens * 0.18)
        semantic_budget = int(max_tokens * 0.18)
        pattern_budget = int(max_tokens * 0.05)
        analysis_budget = int(max_tokens * 0.09)

        context_parts = []

        # 1. Codebase analysis context (Phase 7.4) - project structure understanding
        try:
            if self.codebase_analyzer:
                analysis_context = self.codebase_analyzer.get_context_for_agent(project_id)
                if analysis_context:
                    analysis_context = self._truncate_to_tokens(analysis_context, analysis_budget)
                    context_parts.append({
                        "role": "user",
                        "content": f"[Project structure]\n{analysis_context}"
                    })
                    log.debug("analysis_context_added", project_id=project_id)
        except Exception as e:
            log.warning("analysis_context_failed", error=str(e))

        # 2. Pattern suggestions (learned approaches) - Phase 7.2
        try:
            if self.learner:
                suggestions = self.learner.suggest_patterns(
                    task_description=current_task,
                    project_id=project_id,
                    limit=self.config.pattern_limit
                )
                if suggestions:
                    pattern_text = self._format_patterns(suggestions)
                    pattern_text = self._truncate_to_tokens(pattern_text, pattern_budget)
                    context_parts.append({
                        "role": "user",
                        "content": f"[Learned patterns for similar tasks]\n{pattern_text}"
                    })
                    log.debug("pattern_context_added", patterns=len(suggestions))
        except Exception as e:
            log.warning("pattern_context_failed", error=str(e))

        # 3. Semantic memory (codebase context)
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

        # 4. Episodic memory (past decisions)
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

        # 5. Working memory (recent conversation)
        working_conv = self._fit_conversation(conversation, working_budget)
        log.debug(
            "context_built",
            working_messages=len(working_conv),
            total_parts=len(context_parts) + len(working_conv)
        )

        return context_parts + working_conv

    def _format_patterns(self, suggestions: list) -> str:
        """Format pattern suggestions for context."""
        parts = []
        for pattern, suggestion_text in suggestions:
            parts.append(suggestion_text)
        return "\n\n".join(parts)

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

    # Phase 7.2: Pattern learning methods

    def learn_from_completion(
        self,
        task: "Task",
        iterations: int,
        tool_calls: List[str],
        final_output: str,
        session_turns: Optional[List[dict]] = None
    ) -> Optional[int]:
        """Learn a pattern from a successful task completion.

        Args:
            task: The completed task
            iterations: Number of iterations taken
            tool_calls: List of tool names called during execution
            final_output: The final output/result
            session_turns: Optional conversation history

        Returns:
            Pattern ID if learned, None if learning disabled or skipped
        """
        if not self.learner:
            return None

        return self.learner.learn_from_completion(
            task=task,
            iterations=iterations,
            tool_calls=tool_calls,
            final_output=final_output,
            session_turns=session_turns
        )

    def get_pattern_count(self) -> int:
        """Get the total number of learned patterns.

        Returns:
            Number of patterns stored
        """
        return self.patterns.get_pattern_count()

    def get_learning_stats(self) -> dict:
        """Get statistics about the learning system.

        Returns:
            Dict with pattern counts, contexts, agents, etc.
        """
        if not self.learner:
            return {"learning_enabled": False}

        stats = self.learner.get_stats()
        stats["learning_enabled"] = True
        return stats

    # Phase 7.4: Codebase analysis methods

    def analyze_codebase(
        self,
        project_path: str,
        project_id: Optional[str] = None,
        force: bool = False
    ) -> Optional["CodebaseAnalysis"]:
        """Analyze a codebase structure and store results.

        Args:
            project_path: Path to the project directory
            project_id: Optional project identifier
            force: Force re-analysis even if cached

        Returns:
            CodebaseAnalysis results or None if analysis disabled
        """
        if not self.codebase_analyzer:
            log.warning("codebase_analysis_disabled")
            return None

        from sindri.analysis.results import CodebaseAnalysis
        return self.codebase_analyzer.analyze_project(project_path, project_id, force)

    def get_codebase_analysis(self, project_id: str) -> Optional["CodebaseAnalysis"]:
        """Get stored codebase analysis.

        Args:
            project_id: The project identifier

        Returns:
            CodebaseAnalysis if found, None otherwise
        """
        if not self.codebase_analyzer:
            return None
        return self.codebase_analyzer.store.get(project_id)

    def get_analysis_count(self) -> int:
        """Get the number of analyzed codebases.

        Returns:
            Number of stored codebase analyses
        """
        if not self.codebase_analyzer:
            return 0
        return self.codebase_analyzer.store.get_analysis_count()
