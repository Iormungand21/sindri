"""sqlite-vec integration for vector search."""

import sqlite3
import sqlite_vec
import struct
import json
from typing import Optional
import structlog

log = structlog.get_logger()


def serialize_f32(vector: list[float]) -> bytes:
    """Serialize float vector for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


class VectorStore:
    """SQLite-based vector storage with sqlite-vec."""

    def __init__(self, db_path: str, dimension: int = 768):
        self.db_path = db_path
        self.dimension = dimension
        self.conn = self._init_db()
        log.info("vector_store_initialized", db_path=db_path, dimension=dimension)

    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY,
                namespace TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                embedding F32_BLOB({self.dimension})
            );

            CREATE INDEX IF NOT EXISTS idx_namespace ON embeddings(namespace);
        """
        )
        conn.commit()

        return conn

    def insert(
        self,
        namespace: str,
        content: str,
        embedding: list[float],
        metadata: Optional[dict] = None,
    ) -> int:
        """Insert a vector with content."""
        cursor = self.conn.execute(
            """
            INSERT INTO embeddings (namespace, content, metadata, embedding)
            VALUES (?, ?, ?, ?)
            """,
            (
                namespace,
                content,
                json.dumps(metadata) if metadata else None,
                serialize_f32(embedding),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def search(
        self, namespace: str, query_embedding: list[float], limit: int = 10
    ) -> list[tuple[str, float, dict]]:
        """Search for similar vectors.

        Returns: List of (content, similarity, metadata) tuples
        """
        results = self.conn.execute(
            """
            SELECT content, metadata,
                   vec_distance_cosine(embedding, ?) as distance
            FROM embeddings
            WHERE namespace = ?
            ORDER BY distance
            LIMIT ?
            """,
            (serialize_f32(query_embedding), namespace, limit),
        ).fetchall()

        return [
            (
                row[0],
                1 - row[2],  # Convert distance to similarity
                json.loads(row[1]) if row[1] else {},
            )
            for row in results
        ]

    def delete_namespace(self, namespace: str):
        """Delete all vectors in a namespace."""
        self.conn.execute("DELETE FROM embeddings WHERE namespace = ?", (namespace,))
        self.conn.commit()
        log.info("namespace_deleted", namespace=namespace)

    def count(self, namespace: Optional[str] = None) -> int:
        """Count embeddings in namespace (or all if None)."""
        if namespace:
            result = self.conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE namespace = ?", (namespace,)
            ).fetchone()
        else:
            result = self.conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()
        return result[0]

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
