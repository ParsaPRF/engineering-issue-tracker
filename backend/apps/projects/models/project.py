"""The ``Project`` aggregate root.

Lifecycle decision: projects are **archived**, never deleted (FR-2.4). Tickets reference their
project with ``on_delete=PROTECT``, so a careless ``project.delete()`` raises instead of
silently destroying an audit trail. Restoring means clearing ``archived_at``.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from common.choices import BaseTextChoices
from common.models import BaseModel

#: Project keys become the prefix of every ticket key (``ENG`` in ``ENG-1042``), so they must be
#: short, uppercase and URL-safe.
project_key_validator = RegexValidator(
    regex=r"^[A-Z][A-Z0-9]{1,9}$",
    message=_("Use 2-10 uppercase letters/digits, starting with a letter (e.g. ENG, PAY2)."),
)


class ProjectStatus(BaseTextChoices):
    ACTIVE = "ACTIVE", _("Active")
    ARCHIVED = "ARCHIVED", _("Archived")


class Project(BaseModel):
    """A body of work with its own members, components and ticket key space."""

    key = models.CharField(
        _("key"),
        max_length=10,
        validators=[project_key_validator],
        help_text=_("Short uppercase prefix for ticket keys, e.g. ENG."),
    )
    name = models.CharField(_("name"), max_length=200)
    description = models.TextField(_("description"), blank=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_projects",
        verbose_name=_("owner"),
    )

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.ACTIVE,
        db_index=True,
    )
    archived_at = models.DateTimeField(_("archived at"), null=True, blank=True)

    class Meta:
        verbose_name = _("project")
        verbose_name_plural = _("projects")
        ordering = ["-created_at"]
        constraints = [
            # Case-insensitive uniqueness: "ENG" and "eng" would generate colliding ticket keys.
            models.UniqueConstraint(Lower("key"), name="uniq_project_key_ci"),
        ]
        indexes = [
            models.Index(fields=["status", "key"], name="project_status_key_idx"),
            models.Index(fields=["owner", "status"], name="project_owner_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.key} — {self.name}"

    def save(self, *args, **kwargs):
        if self.key:
            self.key = self.key.strip().upper()
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if self.key:
            self.key = self.key.strip().upper()
        if not self.name.strip():
            raise ValidationError({"name": _("Project name cannot be blank.")})

    @property
    def is_archived(self) -> bool:
        return self.status == ProjectStatus.ARCHIVED

    def archive(self, *, when=None) -> None:
        """Mark archived. Callers must go through ``projects.services.archive_project`` so the
        change is permission-checked and audited; this method only maintains the row's own
        consistency."""
        self.status = ProjectStatus.ARCHIVED
        self.archived_at = when or timezone.now()
        self.save(update_fields=["status", "archived_at", "updated_at"])

    def restore(self) -> None:
        self.status = ProjectStatus.ACTIVE
        self.archived_at = None
        self.save(update_fields=["status", "archived_at", "updated_at"])
