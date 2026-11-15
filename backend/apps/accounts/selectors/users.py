"""Account selectors: all reads that other modules need.

The user directory is sensitive (it is the organisation's address book), so it is not exposed to
every authenticated user. The API layer builds its querysets from here instead of touching
``User.objects`` directly, which keeps the visibility rule in one place.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.models import SystemRole, User

#: Fields safe to return in lists. Deliberately excludes ``password``, permissions and the
#: internal ``is_staff``/``is_superuser`` flags — a directory entry is not an account dump.
PUBLIC_USER_FIELDS = ("id", "email", "full_name", "system_role", "is_active")


def user_queryset() -> QuerySet[User]:
    """Base queryset with the profile joined, avoiding an N+1 on every list response."""
    return User.objects.select_related("profile")


def active_users() -> QuerySet[User]:
    return user_queryset().filter(is_active=True)


def get_user_by_id(user_id) -> User | None:
    return user_queryset().filter(pk=user_id).first()


def get_user_by_email(email: str) -> User | None:
    """Case-insensitive lookup; matches the database constraint on lower(email)."""
    return user_queryset().filter(email__iexact=(email or "").strip()).first()


def search_users(query: str = "", *, limit: int = 20) -> QuerySet[User]:
    """Directory search used when adding project members.

    Bounded by ``limit``: an unbounded autocomplete over the user table is both a performance and
    an enumeration risk.
    """
    queryset = active_users().only(*PUBLIC_USER_FIELDS)
    query = (query or "").strip()
    if query:
        queryset = queryset.filter(Q(email__icontains=query) | Q(full_name__icontains=query))
    return queryset.order_by("full_name")[:limit]


def users_by_ids(user_ids) -> QuerySet[User]:
    return user_queryset().filter(pk__in=list(user_ids))


def administrators() -> QuerySet[User]:
    """Active administrators — used by services that must warn somebody about system-level events."""
    return active_users().filter(system_role=SystemRole.ADMIN)
