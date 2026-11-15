"""Comment services.

Edit and delete rules (FR-6.2, FR-6.3) are business rules, not UI hints, so they live here:

* an author may edit **within a window** (``COMMENT_EDIT_WINDOW_MINUTES``) — after that the comment is
  part of the record and a correction should be a new comment, which is honest about what changed;
* an author may withdraw their own comment (soft delete);
* project managers and Admins may *moderate* (soft delete) any comment, but nobody may rewrite
  somebody else's words — moderating by editing would make the timeline a fiction.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.actions import AuditAction
from apps.audit.services import record as audit_record
from apps.comments.models import Comment
from apps.notifications.services import notify_comment_added
from apps.projects.permissions import can_comment, can_delete_comment, can_edit_comment, can_view_ticket
from apps.tickets.models import Ticket
from common.exceptions import AccessDenied, InvariantViolation


def _edit_deadline(comment: Comment):
    minutes = int(getattr(settings, "COMMENT_EDIT_WINDOW_MINUTES", 30))
    return comment.created_at + timedelta(minutes=minutes)


@transaction.atomic
def create_comment(*, actor, ticket: Ticket, body: str, request=None) -> Comment:
    """Add a comment to a ticket the actor can see (FR-6.1)."""
    if not can_view_ticket(actor, ticket):
        # Foreign tickets are reported as not found by the API layer; the service refuses too.
        raise AccessDenied("You cannot comment on this ticket.")
    if not can_comment(actor, ticket):
        raise AccessDenied("You cannot comment on this ticket.")

    comment = Comment(ticket=ticket, author=actor, body=(body or "").strip())
    comment.full_clean()
    comment.save()

    audit_record(
        action=AuditAction.COMMENT_CREATED,
        actor=actor,
        obj=comment,
        project=ticket.project,
        ticket=ticket,
        metadata={"comment_id": str(comment.pk), "length": len(comment.body)},
        request=request,
    )
    notify_comment_added(comment=comment, actor=actor)
    return comment


@transaction.atomic
def update_comment(*, actor, comment: Comment, body: str, request=None) -> Comment:
    """Edit a comment, if the actor is its author and the window is still open."""
    if not can_view_ticket(actor, comment.ticket):
        raise AccessDenied("You cannot edit this comment.")
    if not can_edit_comment(actor, comment):
        raise AccessDenied("Only the author can edit a comment.")
    if comment.is_deleted:
        raise InvariantViolation("This comment was deleted.", code="comment_deleted")
    if timezone.now() > _edit_deadline(comment):
        raise InvariantViolation(
            "The edit window for this comment has closed; add a new comment instead.",
            code="edit_window_closed",
        )

    text = (body or "").strip()
    if not text:
        raise InvariantViolation(
            "A comment cannot be empty.", code="validation_error", fields={"body": ["This field is required."]}
        )
    if text == comment.body:
        return comment

    comment.body = text
    comment.edited_at = timezone.now()
    comment.full_clean()
    comment.save(update_fields=["body", "edited_at", "updated_at"])

    audit_record(
        action=AuditAction.COMMENT_UPDATED,
        actor=actor,
        obj=comment,
        project=comment.ticket.project,
        ticket=comment.ticket,
        metadata={"comment_id": str(comment.pk)},
        request=request,
    )
    return comment


@transaction.atomic
def delete_comment(*, actor, comment: Comment, request=None) -> Comment:
    """Soft-delete a comment (author, project manager, or Admin).

    Soft, not hard: the audit trail references the comment id, and a resurfacing attachment's
    permission path runs through the comment's ticket.
    """
    if not can_view_ticket(actor, comment.ticket):
        raise AccessDenied("You cannot delete this comment.")
    if not can_delete_comment(actor, comment):
        raise AccessDenied("You cannot delete this comment.")
    if comment.is_deleted:
        raise InvariantViolation("This comment is already deleted.", code="already_deleted")

    comment.is_deleted = True
    comment.save(update_fields=["is_deleted", "updated_at"])

    audit_record(
        action=AuditAction.COMMENT_DELETED,
        actor=actor,
        obj=comment,
        project=comment.ticket.project,
        ticket=comment.ticket,
        # Whether the actor was the author or a moderator is the interesting audit fact.
        metadata={"comment_id": str(comment.pk), "as_moderator": comment.author_id != actor.pk},
        request=request,
    )
    return comment