"""Comment API views.

Comments are reachable through two routes, mirroring how people use them:

* ``/tickets/<ticket_id>/comments/`` — list and create in the context of a ticket;
* ``/comments/<id>/`` — edit and delete a specific comment.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.comments.api.serializers import (
    CommentCreateSerializer,
    CommentSerializer,
    CommentUpdateSerializer,
)
from apps.comments.models import Comment
from apps.comments.selectors import get_visible_comment, ticket_comments
from apps.comments.services import create_comment, delete_comment, update_comment
from apps.tickets.selectors import tickets as ticket_selectors
from common.exceptions import ResourceNotFound


class TicketCommentsView(APIView):
    """``GET`` / ``POST /api/v1/tickets/<ticket_id>/comments/``."""

    @extend_schema(responses={200: CommentSerializer(many=True)})
    def get(self, request, ticket_id):
        ticket = ticket_selectors.get_visible_ticket(request.user, ticket_id)
        if ticket is None:
            raise ResourceNotFound("No such ticket.")
        return Response(CommentSerializer(ticket_comments(ticket), many=True).data)

    @extend_schema(request=CommentCreateSerializer, responses={201: CommentSerializer})
    def post(self, request, ticket_id):
        ticket = ticket_selectors.get_visible_ticket(request.user, ticket_id)
        if ticket is None:
            raise ResourceNotFound("No such ticket.")

        serializer = CommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = create_comment(
            actor=request.user, ticket=ticket, body=serializer.validated_data["body"], request=request
        )
        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class CommentViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """``/api/v1/comments/<id>/`` — retrieve, edit, delete."""

    serializer_class = CommentSerializer

    def get_queryset(self):
        from apps.tickets.selectors.tickets import visible_tickets

        # Scoped by the *ticket's* visibility, which is what governs access to its comments.
        return (
            Comment.objects.filter(ticket__in=visible_tickets(self.request.user))
            .select_related("ticket", "author")
            .prefetch_related("attachments")
        )

    @extend_schema(request=CommentUpdateSerializer, responses={200: CommentSerializer})
    def partial_update(self, request, pk=None):
        comment = get_visible_comment(request.user, pk)
        if comment is None:
            raise ResourceNotFound("No such comment.")

        serializer = CommentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = update_comment(
            actor=request.user, comment=comment, body=serializer.validated_data["body"], request=request
        )
        return Response(CommentSerializer(comment).data)

    @extend_schema(request=None, responses={204: None})
    def destroy(self, request, pk=None):
        comment = get_visible_comment(request.user, pk)
        if comment is None:
            raise ResourceNotFound("No such comment.")

        delete_comment(actor=request.user, comment=comment, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)