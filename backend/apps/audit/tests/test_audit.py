"""Audit trail tests (FR-8.1 … FR-8.4, ADR-011).

The audit trail is a compliance artefact, so the tests are about the *guarantees*, not the fields:
immutability, sanitisation, read-only access, and the fact that a failed operation leaves no
"success" event behind.
"""

from __future__ import annotations

import pytest
from django.db import transaction

from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.audit.services import record, sanitise_metadata
from apps.tickets.tests.factories import TicketFactory

pytestmark = pytest.mark.django_db


def error_code(response) -> str:
    return response.data["error"]["code"]


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------
def test_an_event_cannot_be_updated(team):
    event = record(action=AuditAction.TICKET_CREATED, actor=team.manager, obj=TicketFactory(project=team.project))

    event.action = "tampered"
    with pytest.raises(RuntimeError):
        event.save()


def test_an_event_cannot_be_deleted(team):
    event = record(action=AuditAction.TICKET_CREATED, actor=team.manager)

    with pytest.raises(RuntimeError):
        event.delete()


def test_only_an_attempt_that_committed_leaves_an_event(team):
    """An audit row is written inside the operation's transaction: a rollback takes it with it."""
    before = AuditEvent.objects.count()

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            record(action=AuditAction.PROJECT_UPDATED, actor=team.manager, obj=team.project)
            raise RuntimeError("business operation failed")

    assert AuditEvent.objects.count() == before


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------
def test_events_capture_actor_object_and_request_context(team, rf):
    ticket = TicketFactory(project=team.project)
    request = rf.post("/api/v1/tickets/", HTTP_USER_AGENT="pytest-agent", REMOTE_ADDR="10.1.2.3")

    event = record(
        action=AuditAction.TICKET_UPDATED,
        actor=team.manager,
        obj=ticket,
        metadata={"changed": ["title"]},
        request=request,
    )

    assert event.actor_id == team.manager.id
    assert event.object_type == "tickets.ticket"
    assert event.object_id == ticket.id
    assert event.project_id == team.project.id
    assert event.ticket_id == ticket.id
    assert event.ip_address == "10.1.2.3"
    assert event.user_agent == "pytest-agent"


def test_sensitive_metadata_is_redacted():
    cleaned = sanitise_metadata(
        {
            "email": "a@example.com",
            "password": "hunter2",
            "new_password": "still-secret",
            "api_key": "abc",
            "nested": {"authorization": "Bearer x", "safe": "ok"},
        }
    )

    assert cleaned["email"] == "a@example.com"
    assert cleaned["password"] == "<redacted>"
    assert cleaned["new_password"] == "<redacted>"
    assert cleaned["api_key"] == "<redacted>"
    assert cleaned["nested"]["authorization"] == "<redacted>"
    assert cleaned["nested"]["safe"] == "ok"
    assert "hunter2" not in str(cleaned)


def test_long_values_are_truncated():
    cleaned = sanitise_metadata({"body": "x" * 5_000})

    assert len(cleaned["body"]) <= 501
    assert cleaned["body"].endswith("…")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def test_audit_api_is_admin_only(client_for, team):
    record(action=AuditAction.TICKET_CREATED, actor=team.manager, obj=TicketFactory(project=team.project))

    response = client_for(team.manager).get("/api/v1/audit/")

    assert response.status_code == 403
    assert error_code(response) == "permission_denied"


def test_admin_can_read_the_audit_trail(client_for, admin_user, team):
    record(action=AuditAction.PROJECT_UPDATED, actor=team.manager, obj=team.project, project=team.project)

    response = client_for(admin_user).get("/api/v1/audit/")

    assert response.status_code == 200
    assert response.data["count"] >= 1


def test_audit_api_is_read_only(client_for, admin_user):
    response = client_for(admin_user).post("/api/v1/audit/", {"action": "fake"}, format="json")

    assert response.status_code == 405


def test_audit_api_cannot_delete(client_for, admin_user, team):
    event = record(action=AuditAction.PROJECT_UPDATED, actor=team.manager, obj=team.project)

    response = client_for(admin_user).delete(f"/api/v1/audit/{event.id}/")

    assert response.status_code == 405
    assert AuditEvent.objects.filter(pk=event.pk).exists()


def test_reactions_are_attributed_to_a_real_actor(api_client, team):
    """A registration initiated by a stranger is attributed to the new account, not to "system"."""
    from apps.accounts.models import User

    api_client.post(
        "/api/v1/auth/register/",
        {
            "email": "fresh@example.com",
            "full_name": "Fresh User",
            "password": "Str0ng-Passw0rd!",
            "password_confirm": "Str0ng-Passw0rd!",
        },
        format="json",
    )

    user = User.objects.get(email="fresh@example.com")
    event = AuditEvent.objects.get(action=AuditAction.USER_REGISTERED)
    assert event.actor_id == user.id