"""Persistence layer for session snapshots and tool outputs (Reproducible Sessions)."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

import aiosqlite
import structlog

from sindri.persistence.database import Database

log = structlog.get_logger()


@dataclass
class ModelMetadata:
    """Captured model metadata from Ollama."""

    name: str
    digest: str = ""
    family: str = "unknown"
    parameter_size: str = "unknown"
    quantization_level: str = "unknown"
    format: str = "unknown"
    modified_at: Optional[str] = None
    raw_response: Optional[dict] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "digest": self.digest,
            "family": self.family,
            "parameter_size": self.parameter_size,
            "quantization_level": self.quantization_level,
            "format": self.format,
            "modified_at": self.modified_at,
            "raw_response": self.raw_response,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModelMetadata":
        """Create from dictionary."""
        return cls(
            name=data.get("name", "unknown"),
            digest=data.get("digest", ""),
            family=data.get("family", "unknown"),
            parameter_size=data.get("parameter_size", "unknown"),
            quantization_level=data.get("quantization_level", "unknown"),
            format=data.get("format", "unknown"),
            modified_at=data.get("modified_at"),
            raw_response=data.get("raw_response"),
        )


@dataclass
class InferenceParams:
    """LLM inference parameters for reproducibility."""

    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    seed: Optional[int] = None
    repeat_penalty: float = 1.1
    num_ctx: int = 4096

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "InferenceParams":
        """Create from dictionary."""
        return cls(
            temperature=data.get("temperature", 0.7),
            top_p=data.get("top_p", 0.9),
            top_k=data.get("top_k", 40),
            seed=data.get("seed"),
            repeat_penalty=data.get("repeat_penalty", 1.1),
            num_ctx=data.get("num_ctx", 4096),
        )


@dataclass
class EnvironmentSnapshot:
    """Complete environment capture at session start."""

    sindri_version: str
    python_version: str
    ollama_host: str
    model_metadata: ModelMetadata
    config_snapshot: dict
    sindri_git_commit: Optional[str] = None
    ollama_version: Optional[str] = None
    inference_params: Optional[InferenceParams] = None
    captured_at: Optional[datetime] = None
    # Fallback tracking for model degradation
    primary_model: Optional[str] = None  # Original requested model (when degraded)
    fallback_model_used: Optional[str] = None  # Fallback model used (when degraded)
    degradation_reason: Optional[str] = None  # Why fallback was needed

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "sindri_version": self.sindri_version,
            "sindri_git_commit": self.sindri_git_commit,
            "python_version": self.python_version,
            "ollama_version": self.ollama_version,
            "ollama_host": self.ollama_host,
            "model_metadata": self.model_metadata.to_dict(),
            "inference_params": (
                self.inference_params.to_dict() if self.inference_params else None
            ),
            "config_snapshot": self.config_snapshot,
            "captured_at": (
                self.captured_at.isoformat() if self.captured_at else None
            ),
        }
        # Include fallback tracking fields if degradation occurred
        if self.primary_model:
            result["primary_model"] = self.primary_model
        if self.fallback_model_used:
            result["fallback_model_used"] = self.fallback_model_used
        if self.degradation_reason:
            result["degradation_reason"] = self.degradation_reason
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "EnvironmentSnapshot":
        """Create from dictionary."""
        return cls(
            sindri_version=data.get("sindri_version", "unknown"),
            sindri_git_commit=data.get("sindri_git_commit"),
            python_version=data.get("python_version", "unknown"),
            ollama_version=data.get("ollama_version"),
            ollama_host=data.get("ollama_host", "http://localhost:11434"),
            model_metadata=ModelMetadata.from_dict(
                data.get("model_metadata", {"name": "unknown"})
            ),
            inference_params=(
                InferenceParams.from_dict(data["inference_params"])
                if data.get("inference_params")
                else None
            ),
            config_snapshot=data.get("config_snapshot", {}),
            captured_at=(
                datetime.fromisoformat(data["captured_at"])
                if data.get("captured_at")
                else None
            ),
            # Fallback tracking fields (backward compatible - defaults to None)
            primary_model=data.get("primary_model"),
            fallback_model_used=data.get("fallback_model_used"),
            degradation_reason=data.get("degradation_reason"),
        )


@dataclass
class ToolOutput:
    """Recorded tool output for replay."""

    session_id: str
    turn_index: int
    tool_index: int
    tool_name: str
    arguments: dict
    output: Optional[str]
    output_hash: Optional[str]
    duration_ms: Optional[int]
    success: bool
    created_at: Optional[datetime] = None


class SnapshotStore:
    """Persistence for environment snapshots."""

    def __init__(self, database: Optional[Database] = None):
        """Initialize snapshot store.

        Args:
            database: Database instance. Creates new one if not provided.
        """
        self.db = database or Database()

    async def save_snapshot(
        self, session_id: str, snapshot: EnvironmentSnapshot
    ) -> None:
        """Save snapshot for a session.

        Args:
            session_id: Session ID to associate snapshot with
            snapshot: Environment snapshot to save
        """
        await self.db.initialize()

        # Include fallback fields in config_snapshot for persistence
        # (avoids schema changes while preserving all snapshot data)
        config_with_fallback = dict(snapshot.config_snapshot)
        if snapshot.primary_model:
            config_with_fallback["_fallback_primary_model"] = snapshot.primary_model
        if snapshot.fallback_model_used:
            config_with_fallback["_fallback_model_used"] = snapshot.fallback_model_used
        if snapshot.degradation_reason:
            config_with_fallback["_fallback_degradation_reason"] = snapshot.degradation_reason

        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO session_snapshots (
                    session_id, sindri_version, sindri_git_commit, python_version,
                    ollama_version, ollama_host, model_metadata_json,
                    inference_params_json, config_snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    snapshot.sindri_version,
                    snapshot.sindri_git_commit,
                    snapshot.python_version,
                    snapshot.ollama_version,
                    snapshot.ollama_host,
                    json.dumps(snapshot.model_metadata.to_dict()),
                    (
                        json.dumps(snapshot.inference_params.to_dict())
                        if snapshot.inference_params
                        else None
                    ),
                    json.dumps(config_with_fallback),
                ),
            )
            await conn.commit()

        log.info("snapshot_saved", session_id=session_id, degraded=snapshot.fallback_model_used is not None)

    async def load_snapshot(self, session_id: str) -> Optional[EnvironmentSnapshot]:
        """Load snapshot for a session.

        Args:
            session_id: Session ID to load snapshot for

        Returns:
            EnvironmentSnapshot if found, None otherwise
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT * FROM session_snapshots WHERE session_id = ?
                """,
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        # Extract config and fallback fields
        config_data = json.loads(row["config_snapshot_json"])
        primary_model = config_data.pop("_fallback_primary_model", None)
        fallback_model_used = config_data.pop("_fallback_model_used", None)
        degradation_reason = config_data.pop("_fallback_degradation_reason", None)

        return EnvironmentSnapshot(
            sindri_version=row["sindri_version"],
            sindri_git_commit=row["sindri_git_commit"],
            python_version=row["python_version"],
            ollama_version=row["ollama_version"],
            ollama_host=row["ollama_host"],
            model_metadata=ModelMetadata.from_dict(
                json.loads(row["model_metadata_json"])
            ),
            inference_params=(
                InferenceParams.from_dict(json.loads(row["inference_params_json"]))
                if row["inference_params_json"]
                else None
            ),
            config_snapshot=config_data,
            captured_at=datetime.fromisoformat(row["created_at"]),
            primary_model=primary_model,
            fallback_model_used=fallback_model_used,
            degradation_reason=degradation_reason,
        )

    async def has_snapshot(self, session_id: str) -> bool:
        """Check if session has a snapshot.

        Args:
            session_id: Session ID to check

        Returns:
            True if snapshot exists, False otherwise
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                "SELECT 1 FROM session_snapshots WHERE session_id = ?",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()

        return row is not None

    async def list_sessions_with_snapshots(
        self, limit: int = 50
    ) -> list[dict]:
        """List sessions that have snapshots.

        Args:
            limit: Maximum number of sessions to return

        Returns:
            List of dicts with session_id, model, sindri_version, created_at
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT
                    ss.session_id,
                    s.task,
                    s.model,
                    ss.sindri_version,
                    ss.python_version,
                    ss.created_at
                FROM session_snapshots ss
                JOIN sessions s ON ss.session_id = s.id
                ORDER BY ss.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()

        return [
            {
                "session_id": row["session_id"],
                "task": row["task"],
                "model": row["model"],
                "sindri_version": row["sindri_version"],
                "python_version": row["python_version"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    async def delete_snapshot(self, session_id: str) -> bool:
        """Delete snapshot for a session.

        Args:
            session_id: Session ID to delete snapshot for

        Returns:
            True if deleted, False if not found
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM session_snapshots WHERE session_id = ?",
                (session_id,),
            )
            await conn.commit()

        return cursor.rowcount > 0


