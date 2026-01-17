"""Session feedback collection for Sindri fine-tuning.

This module provides infrastructure for collecting user feedback on session
quality, which can be used for:
- Tracking session quality over time
- Identifying successful interaction patterns
- Exporting training data for model fine-tuning
- Improving agent prompts based on feedback
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import structlog

from sindri.persistence.database import Database

log = structlog.get_logger()


class QualityTag(str, Enum):
    """Quality tags for categorizing feedback."""

    # Positive tags
    CORRECT = "correct"  # Answer/code was correct
    EFFICIENT = "efficient"  # Solution was efficient
    WELL_EXPLAINED = "well_explained"  # Good explanations
    FOLLOWED_INSTRUCTIONS = "followed_instructions"  # Followed user instructions
    GOOD_TOOL_USE = "good_tool_use"  # Appropriate tool selection
    CREATIVE = "creative"  # Creative/novel solution

    # Negative tags
    INCORRECT = "incorrect"  # Answer/code was wrong
    INEFFICIENT = "inefficient"  # Solution was suboptimal
    POOR_EXPLANATION = "poor_explanation"  # Unclear explanations
    IGNORED_INSTRUCTIONS = "ignored_instructions"  # Didn't follow instructions
    WRONG_TOOL = "wrong_tool"  # Used wrong tool
    VERBOSE = "verbose"  # Too much unnecessary output
    HALLUCINATED = "hallucinated"  # Made up information

    # Neutral tags
    PARTIAL = "partial"  # Partially correct
    NEEDED_GUIDANCE = "needed_guidance"  # Required user correction


@dataclass
class SessionFeedback:
    """Feedback on a session or specific turn within a session.

    Attributes:
        session_id: The session this feedback applies to
        rating: Quality rating from 1 (poor) to 5 (excellent)
        turn_index: Optional specific turn index (None = whole session)
        quality_tags: List of quality tags describing the interaction
        notes: Optional free-form notes
        include_in_training: Whether to include in training data export
        id: Database ID (set after save)
        created_at: When feedback was created
    """

    session_id: str
    rating: int  # 1-5 scale
    turn_index: Optional[int] = None
    quality_tags: list[str] = field(default_factory=list)
    notes: Optional[str] = None
    include_in_training: bool = True
    id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Validate rating is in valid range."""
        if not 1 <= self.rating <= 5:
            raise ValueError(f"Rating must be between 1 and 5, got {self.rating}")

    @property
    def is_positive(self) -> bool:
        """Return True if this is positive feedback (4-5 stars)."""
        return self.rating >= 4

    @property
    def is_negative(self) -> bool:
        """Return True if this is negative feedback (1-2 stars)."""
        return self.rating <= 2

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "rating": self.rating,
            "turn_index": self.turn_index,
            "quality_tags": self.quality_tags,
            "notes": self.notes,
            "include_in_training": self.include_in_training,
            "created_at": self.created_at.isoformat(),
        }


