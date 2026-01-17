"""Session comments for code review functionality.

This module provides infrastructure for adding review comments and
annotations to Sindri sessions, enabling collaborative code review.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import structlog

from sindri.persistence.database import Database

log = structlog.get_logger()


class CommentType(str, Enum):
    """Types of review comments."""

    COMMENT = "comment"  # General comment
    SUGGESTION = "suggestion"  # Code suggestion
    QUESTION = "question"  # Question for clarification
    ISSUE = "issue"  # Bug or problem found
    PRAISE = "praise"  # Positive feedback
    NOTE = "note"  # Personal note


class CommentStatus(str, Enum):
    """Status of a comment thread."""

    OPEN = "open"  # Needs attention
    RESOLVED = "resolved"  # Issue addressed
    WONTFIX = "wontfix"  # Decided not to address
    OUTDATED = "outdated"  # No longer relevant


@dataclass
class SessionComment:
    """A review comment on a session.

    Comments can be attached to:
    - The session as a whole (turn_index=None)
    - A specific turn (turn_index set)
    - A specific line within a turn (turn_index + line_number)

    Attributes:
        session_id: Session the comment belongs to
        author: Who wrote the comment
        content: Comment text (supports markdown)
        turn_index: Optional turn to attach to
        line_number: Optional line within turn content
        comment_type: Type of comment
        status: Status of the comment thread
        parent_id: Parent comment ID for replies
        id: Database ID (set after save)
        created_at: When created
        updated_at: When last modified
    """

    session_id: str
    author: str
    content: str
    turn_index: Optional[int] = None
    line_number: Optional[int] = None
    comment_type: CommentType = CommentType.COMMENT
    status: CommentStatus = CommentStatus.OPEN
    parent_id: Optional[int] = None
    id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def is_reply(self) -> bool:
        """Check if this is a reply to another comment."""
        return self.parent_id is not None

    @property
    def is_session_level(self) -> bool:
        """Check if this is a session-level comment (not attached to a turn)."""
        return self.turn_index is None

    @property
    def is_resolved(self) -> bool:
        """Check if this comment is resolved."""
        return self.status in [CommentStatus.RESOLVED, CommentStatus.WONTFIX]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "author": self.author,
            "content": self.content,
            "turn_index": self.turn_index,
            "line_number": self.line_number,
            "comment_type": self.comment_type.value,
            "status": self.status.value,
            "parent_id": self.parent_id,
            "is_reply": self.is_reply,
            "is_resolved": self.is_resolved,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class CommentStore:
    """Manages session comment persistence."""

    def __init__(self, database: Optional[Database] = None):
        """Initialize comment store.

        Args:
            database: Database instance (uses default if not provided)
        """
        self.db = database or Database()

    async def add_comment(self, comment: SessionComment) -> SessionComment:
        """Add a comment to a session.

        Args:
            comment: The comment to add

        Returns:
            The comment with ID populated
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO session_comments
                (session_id, turn_index, line_number, author, content,
                 comment_type, status, parent_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    comment.session_id,
                    comment.turn_index,
                    comment.line_number,
                    comment.author,
                    comment.content,
                    comment.comment_type.value,
                    comment.status.value,
                    comment.parent_id,
                    comment.created_at,
                    comment.updated_at,
                ),
            )
            comment.id = cursor.lastrowid
            await conn.commit()

        log.info(
            "comment_added",
            session_id=comment.session_id,
            comment_id=comment.id,
            author=comment.author,
        )
        return comment

    async def get_comment(self, comment_id: int) -> Optional[SessionComment]:
        """Get a specific comment by ID.

        Args:
            comment_id: The comment ID

        Returns:
            SessionComment if found, None otherwise
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT id, session_id, turn_index, line_number, author, content,
                       comment_type, status, parent_id, created_at, updated_at
                FROM session_comments
                WHERE id = ?
                """,
                (comment_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                return self._row_to_comment(row)

    async def get_comments_for_session(
        self,
        session_id: str,
        include_resolved: bool = True,
    ) -> list[SessionComment]:
        """Get all comments for a session.

        Args:
            session_id: Session ID to get comments for
            include_resolved: Whether to include resolved comments

        Returns:
            List of SessionComment objects
        """
        await self.db.initialize()

        query = """
            SELECT id, session_id, turn_index, line_number, author, content,
                   comment_type, status, parent_id, created_at, updated_at
            FROM session_comments
            WHERE session_id = ?
        """
        params: list[Any] = [session_id]

        if not include_resolved:
            query += " AND status NOT IN ('resolved', 'wontfix')"

        query += " ORDER BY created_at ASC"

        comments = []
        async with self.db.get_connection() as conn:
            async with conn.execute(query, params) as cursor:
                async for row in cursor:
                    comments.append(self._row_to_comment(row))

        return comments

    async def get_comments_for_turn(
        self,
        session_id: str,
        turn_index: int,
    ) -> list[SessionComment]:
        """Get all comments for a specific turn.

        Args:
            session_id: Session ID
            turn_index: Turn index to get comments for

        Returns:
            List of SessionComment objects for the turn
        """
        await self.db.initialize()

        comments = []
        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT id, session_id, turn_index, line_number, author, content,
                       comment_type, status, parent_id, created_at, updated_at
                FROM session_comments
                WHERE session_id = ? AND turn_index = ?
                ORDER BY line_number NULLS FIRST, created_at ASC
                """,
                (session_id, turn_index),
            ) as cursor:
                async for row in cursor:
                    comments.append(self._row_to_comment(row))

        return comments

    async def get_replies(self, parent_id: int) -> list[SessionComment]:
        """Get all replies to a comment.

        Args:
            parent_id: Parent comment ID

        Returns:
            List of reply comments
        """
        await self.db.initialize()

        comments = []
        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT id, session_id, turn_index, line_number, author, content,
                       comment_type, status, parent_id, created_at, updated_at
                FROM session_comments
                WHERE parent_id = ?
                ORDER BY created_at ASC
                """,
                (parent_id,),
            ) as cursor:
                async for row in cursor:
                    comments.append(self._row_to_comment(row))

        return comments

    async def update_comment(
        self,
        comment_id: int,
        content: Optional[str] = None,
        status: Optional[CommentStatus] = None,
    ) -> bool:
        """Update a comment's content or status.

        Args:
            comment_id: Comment to update
            content: New content (None to keep current)
            status: New status (None to keep current)

        Returns:
            True if updated, False if not found
        """
        if content is None and status is None:
            return False

        await self.db.initialize()

        updates = []
        params: list[Any] = []

        if content is not None:
            updates.append("content = ?")
            params.append(content)

        if status is not None:
            updates.append("status = ?")
            params.append(status.value)

        updates.append("updated_at = ?")
        params.append(datetime.now())
        params.append(comment_id)

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                f"UPDATE session_comments SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await conn.commit()

            if cursor.rowcount > 0:
                log.info("comment_updated", comment_id=comment_id)
                return True
            return False

    async def resolve_comment(self, comment_id: int) -> bool:
        """Mark a comment as resolved.

        Args:
            comment_id: Comment to resolve

        Returns:
            True if resolved, False if not found
        """
        return await self.update_comment(comment_id, status=CommentStatus.RESOLVED)

    async def delete_comment(self, comment_id: int) -> bool:
        """Delete a comment and all its replies.

        Args:
            comment_id: Comment to delete

        Returns:
            True if deleted, False if not found
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            # Delete replies first
            await conn.execute(
                "DELETE FROM session_comments WHERE parent_id = ?",
                (comment_id,),
            )

            # Delete the comment
            cursor = await conn.execute(
                "DELETE FROM session_comments WHERE id = ?",
                (comment_id,),
            )
            await conn.commit()

            if cursor.rowcount > 0:
                log.info("comment_deleted", comment_id=comment_id)
                return True
            return False

    async def get_comment_count(
        self,
        session_id: str,
        include_resolved: bool = False,
    ) -> dict[str, int]:
        """Get comment counts for a session.

        Args:
            session_id: Session ID
            include_resolved: Include resolved comments in count

        Returns:
            Dictionary with counts by type and total
        """
        await self.db.initialize()

        status_filter = ""
        if not include_resolved:
            status_filter = "AND status NOT IN ('resolved', 'wontfix')"

        counts: dict[str, int] = {"total": 0}

        async with self.db.get_connection() as conn:
            # Total count
            async with conn.execute(
                f"""
                SELECT COUNT(*) FROM session_comments
                WHERE session_id = ? {status_filter}
                """,
                (session_id,),
            ) as cursor:
                counts["total"] = (await cursor.fetchone())[0]

            # By type
            async with conn.execute(
                f"""
                SELECT comment_type, COUNT(*) FROM session_comments
                WHERE session_id = ? {status_filter}
                GROUP BY comment_type
                """,
                (session_id,),
            ) as cursor:
                async for row in cursor:
                    counts[row[0]] = row[1]

            # Unresolved count (issues specifically)
            async with conn.execute(
                """
                SELECT COUNT(*) FROM session_comments
                WHERE session_id = ? AND status = 'open' AND comment_type = 'issue'
                """,
                (session_id,),
            ) as cursor:
                counts["open_issues"] = (await cursor.fetchone())[0]

        return counts

    async def get_comment_stats(self) -> dict[str, Any]:
        """Get global comment statistics.

        Returns:
            Dictionary with comment statistics
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            # Total comments
            async with conn.execute("SELECT COUNT(*) FROM session_comments") as cursor:
                total_comments = (await cursor.fetchone())[0]

            # Sessions with comments
            async with conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM session_comments"
            ) as cursor:
                sessions_commented = (await cursor.fetchone())[0]

            # Open vs resolved
            status_counts = {}
            async with conn.execute(
                "SELECT status, COUNT(*) FROM session_comments GROUP BY status"
            ) as cursor:
                async for row in cursor:
                    status_counts[row[0]] = row[1]

            # By type
            type_counts = {}
            async with conn.execute(
                "SELECT comment_type, COUNT(*) FROM session_comments GROUP BY comment_type"
            ) as cursor:
                async for row in cursor:
                    type_counts[row[0]] = row[1]

            # Unique authors
            async with conn.execute(
                "SELECT COUNT(DISTINCT author) FROM session_comments"
            ) as cursor:
                unique_authors = (await cursor.fetchone())[0]

        return {
            "total_comments": total_comments,
            "sessions_commented": sessions_commented,
            "unique_authors": unique_authors,
            "status_breakdown": status_counts,
            "type_breakdown": type_counts,
        }

    def _row_to_comment(self, row: tuple) -> SessionComment:
        """Convert a database row to a SessionComment."""
        return SessionComment(
            id=row[0],
            session_id=row[1],
            turn_index=row[2],
            line_number=row[3],
            author=row[4],
            content=row[5],
            comment_type=CommentType(row[6]),
            status=CommentStatus(row[7]),
            parent_id=row[8],
            created_at=datetime.fromisoformat(row[9]) if row[9] else datetime.now(),
            updated_at=datetime.fromisoformat(row[10]) if row[10] else datetime.now(),
        )
