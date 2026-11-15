"""Domain exceptions and the single API error envelope.

Two problems this module solves:

1. **Services must not know about HTTP.** A service raises ``InvariantViolation("ticket_archived",
   "…")``; it never returns a ``Response`` and never imports DRF. The API layer decides that
   this means ``400`` with a JSON body.
2. **Clients must get one predictable error shape.** Every failure — validation, permission,
   not found, throttle, unexpected — is rendered as::

       {"error": {"code": "invalid_transition",
                  "detail": "Cannot move a ticket from RESOLVED to TRIAGED.",
                  "fields": {"to_status": ["…"]}}}   # only for field validation errors

   A stable ``code`` lets the frontend branch on the failure without parsing prose.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class DomainError(Exception):
    """Base class for business-rule failures raised by services.

    Attributes:
        code: stable machine-readable identifier, e.g. ``"invalid_transition"``.
        message: human-readable sentence shown to the user.
        status_code: the HTTP status the API layer should use.
        fields: optional mapping of field name to a list of messages.
    """

    code: str = "domain_error"
    status_code: int = 400
    default_message: str = "The operation could not be completed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        fields: dict[str, list[str]] | None = None,
    ) -> None:
        self.message = message or self.default_message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.fields = fields or {}
        super().__init__(self.message)


class InvariantViolation(DomainError):
    """A business rule was broken; the request is well-formed but not allowed (400)."""

    code = "invariant_violation"
    status_code = 400
    default_message = "This operation violates a business rule."


class AccessDenied(DomainError):
    """The actor may not perform this operation on this object (403)."""

    code = "permission_denied"
    status_code = 403
    default_message = "You do not have permission to perform this action."


class ResourceNotFound(DomainError):
    """The object does not exist *or* is not visible to the actor (404).

    Deliberately one exception for both cases: leaking "exists but forbidden" is an
    information disclosure (NFR-1.3).
    """

    code = "not_found"
    status_code = 404
    default_message = "The requested resource was not found."


class StateConflict(DomainError):
    """The operation conflicts with the current state, e.g. a duplicate key (409)."""

    code = "conflict"
    status_code = 409
    default_message = "The resource is in a conflicting state."


def _field_errors(detail: Any) -> dict[str, list[str]]:
    """Flatten DRF's nested validation detail into ``{field: [messages]}``."""
    if isinstance(detail, dict):
        flattened: dict[str, list[str]] = {}
        for key, value in detail.items():
            if isinstance(value, (list, tuple)):
                flattened[str(key)] = [str(item) for item in value]
            elif isinstance(value, dict):
                nested = _field_errors(value)
                for nested_key, messages in nested.items():
                    flattened[f"{key}.{nested_key}"] = messages
            else:
                flattened[str(key)] = [str(value)]
        return flattened
    if isinstance(detail, (list, tuple)):
        return {"non_field_errors": [str(item) for item in detail]}
    return {"non_field_errors": [str(detail)]}


def envelope_exception_handler(exc: Exception, context: dict) -> Response | None:
    """Convert any exception into the project's error envelope.

    Registered as ``REST_FRAMEWORK["EXCEPTION_HANDLER"]``. Ordering matters: domain exceptions
    are handled first (they carry the best information), then Django's own exceptions that DRF
    does not translate, then DRF's defaults, and finally anything unexpected becomes a generic
    ``500`` so internal details never reach the client (NFR-1.10).
    """
    if isinstance(exc, DomainError):
        payload: dict[str, Any] = {"code": exc.code, "detail": exc.message}
        if exc.fields:
            payload["fields"] = exc.fields
        return Response({"error": payload}, status=exc.status_code)

    if isinstance(exc, DjangoValidationError):
        fields = _field_errors(getattr(exc, "message_dict", None) or exc.messages)
        return Response(
            {
                "error": {
                    "code": "validation_error",
                    "detail": "The submitted data is invalid.",
                    "fields": fields,
                }
            },
            status=400,
        )

    if isinstance(exc, Http404):
        return Response(
            {"error": {"code": "not_found", "detail": "The requested resource was not found."}},
            status=404,
        )

    if isinstance(exc, IntegrityError):
        # Reaching this means a database constraint fired without a service-level guard: a bug
        # worth logging, but the client must not see the SQL.
        return Response(
            {
                "error": {
                    "code": "conflict",
                    "detail": "The operation conflicts with existing data.",
                }
            },
            status=409,
        )

    response = drf_exception_handler(exc, context)

    if response is None:
        return None  # let Django render a 500 and log the traceback

    code_map = {
        drf_exceptions.NotAuthenticated: "not_authenticated",
        drf_exceptions.AuthenticationFailed: "authentication_failed",
        drf_exceptions.PermissionDenied: "permission_denied",
        drf_exceptions.NotFound: "not_found",
        drf_exceptions.MethodNotAllowed: "method_not_allowed",
        drf_exceptions.Throttled: "throttled",
        drf_exceptions.UnsupportedMediaType: "unsupported_media_type",
        drf_exceptions.ParseError: "parse_error",
        drf_exceptions.ValidationError: "validation_error",
    }
    code = "error"
    for exception_class, mapped in code_map.items():
        if isinstance(exc, exception_class):
            code = mapped
            break

    detail = response.data
    payload = {"code": code, "detail": ""}
    if isinstance(exc, drf_exceptions.ValidationError):
        payload["detail"] = "The submitted data is invalid."
        payload["fields"] = _field_errors(getattr(exc, "detail", detail))
    elif isinstance(detail, dict) and "detail" in detail:
        payload["detail"] = str(detail["detail"])
    else:
        payload["detail"] = str(detail)

    response.data = {"error": payload}
    return response
