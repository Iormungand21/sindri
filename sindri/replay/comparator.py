"""Session comparison for Reproducible Sessions."""

import difflib
from dataclasses import dataclass, field
from typing import Optional

import structlog

from sindri.persistence.snapshots import EnvironmentSnapshot, SnapshotStore
from sindri.persistence.state import Session, SessionState, Turn

log = structlog.get_logger()


@dataclass
class TurnDiff:
    """Difference between two turns."""

    turn_index: int
    role: str
    content_diff: Optional[str] = None  # unified diff of content
    content_match: bool = True
    tool_calls_match: bool = True
    tool_calls_diff: list[dict] = field(default_factory=list)
    similarity_score: float = 1.0  # 0.0 to 1.0

    @property
    def is_identical(self) -> bool:
        """Check if turns are identical."""
        return self.content_match and self.tool_calls_match


@dataclass
class EnvironmentDiff:
    """Differences in environment snapshots."""

    sindri_version: Optional[tuple[str, str]] = None
    python_version: Optional[tuple[str, str]] = None
    ollama_version: Optional[tuple[str, str]] = None
    model_name: Optional[tuple[str, str]] = None
    model_quantization: Optional[tuple[str, str]] = None
    model_digest: Optional[tuple[str, str]] = None

    @property
    def has_differences(self) -> bool:
        """Check if there are any environment differences."""
        return any([
            self.sindri_version,
            self.python_version,
            self.ollama_version,
            self.model_name,
            self.model_quantization,
            self.model_digest,
        ])

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {}
        if self.sindri_version:
            result["sindri_version"] = self.sindri_version
        if self.python_version:
            result["python_version"] = self.python_version
        if self.ollama_version:
            result["ollama_version"] = self.ollama_version
        if self.model_name:
            result["model_name"] = self.model_name
        if self.model_quantization:
            result["model_quantization"] = self.model_quantization
        if self.model_digest:
            result["model_digest"] = self.model_digest
        return result


@dataclass
class SessionComparison:
    """Comparison result between two sessions."""

    session1_id: str
    session2_id: str
    session1_task: str
    session2_task: str
    env_diff: EnvironmentDiff
    turn_diffs: list[TurnDiff]
    overall_similarity: float  # 0.0 to 1.0
    turns_compared: int
    turns_identical: int
    summary: str

    @property
    def are_identical(self) -> bool:
        """Check if sessions are identical."""
        return self.overall_similarity == 1.0


