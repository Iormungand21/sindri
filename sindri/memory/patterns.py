"""Pattern storage and retrieval for learning from successful tasks."""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import json
import structlog

log = structlog.get_logger()


@dataclass
class Pattern:
    """A learned pattern from successful task completions."""

    id: int = 0
    name: str = ""
    description: str = ""

    # When to use this pattern
    context: str = ""  # What kind of task this applies to
    trigger_keywords: List[str] = field(default_factory=list)  # Keywords that suggest this pattern

    # What the pattern contains
    approach: str = ""  # The approach/strategy used
    tool_sequence: List[str] = field(default_factory=list)  # Tools used in order
    example_task: str = ""  # Example task description
    example_output: str = ""  # Example successful output

    # Metadata
    agent: str = ""  # Which agent discovered this pattern
    project_id: str = ""  # Source project (if project-specific)
    success_count: int = 1  # How many times this pattern succeeded
    last_used: Optional[datetime] = None
    created_at: Optional[datetime] = None

    # Efficiency metrics
    avg_iterations: float = 0.0  # Average iterations to complete
    min_iterations: int = 0  # Minimum iterations observed

    def matches_task(self, task_description: str) -> float:
        """Compute rough match score for a task description.

        Returns a score 0.0-1.0 based on keyword overlap.
        """
        if not self.trigger_keywords:
            return 0.0

        task_words = set(task_description.lower().split())
        matched = sum(1 for kw in self.trigger_keywords if kw.lower() in task_words)
        return matched / len(self.trigger_keywords)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "context": self.context,
            "trigger_keywords": self.trigger_keywords,
            "approach": self.approach,
            "tool_sequence": self.tool_sequence,
            "example_task": self.example_task,
            "example_output": self.example_output,
            "agent": self.agent,
            "project_id": self.project_id,
            "success_count": self.success_count,
            "avg_iterations": self.avg_iterations,
            "min_iterations": self.min_iterations,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Pattern":
        """Create from dictionary."""
        return cls(
            id=data.get("id", 0),
            name=data.get("name", ""),
            description=data.get("description", ""),
            context=data.get("context", ""),
            trigger_keywords=data.get("trigger_keywords", []),
            approach=data.get("approach", ""),
            tool_sequence=data.get("tool_sequence", []),
            example_task=data.get("example_task", ""),
            example_output=data.get("example_output", ""),
            agent=data.get("agent", ""),
            project_id=data.get("project_id", ""),
            success_count=data.get("success_count", 1),
            avg_iterations=data.get("avg_iterations", 0.0),
            min_iterations=data.get("min_iterations", 0),
        )


