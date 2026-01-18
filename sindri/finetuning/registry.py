"""Model registry for tracking fine-tuned models.

This module provides functionality for:
- Registering fine-tuned models with metadata
- Tracking training parameters and source data
- Version management and model comparison
- Storing performance metrics
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any
import structlog

from sindri.persistence.database import Database

log = structlog.get_logger()


class ModelStatus(str, Enum):
    """Status of a fine-tuned model."""

    TRAINING = "training"  # Currently being trained
    READY = "ready"  # Training complete, ready for use
    ACTIVE = "active"  # Currently the active/default model
    ARCHIVED = "archived"  # No longer in use
    FAILED = "failed"  # Training failed


@dataclass
class TrainingParams:
    """Parameters used for training a model.

    Attributes:
        base_model: The base model used for fine-tuning
        learning_rate: Learning rate (if applicable)
        epochs: Number of training epochs
        batch_size: Training batch size
        context_length: Context window size
        temperature: Default temperature for the model
        quantization: Quantization level (e.g., "q4_0", "q8_0", None)
        extra_params: Any additional training parameters
    """

    base_model: str
    learning_rate: Optional[float] = None
    epochs: Optional[int] = None
    batch_size: Optional[int] = None
    context_length: int = 4096
    temperature: float = 0.7
    quantization: Optional[str] = None
    extra_params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "base_model": self.base_model,
            "learning_rate": self.learning_rate,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "context_length": self.context_length,
            "temperature": self.temperature,
            "quantization": self.quantization,
            "extra_params": self.extra_params,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrainingParams":
        """Create from dictionary."""
        return cls(
            base_model=data.get("base_model", ""),
            learning_rate=data.get("learning_rate"),
            epochs=data.get("epochs"),
            batch_size=data.get("batch_size"),
            context_length=data.get("context_length", 4096),
            temperature=data.get("temperature", 0.7),
            quantization=data.get("quantization"),
            extra_params=data.get("extra_params", {}),
        )


@dataclass
class TrainingMetrics:
    """Metrics from training and evaluation.

    Attributes:
        training_loss: Final training loss
        eval_loss: Evaluation loss
        training_time_seconds: Time taken to train
        tokens_trained: Total tokens in training data
        sessions_used: Number of sessions in training data
        eval_accuracy: Accuracy on evaluation set (if measured)
        custom_metrics: Any additional metrics
    """

    training_loss: Optional[float] = None
    eval_loss: Optional[float] = None
    training_time_seconds: Optional[float] = None
    tokens_trained: int = 0
    sessions_used: int = 0
    eval_accuracy: Optional[float] = None
    custom_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "training_loss": self.training_loss,
            "eval_loss": self.eval_loss,
            "training_time_seconds": self.training_time_seconds,
            "tokens_trained": self.tokens_trained,
            "sessions_used": self.sessions_used,
            "eval_accuracy": self.eval_accuracy,
            "custom_metrics": self.custom_metrics,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrainingMetrics":
        """Create from dictionary."""
        return cls(
            training_loss=data.get("training_loss"),
            eval_loss=data.get("eval_loss"),
            training_time_seconds=data.get("training_time_seconds"),
            tokens_trained=data.get("tokens_trained", 0),
            sessions_used=data.get("sessions_used", 0),
            eval_accuracy=data.get("eval_accuracy"),
            custom_metrics=data.get("custom_metrics", {}),
        )


@dataclass
class FineTunedModel:
    """A fine-tuned model entry in the registry.

    Attributes:
        id: Unique identifier (set after save)
        name: Model name (e.g., "sindri-coder-v1")
        description: Human-readable description
        status: Current model status
        params: Training parameters used
        metrics: Training and evaluation metrics
        training_data_path: Path to training data file
        modelfile_path: Path to Ollama Modelfile
        ollama_name: Name in Ollama (for running)
        version: Version number (auto-incremented)
        created_at: When the model was created
        updated_at: When the model was last updated
        tags: Tags for categorization
    """

    name: str
    description: str = ""
    status: ModelStatus = ModelStatus.TRAINING
    params: TrainingParams = field(default_factory=lambda: TrainingParams(base_model=""))
    metrics: TrainingMetrics = field(default_factory=TrainingMetrics)
    training_data_path: Optional[str] = None
    modelfile_path: Optional[str] = None
    ollama_name: Optional[str] = None
    version: int = 1
    id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "params": self.params.to_dict(),
            "metrics": self.metrics.to_dict(),
            "training_data_path": self.training_data_path,
            "modelfile_path": self.modelfile_path,
            "ollama_name": self.ollama_name,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FineTunedModel":
        """Create from dictionary."""
        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            description=data.get("description", ""),
            status=ModelStatus(data.get("status", "training")),
            params=TrainingParams.from_dict(data.get("params", {})),
            metrics=TrainingMetrics.from_dict(data.get("metrics", {})),
            training_data_path=data.get("training_data_path"),
            modelfile_path=data.get("modelfile_path"),
            ollama_name=data.get("ollama_name"),
            version=data.get("version", 1),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.now()
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if data.get("updated_at")
                else datetime.now()
            ),
            tags=data.get("tags", []),
        )


class ModelRegistry:
    """Registry for tracking fine-tuned models.

    Stores model metadata, training parameters, and metrics
    in SQLite for persistence across sessions.
    """

    def __init__(self, database: Optional[Database] = None):
        """Initialize the model registry.

        Args:
            database: Database instance (uses default if not provided)
        """
        self.db = database or Database()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the database table for fine-tuned models."""
        if self._initialized:
            return

        await self.db.initialize()

        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS finetuned_models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'training',
                    params_json TEXT,
                    metrics_json TEXT,
                    training_data_path TEXT,
                    modelfile_path TEXT,
                    ollama_name TEXT,
                    version INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tags_json TEXT
                )
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_finetuned_models_name
                ON finetuned_models(name)
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_finetuned_models_status
                ON finetuned_models(status)
                """
            )
            await conn.commit()

        self._initialized = True
        log.debug("model_registry_initialized")

    async def register(self, model: FineTunedModel) -> FineTunedModel:
        """Register a new fine-tuned model.

        Args:
            model: The model to register

        Returns:
            The model with ID populated
        """
        await self.initialize()

        # Get the next version for this model name
        existing = await self.get_by_name(model.name)
        if existing:
            model.version = max(m.version for m in existing) + 1

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO finetuned_models
                (name, description, status, params_json, metrics_json,
                 training_data_path, modelfile_path, ollama_name, version,
                 created_at, updated_at, tags_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model.name,
                    model.description,
                    model.status.value,
                    json.dumps(model.params.to_dict()),
                    json.dumps(model.metrics.to_dict()),
                    model.training_data_path,
                    model.modelfile_path,
                    model.ollama_name,
                    model.version,
                    model.created_at,
                    model.updated_at,
                    json.dumps(model.tags),
                ),
            )
            model.id = cursor.lastrowid
            await conn.commit()

        log.info(
            "model_registered",
            name=model.name,
            version=model.version,
            model_id=model.id,
        )
        return model

    async def update(self, model: FineTunedModel) -> bool:
        """Update an existing model entry.

        Args:
            model: The model to update (must have ID set)

        Returns:
            True if updated, False if not found
        """
        if model.id is None:
            raise ValueError("Model must have an ID to update")

        await self.initialize()
        model.updated_at = datetime.now()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE finetuned_models
                SET description = ?, status = ?, params_json = ?,
                    metrics_json = ?, training_data_path = ?,
                    modelfile_path = ?, ollama_name = ?, updated_at = ?,
                    tags_json = ?
                WHERE id = ?
                """,
                (
                    model.description,
                    model.status.value,
                    json.dumps(model.params.to_dict()),
                    json.dumps(model.metrics.to_dict()),
                    model.training_data_path,
                    model.modelfile_path,
                    model.ollama_name,
                    model.updated_at,
                    json.dumps(model.tags),
                    model.id,
                ),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def get_by_id(self, model_id: int) -> Optional[FineTunedModel]:
        """Get a model by ID.

        Args:
            model_id: The model ID

        Returns:
            The model or None if not found
        """
        await self.initialize()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                "SELECT * FROM finetuned_models WHERE id = ?",
                (model_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return self._row_to_model(row)

    async def get_by_name(
        self,
        name: str,
        version: Optional[int] = None,
    ) -> list[FineTunedModel]:
        """Get models by name.

        Args:
            name: Model name to search for
            version: Specific version (None = all versions)

        Returns:
            List of matching models
        """
        await self.initialize()

        query = "SELECT * FROM finetuned_models WHERE name = ?"
        params: list[Any] = [name]

        if version is not None:
            query += " AND version = ?"
            params.append(version)

        query += " ORDER BY version DESC"

        models = []
        async with self.db.get_connection() as conn:
            async with conn.execute(query, params) as cursor:
                async for row in cursor:
                    models.append(self._row_to_model(row))

        return models

    async def get_latest(self, name: str) -> Optional[FineTunedModel]:
        """Get the latest version of a model by name.

        Args:
            name: Model name

        Returns:
            The latest version or None if not found
        """
        models = await self.get_by_name(name)
        return models[0] if models else None

    async def get_active(self) -> Optional[FineTunedModel]:
        """Get the currently active model.

        Returns:
            The active model or None if none is active
        """
        await self.initialize()

        async with self.db.get_connection() as conn:
            async with conn.execute(
                "SELECT * FROM finetuned_models WHERE status = ? LIMIT 1",
                (ModelStatus.ACTIVE.value,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return self._row_to_model(row)

    async def set_active(self, model_id: int) -> bool:
        """Set a model as the active model.

        This deactivates any currently active model and marks
        the specified model as active.

        Args:
            model_id: ID of the model to activate

        Returns:
            True if successful, False if model not found
        """
        await self.initialize()

        model = await self.get_by_id(model_id)
        if not model:
            return False

        async with self.db.get_connection() as conn:
            # Deactivate current active model
            await conn.execute(
                """
                UPDATE finetuned_models
                SET status = ?, updated_at = ?
                WHERE status = ?
                """,
                (ModelStatus.READY.value, datetime.now(), ModelStatus.ACTIVE.value),
            )

            # Activate the new model
            await conn.execute(
                """
                UPDATE finetuned_models
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (ModelStatus.ACTIVE.value, datetime.now(), model_id),
            )
            await conn.commit()

        log.info("model_activated", model_id=model_id, name=model.name)
        return True

    async def list_models(
        self,
        status: Optional[ModelStatus] = None,
        limit: int = 100,
    ) -> list[FineTunedModel]:
        """List all registered models.

        Args:
            status: Filter by status (None = all)
            limit: Maximum number of results

        Returns:
            List of models
        """
        await self.initialize()

        query = "SELECT * FROM finetuned_models"
        params: list[Any] = []

        if status is not None:
            query += " WHERE status = ?"
            params.append(status.value)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        models = []
        async with self.db.get_connection() as conn:
            async with conn.execute(query, params) as cursor:
                async for row in cursor:
                    models.append(self._row_to_model(row))

        return models

    async def delete(self, model_id: int) -> bool:
        """Delete a model from the registry.

        Note: This only removes the registry entry, not the actual
        Ollama model or training data files.

        Args:
            model_id: ID of the model to delete

        Returns:
            True if deleted, False if not found
        """
        await self.initialize()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM finetuned_models WHERE id = ?",
                (model_id,),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def archive(self, model_id: int) -> bool:
        """Archive a model (soft delete).

        Args:
            model_id: ID of the model to archive

        Returns:
            True if archived, False if not found
        """
        await self.initialize()

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE finetuned_models
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (ModelStatus.ARCHIVED.value, datetime.now(), model_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def get_stats(self) -> dict[str, Any]:
        """Get statistics about registered models.

        Returns:
            Dictionary with model statistics
        """
        await self.initialize()

        async with self.db.get_connection() as conn:
            # Total models
            async with conn.execute(
                "SELECT COUNT(*) FROM finetuned_models"
            ) as cursor:
                total_models = (await cursor.fetchone())[0]

            # Status distribution
            status_dist = {}
            async with conn.execute(
                "SELECT status, COUNT(*) FROM finetuned_models GROUP BY status"
            ) as cursor:
                async for row in cursor:
                    status_dist[row[0]] = row[1]

            # Active model info
            active_model = await self.get_active()

            # Recent models
            recent = await self.list_models(limit=5)

        return {
            "total_models": total_models,
            "status_distribution": status_dist,
            "active_model": active_model.name if active_model else None,
            "recent_models": [m.name for m in recent],
        }

    def _row_to_model(self, row) -> FineTunedModel:
        """Convert a database row to a FineTunedModel."""
        params_dict = json.loads(row[4]) if row[4] else {}
        metrics_dict = json.loads(row[5]) if row[5] else {}
        tags = json.loads(row[12]) if row[12] else []

        return FineTunedModel(
            id=row[0],
            name=row[1],
            description=row[2] or "",
            status=ModelStatus(row[3]),
            params=TrainingParams.from_dict(params_dict),
            metrics=TrainingMetrics.from_dict(metrics_dict),
            training_data_path=row[6],
            modelfile_path=row[7],
            ollama_name=row[8],
            version=row[9],
            created_at=(
                datetime.fromisoformat(row[10]) if row[10] else datetime.now()
            ),
            updated_at=(
                datetime.fromisoformat(row[11]) if row[11] else datetime.now()
            ),
            tags=tags,
        )
