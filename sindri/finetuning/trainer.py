"""Training orchestrator for fine-tuning local LLMs.

This module provides functionality for:
- Preparing training data from curated sessions
- Creating Ollama Modelfiles for fine-tuning
- Executing training via Ollama
- Monitoring training progress
"""

import asyncio
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any, Callable
import structlog

from sindri.persistence.database import Database
from sindri.persistence.training_export import (
    TrainingDataExporter,
    ExportFormat,
    generate_modelfile,
)
from sindri.finetuning.curator import DataCurator, CurationConfig, CuratedDataset
from sindri.finetuning.registry import (
    ModelRegistry,
    FineTunedModel,
    ModelStatus,
    TrainingParams,
    TrainingMetrics,
)

log = structlog.get_logger()


class TrainingStatus(str, Enum):
    """Status of a training job."""

    PENDING = "pending"
    PREPARING = "preparing"
    EXPORTING = "exporting"
    TRAINING = "training"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TrainingConfig:
    """Configuration for a training job.

    Attributes:
        base_model: Base Ollama model for fine-tuning
        model_name: Name for the fine-tuned model
        description: Model description
        min_rating: Minimum feedback rating for training data
        max_sessions: Maximum sessions to include
        curation_config: Optional custom curation config
        context_length: Context window size
        temperature: Default temperature
        export_format: Format for training data
        output_dir: Directory for training artifacts
        tags: Tags for the model
    """

    base_model: str = "qwen2.5-coder:7b"
    model_name: str = "sindri-custom"
    description: str = ""
    min_rating: int = 4
    max_sessions: int = 500
    curation_config: Optional[CurationConfig] = None
    context_length: int = 4096
    temperature: float = 0.7
    export_format: ExportFormat = ExportFormat.OLLAMA
    output_dir: Path = field(default_factory=lambda: Path.home() / ".sindri" / "models")
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Ensure output_dir is a Path."""
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)


@dataclass
class TrainingJob:
    """A training job with status and progress tracking.

    Attributes:
        id: Job identifier
        config: Training configuration
        status: Current status
        model_id: ID of the registered model (set after registration)
        dataset: The curated dataset used
        progress: Progress percentage (0-100)
        error: Error message if failed
        started_at: When training started
        completed_at: When training completed
        training_data_path: Path to exported training data
        modelfile_path: Path to generated Modelfile
    """

    id: str
    config: TrainingConfig
    status: TrainingStatus = TrainingStatus.PENDING
    model_id: Optional[int] = None
    dataset: Optional[CuratedDataset] = None
    progress: float = 0.0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    training_data_path: Optional[Path] = None
    modelfile_path: Optional[Path] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "config": {
                "base_model": self.config.base_model,
                "model_name": self.config.model_name,
                "min_rating": self.config.min_rating,
                "max_sessions": self.config.max_sessions,
            },
            "status": self.status.value,
            "model_id": self.model_id,
            "progress": self.progress,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "dataset_sessions": len(self.dataset.sessions) if self.dataset else 0,
        }


class TrainingOrchestrator:
    """Orchestrates the fine-tuning pipeline.

    Handles:
    - Data curation and preparation
    - Training data export
    - Modelfile generation
    - Training execution via Ollama
    - Progress tracking and error handling
    """

    def __init__(
        self,
        database: Optional[Database] = None,
        curator: Optional[DataCurator] = None,
        exporter: Optional[TrainingDataExporter] = None,
        registry: Optional[ModelRegistry] = None,
    ):
        """Initialize the training orchestrator.

        Args:
            database: Database instance
            curator: Data curator instance
            exporter: Training data exporter instance
            registry: Model registry instance
        """
        self.db = database or Database()
        self.curator = curator or DataCurator(self.db)
        self.exporter = exporter or TrainingDataExporter(self.db)
        self.registry = registry or ModelRegistry(self.db)
        self._jobs: dict[str, TrainingJob] = {}
        self._progress_callbacks: list[Callable[[TrainingJob], None]] = []

    def on_progress(self, callback: Callable[[TrainingJob], None]) -> None:
        """Register a callback for progress updates.

        Args:
            callback: Function to call with job updates
        """
        self._progress_callbacks.append(callback)

    def _notify_progress(self, job: TrainingJob) -> None:
        """Notify all progress callbacks."""
        for callback in self._progress_callbacks:
            try:
                callback(job)
            except Exception as e:
                log.warning("progress_callback_error", error=str(e))

    async def prepare_training(
        self,
        config: TrainingConfig,
    ) -> TrainingJob:
        """Prepare training data without starting training.

        This allows previewing what data would be used for training.

        Args:
            config: Training configuration

        Returns:
            TrainingJob with curated dataset
        """
        job_id = f"train-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        job = TrainingJob(id=job_id, config=config)
        self._jobs[job_id] = job

        job.status = TrainingStatus.PREPARING
        job.started_at = datetime.now()
        self._notify_progress(job)

        try:
            # Curate the data
            curation_config = config.curation_config or CurationConfig(
                min_rating=config.min_rating
            )
            dataset = await self.curator.curate(curation_config)

            # Limit to max_sessions
            if len(dataset.sessions) > config.max_sessions:
                dataset.sessions = dataset.sessions[: config.max_sessions]
                dataset.total_turns = sum(s.turns for s in dataset.sessions)

            job.dataset = dataset
            job.progress = 25.0
            self._notify_progress(job)

            log.info(
                "training_data_prepared",
                job_id=job_id,
                sessions=len(dataset.sessions),
                total_turns=dataset.total_turns,
            )

        except Exception as e:
            job.status = TrainingStatus.FAILED
            job.error = str(e)
            log.error("training_preparation_failed", error=str(e))
            raise

        return job

    async def start_training(
        self,
        config: TrainingConfig,
        dry_run: bool = False,
    ) -> TrainingJob:
        """Start a complete training job.

        Args:
            config: Training configuration
            dry_run: If True, prepare data but don't train

        Returns:
            TrainingJob with training results
        """
        # Prepare training data
        job = await self.prepare_training(config)

        if not job.dataset or not job.dataset.sessions:
            job.status = TrainingStatus.FAILED
            job.error = "No training data available"
            return job

        try:
            # Export training data
            job.status = TrainingStatus.EXPORTING
            self._notify_progress(job)

            output_dir = config.output_dir / config.model_name
            output_dir.mkdir(parents=True, exist_ok=True)

            training_data_path = output_dir / f"training_data.{config.export_format.value}"

            # Get session IDs from curated dataset
            session_ids = [s.session_id for s in job.dataset.sessions]

            export_stats = await self.exporter.export_training_data(
                output_path=training_data_path,
                format=config.export_format,
                session_ids=session_ids,
            )

            job.training_data_path = training_data_path
            job.progress = 50.0
            self._notify_progress(job)

            log.info(
                "training_data_exported",
                path=str(training_data_path),
                sessions=export_stats.sessions_exported,
                turns=export_stats.turns_exported,
            )

            # Generate Modelfile
            modelfile_path = output_dir / "Modelfile"
            generate_modelfile(
                base_model=config.base_model,
                training_data_path=training_data_path,
                output_path=modelfile_path,
                model_name=config.model_name,
                temperature=config.temperature,
                context_length=config.context_length,
            )

            job.modelfile_path = modelfile_path
            job.progress = 60.0
            self._notify_progress(job)

            # Register the model
            model = FineTunedModel(
                name=config.model_name,
                description=config.description or f"Fine-tuned from {config.base_model}",
                status=ModelStatus.TRAINING,
                params=TrainingParams(
                    base_model=config.base_model,
                    context_length=config.context_length,
                    temperature=config.temperature,
                ),
                metrics=TrainingMetrics(
                    sessions_used=len(job.dataset.sessions),
                    tokens_trained=export_stats.total_tokens_estimate,
                ),
                training_data_path=str(training_data_path),
                modelfile_path=str(modelfile_path),
                ollama_name=config.model_name,
                tags=config.tags,
            )

            model = await self.registry.register(model)
            job.model_id = model.id

            if dry_run:
                job.status = TrainingStatus.COMPLETED
                job.progress = 100.0
                job.completed_at = datetime.now()
                log.info("dry_run_complete", job_id=job.id)
                return job

            # Execute training with Ollama
            job.status = TrainingStatus.TRAINING
            job.progress = 70.0
            self._notify_progress(job)

            start_time = time.time()
            success = await self._execute_ollama_create(
                model_name=config.model_name,
                modelfile_path=modelfile_path,
            )

            training_time = time.time() - start_time

            if success:
                # Update model status and metrics
                model.status = ModelStatus.READY
                model.metrics.training_time_seconds = training_time
                await self.registry.update(model)

                job.status = TrainingStatus.COMPLETED
                job.progress = 100.0
                job.completed_at = datetime.now()

                log.info(
                    "training_complete",
                    job_id=job.id,
                    model_name=config.model_name,
                    training_time=round(training_time, 2),
                )
            else:
                model.status = ModelStatus.FAILED
                await self.registry.update(model)

                job.status = TrainingStatus.FAILED
                job.error = "Ollama model creation failed"

        except Exception as e:
            job.status = TrainingStatus.FAILED
            job.error = str(e)
            log.error("training_failed", error=str(e), job_id=job.id)

            # Update model status if registered
            if job.model_id:
                model = await self.registry.get_by_id(job.model_id)
                if model:
                    model.status = ModelStatus.FAILED
                    await self.registry.update(model)

        self._notify_progress(job)
        return job

    async def _execute_ollama_create(
        self,
        model_name: str,
        modelfile_path: Path,
    ) -> bool:
        """Execute `ollama create` to build the fine-tuned model.

        Args:
            model_name: Name for the new model
            modelfile_path: Path to the Modelfile

        Returns:
            True if successful, False otherwise
        """
        try:
            # Run ollama create command
            cmd = ["ollama", "create", model_name, "-f", str(modelfile_path)]

            log.info("executing_ollama_create", cmd=" ".join(cmd))

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                log.info(
                    "ollama_create_success",
                    model_name=model_name,
                    stdout=stdout.decode() if stdout else "",
                )
                return True
            else:
                log.error(
                    "ollama_create_failed",
                    returncode=process.returncode,
                    stderr=stderr.decode() if stderr else "",
                )
                return False

        except FileNotFoundError:
            log.error("ollama_not_found", message="Ollama CLI not found in PATH")
            return False
        except Exception as e:
            log.error("ollama_create_error", error=str(e))
            return False

    async def cancel_training(self, job_id: str) -> bool:
        """Cancel a training job.

        Args:
            job_id: ID of the job to cancel

        Returns:
            True if cancelled, False if not found
        """
        job = self._jobs.get(job_id)
        if not job:
            return False

        if job.status in (TrainingStatus.COMPLETED, TrainingStatus.FAILED):
            return False

        job.status = TrainingStatus.CANCELLED
        job.completed_at = datetime.now()
        self._notify_progress(job)

        log.info("training_cancelled", job_id=job_id)
        return True

    def get_job(self, job_id: str) -> Optional[TrainingJob]:
        """Get a training job by ID.

        Args:
            job_id: The job ID

        Returns:
            The job or None if not found
        """
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[TrainingJob]:
        """List all training jobs.

        Returns:
            List of all jobs
        """
        return list(self._jobs.values())

    async def get_training_stats(self) -> dict[str, Any]:
        """Get statistics about training.

        Returns:
            Dictionary with training statistics
        """
        # Curation stats
        curation_stats = await self.curator.get_curation_stats()

        # Registry stats
        registry_stats = await self.registry.get_stats()

        # Job stats
        job_status_counts: dict[str, int] = {}
        for job in self._jobs.values():
            status = job.status.value
            job_status_counts[status] = job_status_counts.get(status, 0) + 1

        return {
            "curation": curation_stats,
            "registry": registry_stats,
            "jobs": {
                "total": len(self._jobs),
                "by_status": job_status_counts,
            },
        }

    async def quick_train(
        self,
        base_model: str = "qwen2.5-coder:7b",
        model_name: Optional[str] = None,
        min_rating: int = 4,
    ) -> TrainingJob:
        """Quick training with minimal configuration.

        A convenience method for starting training with defaults.

        Args:
            base_model: Base model to fine-tune
            model_name: Name for the new model (auto-generated if None)
            min_rating: Minimum feedback rating

        Returns:
            TrainingJob with results
        """
        if model_name is None:
            timestamp = datetime.now().strftime("%Y%m%d")
            model_name = f"sindri-{base_model.split(':')[0]}-{timestamp}"

        config = TrainingConfig(
            base_model=base_model,
            model_name=model_name,
            min_rating=min_rating,
            description=f"Quick fine-tune from {base_model}",
        )

        return await self.start_training(config)
