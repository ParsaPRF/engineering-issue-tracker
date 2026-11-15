"""Workflow-owned persistence: the ticket status timeline.

Relationship to ``AuditEvent`` (ADR-011): this table is the *business record* of the ticket's
lifecycle — "NEW → TRIAGED by Sara on 2026-03-04, with this comment". It is part of the workflow
domain, is displayed in the ticket timeline, and may be read by any project member. It is
written exactly once per accepted transition, inside the same transaction as the status change,
so the timeline can never disagree with ``Ticket.status``.

Rows are never updated or deleted: an append-only timeline is what makes "how did this ticket
get here?" answerable.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import UUIDModel


class TicketStatusHistory(UUIDModel):
    """One accepted status transition."""

    ticket = models.ForeignKey(
        "tickets.Ticket",
        on_delete=models.CASCADE,
        related_name="status_history",
        verbose_name=_("ticket"),
    )
    from_status = models.CharField(  # noqa: DJ001 - NULL means "no previous status" (creation)
        _("from status"),
        max_length=20,
        blank=True,
        null=True,
        # NULL means "the ticket did not exist yet" (the creation entry). An empty string would be a
        # third, ambiguous state — DJ001 normally discourages null on text fields, but here the
        # tri-state semantics are the point, so the rule is suppressed deliberately.
        help_text=_("Null for the entry created together with the ticket."),
    )
    to_status = models.CharField(_("to status"), max_length=20)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="status_changes",
        verbose_name=_("changed by"),
    )
    comment = models.TextField(_("comment"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("ticket status history")
        verbose_name_plural = _("ticket status history")
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["ticket", "created_at"], name="history_ticket_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.ticket_id}: {self.from_status or '∅'} → {self.to_status}"

    def save(self, *args, **kwargs):
        """Append-only guard: a history row, once written, is a historical fact."""
        if not self._state.adding:
            raise RuntimeError("TicketStatusHistory is append-only; create a new row instead.")
        return super().save(*args, **kwargs)
