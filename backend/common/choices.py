"""Choice enumeration helpers.

Django's ``TextChoices`` already gives value/label pairs, and since Django 5.0 it also exposes
``.values`` and ``.labels`` as **class properties** (``TicketStatus.values == ["NEW", ...]``).

A trap worth knowing, and the reason this module does not define its own ``values()`` method: those
properties live on the ``Choices`` metaclass, and a metaclass data descriptor wins over a same-named
method in the class body. Attempting to "add" a ``values()`` classmethod here produced
``TypeError: 'list' object is not callable`` at runtime — the property was still what got called. So
this module adds only what is genuinely missing:

* ``max_length()`` keeps a ``CharField(max_length=...)`` in sync with the longest value.
* ``has_value()`` is the checked membership test used by validators and services.
"""

from __future__ import annotations

from django.db import models


class BaseTextChoices(models.TextChoices):
    """``TextChoices`` plus the two helpers this project needs."""

    @classmethod
    def max_length(cls) -> int:
        return max(len(member.value) for member in cls)

    @classmethod
    def has_value(cls, value: object) -> bool:
        """True when ``value`` is one of this enumeration's stored values."""
        return value in cls.values