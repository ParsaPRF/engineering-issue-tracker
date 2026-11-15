"""Ticket filtering (FR-3.7).

``django-filter`` handles the declarative part; the custom filters below cover two needs it does not
express well:

* **multi-value** filters (``?status=NEW,IN_PROGRESS``) — a comma-separated list is what a UI
  multi-select naturally produces;
* **semantic** filters such as ``overdue`` and ``unassigned``, which are predicates rather than
  column lookups.
"""

from __future__ import annotations

import django_filters
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework.filters import OrderingFilter

from apps.tickets.models import OPEN_STATUSES, Ticket


class CharInFilter(django_filters.BaseInFilter, django_filters.CharFilter):
    """``?status=NEW,IN_PROGRESS`` — split on commas, compare each value."""


class TicketOrderingFilter(OrderingFilter):
    """Ordering that respects the *semantics* of priority and severity.

    Inherits DRF's ``OrderingFilter`` (the *backend*, which owns ``filter_queryset``) — not
    django-filter's filter class, which has a compatible name but no ``filter_queryset`` and would
    fail at request time with ``AttributeError``.

    Ordering by ``priority`` naively sorts the stored strings, which puts ``CRITICAL`` before ``LOW``
    (alphabetical) — a silently wrong "most urgent first" list. This filter maps those two fields to
    their numeric rank annotations, which the viewset adds to the queryset.
    """

    replacements = {"priority": "priority_rank", "severity": "severity_rank"}

    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        if not ordering:
            return ordering
        mapped: list[str] = []
        for field in ordering:
            descending = field.startswith("-")
            name = field[1:] if descending else field
            name = self.replacements.get(name, name)
            mapped.append(f"-{name}" if descending else name)
        return mapped


class TicketFilter(django_filters.FilterSet):
    """Querystring filters for the ticket list."""

    project = django_filters.UUIDFilter(field_name="project_id")
    status = CharInFilter(field_name="status", lookup_expr="in")
    type = CharInFilter(field_name="type", lookup_expr="in")
    priority = CharInFilter(field_name="priority", lookup_expr="in")
    severity = CharInFilter(field_name="severity", lookup_expr="in")
    assignee = django_filters.UUIDFilter(field_name="assignee_id")
    reporter = django_filters.UUIDFilter(field_name="reporter_id")
    component = django_filters.UUIDFilter(field_name="component_id")
    label = django_filters.CharFilter(method="filter_label", label=_("Label name or id"))
    unassigned = django_filters.BooleanFilter(field_name="assignee", lookup_expr="isnull")
    overdue = django_filters.BooleanFilter(method="filter_overdue")
    open_only = django_filters.BooleanFilter(method="filter_open_only")
    due_before = django_filters.DateFilter(field_name="due_date", lookup_expr="lte")
    due_after = django_filters.DateFilter(field_name="due_date", lookup_expr="gte")
    created_after = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Ticket
        fields = ()

    def filter_label(self, queryset, name, value):
        """Match a label by name or by id inside the ticket's project."""
        if not value:
            return queryset
        query = Q(labels__name__iexact=value)
        try:
            query |= Q(labels__id=value)
        except (ValueError, TypeError):  # a non-UUID is simply not an id
            pass
        return queryset.filter(query).distinct()

    def filter_overdue(self, queryset, name, value):
        if value is None:
            return queryset
        predicate = Q(due_date__lt=timezone.localdate(), status__in=list(OPEN_STATUSES))
        return queryset.filter(predicate) if value else queryset.exclude(predicate)

    def filter_open_only(self, queryset, name, value):
        if value is None:
            return queryset
        if value:
            return queryset.filter(status__in=list(OPEN_STATUSES))
        return queryset.exclude(status__in=list(OPEN_STATUSES))