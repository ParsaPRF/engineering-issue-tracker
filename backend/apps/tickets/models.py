"""Ticket aggregate: the core of the product.

Contains ``Ticket``, the human-readable key counter (``TicketKeySequence``) and the labelling
models. Three design points worth reading before changing anything here:

1. **``status`` is not a normal editable field.** It is changed only by
   ``apps.workflows.services.transition_ticket`` (ADR-005). Serializers mark it read-only.
2. **``key`` is allocated, not computed.** ``apps.tickets.services.keys.allocate_ticket_key``
   owns the atomic counter + retry protocol (ADR-007); this module only enforces the format and
   the uniqueness that make that protocol safe.
3. **Priority ≠ Severity.** Priority is how soon (scheduling); severity is how bad technically
   (impact). Both are kept as independent axes because conflating them hides real triage
   decisions.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from common.choices import BaseTextChoices
from common.models import BaseModel

#: ``ENG-1042``: project key, dash, positive integer. Validated on write so that a corrupted key
#: is rejected at the model boundary rather than surfacing as a broken deep link.
ticket_key_validator = RegexValidator(
    regex=r"^[A-Z][A-Z0-9]{1,9}-[1-9][0-9]*$",
    message=_("Ticket keys look like ENG-1042."),
)


class TicketType(BaseTextChoices):
    BUG = "BUG", _("Bug")
    TASK = "TASK", _("Task")
    FEATURE = "FEATURE", _("Feature")
    CHANGE_REQUEST = "CHANGE_REQUEST", _("Change request")
    SUPPORT = "SUPPORT", _("Support request")


class TicketStatus(BaseTextChoices):
    """Lifecycle states. Legal moves between them live in ``apps.workflows.state_machine``."""

    NEW = "NEW", _("New")
    TRIAGED = "TRIAGED", _("Triaged")
    IN_PROGRESS = "IN_PROGRESS", _("In progress")
    IN_REVIEW = "IN_REVIEW", _("In review")
    RESOLVED = "RESOLVED", _("Resolved")
    CLOSED = "CLOSED", _("Closed")
    REOPENED = "REOPENED", _("Reopened")
    BLOCKED = "BLOCKED", _("Blocked")
    REJECTED = "REJECTED", _("Rejected")
    DUPLICATE = "DUPLICATE", _("Duplicate")


class Priority(BaseTextChoices):
    """How soon the work should be addressed."""

    LOWEST = "LOWEST", _("Lowest")
    LOW = "LOW", _("Low")
    MEDIUM = "MEDIUM", _("Medium")
    HIGH = "HIGH", _("High")
    CRITICAL = "CRITICAL", _("Critical")


class Severity(BaseTextChoices):
    """How serious the technical impact is."""

    TRIVIAL = "TRIVIAL", _("Trivial")
    MINOR = "MINOR", _("Minor")
    MAJOR = "MAJOR", _("Major")
    CRITICAL = "CRITICAL", _("Critical")
    BLOCKER = "BLOCKER", _("Blocker")


#: Statuses that mean "the work is not finished yet" — used by the dashboard, the workload
#: report and the default ticket list filter.
OPEN_STATUSES = frozenset(
    {
        TicketStatus.NEW,
        TicketStatus.TRIAGED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.IN_REVIEW,
        TicketStatus.REOPENED,
        TicketStatus.BLOCKED,
    }
)

#: Statuses that end the delivery process. ``resolved_at`` / ``closed_at`` are stamped on entry.
DONE_STATUSES = frozenset({TicketStatus.RESOLVED, TicketStatus.CLOSED})

#: Statuses that require an explanatory comment when entered (enforced by the state machine).
COMMENT_REQUIRED_STATUSES = frozenset(
    {TicketStatus.REJECTED, TicketStatus.DUPLICATE, TicketStatus.BLOCKED, TicketStatus.REOPENED}
)

#: Statuses that require an assignee (you cannot start or finish work nobody owns).
ASSIGNEE_REQUIRED_STATUSES = frozenset(
    {
        TicketStatus.IN_PROGRESS,
        TicketStatus.IN_REVIEW,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
    }
)


class Ticket(BaseModel):
    """A single unit of work inside a project."""

    key = models.CharField(
        _("ticket key"),
        max_length=20,
        unique=True,
        editable=False,
        validators=[ticket_key_validator],
        help_text=_("Human-readable identifier, e.g. ENG-1042. Immutable once created."),
    )

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="tickets",
        verbose_name=_("project"),
    )
    component = models.ForeignKey(
        "projects.Component",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets",
        verbose_name=_("component"),
    )

    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"))

    type = models.CharField(
        _("type"), max_length=20, choices=TicketType.choices, default=TicketType.BUG, db_index=True
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=TicketStatus.choices,
        default=TicketStatus.NEW,
        db_index=True,
        help_text=_("Changed only through the transition endpoint (ADR-005)."),
    )
    priority = models.CharField(
        _("priority"),
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        db_index=True,
        help_text=_("How soon this should be addressed."),
    )
    severity = models.CharField(
        _("severity"),
        max_length=20,
        choices=Severity.choices,
        default=Severity.MAJOR,
        db_index=True,
        help_text=_("How serious the technical impact is."),
    )

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reported_tickets",
        verbose_name=_("reporter"),
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
        verbose_name=_("assignee"),
    )

    due_date = models.DateField(_("due date"), null=True, blank=True)

    # Stamped by the workflow service, never by clients: they are derived facts about the
    # lifecycle, and letting a client set them would make the timeline lie.
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)

    labels = models.ManyToManyField(
        "tickets.Label", through="tickets.TicketLabel", related_name="tickets", blank=True
    )

    class Meta:
        verbose_name = _("ticket")
        verbose_name_plural = _("tickets")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "status"], name="ticket_proj_status_idx"),
            models.Index(fields=["project", "created_at"], name="ticket_proj_created_idx"),
            models.Index(fields=["assignee", "status"], name="ticket_assignee_status_idx"),
            models.Index(fields=["project", "priority"], name="ticket_proj_priority_idx"),
            models.Index(fields=["project", "severity"], name="ticket_proj_severity_idx"),
            models.Index(fields=["status", "-created_at"], name="ticket_status_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.key}: {self.title}"

    def clean(self) -> None:
        """Cross-field invariants that must hold for *any* writer, including the admin."""
        super().clean()
        errors: dict[str, str] = {}

        if not self.title.strip():
            errors["title"] = _("Title cannot be blank.")
        if not self.description.strip():
            errors["description"] = _("Description cannot be blank.")

        if self.component_id and self.project_id and self.component.project_id != self.project_id:
            errors["component"] = _("The component must belong to the ticket's project.")

        if errors:
            raise ValidationError(errors)

    # -- Derived state --------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def is_done(self) -> bool:
        return self.status in DONE_STATUSES

    @property
    def is_overdue(self) -> bool:
        """Overdue means: has a due date in the past and is still open."""
        if not self.due_date or self.is_done:
            return False
        return self.due_date < timezone.localdate()

    @property
    def number(self) -> int:
        """Numeric part of the key (``ENG-1042`` → ``1042``)."""
        try:
            return int(self.key.rsplit("-", 1)[1])
        except (IndexError, ValueError):  # pragma: no cover - guarded by the validator
            return 0


class TicketKeySequence(BaseModel):
    """Per-project monotonic counter backing ticket keys (ADR-007).

    Why a table and not ``MAX(number) + 1``: ``MAX`` requires reading before writing, and two
    concurrent requests read the same maximum, so they would both produce the same key. A single
    row per project that is locked (``SELECT ... FOR UPDATE``) and incremented turns that race
    into a serialisation point. The unique constraint on ``Ticket.key`` remains the ultimate
    guarantee — the counter is an optimisation that keeps retries rare.
    """

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="key_sequence",
        verbose_name=_("project"),
    )
    last_number = models.PositiveIntegerField(_("last allocated number"), default=0)

    class Meta:
        verbose_name = _("ticket key sequence")
        verbose_name_plural = _("ticket key sequences")

    def __str__(self) -> str:
        return f"{self.project_id}: {self.last_number}"


class Label(BaseModel):
    """Project-scoped tag, e.g. ``regression``, ``security``."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="labels",
        verbose_name=_("project"),
    )
    name = models.CharField(_("name"), max_length=50)
    color = models.CharField(
        _("color"),
        max_length=7,
        default="#6b7280",
        help_text=_("Hex colour used by the UI badge."),
    )

    class Meta:
        verbose_name = _("label")
        verbose_name_plural = _("labels")
        ordering = ["project", "name"]
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="uniq_label_project_name"),
        ]

    def __str__(self) -> str:
        return self.name


class TicketLabel(models.Model):
    """Explicit through-model for the ticket↔label relation.

    It exists as a concrete model (rather than relying on Django's implicit M2M table) so that a
    future "who applied this label, when" column is a one-field migration, and so that the table
    has a stable, named location in the schema.
    """

    id = models.BigAutoField(primary_key=True)
    ticket = models.ForeignKey(
        "tickets.Ticket", on_delete=models.CASCADE, related_name="label_links"
    )
    label = models.ForeignKey("tickets.Label", on_delete=models.CASCADE, related_name="ticket_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ticket", "label"], name="uniq_ticketlabel"),
        ]

    def __str__(self) -> str:
        return f"{self.ticket_id} ↔ {self.label_id}"
