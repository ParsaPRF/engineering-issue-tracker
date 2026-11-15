"""Attachments: private files owned by a ticket or a comment.

Security-relevant decisions (ADR-010), all enforced here or in ``validators.py``:

* The **storage key is a random UUID plus a sanitised extension**, never the uploaded name.
  Prevents path traversal, collisions and overwriting another user's object, and stops a crafted
  name from being reflected into a URL.
* The **original name is kept only for display** in ``original_name`` and is escaped by the
  frontend; it is never part of the path.
* ``sha256`` allows integrity checks and cheap duplicate detection.
* Deletion is soft at the row level, but the stored object is removed by the service: keeping the
  bytes of a "deleted" attachment is usually a privacy problem, while keeping the metadata row
  keeps the audit trail honest.
"""

from __future__ import annotations

import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import BaseModel


def attachment_upload_to(instance: Attachment, filename: str) -> str:
    """Build a storage key that contains no user-controlled path components.

    Only the extension is reused, and only when it is on the allow-list; anything else yields an
    extension-less key. The random UUID removes the possibility of guessing another object's key.
    """
    _, extension = os.path.splitext(filename or "")
    extension = extension.lower().lstrip(".")
    allowed = getattr(settings, "ATTACHMENT_ALLOWED_EXTENSIONS", [])
    safe_extension = f".{extension}" if extension and extension in allowed else ""
    return f"attachments/{uuid.uuid4().hex}{safe_extension}"


class Attachment(BaseModel):
    """A stored file, anchored to exactly one ticket or comment."""

    ticket = models.ForeignKey(
        "tickets.Ticket",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("ticket"),
    )
    comment = models.ForeignKey(
        "comments.Comment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("comment"),
    )
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_attachments",
        verbose_name=_("uploader"),
    )
    file = models.FileField(_("file"), upload_to=attachment_upload_to, max_length=255)
    original_name = models.CharField(_("original file name"), max_length=255)
    content_type = models.CharField(_("content type"), max_length=100, blank=True)
    size_bytes = models.PositiveBigIntegerField(_("size (bytes)"))
    sha256 = models.CharField(_("sha256 checksum"), max_length=64, blank=True)
    is_deleted = models.BooleanField(_("deleted"), default=False)

    class Meta:
        verbose_name = _("attachment")
        verbose_name_plural = _("attachments")
        ordering = ["-created_at"]
        constraints = [
            # An attachment must hang off something: a file with no anchor would be
            # unreachable through any authorised path and impossible to permission-check.
            models.CheckConstraint(
                condition=models.Q(ticket__isnull=False) | models.Q(comment__isnull=False),
                name="attachment_has_anchor",
            ),
        ]
        indexes = [
            models.Index(fields=["ticket", "is_deleted"], name="attach_ticket_deleted_idx"),
            models.Index(fields=["comment"], name="attach_comment_idx"),
            models.Index(fields=["uploader", "created_at"], name="attach_uploader_created_idx"),
        ]

    def __str__(self) -> str:
        return self.original_name

    def clean(self) -> None:
        super().clean()

        if not self.ticket_id and not self.comment_id:
            raise ValidationError(
                _("An attachment must belong to a ticket or to a comment.")
            )

        # Keep the anchor consistent: an attachment on a comment implicitly belongs to that
        # comment's ticket, which is what the permission check walks.
        if self.comment_id and self.ticket_id and self.comment.ticket_id != self.ticket_id:
            raise ValidationError(
                {"ticket": _("The ticket must match the comment's ticket.")}
            )

    @property
    def effective_ticket(self):
        """The ticket whose project governs access to this file."""
        return self.ticket or (self.comment.ticket if self.comment_id else None)

    @property
    def size_kb(self) -> float:
        return round(self.size_bytes / 1024, 1)
