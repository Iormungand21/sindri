"""Sindri - Local LLM Orchestration.

Forge code with local LLMs via Ollama, using a hierarchical multi-agent system
inspired by Norse mythology.
"""

__version__ = "1.0.0"
__author__ = "Ryan"

from sindri.core.loop import AgentLoop, LoopConfig, LoopResult
from sindri.config import SindriConfig

__all__ = [
    "__version__",
    "AgentLoop",
    "LoopConfig",
    "LoopResult",
    "SindriConfig",
]
