"""Append-only audit trail.

Why a separate table from ``TicketStatusHistory``: the audit trail answers *compliance* questions
across every module ("who changed this membership, from which IP?"), while status history answers
*business* questions about one ticket's lifecycle. Merging them would force every module's event
into a ticket-shaped table and lose the actor/IP context; keeping two tables with clearly
different purposes is not duplication (ADR-011).

Immutability is enforced twice:

* in Python — ``save()`` refuses to update an existing row and ``delete()`` is blocked, so a bug
  cannot rewrite history;
* in the database — the deployment guide revokes ``UPDATE``/``DELETE`` from the application role,
  which also covers ``bulk_create``/raw SQL.

What must never be stored here: passwords, tokens, secrets, or full request bodies. Services pass
small, relevant metadata, and ``services.sanitise_metadata`` strips anything sensitive.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import UUIDModel


class AuditEvent(UUIDModel):
    """One recorded action. Rows are created and read, never modified."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
        verbose_name=_("actor"),
        help_text=_("Null when the system acted or the account was removed; the event survives."),
    )
    action = models.CharField(_("action"), max_length=50, db_index=True)

    object_type = models.CharField(
        _("object type"),
        max_length=50,
        blank=True,
        help_text=_("Django label of the affected object, e.g. tickets.ticket."),
    )
    object_id = models.UUIDField(_("object id"), null=True, blank=True, db_index=True)

    # Denormalised context: without it, answering "show me this project's audit trail" would
    # need a polymorphic join on object_type for every event.
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
        verbose_name=_("project"),
    )
    ticket = models.ForeignKey(
        "tickets.Ticket",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
        verbose_name=_("ticket"),
    )

    metadata = models.JSONField(_("metadata"), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("user agent"), max_length=300, blank=True)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("audit event")
        verbose_name_plural = _("audit events")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["object_type", "object_id"], name="audit_object_idx"),
            models.Index(fields=["project", "created_at"], name="audit_project_created_idx"),
            models.Index(fields=["actor", "created_at"], name="audit_actor_created_idx"),
            models.Index(fields=["action", "created_at"], name="audit_action_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.actor_id or 'system'} at {self.created_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("AuditEvent rows are append-only and cannot be modified.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("AuditEvent rows are append-only and cannot be deleted.")
