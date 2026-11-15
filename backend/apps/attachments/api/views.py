"""Attachment API: private upload, metadata listing, and the authorised download endpoint.

The download endpoint is the security-critical one (ADR-010):

* it re-checks visibility **from the attachment to its ticket's project** on every request — the
  client never receives a storage URL, so there is no link to share and no object id to guess;
* it forces ``Content-Disposition: attachment`` and a neutral content type, so a file that somehow
  slipped past the extension allow-list still cannot execute in the browser;
* it records the access in the audit trail before streaming.
"""

from __future__ import annotations

from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.attachments.api.serializers import AttachmentSerializer
from apps.attachments.selectors import for_ticket, get_visible_attachment, visible_attachments
from apps.attachments.services import (
    delete_attachment,
    record_download,
    safe_download_name,
    upload_attachment,
)
from apps.comments.selectors import get_visible_comment
from apps.tickets.selectors import tickets as ticket_selectors
from common.exceptions import ResourceNotFound


class TicketAttachmentsView(APIView):
    """``GET`` / ``POST /api/v1/tickets/<ticket_id>/attachments/``."""

    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(responses={200: AttachmentSerializer(many=True)})
    def get(self, request, ticket_id):
        ticket = ticket_selectors.get_visible_ticket(request.user, ticket_id)
        if ticket is None:
            raise ResourceNotFound("No such ticket.")
        return Response(AttachmentSerializer(for_ticket(request.user, ticket), many=True).data)

    @extend_schema(request=AttachmentSerializer, responses={201: AttachmentSerializer})
    def post(self, request, ticket_id):
        ticket = ticket_selectors.get_visible_ticket(request.user, ticket_id)
        if ticket is None:
            raise ResourceNotFound("No such ticket.")

        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response(
                {
                    "error": {
                        "code": "validation_error",
                        "detail": "A file is required.",
                        "fields": {"file": ["No file was submitted."]},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        attachment = upload_attachment(
            actor=request.user, uploaded_file=uploaded, ticket=ticket, request=request
        )
        return Response(AttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)


class CommentAttachmentsView(APIView):
    """``POST /api/v1/comments/<comment_id>/attachments/`` — attach evidence to a comment."""

    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request=AttachmentSerializer, responses={201: AttachmentSerializer})
    def post(self, request, comment_id):
        comment = get_visible_comment(request.user, comment_id)
        if comment is None:
            raise ResourceNotFound("No such comment.")

        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response(
                {
                    "error": {
                        "code": "validation_error",
                        "detail": "A file is required.",
                        "fields": {"file": ["No file was submitted."]},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        attachment = upload_attachment(
            actor=request.user,
            uploaded_file=uploaded,
            ticket=comment.ticket,
            comment=comment,
            request=request,
        )
        return Response(AttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)


class AttachmentViewSet(mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """``/api/v1/attachments/`` — list, delete, download."""

    serializer_class = AttachmentSerializer
    filterset_fields = ("ticket", "comment")

    def get_queryset(self):
        return visible_attachments(self.request.user)

    @extend_schema(responses={200: AttachmentSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=None, responses={204: None})
    def destroy(self, request, *args, **kwargs):
        attachment = self.get_object()
        delete_attachment(actor=request.user, attachment=attachment, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def download(self, request, pk=None):
        """Stream the private object to an authorised caller.

        Not a serializer-based action: the response is a file stream, and routing it through DRF's
        content negotiation would be pointless overhead.
        """
        attachment = get_visible_attachment(request.user, pk)
        if attachment is None:
            raise ResourceNotFound("No such attachment.")

        record_download(actor=request.user, attachment=attachment, request=request)

        response = FileResponse(
            attachment.file.open("rb"),
            as_attachment=True,
            filename=safe_download_name(attachment),
            # Deliberately neutral: never echo the uploaded content type back as the response type.
            content_type="application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response