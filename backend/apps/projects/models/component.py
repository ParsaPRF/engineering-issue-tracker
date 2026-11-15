"""Component: an optional sub-area of a project (e.g. "Billing API", "Mobile App").

Components exist to *route* work: they let reporters pick the right area, let managers filter
load per area, and let a lead be nominated. They are deliberately shallow — one level, no
hierarchy — because nested components add complexity without a stated requirement (KISS).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import BaseModel


class Component(BaseModel):
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="components",
        verbose_name=_("project"),
    )
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"), blank=True)
    lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="led_components",
        verbose_name=_("lead"),
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("component")
        verbose_name_plural = _("components")
        ordering = ["project", "name"]
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="uniq_component_project_name"),
        ]
        indexes = [
            models.Index(fields=["project", "is_active"], name="component_proj_active_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.project_id})"