class PatternStore:
    """SQLite-backed storage for learned patterns."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = self._init_db()
        log.info("pattern_store_initialized", db_path=db_path)

    def _init_db(self) -> sqlite3.Connection:
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                context TEXT,
                trigger_keywords TEXT,
                approach TEXT NOT NULL,
                tool_sequence TEXT,
                example_task TEXT,
                example_output TEXT,
                agent TEXT,
                project_id TEXT,
                success_count INTEGER DEFAULT 1,
                avg_iterations REAL DEFAULT 0,
                min_iterations INTEGER DEFAULT 0,
                last_used TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_patterns_agent ON patterns(agent);
            CREATE INDEX IF NOT EXISTS idx_patterns_project ON patterns(project_id);
            CREATE INDEX IF NOT EXISTS idx_patterns_context ON patterns(context);
        """)
        conn.commit()
        return conn

    def store(self, pattern: Pattern) -> int:
        """Store a new pattern or update existing.

        If a pattern with the same name and context exists, updates it.
        Otherwise creates a new pattern.

        Returns: Pattern ID
        """
        # Check for existing pattern with same name and context
        existing = self.find_by_name_and_context(pattern.name, pattern.context)

        if existing:
            # Update existing pattern
            return self._update_pattern(existing, pattern)
        else:
            # Insert new pattern
            return self._insert_pattern(pattern)

    def _insert_pattern(self, pattern: Pattern) -> int:
        """Insert a new pattern."""
        cursor = self.conn.execute(
            """
            INSERT INTO patterns (
                name, description, context, trigger_keywords, approach,
                tool_sequence, example_task, example_output, agent,
                project_id, success_count, avg_iterations, min_iterations
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pattern.name,
                pattern.description,
                pattern.context,
                json.dumps(pattern.trigger_keywords),
                pattern.approach,
                json.dumps(pattern.tool_sequence),
                pattern.example_task,
                pattern.example_output,
                pattern.agent,
                pattern.project_id,
                pattern.success_count,
                pattern.avg_iterations,
                pattern.min_iterations,
            )
        )
        self.conn.commit()
        pattern_id = cursor.lastrowid
        log.info("pattern_stored", pattern_id=pattern_id, name=pattern.name)
        return pattern_id

    def _update_pattern(self, existing: Pattern, new: Pattern) -> int:
        """Update an existing pattern with new data."""
        # Merge success metrics
        total_successes = existing.success_count + 1
        new_avg = (
            (existing.avg_iterations * existing.success_count + new.avg_iterations)
            / total_successes
        )
        new_min = min(existing.min_iterations or 999, new.min_iterations or 999)
        if new_min == 999:
            new_min = 0

        self.conn.execute(
            """
            UPDATE patterns SET
                success_count = ?,
                avg_iterations = ?,
                min_iterations = ?,
                last_used = CURRENT_TIMESTAMP,
                example_task = COALESCE(?, example_task),
                example_output = COALESCE(?, example_output)
            WHERE id = ?
            """,
            (
                total_successes,
                new_avg,
                new_min,
                new.example_task if new.example_task else None,
                new.example_output if new.example_output else None,
                existing.id,
            )
        )
        self.conn.commit()
        log.info("pattern_updated",
                pattern_id=existing.id,
                name=existing.name,
                success_count=total_successes)
        return existing.id

    def find_by_name_and_context(self, name: str, context: str) -> Optional[Pattern]:
        """Find pattern by name and context."""
        row = self.conn.execute(
            """
            SELECT id, name, description, context, trigger_keywords, approach,
                   tool_sequence, example_task, example_output, agent,
                   project_id, success_count, avg_iterations, min_iterations,
                   last_used, created_at
            FROM patterns
            WHERE name = ? AND context = ?
            """,
            (name, context)
        ).fetchone()

        return self._row_to_pattern(row) if row else None

    def find_relevant(
        self,
        task_description: str,
        context: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Pattern]:
        """Find patterns relevant to a task.

        Uses keyword matching and context filtering to find applicable patterns.
        Prioritizes patterns by success count and recency.
        """
        # Build query with optional filters
        query = """
            SELECT id, name, description, context, trigger_keywords, approach,
                   tool_sequence, example_task, example_output, agent,
                   project_id, success_count, avg_iterations, min_iterations,
                   last_used, created_at
            FROM patterns
            WHERE 1=1
        """
        params = []

        if context:
            query += " AND context = ?"
            params.append(context)

        if project_id:
            query += " AND (project_id = ? OR project_id IS NULL OR project_id = '')"
            params.append(project_id)

        # Order by success count and recency
        query += " ORDER BY success_count DESC, last_used DESC NULLS LAST LIMIT ?"
        params.append(limit * 3)  # Get more to filter by relevance

        rows = self.conn.execute(query, params).fetchall()
        patterns = [self._row_to_pattern(row) for row in rows]

        # Score by task relevance
        scored = []
        task_words = set(task_description.lower().split())

        for pattern in patterns:
            score = pattern.matches_task(task_description)

            # Boost score for high success count
            if pattern.success_count > 1:
                score += 0.1 * min(pattern.success_count / 10, 0.3)

            # Boost score for project-specific patterns
            if pattern.project_id == project_id:
                score += 0.2

            scored.append((pattern, score))

        # Sort by score and return top matches
        scored.sort(key=lambda x: x[1], reverse=True)
        return [p for p, s in scored[:limit] if s > 0]

    def get_by_id(self, pattern_id: int) -> Optional[Pattern]:
        """Get pattern by ID."""
        row = self.conn.execute(
            """
            SELECT id, name, description, context, trigger_keywords, approach,
                   tool_sequence, example_task, example_output, agent,
                   project_id, success_count, avg_iterations, min_iterations,
                   last_used, created_at
            FROM patterns
            WHERE id = ?
            """,
            (pattern_id,)
        ).fetchone()

        return self._row_to_pattern(row) if row else None

    def get_all(self, limit: int = 100) -> List[Pattern]:
        """Get all patterns, ordered by success count."""
        rows = self.conn.execute(
            """
            SELECT id, name, description, context, trigger_keywords, approach,
                   tool_sequence, example_task, example_output, agent,
                   project_id, success_count, avg_iterations, min_iterations,
                   last_used, created_at
            FROM patterns
            ORDER BY success_count DESC, last_used DESC NULLS LAST
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

        return [self._row_to_pattern(row) for row in rows]

    def get_pattern_count(self) -> int:
        """Get total number of stored patterns."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM patterns")
        return cursor.fetchone()[0]

    def delete(self, pattern_id: int) -> bool:
        """Delete a pattern by ID."""
        cursor = self.conn.execute(
            "DELETE FROM patterns WHERE id = ?",
            (pattern_id,)
        )
        self.conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            log.info("pattern_deleted", pattern_id=pattern_id)
        return deleted

    def _row_to_pattern(self, row: tuple) -> Pattern:
        """Convert database row to Pattern object."""
        return Pattern(
            id=row[0],
            name=row[1],
            description=row[2] or "",
            context=row[3] or "",
            trigger_keywords=json.loads(row[4]) if row[4] else [],
            approach=row[5] or "",
            tool_sequence=json.loads(row[6]) if row[6] else [],
            example_task=row[7] or "",
            example_output=row[8] or "",
            agent=row[9] or "",
            project_id=row[10] or "",
            success_count=row[11] or 1,
            avg_iterations=row[12] or 0.0,
            min_iterations=row[13] or 0,
            last_used=datetime.fromisoformat(row[14]) if row[14] else None,
            created_at=datetime.fromisoformat(row[15]) if row[15] else None,
        )

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
