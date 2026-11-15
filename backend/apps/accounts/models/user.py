"""Custom user model (FR-1.1 … FR-1.8).

Why a custom user model at all: Django's default ``User`` has a ``username`` field and no notion
of a system role. Swapping it **after** the first migration is extremely painful (every FK in
the project points at the old table), which is why this file exists in Phase 2/3, before any
other model is migrated (ADR-016).

Design notes:

* ``email`` is the login identifier; it is stored lower-cased and additionally protected by a
  case-insensitive unique constraint, because "Ali@x.com" and "ali@x.com" must not be two
  accounts.
* ``system_role`` is a *global* capability. Project-scoped capability lives on
  ``ProjectMembership``; the effective permission is the combination (ADR-012).
* Deletion is not the lifecycle: accounts are deactivated (``is_active=False``), so tickets,
  comments and audit rows stay attributable (FR-1.7, UC-17).
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.managers import UserManager
from apps.accounts.roles import SystemRole
from common.models import BaseModel

__all__ = ["User", "SystemRole"]


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """Application user.

    Inherits ``password``, ``last_login`` (AbstractBaseUser) and ``is_superuser``, ``groups``,
    ``user_permissions`` (PermissionsMixin); adds the fields and the manager below.
    """

    email = models.EmailField(
        _("email address"),
        unique=True,
        help_text=_("Login identifier. Stored lower-cased."),
    )
    full_name = models.CharField(_("full name"), max_length=150)

    system_role = models.CharField(
        _("system role"),
        max_length=20,
        choices=SystemRole.choices,
        default=SystemRole.REPORTER,
        db_index=True,
        help_text=_("Global capability. Project access is granted separately by membership."),
    )

    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Deactivate instead of deleting so history stays attributable."),
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Grants access to the Django admin site. Not a business role."),
    )
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["full_name", "email"]
        constraints = [
            # Case-insensitive uniqueness at the database level: application code lower-cases
            # addresses, but a data import or a raw query must not be able to create a twin.
            models.UniqueConstraint(Lower("email"), name="uniq_user_email_ci"),
        ]
        indexes = [
            models.Index(fields=["system_role", "is_active"], name="user_role_active_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"

    def save(self, *args, **kwargs):
        """Normalise the email so lookups and the unique constraint behave predictably."""
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if self.email:
            self.email = self.email.strip().lower()
        if not self.full_name.strip():
            from django.core.exceptions import ValidationError

            raise ValidationError({"full_name": _("Full name cannot be blank.")})

    # -- Django conventions ---------------------------------------------------
    def get_full_name(self) -> str:
        return self.full_name

    def get_short_name(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else self.email

    # -- Convenience predicates ----------------------------------------------
    # These answer "what is this user globally?", never "may they do X to object Y?" — the
    # latter belongs to apps.projects.permissions (ADR-012).
    @property
    def is_admin(self) -> bool:
        return self.system_role == SystemRole.ADMIN

    @property
    def is_project_manager(self) -> bool:
        return self.system_role in {SystemRole.ADMIN, SystemRole.PROJECT_MANAGER}

    @property
    def can_create_projects(self) -> bool:
        return self.is_project_manager
