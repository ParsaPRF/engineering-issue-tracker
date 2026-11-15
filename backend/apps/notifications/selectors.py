"""Notification read queries. Everything is scoped to the requesting user's own inbox."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.models import User
from apps.notifications.models import Notification


def inbox(user: User, *, unread_only: bool = False) -> QuerySet[Notification]:
    """The caller's notifications.

    There is deliberately no "all notifications" query: a notification belongs to exactly one
    recipient, and an endpoint that could list somebody else's inbox would be an authorisation bug
    waiting to happen.
    """
    queryset = Notification.objects.filter(recipient=user).select_related(
        "actor", "ticket", "ticket__project", "project"
    )
    if unread_only:
        queryset = queryset.filter(is_read=False)
    return queryset


def unread_count(user: User) -> int:
    return Notification.objects.filter(recipient=user, is_read=False).count()


def search(user: User, term: str) -> QuerySet[Notification]:
    queryset = inbox(user)
    if term:
        queryset = queryset.filter(Q(title__icontains=term) | Q(body__icontains=term))
    return queryset