class SessionComparator:
    """Compare two sessions for differences."""

    def __init__(
        self,
        snapshot_store: Optional[SnapshotStore] = None,
        session_state: Optional[SessionState] = None,
    ):
        """Initialize comparator.

        Args:
            snapshot_store: Snapshot persistence layer
            session_state: Session persistence layer
        """
        self.snapshots = snapshot_store or SnapshotStore()
        self.sessions = session_state or SessionState()

    async def compare(
        self, session1_id: str, session2_id: str
    ) -> SessionComparison:
        """Compare two sessions.

        Args:
            session1_id: First session ID
            session2_id: Second session ID

        Returns:
            SessionComparison with detailed differences
        """
        # Load both sessions
        s1 = await self.sessions.load_session(session1_id)
        s2 = await self.sessions.load_session(session2_id)

        if not s1:
            raise ValueError(f"Session {session1_id} not found")
        if not s2:
            raise ValueError(f"Session {session2_id} not found")

        # Load snapshots (may be None)
        snap1 = await self.snapshots.load_snapshot(session1_id)
        snap2 = await self.snapshots.load_snapshot(session2_id)

        # Compare environments
        env_diff = self._compare_environments(snap1, snap2)

        # Compare turns
        turn_diffs = self._compare_turns(s1.turns, s2.turns)

        # Calculate overall similarity
        overall = self._calculate_similarity(turn_diffs)

        # Count identical turns
        turns_identical = sum(1 for td in turn_diffs if td.is_identical)

        # Generate summary
        summary = self._generate_summary(s1, s2, env_diff, turn_diffs, overall)

        comparison = SessionComparison(
            session1_id=session1_id,
            session2_id=session2_id,
            session1_task=s1.task,
            session2_task=s2.task,
            env_diff=env_diff,
            turn_diffs=turn_diffs,
            overall_similarity=overall,
            turns_compared=len(turn_diffs),
            turns_identical=turns_identical,
            summary=summary,
        )

        log.info(
            "sessions_compared",
            session1=session1_id,
            session2=session2_id,
            similarity=overall,
            turns_compared=len(turn_diffs),
        )

        return comparison

    def _compare_environments(
        self,
        snap1: Optional[EnvironmentSnapshot],
        snap2: Optional[EnvironmentSnapshot],
    ) -> EnvironmentDiff:
        """Compare environment snapshots.

        Args:
            snap1: First snapshot (may be None)
            snap2: Second snapshot (may be None)

        Returns:
            EnvironmentDiff with differences
        """
        diff = EnvironmentDiff()

        if not snap1 or not snap2:
            return diff

        if snap1.sindri_version != snap2.sindri_version:
            diff.sindri_version = (snap1.sindri_version, snap2.sindri_version)

        if snap1.python_version != snap2.python_version:
            diff.python_version = (snap1.python_version, snap2.python_version)

        if snap1.ollama_version != snap2.ollama_version:
            diff.ollama_version = (
                snap1.ollama_version or "unknown",
                snap2.ollama_version or "unknown",
            )

        if snap1.model_metadata.name != snap2.model_metadata.name:
            diff.model_name = (
                snap1.model_metadata.name,
                snap2.model_metadata.name,
            )

        if snap1.model_metadata.quantization_level != snap2.model_metadata.quantization_level:
            diff.model_quantization = (
                snap1.model_metadata.quantization_level,
                snap2.model_metadata.quantization_level,
            )

        if snap1.model_metadata.digest != snap2.model_metadata.digest:
            # Truncate digests for readability
            d1 = snap1.model_metadata.digest[:12] if snap1.model_metadata.digest else "none"
            d2 = snap2.model_metadata.digest[:12] if snap2.model_metadata.digest else "none"
            diff.model_digest = (d1, d2)

        return diff

    def _compare_turns(
        self, turns1: list[Turn], turns2: list[Turn]
    ) -> list[TurnDiff]:
        """Compare turns between two sessions.

        Args:
            turns1: Turns from first session
            turns2: Turns from second session

        Returns:
            List of TurnDiff objects
        """
        diffs = []
        max_turns = max(len(turns1), len(turns2))

        for i in range(max_turns):
            t1 = turns1[i] if i < len(turns1) else None
            t2 = turns2[i] if i < len(turns2) else None

            if t1 is None or t2 is None:
                # One session is shorter
                diffs.append(TurnDiff(
                    turn_index=i,
                    role=t1.role if t1 else t2.role,
                    content_match=False,
                    tool_calls_match=t1 is None and t2 is None,
                    similarity_score=0.0 if (t1 is None) != (t2 is None) else 1.0,
                ))
                continue

            # Compare content
            content_match = t1.content == t2.content
            content_diff = None
            similarity = 1.0

            if not content_match:
                # Generate unified diff
                diff_lines = list(difflib.unified_diff(
                    t1.content.splitlines(keepends=True),
                    t2.content.splitlines(keepends=True),
                    fromfile=f"session1/turn{i}",
                    tofile=f"session2/turn{i}",
                    lineterm="",
                ))
                content_diff = "".join(diff_lines)

                # Calculate similarity using SequenceMatcher
                similarity = difflib.SequenceMatcher(
                    None, t1.content, t2.content
                ).ratio()

            # Compare tool calls
            tool_calls_match = self._compare_tool_calls(t1.tool_calls, t2.tool_calls)
            tool_calls_diff = []

            if not tool_calls_match:
                tool_calls_diff = self._get_tool_calls_diff(
                    t1.tool_calls, t2.tool_calls
                )
                # Reduce similarity if tool calls differ
                similarity *= 0.8

            diffs.append(TurnDiff(
                turn_index=i,
                role=t1.role,
                content_diff=content_diff,
                content_match=content_match,
                tool_calls_match=tool_calls_match,
                tool_calls_diff=tool_calls_diff,
                similarity_score=similarity,
            ))

        return diffs

    def _compare_tool_calls(
        self,
        tc1: Optional[list],
        tc2: Optional[list],
    ) -> bool:
        """Compare tool calls for equality.

        Args:
            tc1: Tool calls from first turn
            tc2: Tool calls from second turn

        Returns:
            True if tool calls are equivalent
        """
        if tc1 is None and tc2 is None:
            return True
        if tc1 is None or tc2 is None:
            return False
        if len(tc1) != len(tc2):
            return False

        for call1, call2 in zip(tc1, tc2):
            # Compare tool names
            name1 = self._get_tool_name(call1)
            name2 = self._get_tool_name(call2)
            if name1 != name2:
                return False

            # Compare arguments
            args1 = self._get_tool_args(call1)
            args2 = self._get_tool_args(call2)
            if args1 != args2:
                return False

        return True

    def _get_tool_name(self, tool_call: dict) -> str:
        """Extract tool name from tool call."""
        if "function" in tool_call:
            return tool_call["function"].get("name", "")
        return tool_call.get("name", "")

    def _get_tool_args(self, tool_call: dict) -> dict:
        """Extract tool arguments from tool call."""
        if "function" in tool_call:
            return tool_call["function"].get("arguments", {})
        return tool_call.get("arguments", {})

    def _get_tool_calls_diff(
        self,
        tc1: Optional[list],
        tc2: Optional[list],
    ) -> list[dict]:
        """Get detailed diff of tool calls.

        Args:
            tc1: Tool calls from first turn
            tc2: Tool calls from second turn

        Returns:
            List of diff entries
        """
        diffs = []
        tc1 = tc1 or []
        tc2 = tc2 or []

        max_calls = max(len(tc1), len(tc2))
        for i in range(max_calls):
            c1 = tc1[i] if i < len(tc1) else None
            c2 = tc2[i] if i < len(tc2) else None

            if c1 is None:
                diffs.append({"type": "added", "index": i, "call": c2})
            elif c2 is None:
                diffs.append({"type": "removed", "index": i, "call": c1})
            elif self._get_tool_name(c1) != self._get_tool_name(c2):
                diffs.append({
                    "type": "name_changed",
                    "index": i,
                    "from": self._get_tool_name(c1),
                    "to": self._get_tool_name(c2),
                })
            elif self._get_tool_args(c1) != self._get_tool_args(c2):
                diffs.append({
                    "type": "args_changed",
                    "index": i,
                    "tool": self._get_tool_name(c1),
                    "from": self._get_tool_args(c1),
                    "to": self._get_tool_args(c2),
                })

        return diffs

    def _calculate_similarity(self, turn_diffs: list[TurnDiff]) -> float:
        """Calculate overall similarity score.

        Args:
            turn_diffs: List of turn differences

        Returns:
            Similarity score from 0.0 to 1.0
        """
        if not turn_diffs:
            return 1.0

        total_score = sum(td.similarity_score for td in turn_diffs)
        return total_score / len(turn_diffs)

    def _generate_summary(
        self,
        s1: Session,
        s2: Session,
        env_diff: EnvironmentDiff,
        turn_diffs: list[TurnDiff],
        overall: float,
    ) -> str:
        """Generate human-readable comparison summary.

        Args:
            s1: First session
            s2: Second session
            env_diff: Environment differences
            turn_diffs: Turn differences
            overall: Overall similarity

        Returns:
            Summary string
        """
        parts = []

        # Overall assessment
        if overall >= 0.99:
            parts.append("Sessions are nearly identical.")
        elif overall >= 0.9:
            parts.append(f"Sessions are highly similar ({overall:.1%} match).")
        elif overall >= 0.7:
            parts.append(f"Sessions are moderately similar ({overall:.1%} match).")
        elif overall >= 0.5:
            parts.append(f"Sessions have significant differences ({overall:.1%} match).")
        else:
            parts.append(f"Sessions are very different ({overall:.1%} match).")

        # Turn count
        if len(s1.turns) != len(s2.turns):
            parts.append(
                f"Turn count differs: {len(s1.turns)} vs {len(s2.turns)}."
            )
        else:
            identical = sum(1 for td in turn_diffs if td.is_identical)
            parts.append(
                f"{identical}/{len(turn_diffs)} turns are identical."
            )

        # Environment differences
        if env_diff.has_differences:
            env_parts = []
            if env_diff.sindri_version:
                env_parts.append("Sindri version")
            if env_diff.python_version:
                env_parts.append("Python version")
            if env_diff.model_quantization:
                env_parts.append("model quantization")
            if env_diff.model_digest:
                env_parts.append("model digest")
            if env_parts:
                parts.append(f"Environment differs: {', '.join(env_parts)}.")

        return " ".join(parts)
