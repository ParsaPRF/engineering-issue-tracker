"""Ticket API views (FR-3.x, FR-4.x).

The list endpoint is the hottest path in the product, so two performance habits are baked in:

* the queryset comes from a selector that has already joined every rendered relation,
* filters/ordering/search run in SQL through ``django-filter`` and DRF's filter backends.

Authorisation never appears as an ``if`` in this file: the queryset is permission-scoped, and writes
go through services that re-check the capability. A view that forgets a check still cannot leak.
"""

from __future__ import annotations

from django.db.models import Case, IntegerField, Value, When
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from apps.accounts.selectors import users as user_selectors
from apps.projects.models import Component
from apps.projects.selectors import projects as project_selectors
from apps.tickets.api.filters import TicketFilter, TicketOrderingFilter
from apps.tickets.api.serializers import (
    AssignTicketSerializer,
    LabelSerializer,
    TicketChoicesSerializer,
    TicketCreateSerializer,
    TicketListSerializer,
    TicketSerializer,
    TicketUpdateSerializer,
)
from apps.tickets.models import Label, Priority, Severity, TicketStatus, TicketType
from apps.tickets.selectors import tickets as ticket_selectors
from apps.tickets.services import tickets as ticket_services
from common.exceptions import InvariantViolation, ResourceNotFound

#: Numeric ranks for the two qualitative orderings. Declared once so the API and any report agree.
PRIORITY_RANK = {"LOWEST": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4, "CRITICAL": 5}
SEVERITY_RANK = {"TRIVIAL": 1, "MINOR": 2, "MAJOR": 3, "CRITICAL": 4, "BLOCKER": 5}


def _rank(field_name: str, mapping: dict[str, int]):
    """``CASE WHEN field = value THEN rank`` — makes qualitative ordering correct in SQL."""
    return Case(
        *[When(**{field_name: value}, then=Value(rank)) for value, rank in mapping.items()],
        default=Value(0),
        output_field=IntegerField(),
    )


def _choices(enum_class) -> list[dict]:
    return [{"value": member.value, "label": member.label} for member in enum_class]


class TicketViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """``/api/v1/tickets/`` — the ticket collection and its operations."""

    filterset_class = TicketFilter
    filter_backends = (DjangoFilterBackend, SearchFilter, TicketOrderingFilter)
    search_fields = ("key", "title", "description")
    ordering_fields = (
        "created_at",
        "updated_at",
        "priority",
        "severity",
        "due_date",
        "status",
        "key",
        "title",
    )
    ordering = ("-created_at",)

    def get_queryset(self):
        queryset = ticket_selectors.with_counts(ticket_selectors.visible_tickets(self.request.user))
        # Rank annotations make ?ordering=priority / ordering=severity semantically correct; see
        # TicketOrderingFilter. Cheap: two CASE expressions, evaluated in the same query.
        return queryset.annotate(
            priority_rank=_rank("priority", PRIORITY_RANK),
            severity_rank=_rank("severity", SEVERITY_RANK),
        )

    def get_serializer_class(self):
        # The list does not need descriptions and labels; the detail does.
        return TicketListSerializer if self.action == "list" else TicketSerializer

    # -- Read -----------------------------------------------------------------
    @extend_schema(responses={200: TicketListSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(responses={200: TicketSerializer})
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    # -- Create ---------------------------------------------------------------
    @extend_schema(request=TicketCreateSerializer, responses={201: TicketSerializer})
    def create(self, request, *args, **kwargs):
        serializer = TicketCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        project = project_selectors.get_visible_project(request.user, data["project"])
        if project is None:
            raise ResourceNotFound("No such project.")

        component = None
        if data.get("component"):
            component = Component.objects.filter(pk=data["component"], project=project).first()
            if component is None:
                raise ResourceNotFound("No such component in this project.")

        assignee = None
        if data.get("assignee"):
            assignee = user_selectors.get_user_by_id(data["assignee"])
            if assignee is None:
                raise ResourceNotFound("No such user.")

        ticket = ticket_services.create_ticket(
            actor=request.user,
            project=project,
            title=data["title"],
            description=data["description"],
            type=data.get("type", TicketType.BUG),
            priority=data.get("priority", Priority.MEDIUM),
            severity=data.get("severity", Severity.MAJOR),
            component=component,
            assignee=assignee,
            due_date=data.get("due_date"),
            labels=data.get("labels"),
            request=request,
        )
        return Response(
            TicketSerializer(ticket, context={"request": request}).data, status=status.HTTP_201_CREATED
        )

    # -- Update ---------------------------------------------------------------
    @extend_schema(request=TicketUpdateSerializer, responses={200: TicketSerializer})
    def partial_update(self, request, *args, **kwargs):
        ticket = self.get_object()

        # Reject rather than silently drop: a client sending `status` must not believe it worked.
        if "status" in request.data:
            raise InvariantViolation(
                "Ticket status changes go through the transition endpoint.",
                code="use_transition_endpoint",
                fields={"status": ["Use POST /tickets/<id>/transitions/ to change the status."]},
            )
        if "assignee" in request.data:
            raise InvariantViolation(
                "Use the assignment endpoint to change the assignee.",
                code="use_assignment_endpoint",
                fields={"assignee": ["Use POST /tickets/<id>/assign/."]},
            )

        serializer = TicketUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        data = dict(serializer.validated_data)
        if "component" in data and data["component"] is not None:
            component = Component.objects.filter(pk=data["component"], project=ticket.project).first()
            if component is None:
                raise ResourceNotFound("No such component in this project.")
            data["component"] = component

        ticket = ticket_services.update_ticket(
            actor=request.user, ticket=ticket, data=data, request=request
        )
        return Response(TicketSerializer(ticket, context={"request": request}).data)

    # -- Assignment -----------------------------------------------------------
    @extend_schema(request=AssignTicketSerializer, responses={200: TicketSerializer})
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        ticket = self.get_object()
        serializer = AssignTicketSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assignee = None
        if serializer.validated_data.get("assignee"):
            assignee = user_selectors.get_user_by_id(serializer.validated_data["assignee"])
            if assignee is None:
                raise ResourceNotFound("No such user.")

        ticket = ticket_services.assign_ticket(
            actor=request.user, ticket=ticket, assignee=assignee, request=request
        )
        return Response(TicketSerializer(ticket, context={"request": request}).data)

    # -- Collections ----------------------------------------------------------
    @extend_schema(responses={200: TicketListSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="my-assignments")
    def my_assignments(self, request):
        include_done = request.query_params.get("include_done") == "true"
        queryset = ticket_selectors.my_assignments(request.user, include_done=include_done)

        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(TicketListSerializer(page, many=True).data)
        return Response(TicketListSerializer(queryset, many=True).data)

    @extend_schema(responses={200: TicketChoicesSerializer})
    @action(detail=False, methods=["get"])
    def choices(self, request):
        """Enumerations for the ticket forms.

        Exposed so the frontend does not hard-code statuses and priorities: adding a state in the
        backend then shows up in the UI without a frontend release.
        """
        return Response(
            {
                "statuses": _choices(TicketStatus),
                "types": _choices(TicketType),
                "priorities": _choices(Priority),
                "severities": _choices(Severity),
            }
        )


class LabelViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """``/api/v1/labels/`` — project labels.

    Scoped by project like everything else: a caller only sees labels of projects they belong to, and
    only managers may create them (labels are project taxonomy, not personal tags).
    """

    serializer_class = LabelSerializer
    filterset_fields = ("project",)
    ordering = ("name",)

    def get_queryset(self):
        return Label.objects.filter(
            project__in=project_selectors.projects_visible_to(self.request.user)
        ).select_related("project")

    @extend_schema(request=LabelSerializer, responses={201: LabelSerializer})
    def create(self, request, *args, **kwargs):
        from apps.projects.permissions import can_manage_components

        serializer = LabelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project_id = request.data.get("project")
        project = project_selectors.get_visible_project(request.user, project_id)
        if project is None:
            raise ResourceNotFound("No such project.")
        if not can_manage_components(request.user, project):
            from common.exceptions import AccessDenied

            raise AccessDenied("Only project managers can create labels.")

        label, _created = Label.objects.get_or_create(
            project=project, name=serializer.validated_data["name"].strip(), defaults={"color": serializer.validated_data.get("color", "#6b7280")}
        )
        return Response(LabelSerializer(label).data, status=status.HTTP_201_CREATED)