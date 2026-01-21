"""Replay engine for Reproducible Sessions."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import structlog

from sindri.persistence.snapshots import (
    EnvironmentSnapshot,
    SnapshotStore,
    ToolOutput,
    ToolOutputStore,
)
from sindri.persistence.state import Session, SessionState

log = structlog.get_logger()


class ReplayMode(Enum):
    """Replay execution modes."""

    FULL = "full"  # Re-run with LLM, compare outputs
    TOOL_ONLY = "tool_only"  # Skip LLM, replay recorded tool calls only


@dataclass
class ReplayResult:
    """Result of a replay execution."""

    source_session_id: str
    mode: ReplayMode
    status: str  # completed, diverged, failed, no_outputs
    replay_session_id: Optional[str] = None
    divergence_point: Optional[int] = None
    divergence_reason: Optional[str] = None
    tool_outputs_replayed: int = 0
    tool_outputs_total: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get replay duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class RecordedToolExecutor:
    """Mock tool executor that returns recorded outputs."""

    def __init__(self, tool_outputs: list[ToolOutput]):
        """Initialize with recorded outputs.

        Args:
            tool_outputs: List of recorded tool outputs
        """
        self._outputs: dict[tuple[int, int], ToolOutput] = {}
        for output in tool_outputs:
            key = (output.turn_index, output.tool_index)
            self._outputs[key] = output

    def get_output(self, turn_index: int, tool_index: int) -> Optional[ToolOutput]:
        """Get recorded output for a tool call.

        Args:
            turn_index: Turn index
            tool_index: Tool call index within turn

        Returns:
            ToolOutput if found, None otherwise
        """
        return self._outputs.get((turn_index, tool_index))

    def has_output(self, turn_index: int, tool_index: int) -> bool:
        """Check if recorded output exists.

        Args:
            turn_index: Turn index
            tool_index: Tool call index within turn

        Returns:
            True if output exists
        """
        return (turn_index, tool_index) in self._outputs

    @property
    def total_outputs(self) -> int:
        """Total number of recorded outputs."""
        return len(self._outputs)


class ReplayEngine:
    """Orchestrates session replay execution."""

    def __init__(
        self,
        session_state: Optional[SessionState] = None,
        snapshot_store: Optional[SnapshotStore] = None,
        tool_output_store: Optional[ToolOutputStore] = None,
    ):
        """Initialize replay engine.

        Args:
            session_state: Session persistence layer
            snapshot_store: Snapshot persistence layer
            tool_output_store: Tool output persistence layer
        """
        self.session_state = session_state or SessionState()
        self.snapshots = snapshot_store or SnapshotStore()
        self.tool_outputs = tool_output_store or ToolOutputStore()

    async def replay(
        self,
        session_id: str,
        mode: ReplayMode = ReplayMode.TOOL_ONLY,
        stop_on_diverge: bool = False,
    ) -> ReplayResult:
        """Replay a session.

        Args:
            session_id: Session ID to replay
            mode: Replay mode (FULL or TOOL_ONLY)
            stop_on_diverge: Stop if outputs diverge (FULL mode only)

        Returns:
            ReplayResult with status and details
        """
        result = ReplayResult(
            source_session_id=session_id,
            mode=mode,
            status="pending",
            started_at=datetime.now(),
        )

        try:
            # Load original session
            session = await self.session_state.load_session(session_id)
            if not session:
                result.status = "failed"
                result.errors.append(f"Session {session_id} not found")
                result.completed_at = datetime.now()
                return result

            # Load snapshot
            snapshot = await self.snapshots.load_snapshot(session_id)
            if not snapshot:
                result.status = "failed"
                result.errors.append(f"No snapshot found for session {session_id}")
                result.completed_at = datetime.now()
                return result

            # Load tool outputs
            tool_outputs = await self.tool_outputs.get_session_outputs(session_id)
            result.tool_outputs_total = len(tool_outputs)

            if not tool_outputs:
                result.status = "no_outputs"
                result.errors.append("No tool outputs recorded for this session")
                result.completed_at = datetime.now()
                return result

            # Execute based on mode
            if mode == ReplayMode.TOOL_ONLY:
                return await self._replay_tool_only(result, session, snapshot, tool_outputs)
            elif mode == ReplayMode.FULL:
                return await self._replay_full(
                    result, session, snapshot, tool_outputs, stop_on_diverge
                )
            else:
                result.status = "failed"
                result.errors.append(f"Unknown replay mode: {mode}")
                result.completed_at = datetime.now()
                return result

        except Exception as e:
            log.exception("replay_failed", session_id=session_id, error=str(e))
            result.status = "failed"
            result.errors.append(str(e))
            result.completed_at = datetime.now()
            return result

    async def _replay_tool_only(
        self,
        result: ReplayResult,
        session: Session,
        snapshot: EnvironmentSnapshot,
        tool_outputs: list[ToolOutput],
    ) -> ReplayResult:
        """Replay using only recorded tool outputs (deterministic).

        This mode doesn't re-run the LLM or tools - it just verifies
        the recorded outputs are available and summarizes them.

        Args:
            result: ReplayResult to populate
            session: Original session
            snapshot: Environment snapshot
            tool_outputs: Recorded tool outputs

        Returns:
            Updated ReplayResult
        """
        executor = RecordedToolExecutor(tool_outputs)

        # In tool-only mode, we just verify all outputs are available
        # and could be used for replay
        replayed_count = 0

        for output in tool_outputs:
            if executor.has_output(output.turn_index, output.tool_index):
                replayed_count += 1
                log.debug(
                    "tool_output_verified",
                    turn_index=output.turn_index,
                    tool_index=output.tool_index,
                    tool_name=output.tool_name,
                    success=output.success,
                )

        result.tool_outputs_replayed = replayed_count
        result.status = "completed"
        result.completed_at = datetime.now()

        log.info(
            "tool_only_replay_completed",
            session_id=session.id,
            outputs_replayed=replayed_count,
            outputs_total=len(tool_outputs),
        )

        return result

    async def _replay_full(
        self,
        result: ReplayResult,
        session: Session,
        snapshot: EnvironmentSnapshot,
        tool_outputs: list[ToolOutput],
        stop_on_diverge: bool,
    ) -> ReplayResult:
        """Full replay with LLM, comparing outputs.

        Note: Full replay requires orchestrator integration which is
        not implemented in this initial version. This provides the
        framework for future implementation.

        Args:
            result: ReplayResult to populate
            session: Original session
            snapshot: Environment snapshot
            tool_outputs: Recorded tool outputs
            stop_on_diverge: Stop if outputs diverge

        Returns:
            Updated ReplayResult
        """
        # Full replay requires deeper integration with the orchestrator
        # For now, we mark this as not implemented
        result.status = "failed"
        result.errors.append(
            "Full replay mode requires orchestrator integration. "
            "Use tool-only mode for deterministic replay."
        )
        result.completed_at = datetime.now()

        log.warning(
            "full_replay_not_implemented",
            session_id=session.id,
        )

        return result

    async def get_replay_info(self, session_id: str) -> dict:
        """Get information about what can be replayed for a session.

        Args:
            session_id: Session ID to check

        Returns:
            Dictionary with replay capability information
        """
        info = {
            "session_id": session_id,
            "has_snapshot": False,
            "has_tool_outputs": False,
            "tool_output_count": 0,
            "replayable": False,
            "snapshot": None,
        }

        # Check for snapshot
        snapshot = await self.snapshots.load_snapshot(session_id)
        if snapshot:
            info["has_snapshot"] = True
            info["snapshot"] = snapshot.to_dict()

        # Check for tool outputs
        output_count = await self.tool_outputs.get_output_count(session_id)
        if output_count > 0:
            info["has_tool_outputs"] = True
            info["tool_output_count"] = output_count

        # Determine if replayable
        info["replayable"] = info["has_snapshot"] and info["has_tool_outputs"]

        return info

    async def validate_environment(
        self, snapshot: EnvironmentSnapshot
    ) -> tuple[bool, list[str]]:
        """Validate current environment against snapshot.

        Args:
            snapshot: Snapshot to validate against

        Returns:
            Tuple of (is_compatible, list of warnings)
        """
        warnings = []

        # Check Sindri version
        from sindri.replay.snapshot import SnapshotCapture

        capture = SnapshotCapture()
        current_version = capture._get_sindri_version()

        if current_version != snapshot.sindri_version:
            warnings.append(
                f"Sindri version mismatch: {current_version} vs {snapshot.sindri_version}"
            )

        # Check Python version
        import sys

        current_python = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        if current_python != snapshot.python_version:
            warnings.append(
                f"Python version mismatch: {current_python} vs {snapshot.python_version}"
            )

        # Model metadata can't be validated without making an API call
        # We could add that check if needed

        is_compatible = len(warnings) == 0
        return is_compatible, warnings