class ToolOutputStore:
    """Persistence for full tool outputs (for deterministic replay)."""

    def __init__(self, database: Optional[Database] = None):
        """Initialize tool output store.

        Args:
            database: Database instance. Creates new one if not provided.
        """
        self.db = database or Database()

    async def save_tool_output(
        self,
        session_id: str,
        turn_index: int,
        tool_index: int,
        tool_name: str,
        arguments: dict,
        output: Optional[str],
        success: bool,
        duration_ms: Optional[int] = None,
    ) -> None:
        """Save full tool output.

        Args:
            session_id: Session ID
            turn_index: Turn index in session
            tool_index: Tool call index within turn
            tool_name: Name of tool executed
            arguments: Tool arguments dict
            output: Full tool output (not truncated)
            success: Whether tool succeeded
            duration_ms: Execution duration in milliseconds
        """
        await self.db.initialize()

        output_hash = None
        if output:
            output_hash = hashlib.sha256(output.encode()).hexdigest()

        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO session_tool_outputs (
                    session_id, turn_index, tool_index, tool_name,
                    arguments_json, output_full, output_hash, duration_ms, success
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    turn_index,
                    tool_index,
                    tool_name,
                    json.dumps(arguments),
                    output,
                    output_hash,
                    duration_ms,
                    1 if success else 0,
                ),
            )
            await conn.commit()

        log.debug(
            "tool_output_saved",
            session_id=session_id,
            turn_index=turn_index,
            tool_index=tool_index,
            tool_name=tool_name,
        )

    async def get_session_outputs(self, session_id: str) -> list[ToolOutput]:
        """Get all tool outputs for a session.

        Args:
            session_id: Session ID to get outputs for

        Returns:
            List of ToolOutput objects ordered by turn_index, tool_index
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT * FROM session_tool_outputs
                WHERE session_id = ?
                ORDER BY turn_index, tool_index
                """,
                (session_id,),
            ) as cursor:
                rows = await cursor.fetchall()

        return [
            ToolOutput(
                session_id=row["session_id"],
                turn_index=row["turn_index"],
                tool_index=row["tool_index"],
                tool_name=row["tool_name"],
                arguments=json.loads(row["arguments_json"]),
                output=row["output_full"],
                output_hash=row["output_hash"],
                duration_ms=row["duration_ms"],
                success=bool(row["success"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    async def get_tool_output(
        self, session_id: str, turn_index: int, tool_index: int
    ) -> Optional[ToolOutput]:
        """Get a specific tool output.

        Args:
            session_id: Session ID
            turn_index: Turn index
            tool_index: Tool call index

        Returns:
            ToolOutput if found, None otherwise
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT * FROM session_tool_outputs
                WHERE session_id = ? AND turn_index = ? AND tool_index = ?
                """,
                (session_id, turn_index, tool_index),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        return ToolOutput(
            session_id=row["session_id"],
            turn_index=row["turn_index"],
            tool_index=row["tool_index"],
            tool_name=row["tool_name"],
            arguments=json.loads(row["arguments_json"]),
            output=row["output_full"],
            output_hash=row["output_hash"],
            duration_ms=row["duration_ms"],
            success=bool(row["success"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    async def verify_output_hash(
        self, session_id: str, turn_index: int, tool_index: int, output: str
    ) -> bool:
        """Verify tool output matches recorded hash.

        Args:
            session_id: Session ID
            turn_index: Turn index
            tool_index: Tool call index
            output: Output to verify

        Returns:
            True if hash matches, False otherwise
        """
        tool_output = await self.get_tool_output(session_id, turn_index, tool_index)
        if not tool_output or not tool_output.output_hash:
            return False

        computed_hash = hashlib.sha256(output.encode()).hexdigest()
        return computed_hash == tool_output.output_hash

    async def delete_session_outputs(self, session_id: str) -> int:
        """Delete all tool outputs for a session.

        Args:
            session_id: Session ID to delete outputs for

        Returns:
            Number of outputs deleted
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM session_tool_outputs WHERE session_id = ?",
                (session_id,),
            )
            await conn.commit()

        return cursor.rowcount

    async def get_output_count(self, session_id: str) -> int:
        """Get count of tool outputs for a session.

        Args:
            session_id: Session ID

        Returns:
            Number of tool outputs
        """
        await self.db.initialize()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM session_tool_outputs WHERE session_id = ?",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()

        return row[0] if row else 0
