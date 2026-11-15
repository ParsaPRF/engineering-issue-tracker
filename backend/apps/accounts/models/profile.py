"""Profile data that is not needed for authentication.

Kept in a separate table on purpose: ``User`` is read on every request (session lookup, audit
attribution), so it should stay narrow. Preferences and presentation fields that are read
rarely live here.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import BaseModel


class UserProfile(BaseModel):
    """One-to-one extension of the user model."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("user"),
    )

    job_title = models.CharField(_("job title"), max_length=120, blank=True)
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    timezone = models.CharField(
        _("time zone"),
        max_length=64,
        default="UTC",
        help_text=_("IANA name, e.g. Europe/Berlin. Used to render times for this user."),
    )
    avatar_key = models.CharField(
        _("avatar storage key"),
        max_length=255,
        blank=True,
        help_text=_("Object key in private storage. Never a public URL (ADR-010)."),
    )

    # Notification preferences: opt-out, because the default expectation is "tell me about my work".
    notify_on_assignment = models.BooleanField(_("notify on assignment"), default=True)
    notify_on_comment = models.BooleanField(_("notify on comment"), default=True)
    notify_on_status_change = models.BooleanField(_("notify on status change"), default=True)

    class Meta:
        verbose_name = _("user profile")
        verbose_name_plural = _("user profiles")

    def __str__(self) -> str:
        return f"Profile of {self.user_id}"

    def clean(self) -> None:
        super().clean()
        if self.timezone:
            try:
                ZoneInfo(self.timezone)
            except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
                raise ValidationError({"timezone": _("Unknown time zone: %(tz)s") % {"tz": self.timezone}}) from exc
