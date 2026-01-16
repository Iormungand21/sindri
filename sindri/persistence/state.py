"""Session state management for Sindri."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
import structlog

from sindri.persistence.database import Database

log = structlog.get_logger()


def serialize_tool_calls(tool_calls):
    """Convert tool calls to JSON-serializable format."""
    if not tool_calls:
        return None

    serialized = []
    for call in tool_calls:
        # Handle ollama native ToolCall objects
        if hasattr(call, 'function'):
            serialized.append({
                'function': {
                    'name': call.function.name,
                    'arguments': call.function.arguments
                }
            })
        # Handle dict format
        elif isinstance(call, dict):
            serialized.append(call)
        else:
            # Fallback: try to convert to dict
            serialized.append(str(call))

    return json.dumps(serialized)


@dataclass
class Turn:
    """A single conversational turn."""

    role: str
    content: str
    tool_calls: Optional[list] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Session:
    """A Sindri task session."""

    id: str
    task: str
    model: str
    status: str
    turns: list[Turn] = field(default_factory=list)
    iterations: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    def add_turn(self, role: str, content: str, tool_calls: Optional[list] = None):
        """Add a turn to the session."""
        turn = Turn(role=role, content=content, tool_calls=tool_calls)
        self.turns.append(turn)


class SessionState:
    """Manages session persistence."""

    def __init__(self, database: Optional[Database] = None):
        self.db = database or Database()

    async def create_session(self, task: str, model: str = "qwen2.5-coder:14b") -> Session:
        """Create a new session."""

        await self.db.initialize()

        session_id = str(uuid.uuid4())
        session = Session(
            id=session_id,
            task=task,
            model=model,
            status="active"
        )

        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO sessions (id, task, model, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session.id, session.task, session.model, session.status, session.created_at)
            )
            await conn.commit()

        log.info("session_created", session_id=session_id, task=task)
        return session

    async def save_session(self, session: Session):
        """Save session state to database."""

        async with self.db.get_connection() as conn:
            # Update session
            await conn.execute(
                """
                UPDATE sessions
                SET status = ?, iterations = ?, completed_at = ?
                WHERE id = ?
                """,
                (session.status, session.iterations, session.completed_at, session.id)
            )

            # Save new turns (simple approach: delete and re-insert all)
            await conn.execute("DELETE FROM turns WHERE session_id = ?", (session.id,))

            for turn in session.turns:
                tool_calls_json = serialize_tool_calls(turn.tool_calls)
                await conn.execute(
                    """
                    INSERT INTO turns (session_id, role, content, tool_calls, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session.id, turn.role, turn.content, tool_calls_json, turn.created_at)
                )

            await conn.commit()

        log.info("session_saved", session_id=session.id, turns=len(session.turns))

    async def load_session(self, session_id: str) -> Optional[Session]:
        """Load a session from database."""

        async with self.db.get_connection() as conn:
            # Load session
            async with conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                session = Session(
                    id=row[0],
                    task=row[1],
                    model=row[2],
                    status=row[3],
                    created_at=datetime.fromisoformat(row[4]),
                    completed_at=datetime.fromisoformat(row[5]) if row[5] else None,
                    iterations=row[6]
                )

            # Load turns
            async with conn.execute(
                "SELECT role, content, tool_calls, created_at FROM turns WHERE session_id = ? ORDER BY id",
                (session_id,)
            ) as cursor:
                async for row in cursor:
                    tool_calls = json.loads(row[2]) if row[2] else None
                    turn = Turn(
                        role=row[0],
                        content=row[1],
                        tool_calls=tool_calls,
                        created_at=datetime.fromisoformat(row[3])
                    )
                    session.turns.append(turn)

        log.info("session_loaded", session_id=session_id, turns=len(session.turns))
        return session

    async def complete_session(self, session_id: str):
        """Mark a session as completed."""

        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                UPDATE sessions
                SET status = 'completed', completed_at = ?
                WHERE id = ?
                """,
                (datetime.now(), session_id)
            )
            await conn.commit()

        log.info("session_completed", session_id=session_id)

    async def list_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        """List recent sessions."""

        async with self.db.get_connection() as conn:
            async with conn.execute(
                """
                SELECT id, task, model, status, created_at, iterations
                FROM sessions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,)
            ) as cursor:
                sessions = []
                async for row in cursor:
                    sessions.append({
                        "id": row[0],
                        "task": row[1],
                        "model": row[2],
                        "status": row[3],
                        "created_at": row[4],
                        "iterations": row[5]
                    })
                return sessions

    async def cleanup_stale_sessions(self, max_age_hours: float = 1.0) -> int:
        """Mark stale 'active' sessions as 'failed'.

        Sessions that are marked as 'active' but older than max_age_hours
        are considered stale (likely from crashed/interrupted processes)
        and are marked as 'failed'.

        Args:
            max_age_hours: Maximum age in hours for an active session before
                          it's considered stale. Default is 1 hour.

        Returns:
            Number of sessions marked as failed.
        """
        from datetime import timedelta

        await self.db.initialize()

        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        async with self.db.get_connection() as conn:
            # First, count how many we'll update
            async with conn.execute(
                """
                SELECT COUNT(*) FROM sessions
                WHERE status = 'active' AND created_at < ?
                """,
                (cutoff_time.isoformat(),)
            ) as cursor:
                row = await cursor.fetchone()
                count = row[0] if row else 0

            if count > 0:
                # Mark stale active sessions as failed
                await conn.execute(
                    """
                    UPDATE sessions
                    SET status = 'failed', completed_at = ?
                    WHERE status = 'active' AND created_at < ?
                    """,
                    (datetime.now(), cutoff_time.isoformat())
                )
                await conn.commit()

                log.info("stale_sessions_cleaned", count=count, max_age_hours=max_age_hours)

        return count

    async def get_active_session_count(self) -> int:
        """Get count of active sessions."""
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE status = 'active'"
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
