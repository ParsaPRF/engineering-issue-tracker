"""UUID helpers used by every primary key in the system (ADR-006).

Why this module exists instead of calling ``uuid.uuid4`` inline:

* **UUIDv7 is time-ordered.** Random v4 keys scatter B-tree inserts across the whole index;
  v7 keys append near the end, which keeps indexes compact and inserts fast while still being
  non-guessable enough to expose in URLs (the embedded timestamp is not a secret, and object
  access is authorised separately — a UUID is never an access token).
* **One import site.** Every model uses ``default=uuid7``; changing the scheme later is a single
  edit rather than a search across nine apps.
"""

from __future__ import annotations

import uuid
from typing import Any

try:  # Python 3.14+ ships uuid.uuid7 in the standard library.
    from uuid import uuid7 as _stdlib_uuid7
except ImportError:  # pragma: no cover - older interpreters
    _stdlib_uuid7 = None

UUID7_AVAILABLE = _stdlib_uuid7 is not None


def uuid7() -> uuid.UUID:
    """Return a time-ordered UUID (version 7).

    Falls back to :func:`uuid.uuid4` on interpreters without ``uuid.uuid7``; the fallback is
    correct, only the index-locality benefit is lost. ``UUID7_AVAILABLE`` records which path is
    in use so tests and the delivery report can state it explicitly instead of assuming.
    """
    if _stdlib_uuid7 is not None:
        return _stdlib_uuid7()
    return uuid.uuid4()  # pragma: no cover - only on Python < 3.14


def is_uuid(value: Any) -> bool:
    """True when ``value`` is a UUID instance or a parseable UUID string."""
    if isinstance(value, uuid.UUID):
        return True
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True
