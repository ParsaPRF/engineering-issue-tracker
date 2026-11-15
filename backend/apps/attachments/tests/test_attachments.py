"""Attachment tests (FR-6.5 … FR-6.8, NFR-1.8, NFR-1.9).

The upload rules and the download authorisation are the point of this module, so the tests spend
their effort on the *rejections*: a wrong extension, an oversized file, a foreign ticket, an object
that does not exist. A file-upload feature that only tests the happy path is a liability.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.attachments.models import Attachment
from apps.attachments.tests.factories import AttachmentFactory
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.comments.tests.factories import CommentFactory
from apps.tickets.tests.factories import TicketFactory

pytestmark = pytest.mark.django_db


def ticket_attachments_url(ticket) -> str:
    return f"/api/v1/tickets/{ticket.id}/attachments/"


def download_url(attachment) -> str:
    return f"/api/v1/attachments/{attachment.id}/download/"


def error_code(response) -> str:
    return response.data["error"]["code"]


def upload(client, url, *, name="evidence.txt", content=b"hello world", content_type="text/plain"):
    return client.post(url, {"file": SimpleUploadedFile(name, content, content_type=content_type)}, format="multipart")


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
def test_member_can_upload_a_ticket_attachment(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = upload(client_for(team.engineer), ticket_attachments_url(ticket))

    assert response.status_code == 201, response.data
    attachment = Attachment.objects.get(pk=response.data["id"])
    assert attachment.original_name == "evidence.txt"
    assert attachment.size_bytes == 11
    assert len(attachment.sha256) == 64
    assert attachment.uploader_id == team.engineer.id
    assert AuditEvent.objects.filter(action=AuditAction.ATTACHMENT_UPLOADED, ticket=ticket).exists()


def test_storage_key_is_random_and_keeps_only_the_extension(client_for, team):
    ticket = TicketFactory(project=team.project)
    response = upload(
        client_for(team.engineer),
        ticket_attachments_url(ticket),
        name="../../etc/passwd.txt",
    )

    attachment = Attachment.objects.get(pk=response.data["id"])
    stored = attachment.file.name
    assert stored.startswith("attachments/")
    assert "passwd" not in stored
    assert ".." not in stored
    assert stored.endswith(".txt")


def test_executable_extension_is_rejected(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = upload(
        client_for(team.engineer),
        ticket_attachments_url(ticket),
        name="payload.svg",
        content_type="image/svg+xml",
    )

    assert response.status_code == 400
    assert error_code(response) == "dangerous_file_type"
    assert not Attachment.objects.exists()


def test_extension_outside_the_allow_list_is_rejected(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = upload(client_for(team.engineer), ticket_attachments_url(ticket), name="data.bin", content_type="application/pdf")

    assert response.status_code == 400
    assert error_code(response) == "unsupported_file_type"


@override_settings(ATTACHMENT_MAX_BYTES=10)
def test_oversized_file_is_rejected_with_an_actionable_message(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = upload(client_for(team.engineer), ticket_attachments_url(ticket), content=b"x" * 50)

    assert response.status_code == 400
    assert error_code(response) == "attachment_too_large"
    assert not Attachment.objects.exists()


def test_missing_file_field_is_a_clear_400(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.engineer).post(ticket_attachments_url(ticket), {}, format="multipart")

    assert response.status_code == 400
    assert "file" in response.data["error"]["fields"]


def test_attachment_on_comment_belongs_to_the_comment_ticket(client_for, team):
    ticket = TicketFactory(project=team.project)
    comment = CommentFactory(ticket=ticket, author=team.engineer)

    response = upload(client_for(team.engineer), f"/api/v1/comments/{comment.id}/attachments/")

    assert response.status_code == 201
    attachment = Attachment.objects.get(pk=response.data["id"])
    assert attachment.comment_id == comment.id
    assert attachment.effective_ticket.id == ticket.id


@pytest.mark.security
def test_outsider_cannot_upload(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = upload(client_for(team.outsider), ticket_attachments_url(ticket))

    assert response.status_code == 404
    assert not Attachment.objects.exists()


# ---------------------------------------------------------------------------
# Read / download
# ---------------------------------------------------------------------------
def test_serializer_never_exposes_a_storage_url(client_for, team):
    ticket = TicketFactory(project=team.project)
    response = upload(client_for(team.engineer), ticket_attachments_url(ticket))

    payload = response.data
    # Only our authorising endpoint — never a bucket URL or a storage path.
    assert payload["download_url"] == f"/api/v1/attachments/{payload['id']}/download/"
    assert "file" not in payload
    assert "http" not in payload["download_url"]


def test_authorised_member_can_download(client_for, team):
    ticket = TicketFactory(project=team.project)
    upload_response = upload(client_for(team.engineer), ticket_attachments_url(ticket), content=b"secret contents")
    attachment_id = upload_response.data["id"]

    response = client_for(team.reporter).get(f"/api/v1/attachments/{attachment_id}/download/")

    assert response.status_code == 200
    body = b"".join(response.streaming_content)
    assert body == b"secret contents"
    # Never rendered inline: neutral type + attachment disposition (stored-XSS defence).
    assert response["Content-Type"] == "application/octet-stream"
    assert "attachment" in response["Content-Disposition"]
    assert AuditEvent.objects.filter(action=AuditAction.ATTACHMENT_DOWNLOADED).exists()


@pytest.mark.security
def test_outsider_gets_404_for_a_download(client_for, team):
    ticket = TicketFactory(project=team.project)
    attachment = AttachmentFactory(ticket=ticket, uploader=team.engineer, is_deleted=False)

    response = client_for(team.outsider).get(download_url(attachment))

    assert response.status_code == 404


@pytest.mark.security
def test_deleted_attachment_is_not_downloadable(client_for, team):
    ticket = TicketFactory(project=team.project)
    attachment = AttachmentFactory(ticket=ticket, uploader=team.engineer, is_deleted=True)

    response = client_for(team.engineer).get(download_url(attachment))

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
def test_uploader_can_delete_and_the_object_is_removed(client_for, team):
    ticket = TicketFactory(project=team.project)
    attachment = AttachmentFactory(ticket=ticket, uploader=team.engineer)

    response = client_for(team.engineer).delete(f"/api/v1/attachments/{attachment.id}/")

    assert response.status_code == 204
    attachment.refresh_from_db()
    assert attachment.is_deleted is True
    assert AuditEvent.objects.filter(action=AuditAction.ATTACHMENT_DELETED).exists()


def test_stranger_cannot_delete_somebody_elses_attachment(client_for, team):
    from apps.accounts.tests.factories import UserFactory
    from apps.projects.models import ProjectMembership, ProjectRole

    other = UserFactory()
    ProjectMembership.objects.create(project=team.project, user=other, role=ProjectRole.ENGINEER)
    ticket = TicketFactory(project=team.project)
    attachment = AttachmentFactory(ticket=ticket, uploader=team.engineer)

    response = client_for(other).delete(f"/api/v1/attachments/{attachment.id}/")

    assert response.status_code == 403
    attachment.refresh_from_db()
    assert attachment.is_deleted is False