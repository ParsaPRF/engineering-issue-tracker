"""The audit vocabulary.

One enumeration, used by every module. Keeping the strings centralised means:

* the API can filter by action without a free-text guess,
* the frontend can map an action to an icon/label,
* a typo in a service call raises at review time rather than creating an unmatchable event.

Naming convention: ``<object>.<past_tense_verb>``, lower snake case, e.g. ``ticket.status_changed``.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from common.choices import BaseTextChoices


class AuditAction(BaseTextChoices):
    # --- Identity -----------------------------------------------------------
    USER_REGISTERED = "user.registered", _("User registered")
    USER_LOGGED_IN = "user.logged_in", _("User logged in")
    USER_LOGGED_OUT = "user.logged_out", _("User logged out")
    USER_ACTIVATED = "user.activated", _("User activated")
    USER_DEACTIVATED = "user.deactivated", _("User deactivated")
    USER_ROLE_CHANGED = "user.role_changed", _("System role changed")
    USER_PROFILE_UPDATED = "user.profile_updated", _("Profile updated")

    # --- Projects -----------------------------------------------------------
    PROJECT_CREATED = "project.created", _("Project created")
    PROJECT_UPDATED = "project.updated", _("Project updated")
    PROJECT_ARCHIVED = "project.archived", _("Project archived")
    PROJECT_RESTORED = "project.restored", _("Project restored")
    MEMBERSHIP_ADDED = "membership.added", _("Member added")
    MEMBERSHIP_REACTIVATED = "membership.reactivated", _("Member reactivated")
    MEMBERSHIP_ROLE_CHANGED = "membership.role_changed", _("Member role changed")
    MEMBERSHIP_REMOVED = "membership.removed", _("Member removed")
    COMPONENT_CREATED = "component.created", _("Component created")
    COMPONENT_UPDATED = "component.updated", _("Component updated")
    COMPONENT_DEACTIVATED = "component.deactivated", _("Component deactivated")

    # --- Tickets ------------------------------------------------------------
    TICKET_CREATED = "ticket.created", _("Ticket created")
    TICKET_UPDATED = "ticket.updated", _("Ticket updated")
    TICKET_ASSIGNED = "ticket.assigned", _("Ticket assigned")
    TICKET_REASSIGNED = "ticket.reassigned", _("Ticket reassigned")
    TICKET_UNASSIGNED = "ticket.unassigned", _("Ticket unassigned")
    TICKET_STATUS_CHANGED = "ticket.status_changed", _("Ticket status changed")
    TICKET_LABELS_CHANGED = "ticket.labels_changed", _("Ticket labels changed")

    # --- Collaboration ------------------------------------------------------
    COMMENT_CREATED = "comment.created", _("Comment created")
    COMMENT_UPDATED = "comment.updated", _("Comment updated")
    COMMENT_DELETED = "comment.deleted", _("Comment deleted")
    ATTACHMENT_UPLOADED = "attachment.uploaded", _("Attachment uploaded")
    ATTACHMENT_DOWNLOADED = "attachment.downloaded", _("Attachment downloaded")
    ATTACHMENT_DELETED = "attachment.deleted", _("Attachment deleted")


#: Actions that are recorded for security review but should not flood the activity feed.
SECURITY_SENSITIVE_ACTIONS = frozenset(
    {
        AuditAction.USER_LOGGED_IN,
        AuditAction.USER_LOGGED_OUT,
        AuditAction.USER_DEACTIVATED,
        AuditAction.USER_ROLE_CHANGED,
        AuditAction.ATTACHMENT_DOWNLOADED,
    }
)
