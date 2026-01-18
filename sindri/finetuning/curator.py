"""Data curation for fine-tuning training data.

This module provides functionality for:
- Filtering sessions by quality criteria
- Deduplicating similar conversations
- Balancing training data by task types
- Computing quality scores for prioritization
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import structlog

from sindri.persistence.database import Database
from sindri.persistence.state import SessionState, Session
from sindri.persistence.feedback import FeedbackStore, QualityTag

log = structlog.get_logger()


class TaskCategory(str, Enum):
    """Categories for classifying tasks."""

    CODE_GENERATION = "code_generation"
    BUG_FIX = "bug_fix"
    REFACTORING = "refactoring"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    EXPLANATION = "explanation"
    DEBUGGING = "debugging"
    REVIEW = "review"
    OTHER = "other"


@dataclass
class CurationConfig:
    """Configuration for data curation.

    Attributes:
        min_rating: Minimum feedback rating to include (1-5)
        min_turns: Minimum number of turns in a session
        max_turns: Maximum number of turns (longer may be lower quality)
        exclude_errors: Exclude sessions that ended in errors
        exclude_hallucinated: Exclude sessions tagged as hallucinated
        deduplicate: Enable deduplication of similar conversations
        similarity_threshold: Threshold for considering sessions similar (0-1)
        balance_categories: Balance training data across task categories
        max_per_category: Maximum sessions per category when balancing
    """

    min_rating: int = 4
    min_turns: int = 2
    max_turns: int = 100
    exclude_errors: bool = True
    exclude_hallucinated: bool = True
    deduplicate: bool = True
    similarity_threshold: float = 0.85
    balance_categories: bool = False
    max_per_category: int = 100


@dataclass
class CuratedSession:
    """A curated session ready for training.

    Attributes:
        session_id: The original session ID
        task: The task description
        model: The model used
        turns: Number of turns
        rating: Average feedback rating
        quality_score: Computed quality score (0-1)
        category: Classified task category
        content_hash: Hash for deduplication
        quality_tags: Quality tags from feedback
    """

    session_id: str
    task: str
    model: str
    turns: int
    rating: float
    quality_score: float
    category: TaskCategory
    content_hash: str
    quality_tags: list[str] = field(default_factory=list)


@dataclass
class CuratedDataset:
    """A curated dataset ready for training export.

    Attributes:
        sessions: List of curated sessions
        total_turns: Total number of turns across all sessions
        category_distribution: Count of sessions per category
        avg_quality_score: Average quality score
        created_at: When the dataset was curated
        config: The curation config used
    """

    sessions: list[CuratedSession]
    total_turns: int
    category_distribution: dict[str, int]
    avg_quality_score: float
    created_at: datetime = field(default_factory=datetime.now)
    config: Optional[CurationConfig] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_count": len(self.sessions),
            "total_turns": self.total_turns,
            "category_distribution": self.category_distribution,
            "avg_quality_score": round(self.avg_quality_score, 3),
            "created_at": self.created_at.isoformat(),
            "session_ids": [s.session_id for s in self.sessions],
        }


class DataCurator:
    """Curates session data for fine-tuning.

    The curator filters, deduplicates, and balances training data
    to produce high-quality datasets for model fine-tuning.
    """

    # Patterns for classifying tasks - ordered from most specific to least specific
    # More specific categories should match first
    CATEGORY_PATTERNS = {
        TaskCategory.TESTING: [
            r"\btest\b|\btests\b|pytest|unittest|spec\b|coverage",
            r"write\s+tests|add\s+tests|test\s+file|unit\s+test",
        ],
        TaskCategory.DEBUGGING: [
            r"\bdebug\b|trace\b|investigate|figure\s+out|find.*cause",
            r"why\s+is|what'?s\s+causing|troubleshoot",
        ],
        TaskCategory.DOCUMENTATION: [
            r"\bdocument\b|readme|docstring|add\s+docs",
            r"write\s+documentation|update\s+docs",
        ],
        TaskCategory.EXPLANATION: [
            r"\bexplain\b|how\s+does|what\s+is|describe\b",
            r"help\s+me\s+understand|walk\s+through",
        ],
        TaskCategory.BUG_FIX: [
            r"\bfix\b|\bbug\b|\berror\b|broken|not\s+working|crash",
            r"doesn'?t\s+work|failing|\bproblem\b",
        ],
        TaskCategory.REFACTORING: [
            r"\brefactor\b|clean\s+up|\boptimize\b|restructure",
            r"\brename\b|\bextract\b|simplify|reorganize",
        ],
        TaskCategory.REVIEW: [
            r"\breview\b|\baudit\b|\binspect\b",
            r"look\s+at|evaluate|assess",
        ],
        TaskCategory.CODE_GENERATION: [
            r"\bcreate\b|\bwrite\b|\bimplement\b|\bbuild\b|\bgenerate\b",
            r"add\s+.*function|make\s+.*class|new\s+feature",
        ],
    }

    def __init__(
        self,
        database: Optional[Database] = None,
        session_state: Optional[SessionState] = None,
        feedback_store: Optional[FeedbackStore] = None,
    ):
        """Initialize the data curator.

        Args:
            database: Database instance (uses default if not provided)
            session_state: SessionState for loading sessions
            feedback_store: FeedbackStore for feedback queries
        """
        self.db = database or Database()
        self.session_state = session_state or SessionState(self.db)
        self.feedback_store = feedback_store or FeedbackStore(self.db)

    async def curate(
        self,
        config: Optional[CurationConfig] = None,
        session_ids: Optional[list[str]] = None,
    ) -> CuratedDataset:
        """Curate sessions into a training dataset.

        Args:
            config: Curation configuration (uses defaults if not provided)
            session_ids: Specific session IDs to consider (None = all rated)

        Returns:
            CuratedDataset ready for export
        """
        config = config or CurationConfig()

        # Get candidate sessions
        if session_ids is None:
            session_ids = await self.feedback_store.get_training_candidates(
                min_rating=config.min_rating,
                limit=10000,  # Large limit, we'll filter further
            )

        log.info("curating_sessions", candidate_count=len(session_ids))

        # Filter and score sessions
        curated_sessions = []
        for session_id in session_ids:
            session = await self.session_state.load_session(session_id)
            if not session:
                continue

            # Get feedback for the session
            feedback_list = await self.feedback_store.get_feedback(session_id)
            if not feedback_list:
                continue

            # Apply filters
            if not self._passes_filters(session, feedback_list, config):
                continue

            # Compute quality score and category
            quality_score = self._compute_quality_score(session, feedback_list)
            category = self._classify_task(session.task)
            content_hash = self._compute_content_hash(session)
            avg_rating = sum(f.rating for f in feedback_list) / len(feedback_list)
            all_tags = []
            for f in feedback_list:
                all_tags.extend(f.quality_tags)

            curated = CuratedSession(
                session_id=session_id,
                task=session.task,
                model=session.model,
                turns=len(session.turns),
                rating=avg_rating,
                quality_score=quality_score,
                category=category,
                content_hash=content_hash,
                quality_tags=list(set(all_tags)),
            )
            curated_sessions.append(curated)

        # Deduplicate if enabled
        if config.deduplicate:
            curated_sessions = self._deduplicate(
                curated_sessions, config.similarity_threshold
            )

        # Balance categories if enabled
        if config.balance_categories:
            curated_sessions = self._balance_categories(
                curated_sessions, config.max_per_category
            )

        # Sort by quality score (highest first)
        curated_sessions.sort(key=lambda s: s.quality_score, reverse=True)

        # Compute dataset statistics
        total_turns = sum(s.turns for s in curated_sessions)
        category_dist = {}
        for s in curated_sessions:
            category_dist[s.category.value] = category_dist.get(s.category.value, 0) + 1

        avg_quality = (
            sum(s.quality_score for s in curated_sessions) / len(curated_sessions)
            if curated_sessions
            else 0
        )

        dataset = CuratedDataset(
            sessions=curated_sessions,
            total_turns=total_turns,
            category_distribution=category_dist,
            avg_quality_score=avg_quality,
            config=config,
        )

        log.info(
            "curation_complete",
            sessions=len(curated_sessions),
            total_turns=total_turns,
            avg_quality=round(avg_quality, 3),
        )

        return dataset

    def _passes_filters(
        self,
        session: Session,
        feedback_list: list,
        config: CurationConfig,
    ) -> bool:
        """Check if a session passes all configured filters."""
        # Check turn count
        turn_count = len(session.turns) if session.turns else 0
        if turn_count < config.min_turns or turn_count > config.max_turns:
            return False

        # Check for error status
        if config.exclude_errors and session.status == "failed":
            return False

        # Check for hallucination tag
        if config.exclude_hallucinated:
            for feedback in feedback_list:
                if QualityTag.HALLUCINATED.value in feedback.quality_tags:
                    return False

        # Check minimum rating
        avg_rating = sum(f.rating for f in feedback_list) / len(feedback_list)
        if avg_rating < config.min_rating:
            return False

        return True

    def _compute_quality_score(
        self,
        session: Session,
        feedback_list: list,
    ) -> float:
        """Compute a quality score (0-1) for a session.

        The score is based on:
        - Average rating (40%)
        - Positive tag count vs negative (30%)
        - Session completion status (15%)
        - Turn count efficiency (15%)
        """
        # Rating component (0-1)
        avg_rating = sum(f.rating for f in feedback_list) / len(feedback_list)
        rating_score = (avg_rating - 1) / 4  # Normalize 1-5 to 0-1

        # Tag component (0-1)
        positive_tags = {
            QualityTag.CORRECT.value,
            QualityTag.EFFICIENT.value,
            QualityTag.WELL_EXPLAINED.value,
            QualityTag.FOLLOWED_INSTRUCTIONS.value,
            QualityTag.GOOD_TOOL_USE.value,
            QualityTag.CREATIVE.value,
        }
        negative_tags = {
            QualityTag.INCORRECT.value,
            QualityTag.INEFFICIENT.value,
            QualityTag.POOR_EXPLANATION.value,
            QualityTag.IGNORED_INSTRUCTIONS.value,
            QualityTag.WRONG_TOOL.value,
            QualityTag.VERBOSE.value,
            QualityTag.HALLUCINATED.value,
        }

        pos_count = 0
        neg_count = 0
        for feedback in feedback_list:
            for tag in feedback.quality_tags:
                if tag in positive_tags:
                    pos_count += 1
                elif tag in negative_tags:
                    neg_count += 1

        total_tags = pos_count + neg_count
        tag_score = pos_count / total_tags if total_tags > 0 else 0.5

        # Completion component (0-1)
        completion_score = 1.0 if session.status == "completed" else 0.5

        # Efficiency component (0-1) - penalize very long sessions
        turn_count = len(session.turns) if session.turns else 0
        # Ideal range is 3-15 turns
        if turn_count < 3:
            efficiency_score = 0.5
        elif turn_count <= 15:
            efficiency_score = 1.0
        elif turn_count <= 30:
            efficiency_score = 0.8
        elif turn_count <= 50:
            efficiency_score = 0.6
        else:
            efficiency_score = 0.4

        # Weighted combination
        score = (
            rating_score * 0.4
            + tag_score * 0.3
            + completion_score * 0.15
            + efficiency_score * 0.15
        )

        return min(1.0, max(0.0, score))

    def _classify_task(self, task: str) -> TaskCategory:
        """Classify a task into a category based on patterns."""
        task_lower = task.lower()

        for category, patterns in self.CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, task_lower):
                    return category

        return TaskCategory.OTHER

    def _compute_content_hash(self, session: Session) -> str:
        """Compute a hash of session content for deduplication.

        Uses the task description and first few assistant responses
        to identify similar sessions.
        """
        # Combine task and early assistant turns
        content_parts = [session.task]

        if session.turns:
            for turn in session.turns[:5]:  # First 5 turns
                if turn.role == "assistant" and turn.content:
                    # Take first 200 chars of each response
                    content_parts.append(turn.content[:200])

        content = "|".join(content_parts)
        return hashlib.md5(content.encode()).hexdigest()

    def _deduplicate(
        self,
        sessions: list[CuratedSession],
        threshold: float,
    ) -> list[CuratedSession]:
        """Remove duplicate or very similar sessions.

        For sessions with the same hash, keep the one with highest quality score.
        """
        # Group by content hash
        hash_groups: dict[str, list[CuratedSession]] = {}
        for session in sessions:
            if session.content_hash not in hash_groups:
                hash_groups[session.content_hash] = []
            hash_groups[session.content_hash].append(session)

        # Keep best from each group
        deduplicated = []
        duplicates_removed = 0
        for group in hash_groups.values():
            # Sort by quality score descending
            group.sort(key=lambda s: s.quality_score, reverse=True)
            deduplicated.append(group[0])
            duplicates_removed += len(group) - 1

        if duplicates_removed > 0:
            log.info("deduplication_complete", removed=duplicates_removed)

        return deduplicated

    def _balance_categories(
        self,
        sessions: list[CuratedSession],
        max_per_category: int,
    ) -> list[CuratedSession]:
        """Balance sessions across categories.

        Limits the number of sessions per category to avoid
        over-representation of common task types.
        """
        category_counts: dict[TaskCategory, int] = {}
        balanced = []

        # Sort by quality score first so we keep the best
        sessions.sort(key=lambda s: s.quality_score, reverse=True)

        for session in sessions:
            count = category_counts.get(session.category, 0)
            if count < max_per_category:
                balanced.append(session)
                category_counts[session.category] = count + 1

        log.info(
            "balancing_complete",
            original=len(sessions),
            balanced=len(balanced),
            categories=dict(category_counts),
        )

        return balanced

    async def get_curation_stats(self) -> dict[str, Any]:
        """Get statistics about available data for curation.

        Returns:
            Dictionary with curation statistics
        """
        await self.db.initialize()

        # Get all sessions with feedback
        rated_sessions = await self.feedback_store.list_rated_sessions(
            min_rating=1,
            max_rating=5,
            limit=10000,
        )

        # Classify tasks
        category_counts: dict[str, int] = {}
        rating_dist: dict[int, int] = {}

        for session in rated_sessions:
            category = self._classify_task(session.get("task", ""))
            category_counts[category.value] = category_counts.get(category.value, 0) + 1

            rating = int(session.get("avg_rating", 3))
            rating_dist[rating] = rating_dist.get(rating, 0) + 1

        # Training candidates (4+ stars)
        candidates = await self.feedback_store.get_training_candidates(
            min_rating=4, limit=10000
        )

        return {
            "total_rated_sessions": len(rated_sessions),
            "training_candidates": len(candidates),
            "category_distribution": category_counts,
            "rating_distribution": rating_dist,
        }
