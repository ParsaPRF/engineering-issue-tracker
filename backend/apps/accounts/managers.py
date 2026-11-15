"""User manager: the single funnel for creating users.

Two things make this manager worth writing rather than using ``User.objects.create_user`` from
``django.contrib.auth``:

* **Normalisation and role defaults** live in one place, so registration, tests, the seed command
  and the Django admin cannot diverge.
* **Profile creation is explicit.** Creating a ``UserProfile`` here (instead of in a
  ``post_save`` signal) keeps the side effect visible: signals are easy to forget and hard to
  trace, and the profile is simply part of "a user was created".
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import BaseUserManager

from apps.accounts.roles import SystemRole


class UserManager(BaseUserManager):
    """Manager for the email-based custom user model."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields: Any):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).strip().lower()

        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)

        # Imported locally to avoid a circular import: models import this manager at module level.
        from apps.accounts.models.profile import UserProfile

        UserProfile.objects.get_or_create(user=user)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields: Any):
        """Create an ordinary account. Defaults are the *least* privileged ones."""
        extra_fields.setdefault("system_role", SystemRole.REPORTER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields: Any):
        """``manage.py createsuperuser`` path: administrator with Django admin access."""
        extra_fields.setdefault("system_role", SystemRole.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, username: str):
        """Case-insensitive lookup used by ``authenticate()``.

        Without this, ``authenticate(email="Ali@x.com")`` would miss the row stored as
        ``ali@x.com`` — a confusing "wrong password" for a correct password.
        """
        return self.get(**{f"{self.model.USERNAME_FIELD}__iexact": username})
