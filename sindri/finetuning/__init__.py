"""Fine-tuning pipeline for Sindri local LLMs.

This module provides infrastructure for fine-tuning local LLMs based on
user feedback and session data. Key components:

- curator: Data filtering, deduplication, and quality scoring
- registry: Track fine-tuned models and their metadata
- trainer: Orchestrate training with Ollama integration
- evaluator: Benchmark and compare model performance
"""

from sindri.finetuning.curator import DataCurator, CurationConfig, CuratedDataset
from sindri.finetuning.registry import ModelRegistry, FineTunedModel
from sindri.finetuning.trainer import TrainingOrchestrator, TrainingConfig, TrainingJob
from sindri.finetuning.evaluator import ModelEvaluator, EvaluationResult, BenchmarkSuite

__all__ = [
    "DataCurator",
    "CurationConfig",
    "CuratedDataset",
    "ModelRegistry",
    "FineTunedModel",
    "TrainingOrchestrator",
    "TrainingConfig",
    "TrainingJob",
    "ModelEvaluator",
    "EvaluationResult",
    "BenchmarkSuite",
]