class FeedbackStore:
    """Manages session feedback persistence."""

    def __init__(self, database: Optional[Database] = None):
        """Initialize feedback store.

        Args:
            database: Database instance (uses default if not provided)
        """
        self.db = database or Database()

    async def add_feedback(self, feedback: SessionFeedback) -> SessionFeedback:
        """Add feedback for a session.

        Args:
            feedback: The feedback to store

        Returns:
            The feedback with ID populated
        """
        await self.db.initialize()

        quality_tags_json = json.dumps(feedback.quality_tags) if feedback.quality_tags else None

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO session_feedback
                (session_id, turn_index, rating, quality_tags, notes, include_in_training, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback.session_id,
                    feedback.turn_index,
                    feedback.rating,
                    quality_tags_json,
                    feedback.notes,
                    1 if feedback.include_in_training else 0,
                    feedback.created_at,
                ),
            )
            feedback.id = cursor.lastrowid
            await conn.commit()

        log.info(
            "feedback_added",
            session_id=feedback.session_id,
            rating=feedback.rating,
            feedback_id=feedback.id,
        )
        return feedback

    async def get_feedback(self, session_id: str) -> list[SessionFeedback]:
        """Get all feedback for a session.

        Args:
            session_id: The session ID to get feedback for

        Returns:
            List of feedback entries for the session
        """
        await self.db.initialize()

        feedback_list = []
        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT id, session_id, turn_index, rating, quality_tags, notes,
                       include_in_training, created_at
                FROM session_feedback
                WHERE session_id = ?
                ORDER BY created_at
                """,
                (session_id,),
            ) as cursor:
                async for row in cursor:
                    quality_tags = json.loads(row[4]) if row[4] else []
                    feedback = SessionFeedback(
                        id=row[0],
                        session_id=row[1],
                        turn_index=row[2],
                        rating=row[3],
                        quality_tags=quality_tags,
                        notes=row[5],
                        include_in_training=bool(row[6]),
                        created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(),
                    )
                    feedback_list.append(feedback)

        return feedback_list

    async def get_feedback_by_id(self, feedback_id: int) -> Optional[SessionFeedback]:
        """Get a specific feedback entry by ID.

        Args:
            feedback_id: The feedback ID

        Returns:
            The feedback entry or None if not found
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT id, session_id, turn_index, rating, quality_tags, notes,
                       include_in_training, created_at
                FROM session_feedback
                WHERE id = ?
                """,
                (feedback_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                quality_tags = json.loads(row[4]) if row[4] else []
                return SessionFeedback(
                    id=row[0],
                    session_id=row[1],
                    turn_index=row[2],
                    rating=row[3],
                    quality_tags=quality_tags,
                    notes=row[5],
                    include_in_training=bool(row[6]),
                    created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(),
                )

    async def update_feedback(self, feedback: SessionFeedback) -> bool:
        """Update an existing feedback entry.

        Args:
            feedback: The feedback to update (must have ID set)

        Returns:
            True if updated, False if not found
        """
        if feedback.id is None:
            raise ValueError("Feedback must have an ID to update")

        await self.db.initialize()

        quality_tags_json = json.dumps(feedback.quality_tags) if feedback.quality_tags else None

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE session_feedback
                SET rating = ?, quality_tags = ?, notes = ?, include_in_training = ?
                WHERE id = ?
                """,
                (
                    feedback.rating,
                    quality_tags_json,
                    feedback.notes,
                    1 if feedback.include_in_training else 0,
                    feedback.id,
                ),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_feedback(self, feedback_id: int) -> bool:
        """Delete a feedback entry.

        Args:
            feedback_id: The feedback ID to delete

        Returns:
            True if deleted, False if not found
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM session_feedback WHERE id = ?",
                (feedback_id,),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def list_rated_sessions(
        self,
        min_rating: int = 1,
        max_rating: int = 5,
        include_in_training_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List sessions that have feedback.

        Args:
            min_rating: Minimum rating filter
            max_rating: Maximum rating filter
            include_in_training_only: Only include sessions marked for training
            limit: Maximum number of results

        Returns:
            List of session info with feedback summary
        """
        await self.db.initialize()

        query = """
            SELECT
                s.id, s.task, s.model, s.status, s.created_at, s.iterations,
                AVG(f.rating) as avg_rating,
                COUNT(f.id) as feedback_count,
                GROUP_CONCAT(DISTINCT f.quality_tags) as all_tags
            FROM sessions s
            INNER JOIN session_feedback f ON s.id = f.session_id
            WHERE f.rating >= ? AND f.rating <= ?
        """
        params: list[Any] = [min_rating, max_rating]

        if include_in_training_only:
            query += " AND f.include_in_training = 1"

        query += """
            GROUP BY s.id
            ORDER BY avg_rating DESC, s.created_at DESC
            LIMIT ?
        """
        params.append(limit)

        sessions = []
        async with self.db.get_connection() as conn:
            async with conn.execute(query, params) as cursor:
                async for row in cursor:
                    # Parse all quality tags from concatenated JSON arrays
                    all_tags = set()
                    if row[8]:
                        for tag_json in row[8].split(","):
                            try:
                                tags = json.loads(tag_json)
                                all_tags.update(tags)
                            except json.JSONDecodeError:
                                pass

                    sessions.append(
                        {
                            "id": row[0],
                            "task": row[1],
                            "model": row[2],
                            "status": row[3],
                            "created_at": row[4],
                            "iterations": row[5],
                            "avg_rating": round(row[6], 2) if row[6] else None,
                            "feedback_count": row[7],
                            "quality_tags": list(all_tags),
                        }
                    )

        return sessions

    async def get_training_candidates(
        self,
        min_rating: int = 4,
        limit: int = 1000,
    ) -> list[str]:
        """Get session IDs that are good candidates for training.

        Args:
            min_rating: Minimum average rating (default 4 = "good")
            limit: Maximum number of session IDs to return

        Returns:
            List of session IDs suitable for training data export
        """
        await self.db.initialize()

        session_ids = []
        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT DISTINCT f.session_id
                FROM session_feedback f
                WHERE f.rating >= ? AND f.include_in_training = 1
                GROUP BY f.session_id
                HAVING AVG(f.rating) >= ?
                ORDER BY AVG(f.rating) DESC
                LIMIT ?
                """,
                (min_rating, min_rating, limit),
            ) as cursor:
                async for row in cursor:
                    session_ids.append(row[0])

        return session_ids

    async def get_feedback_stats(self) -> dict[str, Any]:
        """Get aggregate statistics about feedback.

        Returns:
            Dictionary with feedback statistics
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            # Total feedback count
            async with conn.execute("SELECT COUNT(*) FROM session_feedback") as cursor:
                total_feedback = (await cursor.fetchone())[0]

            # Sessions with feedback
            async with conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM session_feedback"
            ) as cursor:
                sessions_with_feedback = (await cursor.fetchone())[0]

            # Rating distribution
            rating_dist = {}
            async with conn.execute(
                "SELECT rating, COUNT(*) FROM session_feedback GROUP BY rating ORDER BY rating"
            ) as cursor:
                async for row in cursor:
                    rating_dist[row[0]] = row[1]

            # Average rating
            async with conn.execute("SELECT AVG(rating) FROM session_feedback") as cursor:
                avg_rating = (await cursor.fetchone())[0]

            # Training candidates (4+ rating, marked for training)
            async with conn.execute(
                """
                SELECT COUNT(DISTINCT session_id)
                FROM session_feedback
                WHERE rating >= 4 AND include_in_training = 1
                """
            ) as cursor:
                training_candidates = (await cursor.fetchone())[0]

            # Most common quality tags
            tag_counts: dict[str, int] = {}
            async with conn.execute(
                "SELECT quality_tags FROM session_feedback WHERE quality_tags IS NOT NULL"
            ) as cursor:
                async for row in cursor:
                    try:
                        tags = json.loads(row[0])
                        for tag in tags:
                            tag_counts[tag] = tag_counts.get(tag, 0) + 1
                    except json.JSONDecodeError:
                        pass

            # Sort by count, take top 10
            top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_feedback": total_feedback,
            "sessions_with_feedback": sessions_with_feedback,
            "rating_distribution": rating_dist,
            "average_rating": round(avg_rating, 2) if avg_rating else None,
            "training_candidates": training_candidates,
            "top_quality_tags": dict(top_tags),
        }
