"""Pattern learner - extracts patterns from successful task completions."""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
import structlog

from sindri.memory.patterns import Pattern, PatternStore
from sindri.core.tasks import Task, TaskStatus

log = structlog.get_logger()


@dataclass
class LearningConfig:
    """Configuration for pattern learning."""

    # Only learn from tasks that complete in fewer iterations than max
    efficiency_threshold: int = 10

    # Minimum iterations to consider learning (avoid trivial patterns)
    min_iterations: int = 2

    # Extract keywords from task description
    max_keywords: int = 10

    # Tool sequence length limit
    max_tool_sequence: int = 20


class PatternLearner:
    """Learns patterns from successful task completions.

    Extracts:
    - Task context and trigger keywords
    - Tool usage sequences
    - Successful approaches
    - Efficiency metrics
    """

    def __init__(self, store: PatternStore, config: LearningConfig = None):
        self.store = store
        self.config = config or LearningConfig()
        log.info("pattern_learner_initialized")

    def learn_from_completion(
        self,
        task: Task,
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
            Pattern ID if learned, None if skipped
        """
        # Skip if task wasn't successful
        if task.status != TaskStatus.COMPLETE:
            log.debug("skip_learning_not_complete", task_id=task.id)
            return None

        # Skip if too many iterations (inefficient pattern)
        if iterations > self.config.efficiency_threshold:
            log.debug("skip_learning_inefficient",
                     task_id=task.id,
                     iterations=iterations)
            return None

        # Skip trivial completions (too few iterations)
        if iterations < self.config.min_iterations:
            log.debug("skip_learning_trivial",
                     task_id=task.id,
                     iterations=iterations)
            return None

        # Extract pattern components
        context = self._infer_context(task.description, task.task_type)
        keywords = self._extract_keywords(task.description)
        approach = self._extract_approach(session_turns, final_output)
        tool_sequence = self._extract_tool_sequence(tool_calls)

        # Generate pattern name
        name = self._generate_pattern_name(context, keywords)

        # Create pattern
        pattern = Pattern(
            name=name,
            description=f"Learned from task: {task.description[:100]}",
            context=context,
            trigger_keywords=keywords,
            approach=approach,
            tool_sequence=tool_sequence,
            example_task=task.description,
            example_output=final_output[:500] if final_output else "",
            agent=task.assigned_agent,
            project_id=task.context.get("project_id", ""),
            success_count=1,
            avg_iterations=float(iterations),
            min_iterations=iterations,
        )

        # Store pattern
        pattern_id = self.store.store(pattern)

        log.info("pattern_learned",
                pattern_id=pattern_id,
                name=name,
                context=context,
                iterations=iterations,
                tools=len(tool_sequence))

        return pattern_id

    def _infer_context(self, description: str, task_type: str) -> str:
        """Infer the task context from description and type.

        Returns context categories like:
        - code_generation
        - file_editing
        - testing
        - refactoring
        - review
        - shell_execution
        - orchestration
        """
        desc_lower = description.lower()

        # Check for specific patterns in description
        if any(w in desc_lower for w in ["test", "pytest", "unittest", "spec"]):
            return "testing"
        if any(w in desc_lower for w in ["refactor", "rename", "extract", "restructure"]):
            return "refactoring"
        if any(w in desc_lower for w in ["review", "check", "analyze", "audit"]):
            return "review"
        if any(w in desc_lower for w in ["create", "write", "implement", "add"]):
            if any(w in desc_lower for w in ["test", "spec"]):
                return "testing"
            return "code_generation"
        if any(w in desc_lower for w in ["edit", "modify", "update", "fix", "change"]):
            return "file_editing"
        if any(w in desc_lower for w in ["run", "execute", "shell", "command"]):
            return "shell_execution"
        if any(w in desc_lower for w in ["plan", "delegate", "orchestrate", "coordinate"]):
            return "orchestration"
        if any(w in desc_lower for w in ["sql", "query", "database", "schema"]):
            return "database"

        # Fallback to task_type
        return task_type or "general"

    def _extract_keywords(self, description: str) -> List[str]:
        """Extract meaningful keywords from task description."""
        # Normalize
        text = description.lower()

        # Remove common stop words
        stop_words = {
            "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "must", "shall", "can", "need",
            "that", "this", "these", "those", "it", "its", "i", "me", "my", "we",
            "our", "you", "your", "they", "them", "their", "he", "she", "him",
            "her", "what", "which", "who", "whom", "where", "when", "why", "how",
            "all", "each", "every", "both", "few", "more", "most", "other",
            "some", "such", "no", "not", "only", "same", "so", "than", "too",
            "very", "just", "also", "now", "here", "there", "if", "then", "else",
            "as", "because", "while", "although", "though", "even", "about"
        }

        # Extract words
        words = re.findall(r'[a-z_][a-z0-9_]*', text)

        # Filter and deduplicate
        keywords = []
        seen = set()
        for word in words:
            if word not in stop_words and len(word) > 2 and word not in seen:
                keywords.append(word)
                seen.add(word)
                if len(keywords) >= self.config.max_keywords:
                    break

        return keywords

    def _extract_approach(
        self,
        session_turns: Optional[List[dict]],
        final_output: str
    ) -> str:
        """Extract the approach/strategy from session history.

        Summarizes what the agent did to complete the task.
        """
        if not session_turns:
            return final_output[:200] if final_output else ""

        # Get assistant turns (agent's reasoning)
        assistant_turns = [
            t["content"] for t in session_turns
            if t.get("role") == "assistant" and t.get("content")
        ]

        if not assistant_turns:
            return final_output[:200] if final_output else ""

        # Take first assistant message (usually contains approach)
        first_response = assistant_turns[0][:500]

        # Clean up any tool call markers
        approach = re.sub(r'```[^`]*```', '[code]', first_response)
        approach = re.sub(r'\{[^}]*\}', '[json]', approach)

        return approach[:300]

    def _extract_tool_sequence(self, tool_calls: List[str]) -> List[str]:
        """Extract unique tool sequence, preserving order but removing duplicates."""
        seen = set()
        sequence = []

        for tool in tool_calls:
            if tool not in seen:
                sequence.append(tool)
                seen.add(tool)
                if len(sequence) >= self.config.max_tool_sequence:
                    break

        return sequence

    def _generate_pattern_name(self, context: str, keywords: List[str]) -> str:
        """Generate a descriptive pattern name."""
        if not keywords:
            return f"{context}_pattern"

        # Use first 2-3 keywords
        key_parts = keywords[:3]
        name_parts = [context] + key_parts

        return "_".join(name_parts)

    def suggest_patterns(
        self,
        task_description: str,
        project_id: Optional[str] = None,
        limit: int = 3
    ) -> List[Tuple[Pattern, str]]:
        """Suggest relevant patterns for a new task.

        Returns list of (pattern, suggestion_text) tuples.
        """
        context = self._infer_context(task_description, "general")

        patterns = self.store.find_relevant(
            task_description=task_description,
            context=context,
            project_id=project_id,
            limit=limit
        )

        suggestions = []
        for pattern in patterns:
            suggestion = self._format_suggestion(pattern)
            suggestions.append((pattern, suggestion))

        return suggestions

    def _format_suggestion(self, pattern: Pattern) -> str:
        """Format a pattern as a suggestion for agent context."""
        parts = [f"Similar tasks succeeded using: {pattern.name}"]

        if pattern.approach:
            parts.append(f"Approach: {pattern.approach[:200]}")

        if pattern.tool_sequence:
            tools = ", ".join(pattern.tool_sequence[:5])
            parts.append(f"Tools used: {tools}")

        if pattern.success_count > 1:
            parts.append(f"(Used successfully {pattern.success_count} times, "
                        f"avg {pattern.avg_iterations:.1f} iterations)")

        return "\n".join(parts)

    def get_stats(self) -> dict:
        """Get learning system statistics."""
        all_patterns = self.store.get_all(limit=1000)

        if not all_patterns:
            return {
                "total_patterns": 0,
                "total_successes": 0,
                "contexts": {},
                "agents": {},
            }

        contexts = {}
        agents = {}
        total_successes = 0

        for pattern in all_patterns:
            total_successes += pattern.success_count

            if pattern.context:
                contexts[pattern.context] = contexts.get(pattern.context, 0) + 1

            if pattern.agent:
                agents[pattern.agent] = agents.get(pattern.agent, 0) + 1

        return {
            "total_patterns": len(all_patterns),
            "total_successes": total_successes,
            "contexts": contexts,
            "agents": agents,
            "avg_success_per_pattern": total_successes / len(all_patterns) if all_patterns else 0,
        }
