"""Presence tracking for real-time collaboration.

This module provides infrastructure for tracking who is currently
viewing or interacting with a session, enabling real-time awareness
of other participants.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Any, Callable, Awaitable
from enum import Enum
import structlog

log = structlog.get_logger()


class ParticipantStatus(str, Enum):
    """Status of a participant in a session."""

    VIEWING = "viewing"  # Just watching
    ACTIVE = "active"  # Recently interacted
    IDLE = "idle"  # Connected but inactive
    TYPING = "typing"  # Currently typing (for comments)


@dataclass
class Participant:
    """A participant in a collaborative session.

    Attributes:
        user_id: Unique identifier for the user
        display_name: Name to show in UI
        session_id: Session they're in
        status: Current activity status
        cursor_position: Where they're looking (turn index, line number)
        color: Assigned color for UI highlighting
        joined_at: When they joined
        last_activity: When they were last active
    """

    user_id: str
    display_name: str
    session_id: str
    status: ParticipantStatus = ParticipantStatus.VIEWING
    cursor_turn: Optional[int] = None
    cursor_line: Optional[int] = None
    color: Optional[str] = None
    joined_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    @property
    def is_idle(self) -> bool:
        """Check if participant has been idle for more than 5 minutes."""
        return (datetime.now() - self.last_activity) > timedelta(minutes=5)

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now()
        if self.status == ParticipantStatus.IDLE:
            self.status = ParticipantStatus.ACTIVE

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "session_id": self.session_id,
            "status": self.status.value,
            "cursor_turn": self.cursor_turn,
            "cursor_line": self.cursor_line,
            "color": self.color,
            "joined_at": self.joined_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "is_idle": self.is_idle,
        }


# Color palette for participant highlighting
PARTICIPANT_COLORS = [
    "#FF6B6B",  # Red
    "#4ECDC4",  # Teal
    "#45B7D1",  # Blue
    "#96CEB4",  # Green
    "#FFEAA7",  # Yellow
    "#DDA0DD",  # Plum
    "#98D8C8",  # Mint
    "#F7DC6F",  # Gold
    "#BB8FCE",  # Purple
    "#85C1E9",  # Light Blue
]


class PresenceManager:
    """Manages real-time presence tracking for collaborative sessions.

    This is an in-memory manager - presence data is not persisted to database.
    Each server instance maintains its own presence state.
    """

    def __init__(
        self,
        idle_timeout_minutes: int = 5,
        cleanup_interval_seconds: int = 60,
    ):
        """Initialize presence manager.

        Args:
            idle_timeout_minutes: Minutes of inactivity before marking idle
            cleanup_interval_seconds: How often to clean up disconnected users
        """
        self.idle_timeout = timedelta(minutes=idle_timeout_minutes)
        self.cleanup_interval = cleanup_interval_seconds

        # session_id -> {user_id -> Participant}
        self._sessions: dict[str, dict[str, Participant]] = {}

        # user_id -> session_id (for quick lookup)
        self._user_sessions: dict[str, str] = {}

        # Callbacks for presence changes
        self._on_join_callbacks: list[Callable[[Participant], Awaitable[None]]] = []
        self._on_leave_callbacks: list[Callable[[Participant], Awaitable[None]]] = []
        self._on_update_callbacks: list[Callable[[Participant], Awaitable[None]]] = []

        # Color assignment counter per session
        self._color_counters: dict[str, int] = {}

        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None

    def start_cleanup_task(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            log.info("presence_cleanup_started")

    def stop_cleanup_task(self) -> None:
        """Stop the background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            log.info("presence_cleanup_stopped")

    async def _cleanup_loop(self) -> None:
        """Background task to clean up idle participants."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._mark_idle_participants()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("presence_cleanup_error", error=str(e))

    async def _mark_idle_participants(self) -> None:
        """Mark participants as idle if they've been inactive."""
        now = datetime.now()

        for session_id, participants in list(self._sessions.items()):
            for user_id, participant in list(participants.items()):
                if (now - participant.last_activity) > self.idle_timeout:
                    if participant.status != ParticipantStatus.IDLE:
                        participant.status = ParticipantStatus.IDLE
                        await self._notify_update(participant)
                        log.debug(
                            "participant_marked_idle",
                            user_id=user_id,
                            session_id=session_id,
                        )

    def _assign_color(self, session_id: str) -> str:
        """Assign a color to a new participant in a session."""
        if session_id not in self._color_counters:
            self._color_counters[session_id] = 0

        color = PARTICIPANT_COLORS[
            self._color_counters[session_id] % len(PARTICIPANT_COLORS)
        ]
        self._color_counters[session_id] += 1
        return color

    async def join_session(
        self,
        session_id: str,
        user_id: str,
        display_name: str,
    ) -> Participant:
        """Add a participant to a session.

        Args:
            session_id: Session to join
            user_id: Unique user identifier
            display_name: Name to display

        Returns:
            The created Participant
        """
        # Leave any existing session first
        if user_id in self._user_sessions:
            await self.leave_session(user_id)

        # Create participant
        participant = Participant(
            user_id=user_id,
            display_name=display_name,
            session_id=session_id,
            color=self._assign_color(session_id),
        )

        # Add to tracking
        if session_id not in self._sessions:
            self._sessions[session_id] = {}

        self._sessions[session_id][user_id] = participant
        self._user_sessions[user_id] = session_id

        await self._notify_join(participant)

        log.info(
            "participant_joined",
            user_id=user_id,
            session_id=session_id,
            display_name=display_name,
        )

        return participant

    async def leave_session(self, user_id: str) -> Optional[Participant]:
        """Remove a participant from their session.

        Args:
            user_id: User to remove

        Returns:
            The removed Participant, or None if not found
        """
        if user_id not in self._user_sessions:
            return None

        session_id = self._user_sessions[user_id]

        if session_id in self._sessions and user_id in self._sessions[session_id]:
            participant = self._sessions[session_id].pop(user_id)
            del self._user_sessions[user_id]

            # Clean up empty sessions
            if not self._sessions[session_id]:
                del self._sessions[session_id]
                if session_id in self._color_counters:
                    del self._color_counters[session_id]

            await self._notify_leave(participant)

            log.info(
                "participant_left",
                user_id=user_id,
                session_id=session_id,
            )

            return participant

        return None

    async def update_cursor(
        self,
        user_id: str,
        turn_index: Optional[int],
        line_number: Optional[int] = None,
    ) -> Optional[Participant]:
        """Update a participant's cursor position.

        Args:
            user_id: User to update
            turn_index: Turn they're viewing
            line_number: Line within turn (optional)

        Returns:
            Updated Participant, or None if not found
        """
        participant = self.get_participant(user_id)
        if not participant:
            return None

        participant.cursor_turn = turn_index
        participant.cursor_line = line_number
        participant.touch()

        await self._notify_update(participant)

        return participant

    async def update_status(
        self,
        user_id: str,
        status: ParticipantStatus,
    ) -> Optional[Participant]:
        """Update a participant's status.

        Args:
            user_id: User to update
            status: New status

        Returns:
            Updated Participant, or None if not found
        """
        participant = self.get_participant(user_id)
        if not participant:
            return None

        participant.status = status
        participant.touch()

        await self._notify_update(participant)

        return participant

    def get_participant(self, user_id: str) -> Optional[Participant]:
        """Get a participant by user ID.

        Args:
            user_id: User to look up

        Returns:
            Participant if found, None otherwise
        """
        if user_id not in self._user_sessions:
            return None

        session_id = self._user_sessions[user_id]
        return self._sessions.get(session_id, {}).get(user_id)

    def get_session_participants(self, session_id: str) -> list[Participant]:
        """Get all participants in a session.

        Args:
            session_id: Session to get participants for

        Returns:
            List of Participants
        """
        if session_id not in self._sessions:
            return []

        return list(self._sessions[session_id].values())

    def get_session_count(self, session_id: str) -> int:
        """Get the number of participants in a session.

        Args:
            session_id: Session to count

        Returns:
            Number of participants
        """
        return len(self._sessions.get(session_id, {}))

    def get_all_sessions(self) -> dict[str, int]:
        """Get all sessions with participant counts.

        Returns:
            Dict mapping session_id to participant count
        """
        return {
            session_id: len(participants)
            for session_id, participants in self._sessions.items()
        }

    def on_join(self, callback: Callable[[Participant], Awaitable[None]]) -> None:
        """Register a callback for when a participant joins."""
        self._on_join_callbacks.append(callback)

    def on_leave(self, callback: Callable[[Participant], Awaitable[None]]) -> None:
        """Register a callback for when a participant leaves."""
        self._on_leave_callbacks.append(callback)

    def on_update(self, callback: Callable[[Participant], Awaitable[None]]) -> None:
        """Register a callback for when a participant's status changes."""
        self._on_update_callbacks.append(callback)

    async def _notify_join(self, participant: Participant) -> None:
        """Notify callbacks of a participant joining."""
        for callback in self._on_join_callbacks:
            try:
                await callback(participant)
            except Exception as e:
                log.error("presence_callback_error", type="join", error=str(e))

    async def _notify_leave(self, participant: Participant) -> None:
        """Notify callbacks of a participant leaving."""
        for callback in self._on_leave_callbacks:
            try:
                await callback(participant)
            except Exception as e:
                log.error("presence_callback_error", type="leave", error=str(e))

    async def _notify_update(self, participant: Participant) -> None:
        """Notify callbacks of a participant status change."""
        for callback in self._on_update_callbacks:
            try:
                await callback(participant)
            except Exception as e:
                log.error("presence_callback_error", type="update", error=str(e))

    def get_stats(self) -> dict[str, Any]:
        """Get presence statistics.

        Returns:
            Dictionary with presence statistics
        """
        total_participants = sum(len(p) for p in self._sessions.values())
        active_sessions = len(self._sessions)

        status_counts: dict[str, int] = {}
        for session in self._sessions.values():
            for participant in session.values():
                status = participant.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_participants": total_participants,
            "active_sessions": active_sessions,
            "status_breakdown": status_counts,
        }
