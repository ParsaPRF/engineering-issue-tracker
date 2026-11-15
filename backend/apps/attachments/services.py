"""Attachment services: upload, delete, and the storage lifecycle around them.

The interesting engineering here is *ordering*:

* on upload, the file is written before the row is committed — a row pointing at a missing object is
  worse than an orphaned object;
* on delete, the row is flagged **first** and the stored object is removed only after the transaction
  commits (``transaction.on_commit``). Deleting bytes inside the transaction would leave a row that
  survived a rollback pointing at nothing at all.
"""

from __future__ import annotations

import logging

from django.db import transaction

from apps.attachments.models import Attachment
from apps.attachments.validators import compute_sha256, get_extension, validate_upload
from apps.audit.actions import AuditAction
from apps.audit.services import record as audit_record
from apps.comments.models import Comment
from apps.projects.permissions import can_attach_to_ticket, can_delete_attachment, can_view_ticket
from apps.tickets.models import Ticket
from common.exceptions import AccessDenied, InvariantViolation

logger = logging.getLogger(__name__)


@transaction.atomic
def upload_attachment(
    *,
    actor,
    uploaded_file,
    ticket: Ticket,
    comment: Comment | None = None,
    request=None,
) -> Attachment:
    """Store a validated file against a ticket, or against one of its comments (FR-6.5, FR-6.6)."""
    if not can_view_ticket(actor, ticket):
        raise AccessDenied("You cannot attach files to this ticket.")
    if not can_attach_to_ticket(actor, ticket):
        raise AccessDenied("You cannot attach files to this ticket.")
    if comment is not None and comment.ticket_id != ticket.id:
        raise InvariantViolation(
            "The comment belongs to another ticket.",
            code="comment_ticket_mismatch",
            fields={"comment": ["This comment belongs to a different ticket."]},
        )

    extension = validate_upload(uploaded_file)  # raises with an actionable error code
    checksum = compute_sha256(uploaded_file)

    attachment = Attachment(
        ticket=ticket,
        comment=comment,
        uploader=actor,
        file=uploaded_file,
        # ``basename`` strips any path the client tried to include; the stored key is random anyway.
        original_name=(getattr(uploaded_file, "name", "") or "file")[:255],
        content_type=(getattr(uploaded_file, "content_type", "") or "")[:100],
        size_bytes=int(getattr(uploaded_file, "size", 0) or 0),
        sha256=checksum,
    )
    attachment.full_clean(exclude=["file"])
    attachment.save()

    audit_record(
        action=AuditAction.ATTACHMENT_UPLOADED,
        actor=actor,
        obj=attachment,
        project=ticket.project,
        ticket=ticket,
        metadata={
            "attachment_id": str(attachment.pk),
            "extension": extension,
            "size_bytes": attachment.size_bytes,
            "sha256": checksum,
        },
        request=request,
    )
    return attachment


@transaction.atomic
def delete_attachment(*, actor, attachment: Attachment, request=None) -> Attachment:
    """Flag the attachment as deleted and remove the stored object after commit (FR-6.8)."""
    ticket = attachment.effective_ticket
    if ticket is None:  # pragma: no cover - prevented by the schema
        raise AccessDenied("You cannot delete this attachment.")
    if not can_view_ticket(actor, ticket):
        raise AccessDenied("You cannot delete this attachment.")
    if not can_delete_attachment(actor, attachment):
        raise AccessDenied("You cannot delete this attachment.")
    if attachment.is_deleted:
        raise InvariantViolation("This attachment is already deleted.", code="already_deleted")

    attachment.is_deleted = True
    attachment.save(update_fields=["is_deleted", "updated_at"])

    storage, name = attachment.file.storage, attachment.file.name

    def _remove_object() -> None:
        try:
            storage.delete(name)
        except Exception:  # pragma: no cover - storage outages must not break the request
            # The metadata is already hidden from the API, so a leftover object is an operational
            # cleanup task rather than a reason to fail the user's delete — but it is worth knowing
            # about, hence the log rather than a silent pass.
            logger.warning("Could not delete attachment object %s from storage.", name, exc_info=True)

    transaction.on_commit(_remove_object)

    audit_record(
        action=AuditAction.ATTACHMENT_DELETED,
        actor=actor,
        obj=attachment,
        project=ticket.project,
        ticket=ticket,
        metadata={"attachment_id": str(attachment.pk), "original_name": attachment.original_name},
        request=request,
    )
    return attachment


def record_download(*, actor, attachment: Attachment, request=None) -> None:
    """Record that a private file was read.

    Downloading customer data is an auditable event (FR-8.1); the audit row is written before the
    response starts streaming so a cancelled download is still visible.
    """
    ticket = attachment.effective_ticket
    audit_record(
        action=AuditAction.ATTACHMENT_DOWNLOADED,
        actor=actor,
        obj=attachment,
        project=ticket.project if ticket else None,
        ticket=ticket,
        metadata={"attachment_id": str(attachment.pk), "original_name": attachment.original_name},
        request=request,
    )


def safe_download_name(attachment: Attachment) -> str:
    """Filename for ``Content-Disposition``, stripped of anything that could break the header."""
    name = (attachment.original_name or "attachment").replace('"', "").replace("\\", "").replace("\r", "").replace("\n", "")
    return name[:255] or f"attachment.{get_extension(name) or 'bin'}"