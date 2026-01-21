"""Reproducible Sessions module for Sindri.

Provides tools for capturing session environment snapshots, replaying
sessions with deterministic tool outputs, and comparing session results.
"""

from sindri.replay.comparator import SessionComparator, SessionComparison, TurnDiff
from sindri.replay.engine import ReplayEngine, ReplayMode, ReplayResult
from sindri.replay.snapshot import SnapshotCapture

__all__ = [
    "SnapshotCapture",
    "ReplayEngine",
    "ReplayMode",
    "ReplayResult",
    "SessionComparator",
    "SessionComparison",
    "TurnDiff",
]
