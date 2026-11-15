"""Comments: the discussion attached to a ticket.

Deletion is **soft** (``is_deleted``). A hard delete would either destroy history that the audit
trail references, or force ``on_delete=SET_NULL`` everywhere and leave anonymous remarks. A soft
delete keeps the row, hides it from the API, and lets moderators see what was removed.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import BaseModel

MAX_COMMENT_LENGTH = 10_000


class Comment(BaseModel):
    ticket = models.ForeignKey(
        "tickets.Ticket",
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name=_("ticket"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="comments",
        verbose_name=_("author"),
    )
    body = models.TextField(_("body"), max_length=MAX_COMMENT_LENGTH)
    is_deleted = models.BooleanField(
        _("deleted"),
        default=False,
        help_text=_("Soft deletion: the row is retained so history stays traceable."),
    )
    edited_at = models.DateTimeField(
        _("edited at"), null=True, blank=True, help_text=_("Set when the author edits the body.")
    )

    class Meta:
        verbose_name = _("comment")
        verbose_name_plural = _("comments")
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["ticket", "created_at"], name="comment_ticket_created_idx"),
            models.Index(fields=["ticket", "is_deleted"], name="comment_ticket_deleted_idx"),
        ]

    def __str__(self) -> str:
        return f"Comment by {self.author_id} on {self.ticket_id}"

    def clean(self) -> None:
        super().clean()
        body = (self.body or "").strip()
        if not body:
            raise ValidationError({"body": _("A comment cannot be empty.")})
        if len(body) > MAX_COMMENT_LENGTH:
            raise ValidationError(
                {"body": _("Comments are limited to %(max)s characters.") % {"max": MAX_COMMENT_LENGTH}}
            )

    @property
    def is_edited(self) -> bool:
        return self.edited_at is not None
