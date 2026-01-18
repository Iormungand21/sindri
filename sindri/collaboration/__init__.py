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
- Webhooks for external integrations
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
from sindri.collaboration.webhooks import (
    Webhook,
    WebhookEventType,
    WebhookFormat,
    WebhookDelivery,
    DeliveryStatus,
    WebhookStore,
    WebhookDeliveryService,
    trigger_webhook_event,
    verify_webhook_signature,
)
from sindri.collaboration.audit import (
    AuditLogEntry,
    AuditCategory,
    AuditAction,
    AuditSeverity,
    AuditOutcome,
    AuditQuery,
    AuditStore,
    audit_login_success,
    audit_login_failed,
    audit_logout,
    audit_permission_change,
    audit_role_change,
    audit_session_access,
    audit_access_denied,
    audit_suspicious_activity,
    audit_brute_force_detected,
    check_brute_force,
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
    # Webhooks
    "Webhook",
    "WebhookEventType",
    "WebhookFormat",
    "WebhookDelivery",
    "DeliveryStatus",
    "WebhookStore",
    "WebhookDeliveryService",
    "trigger_webhook_event",
    "verify_webhook_signature",
    # Audit Logging
    "AuditLogEntry",
    "AuditCategory",
    "AuditAction",
    "AuditSeverity",
    "AuditOutcome",
    "AuditQuery",
    "AuditStore",
    "audit_login_success",
    "audit_login_failed",
    "audit_logout",
    "audit_permission_change",
    "audit_role_change",
    "audit_session_access",
    "audit_access_denied",
    "audit_suspicious_activity",
    "audit_brute_force_detected",
    "check_brute_force",
]
