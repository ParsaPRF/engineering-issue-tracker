"""Notifications: the in-app inbox and its delivery bookkeeping.

The data model carries the reliability properties (ADR-009), so the Celery task can stay simple:

* ``dedup_key`` is **unique**. A retried or duplicated task, or two services racing to notify the
  same person about the same event, produces one row and therefore one notification.
* ``is_sent`` / ``sent_at`` record delivery, so a periodic task can re-drive anything that a
  crashed worker left behind, and the API can still show in-app notifications meanwhile.
* ``payload`` keeps presentation-agnostic context (ids, keys) instead of prose, so the UI can
  link to the object.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from common.choices import BaseTextChoices
from common.models import BaseModel


class NotificationEvent(BaseTextChoices):
    """The vocabulary of things users get told about (FR-7.1)."""

    TICKET_CREATED = "ticket.created", _("Ticket created")
    TICKET_ASSIGNED = "ticket.assigned", _("Ticket assigned")
    TICKET_REASSIGNED = "ticket.reassigned", _("Ticket reassigned")
    TICKET_STATUS_CHANGED = "ticket.status_changed", _("Ticket status changed")
    TICKET_RESOLVED = "ticket.resolved", _("Ticket resolved")
    TICKET_REOPENED = "ticket.reopened", _("Ticket reopened")
    COMMENT_ADDED = "comment.added", _("Comment added")
    MEMBERSHIP_ADDED = "membership.added", _("Added to a project")


class Notification(BaseModel):
    """One message for one recipient."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("recipient"),
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_notifications",
        verbose_name=_("actor"),
        help_text=_("Who caused the event. Null when the system acted."),
    )

    event_type = models.CharField(
        _("event type"), max_length=50, choices=NotificationEvent.choices, db_index=True
    )
    title = models.CharField(_("title"), max_length=200)
    body = models.TextField(_("body"), blank=True)

    ticket = models.ForeignKey(
        "tickets.Ticket",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name=_("ticket"),
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name=_("project"),
    )
    payload = models.JSONField(_("payload"), default=dict, blank=True)

    dedup_key = models.CharField(
        _("deduplication key"),
        max_length=120,
        unique=True,
        null=True,
        blank=True,
        help_text=_("Unique per (recipient, event, subject) so retries cannot duplicate a row."),
    )

    is_sent = models.BooleanField(_("dispatched"), default=False)
    sent_at = models.DateTimeField(_("dispatched at"), null=True, blank=True)
    is_read = models.BooleanField(_("read"), default=False)
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]
        indexes = [
            # The bell badge query: "how many unread notifications for me".
            models.Index(fields=["recipient", "is_read", "created_at"], name="notif_recipient_unread_idx"),
            models.Index(fields=["recipient", "created_at"], name="notif_recipient_created_idx"),
            # The periodic re-drive query: "what was never dispatched".
            models.Index(fields=["is_sent", "created_at"], name="notif_unsent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} → {self.recipient_id}"

    def mark_sent(self) -> None:
        self.is_sent = True
        self.sent_at = timezone.now()
        self.save(update_fields=["is_sent", "sent_at", "updated_at"])

    def mark_read(self) -> None:
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at", "updated_at"])
