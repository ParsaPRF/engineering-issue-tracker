"""Attachment read queries. Visibility always follows the owning ticket's project."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.attachments.models import Attachment
from apps.tickets.selectors.tickets import visible_tickets


def visible_attachments(actor) -> QuerySet[Attachment]:
    """Attachments on tickets the actor can see, whether anchored to the ticket or to a comment.

    The ``Q`` expression matters: an attachment hanging off a comment has ``ticket = NULL`` and is
    reachable only through ``comment__ticket``. Filtering solely on ``ticket__in=...`` would silently
    hide every comment attachment — a bug that looks like "the file did not upload".
    """
    tickets = visible_tickets(actor)
    return (
        Attachment.objects.filter(is_deleted=False)
        .filter(Q(ticket__in=tickets) | Q(comment__ticket__in=tickets))
        .select_related("uploader", "ticket", "comment", "comment__ticket")
    )


def for_ticket(actor, ticket) -> QuerySet[Attachment]:
    """Attachments listed on the ticket page: those attached to the ticket itself."""
    if ticket is None:
        return Attachment.objects.none()
    return (
        Attachment.objects.filter(ticket=ticket, is_deleted=False)
        .select_related("uploader")
        .order_by("-created_at")
    )


def get_visible_attachment(actor, attachment_id) -> Attachment | None:
    """Fetch an attachment the actor may read; anything else returns ``None`` → 404.

    Deleted attachments are excluded here rather than only in list endpoints. Filtering in the list
    view alone would leave the download endpoint serving a soft-deleted file to anyone who kept the
    URL — the exact "deleted but still reachable" hole this check exists to close.
    """
    attachment = (
        Attachment.objects.filter(id=attachment_id, is_deleted=False)
        .select_related("ticket", "comment", "comment__ticket", "uploader")
        .first()
    )
    if attachment is None:
        return None
    ticket = attachment.effective_ticket
    if ticket is None:
        return None
    if not visible_tickets(actor).filter(pk=ticket.pk).exists():
        return None
    return attachment


def comment_attachments(comment) -> QuerySet[Attachment]:
    return Attachment.objects.filter(comment=comment, is_deleted=False).select_related("uploader")