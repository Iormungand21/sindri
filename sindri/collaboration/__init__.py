"""Remote collaboration module for Sindri.

This module provides infrastructure for:
- Session sharing with unique links and permissions
- Real-time presence tracking
- Review comments and annotations
- Collaborative session viewing
- User management (Team Mode)
- Team-based collaboration with roles (Team Mode)
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
from sindri.collaboration.users import (
    User,
    UserStore,
)
from sindri.collaboration.teams import (
    Team,
    TeamRole,
    TeamMembership,
    TeamSession,
    TeamStore,
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
    # Users (Team Mode)
    "User",
    "UserStore",
    # Teams (Team Mode)
    "Team",
    "TeamRole",
    "TeamMembership",
    "TeamSession",
    "TeamStore",
]
