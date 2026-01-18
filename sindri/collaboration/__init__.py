"""Remote collaboration module for Sindri.

This module provides infrastructure for:
- Session sharing with unique links and permissions
- Real-time presence tracking
- Review comments and annotations
- Collaborative session viewing
- User management (Team Mode)
- Team-based collaboration with roles (Team Mode)
- Notification system for team collaboration
- Activity feed for team activity timeline
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
from sindri.collaboration.notifications import (
    Notification,
    NotificationType,
    NotificationPriority,
    NotificationPreferences,
    NotificationStore,
    notify_mention,
    notify_comment,
    notify_team_invite,
    notify_session_shared,
)
from sindri.collaboration.activity import (
    Activity,
    ActivityType,
    ActivityStore,
    TargetType,
    log_session_created,
    log_session_completed,
    log_session_failed,
    log_member_joined,
    log_member_left,
    log_role_changed,
    log_comment_added,
    log_session_shared,
    log_team_updated,
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
    # Notifications
    "Notification",
    "NotificationType",
    "NotificationPriority",
    "NotificationPreferences",
    "NotificationStore",
    "notify_mention",
    "notify_comment",
    "notify_team_invite",
    "notify_session_shared",
    # Activity Feed
    "Activity",
    "ActivityType",
    "ActivityStore",
    "TargetType",
    "log_session_created",
    "log_session_completed",
    "log_session_failed",
    "log_member_joined",
    "log_member_left",
    "log_role_changed",
    "log_comment_added",
    "log_session_shared",
    "log_team_updated",
]
