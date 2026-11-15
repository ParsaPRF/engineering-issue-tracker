"""Comment API serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.accounts.api.serializers import UserSummarySerializer
from apps.comments.models import Comment


class CommentSerializer(serializers.ModelSerializer):
    """Read representation of a comment."""

    author = UserSummarySerializer(read_only=True)
    is_edited = serializers.BooleanField(read_only=True)
    attachment_count = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = (
            "id",
            "ticket",
            "author",
            "body",
            "is_deleted",
            "is_edited",
            "edited_at",
            "attachment_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_attachment_count(self, obj: Comment) -> int:
        return sum(1 for attachment in obj.attachments.all() if not attachment.is_deleted)


class CommentCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=10_000)

    def validate_body(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A comment cannot be empty.")
        return value


class CommentUpdateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=10_000)

    def validate_body(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A comment cannot be empty.")
        return value