"""Project membership: the pivot of the authorisation model (ADR-012).

A user's effective capability on an object is derived from **(system role, project role)**:

* global ``ADMIN`` bypasses membership (they operate the installation);
* everyone else must have an *active* membership row in the object's project;
* the project role then decides *what* they may do inside it.

Membership is deactivated, never deleted, so that "who was on this project when the ticket was
closed?" remains answerable. The unique constraint on ``(project, user)`` means re-adding a
former member reactivates the existing row instead of accumulating duplicates.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from common.choices import BaseTextChoices
from common.models import BaseModel


class ProjectRole(BaseTextChoices):
    """Role *inside one project*. Distinct from ``SystemRole`` on purpose."""

    REPORTER = "REPORTER", _("Reporter")
    ENGINEER = "ENGINEER", _("Engineer")
    MANAGER = "MANAGER", _("Project Manager")


#: Who may be given a ticket. Reporters can file and comment but are not assigned work
#: (assumption A-14); managers are included because they also carry a workload.
ELIGIBLE_ASSIGNEE_ROLES = frozenset({ProjectRole.ENGINEER, ProjectRole.MANAGER})


def eligible_assignee_roles() -> frozenset[str]:
    """Exposed as a function so settings/permission code can depend on the *rule*, not the tuple."""
    return ELIGIBLE_ASSIGNEE_ROLES


class ProjectMembership(BaseModel):
    """Active link between a user and a project, carrying the project-scoped role."""

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("project"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
        verbose_name=_("user"),
    )
    role = models.CharField(
        _("project role"),
        max_length=20,
        choices=ProjectRole.choices,
        default=ProjectRole.REPORTER,
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Deactivate to remove access while keeping the historical record."),
    )
    joined_at = models.DateTimeField(_("joined at"), default=timezone.now)

    class Meta:
        verbose_name = _("project membership")
        verbose_name_plural = _("project memberships")
        ordering = ["project", "user__full_name"]
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="uniq_membership_project_user"),
        ]
        indexes = [
            # "my projects" — the query every request that scopes a queryset will run.
            models.Index(fields=["user", "is_active"], name="membership_user_active_idx"),
            # "who are the managers of this project" — notification recipient computation.
            models.Index(fields=["project", "role", "is_active"], name="membership_proj_role_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.project_id} as {self.role}"

    def clean(self) -> None:
        super().clean()
        if self.project_id and self.user_id:
            if self.project.owner_id == self.user_id and self.role != ProjectRole.MANAGER:
                raise ValidationError(
                    {"role": _("The project owner must hold the MANAGER role.")}
                )

    @property
    def is_manager(self) -> bool:
        return self.role == ProjectRole.MANAGER
