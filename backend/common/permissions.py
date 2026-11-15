"""Reusable DRF permission primitives.

These are *endpoint-level* guards ("must be logged in", "must be an Admin"). Anything that
depends on a specific project or object belongs to the permission kernel in
``apps.projects.permissions`` (ADR-012), because the same rules must be reusable from services.
"""

from __future__ import annotations

from typing import Any

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import SystemRole


class IsActiveUser(BasePermission):
    """Reject deactivated accounts even if they still hold a valid session (FR-1.7)."""

    message = "This account is inactive."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_active)


class IsAdmin(BasePermission):
    """Only system administrators."""

    message = "Administrator privileges are required."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.system_role == SystemRole.ADMIN)


class IsAdminOrReadOnly(BasePermission):
    """Anyone authenticated may read; only Admins may write (used by audit endpoints)."""

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and user.is_active):
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.system_role == SystemRole.ADMIN


class IsOwnerOrAdmin(BasePermission):
    """Object-level guard for user-owned rows such as notifications and profiles."""

    def has_object_permission(self, request, view, obj: Any) -> bool:
        user = request.user
        if user.system_role == SystemRole.ADMIN:
            return True
        owner_id = getattr(obj, "user_id", None) or getattr(obj, "recipient_id", None)
        return owner_id == user.id
