"""Global system roles.

Deliberately **not** defined inside ``models/user.py``: the user model imports its manager, and the
manager needs the role enumeration for its defaults. Keeping the enumeration in a leaf module that
imports nothing from the app removes that cycle at the source, instead of hiding it behind a
function-level import.

Global role vs project role: this enumeration answers "what is this person in the organisation?".
``apps.projects.models.membership.ProjectRole`` answers "what are they allowed to do inside this
project?". The effective permission is the combination of both (ADR-012).
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from common.choices import BaseTextChoices


class SystemRole(BaseTextChoices):
    """Ordered from least to most privileged."""

    REPORTER = "REPORTER", _("Reporter")
    ENGINEER = "ENGINEER", _("Engineer")
    PROJECT_MANAGER = "PROJECT_MANAGER", _("Project Manager")
    ADMIN = "ADMIN", _("Administrator")
