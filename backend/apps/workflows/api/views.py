"""Workflow API: the transition operation and the lifecycle catalogue."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tickets.api.serializers import TicketSerializer
from apps.tickets.selectors import tickets as ticket_selectors
from apps.workflows import services as workflow_services
from apps.workflows import state_machine
from apps.workflows.selectors import ticket_history, transition_catalogue


class TransitionInputSerializer(serializers.Serializer):
    """Payload for a status change.

    ``to_status`` is validated as a plain string here and against the state machine in the service:
    the serializer cannot know the ticket's current status, so it cannot know which moves are legal.
    """

    to_status = serializers.CharField(max_length=20)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class StatusHistorySerializer(serializers.Serializer):
    """One point in the ticket timeline."""

    id = serializers.UUIDField()
    from_status = serializers.CharField(allow_null=True)
    to_status = serializers.CharField()
    changed_by = serializers.UUIDField(source="changed_by_id")
    changed_by_name = serializers.CharField(source="changed_by.full_name")
    comment = serializers.CharField()
    created_at = serializers.DateTimeField()


class TicketTransitionViewSet(viewsets.GenericViewSet):
    """Ticket-scoped workflow actions, mounted under ``/tickets/<ticket_id>/``."""

    serializer_class = TicketSerializer
    # The URL carries the ticket id, so the kwarg is renamed — but the *lookup* stays on the primary
    # key. Setting lookup_field="ticket_id" would filter by a non-existent column.
    lookup_field = "pk"
    lookup_url_kwarg = "ticket_id"

    def get_queryset(self):
        # Permission-scoped: a ticket the caller cannot see yields 404, not 403 (NFR-1.3).
        return ticket_selectors.visible_tickets(self.request.user)

    @extend_schema(request=TransitionInputSerializer, responses={200: TicketSerializer})
    @action(detail=True, methods=["post"], url_path="transitions")
    def transitions(self, request, ticket_id=None):
        ticket = self.get_object()
        serializer = TransitionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        workflow_services.transition_ticket(
            ticket=ticket,
            to_status=serializer.validated_data["to_status"],
            actor=request.user,
            comment=serializer.validated_data.get("comment", ""),
            request=request,
        )
        ticket.refresh_from_db()
        return Response(
            TicketSerializer(ticket, context={"request": request}).data, status=status.HTTP_200_OK
        )

    @extend_schema(responses={200: StatusHistorySerializer(many=True)})
    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, ticket_id=None):
        ticket = self.get_object()
        return Response(StatusHistorySerializer(ticket_history(ticket), many=True).data)


class TicketTransitionsView(APIView):
    """``GET /workflows/transitions/?ticket=<uuid>`` — what the caller may do next (FR-5.8).

    The frontend renders status buttons from this response, so the UI can never offer a move the
    backend would reject, and can explain unavailable ones through ``blocked_by``.
    """

    @extend_schema(responses={200: None})
    def get(self, request):
        ticket_id = request.query_params.get("ticket")
        if not ticket_id:
            return Response(
                {
                    "error": {
                        "code": "validation_error",
                        "detail": _("The 'ticket' query parameter is required."),
                        "fields": {"ticket": ["This query parameter is required."]},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        ticket = ticket_selectors.get_visible_ticket(request.user, ticket_id)
        if ticket is None:
            return Response(
                {"error": {"code": "not_found", "detail": _("The requested resource was not found.")}},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "ticket_id": str(ticket.id),
                "current_status": ticket.status,
                "allowed": workflow_services.allowed_transitions_for(ticket=ticket, actor=request.user),
            }
        )


class WorkflowCatalogueView(APIView):
    """``GET /workflows/`` — the complete lifecycle definition, for documentation and clients."""

    @extend_schema(responses={200: None})
    def get(self, request):
        transitions, statuses = transition_catalogue()
        return Response(
            {
                "statuses": statuses,
                "transitions": transitions,
                "declared_move_count": len(state_machine.TRANSITION_TABLE),
            }
        )