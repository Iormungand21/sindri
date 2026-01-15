"""Episodic memory - project session history."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import json
import structlog

log = structlog.get_logger()


@dataclass
class Episode:
    """A stored memory episode."""
    id: int
    project_id: str
    event_type: str      # task_complete, decision, error, milestone
    content: str
    metadata: dict
    timestamp: datetime
    embedding: Optional[list[float]] = None


class EpisodicMemory:
    """Stores and retrieves project history."""

    def __init__(self, db_path: str, embedder: 'LocalEmbedder'):
        self.db_path = db_path
        self.embedder = embedder
        self.conn = self._init_db()
        log.info("episodic_memory_initialized", db_path=db_path)

    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY,
                project_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_project ON episodes(project_id);
            CREATE INDEX IF NOT EXISTS idx_event_type ON episodes(event_type);
        """)
        conn.commit()
        return conn

    def store(
        self,
        project_id: str,
        event_type: str,
        content: str,
        metadata: Optional[dict] = None
    ) -> int:
        """Store an episode."""
        cursor = self.conn.execute(
            """
            INSERT INTO episodes (project_id, event_type, content, metadata)
            VALUES (?, ?, ?, ?)
            """,
            (
                project_id,
                event_type,
                content,
                json.dumps(metadata) if metadata else None
            )
        )
        self.conn.commit()
        log.info(
            "episode_stored",
            episode_id=cursor.lastrowid,
            project_id=project_id,
            event_type=event_type
        )
        return cursor.lastrowid

    def retrieve_recent(
        self,
        project_id: str,
        limit: int = 10
    ) -> list[Episode]:
        """Get recent episodes for a project."""
        rows = self.conn.execute(
            """
            SELECT id, project_id, event_type, content, metadata, timestamp
            FROM episodes
            WHERE project_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (project_id, limit)
        ).fetchall()

        return [
            Episode(
                id=r[0],
                project_id=r[1],
                event_type=r[2],
                content=r[3],
                metadata=json.loads(r[4]) if r[4] else {},
                timestamp=datetime.fromisoformat(r[5])
            )
            for r in rows
        ]

    def retrieve_relevant(
        self,
        project_id: str,
        query: str,
        limit: int = 5
    ) -> list[Episode]:
        """Retrieve episodes semantically similar to query."""
        # Get all episodes for project
        episodes = self.retrieve_recent(project_id, limit=100)

        if not episodes:
            return []

        # Embed query
        query_emb = self.embedder.embed(query)

        # Score episodes
        scored = []
        for ep in episodes:
            ep_emb = self.embedder.embed(ep.content)
            score = self.embedder.similarity(query_emb, ep_emb)
            scored.append((ep, score))

        # Return top matches
        scored.sort(key=lambda x: x[1], reverse=True)
        return [ep for ep, _ in scored[:limit]]

    def get_by_id(self, episode_id: int) -> Optional[Episode]:
        """Get a specific episode by ID."""
        row = self.conn.execute(
            """
            SELECT id, project_id, event_type, content, metadata, timestamp
            FROM episodes
            WHERE id = ?
            """,
            (episode_id,)
        ).fetchone()

        if not row:
            return None

        return Episode(
            id=row[0],
            project_id=row[1],
            event_type=row[2],
            content=row[3],
            metadata=json.loads(row[4]) if row[4] else {},
            timestamp=datetime.fromisoformat(row[5])
        )

    def get_episode_count(self) -> int:
        """Get the total number of episodes stored.

        Returns:
            Number of episodes in the database
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM episodes")
        count = cursor.fetchone()[0]
        return count

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
