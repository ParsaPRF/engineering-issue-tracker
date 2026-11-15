"""Attachment API serializers.

Note what the read serializer does **not** contain: a URL to the file. The only way to obtain the
bytes is the authorising download endpoint, so a leaked API response contains no usable link
(ADR-010).
"""

from __future__ import annotations

from rest_framework import serializers

from apps.accounts.api.serializers import UserSummarySerializer
from apps.attachments.models import Attachment


class AttachmentSerializer(serializers.ModelSerializer):
    uploader = UserSummarySerializer(read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = (
            "id",
            "ticket",
            "comment",
            "uploader",
            "original_name",
            "content_type",
            "size_bytes",
            "sha256",
            "download_url",
            "created_at",
        )
        read_only_fields = fields

    def get_download_url(self, obj: Attachment) -> str:
        """Relative API path, not a storage URL: the request still has to be authorised."""
        return f"/api/v1/attachments/{obj.pk}/download/"