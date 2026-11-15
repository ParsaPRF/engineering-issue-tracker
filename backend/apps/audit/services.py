"""Audit recording: the only write path into ``AuditEvent``.

Called by every other module's services. Two rules keep the trail trustworthy and small:

1. **One event per business action.** ``record`` is called from the service that performed the
   action, not from a signal, so an event cannot be emitted twice by two mechanisms or missed
   because a signal was not connected (ADR-011).
2. **Metadata is sanitised.** Anything that looks like a credential is dropped, strings are
   truncated and nesting is bounded. An audit table that accumulates secrets is worse than no
   audit table (FR-8.4).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from django.db import models

from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from common.utils import get_client_ip, get_user_agent

#: Keys that must never be persisted, matched case-insensitively anywhere in the metadata tree.
SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|passwd|passphrase|token|secret|api[_-]?key|authorization|cookie|sessionid)",
    re.IGNORECASE,
)

MAX_STRING_LENGTH = 500
MAX_LIST_ITEMS = 20
MAX_DEPTH = 3


def _sanitise_value(value: Any, *, depth: int) -> Any:
    """Recursively clean one value, bounding depth, size and content."""
    if depth > MAX_DEPTH:
        return "<truncated>"
    if isinstance(value, Mapping):
        return sanitise_metadata(value, depth=depth + 1)
    if isinstance(value, (list, tuple)):
        return [_sanitise_value(item, depth=depth + 1) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, str):
        return value if len(value) <= MAX_STRING_LENGTH else f"{value[:MAX_STRING_LENGTH]}…"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if hasattr(value, "isoformat"):  # dates, datetimes
        return value.isoformat()
    return str(value)[:MAX_STRING_LENGTH]


def sanitise_metadata(metadata: Mapping[str, Any] | None, *, depth: int = 0) -> dict[str, Any]:
    """Return a JSON-safe copy of ``metadata`` with sensitive keys removed."""
    if not metadata:
        return {}
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if SENSITIVE_KEY_PATTERN.search(str(key)):
            clean[str(key)] = "<redacted>"
            continue
        clean[str(key)] = _sanitise_value(value, depth=depth)
    return clean


def record(
    *,
    action: AuditAction | str,
    actor=None,
    obj: models.Model | None = None,
    project=None,
    ticket=None,
    metadata: Mapping[str, Any] | None = None,
    request=None,
) -> AuditEvent:
    """Write one audit event and return it.

    Args:
        action: member of :class:`AuditAction` (a plain string is accepted for flexibility).
        actor: the user who performed the action, or ``None`` for system actions.
        obj: the affected object; ``object_type``/``object_id`` are derived from it.
        project: explicit project context. Falls back to ``obj.project`` when available, because
            almost every scoped event should be filterable by project.
        ticket: explicit ticket context. Falls back to ``obj`` when the object *is* a ticket.
        metadata: small, relevant facts — never a full request body.
        request: used only to capture IP and user agent.

    The fallbacks exist so callers do not have to repeat themselves, but they are deliberately
    conservative: nothing is guessed from an object's attribute chain beyond ``project`` and
    ``pk``.
    """
    action_value = action.value if isinstance(action, AuditAction) else str(action)

    object_type = ""
    object_id = None
    if obj is not None:
        object_type = obj._meta.label_lower
        object_id = getattr(obj, "pk", None)

    resolved_project = project
    if resolved_project is None and obj is not None and hasattr(obj, "project_id"):
        resolved_project = getattr(obj, "project", None)

    resolved_ticket = ticket
    if resolved_ticket is None and obj is not None and object_type == "tickets.ticket":
        resolved_ticket = obj

    if actor is not None and not getattr(actor, "is_authenticated", True):
        actor = None

    return AuditEvent.objects.create(
        action=action_value,
        actor=actor,
        object_type=object_type,
        object_id=object_id,
        project=resolved_project,
        ticket=resolved_ticket,
        metadata=sanitise_metadata(metadata),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
