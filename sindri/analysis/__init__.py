"""Codebase analysis module - Phase 7.4: Codebase Understanding.

Provides tools for analyzing project structure, dependencies, and conventions.
"""

from sindri.analysis.results import (
    CodebaseAnalysis,
    DependencyInfo,
    ArchitectureInfo,
    StyleInfo,
)
from sindri.analysis.dependencies import DependencyAnalyzer
from sindri.analysis.architecture import ArchitectureDetector
from sindri.analysis.style import StyleAnalyzer

__all__ = [
    "CodebaseAnalysis",
    "DependencyInfo",
    "ArchitectureInfo",
    "StyleInfo",
    "DependencyAnalyzer",
    "ArchitectureDetector",
    "StyleAnalyzer",
]
