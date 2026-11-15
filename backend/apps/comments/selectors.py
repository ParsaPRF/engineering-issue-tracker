"""Comment read queries."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.comments.models import Comment


def ticket_comments(ticket, *, include_deleted: bool = False) -> QuerySet[Comment]:
    """The ticket's discussion, oldest first.

    ``select_related("author")`` because every rendered comment shows its author; without it the
    endpoint would issue one query per comment. Deleted comments are excluded by default: they are
    retained for the record, not for reading.
    """
    queryset = Comment.objects.filter(ticket=ticket).select_related("author", "author__profile")
    if not include_deleted:
        queryset = queryset.filter(is_deleted=False)
    return queryset.prefetch_related("attachments").order_by("created_at")


def get_visible_comment(actor, comment_id):
    """Fetch a comment only if its ticket is visible to the actor."""
    from apps.tickets.selectors.tickets import get_visible_ticket

    comment = Comment.objects.filter(pk=comment_id).select_related("ticket", "author").first()
    if comment is None:
        return None
    if get_visible_ticket(actor, comment.ticket_id) is None:
        return None
    return comment


def comment_count(ticket) -> int:
    return Comment.objects.filter(ticket=ticket, is_deleted=False).count()