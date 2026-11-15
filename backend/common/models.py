"""Abstract model bases shared by every app.

Two reasons to centralise them:

1. **Consistency** — every major entity gets a UUIDv7 primary key and automatic timestamps with
   exactly the same semantics, so no reviewer has to check each model.
2. **DRY without a generic repository** — these are plain abstract Django models. They add
   fields; they do not add querying behaviour, which stays in selectors (ADR-004).
"""

from __future__ import annotations

from django.db import models

from common.uuid import uuid7


class UUIDModel(models.Model):
    """Primary key as a time-ordered UUID (ADR-006).

    ``editable=False`` keeps the field out of Django admin forms and out of DRF serializer
    input, so a client can never choose its own identifier.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False, verbose_name="ID")

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """``created_at`` / ``updated_at`` maintained by the database-facing ORM layer.

    ``auto_now_add`` and ``auto_now`` run on ``save()`` and on ``QuerySet.update()`` they are
    *not* applied, which is why services that bulk-update must set ``updated_at`` explicitly.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated at")

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    """UUID primary key plus timestamps: the default base for major business entities."""

    class Meta:
        abstract = True
        ordering = ("-created_at",)
