"""Small helpers with no business meaning."""

from __future__ import annotations

from django.http import HttpRequest


def get_client_ip(request: HttpRequest | None) -> str | None:
    """Best-effort client IP for the audit trail.

    ``X-Forwarded-For`` is only meaningful behind a trusted proxy, which is our deployment
    topology (Nginx sets it). The left-most entry is the original client. The value is recorded
    for audit purposes only — it is never used for authorisation, because a header is
    client-controlled unless a trusted proxy overwrites it.
    """
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return (request.META.get("REMOTE_ADDR") or "")[:45] or None


def get_user_agent(request: HttpRequest | None) -> str:
    """Truncated user agent, bounded to the column width."""
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:300]
