"""Remote collaboration module for Sindri.

This module provides infrastructure for:
- Session sharing with unique links and permissions
- Real-time presence tracking
- Review comments and annotations
- Collaborative session viewing
"""

from sindri.collaboration.sharing import (
    SessionShare,
    SharePermission,
    ShareStore,
)
from sindri.collaboration.comments import (
    SessionComment,
    CommentType,
    CommentStatus,
    CommentStore,
)
from sindri.collaboration.presence import (
    Participant,
    PresenceManager,
)

__all__ = [
    # Sharing
    "SessionShare",
    "SharePermission",
    "ShareStore",
    # Comments
    "SessionComment",
    "CommentType",
    "CommentStatus",
    "CommentStore",
    # Presence
    "Participant",
    "PresenceManager",
]
