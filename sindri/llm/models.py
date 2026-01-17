"""Model definitions and utilities for Sindri."""

from enum import Enum


class ModelSize(Enum):
    """Model size categories."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


# Default models for different tasks
DEFAULT_MODELS = {
    "coder": "qwen2.5-coder:14b",
    "general": "qwen2.5:7b",
    "small": "qwen2.5:3b",
}
