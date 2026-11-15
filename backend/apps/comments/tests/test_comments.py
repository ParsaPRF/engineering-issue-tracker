"""Comment tests (FR-6.1 … FR-6.4).

The edit/delete rules are the interesting part: an author may correct their words for a while, then
the comment becomes part of the record; a manager may moderate but never rewrite.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.comments.models import Comment
from apps.comments.tests.factories import CommentFactory
from apps.notifications.models import Notification, NotificationEvent
from apps.tickets.tests.factories import TicketFactory

pytestmark = pytest.mark.django_db


def comments_url(ticket) -> str:
    return f"/api/v1/tickets/{ticket.id}/comments/"


def comment_url(comment) -> str:
    return f"/api/v1/comments/{comment.id}/"


def error_code(response) -> str:
    return response.data["error"]["code"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
def test_member_can_comment(client_for, team):
    ticket = TicketFactory(project=team.project, reporter=team.reporter)

    response = client_for(team.engineer).post(comments_url(ticket), {"body": "Reproduced on staging"}, format="json")

    assert response.status_code == 201, response.data
    comment = Comment.objects.get(pk=response.data["id"])
    assert comment.body == "Reproduced on staging"
    assert comment.author_id == team.engineer.id
    assert AuditEvent.objects.filter(action=AuditAction.COMMENT_CREATED, ticket=ticket).exists()


def test_empty_comment_is_rejected(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.engineer).post(comments_url(ticket), {"body": "   "}, format="json")

    assert response.status_code == 400
    assert error_code(response) == "validation_error"


def test_comment_length_is_bounded(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.engineer).post(comments_url(ticket), {"body": "x" * 10_001}, format="json")

    assert response.status_code == 400


@pytest.mark.security
def test_outsider_cannot_comment(client_for, team):
    ticket = TicketFactory(project=team.project)

    response = client_for(team.outsider).post(comments_url(ticket), {"body": "hello"}, format="json")

    assert response.status_code == 404


def test_deleted_comments_are_hidden_from_the_list(client_for, team):
    ticket = TicketFactory(project=team.project)
    CommentFactory(ticket=ticket, author=team.engineer, body="visible")
    CommentFactory(ticket=ticket, author=team.engineer, body="hidden", is_deleted=True)

    response = client_for(team.engineer).get(comments_url(ticket))

    assert response.status_code == 200
    assert [row["body"] for row in response.data] == ["visible"]


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------
def test_author_can_edit_within_the_window(client_for, team):
    ticket = TicketFactory(project=team.project)
    comment = CommentFactory(ticket=ticket, author=team.engineer, body="typo")

    response = client_for(team.engineer).patch(comment_url(comment), {"body": "fixed"}, format="json")

    assert response.status_code == 200
    comment.refresh_from_db()
    assert comment.body == "fixed"
    assert comment.edited_at is not None
    assert AuditEvent.objects.filter(action=AuditAction.COMMENT_UPDATED, ticket=ticket).exists()


def test_edit_window_closes(client_for, team):
    ticket = TicketFactory(project=team.project)
    comment = CommentFactory(ticket=ticket, author=team.engineer, body="old")
    Comment.objects.filter(pk=comment.pk).update(created_at=timezone.now() - timedelta(hours=2))

    response = client_for(team.engineer).patch(comment_url(comment), {"body": "too late"}, format="json")

    assert response.status_code == 400
    assert error_code(response) == "edit_window_closed"


def test_only_the_author_can_edit(client_for, team):
    ticket = TicketFactory(project=team.project)
    comment = CommentFactory(ticket=ticket, author=team.engineer, body="mine")

    response = client_for(team.manager).patch(comment_url(comment), {"body": "rewritten"}, format="json")

    assert response.status_code == 403
    comment.refresh_from_db()
    assert comment.body == "mine"  # managers moderate, they do not rewrite other people's words


def test_edited_flag_is_exposed(client_for, team):
    ticket = TicketFactory(project=team.project)
    comment = CommentFactory(ticket=ticket, author=team.engineer, body="v1")
    client_for(team.engineer).patch(comment_url(comment), {"body": "v2"}, format="json")

    response = client_for(team.engineer).get(comment_url(comment))

    assert response.data["is_edited"] is True


# ---------------------------------------------------------------------------
# Delete (soft)
# ---------------------------------------------------------------------------
def test_author_can_delete_their_comment_softly(client_for, team):
    ticket = TicketFactory(project=team.project)
    comment = CommentFactory(ticket=ticket, author=team.engineer)

    response = client_for(team.engineer).delete(comment_url(comment))

    assert response.status_code == 204
    comment.refresh_from_db()
    assert comment.is_deleted is True  # the row survives for the record
    assert AuditEvent.objects.filter(action=AuditAction.COMMENT_DELETED, ticket=ticket).exists()


def test_manager_can_moderate_any_comment(client_for, team):
    ticket = TicketFactory(project=team.project)
    comment = CommentFactory(ticket=ticket, author=team.engineer)

    response = client_for(team.manager).delete(comment_url(comment))

    assert response.status_code == 204
    comment.refresh_from_db()
    assert comment.is_deleted is True
    event = AuditEvent.objects.get(action=AuditAction.COMMENT_DELETED, ticket=ticket)
    assert event.metadata["as_moderator"] is True


def test_unrelated_member_cannot_delete_someone_elses_comment(client_for, team):
    from apps.projects.models import ProjectMembership, ProjectRole

    other = UserFactory()
    ProjectMembership.objects.create(project=team.project, user=other, role=ProjectRole.ENGINEER)
    ticket = TicketFactory(project=team.project)
    comment = CommentFactory(ticket=ticket, author=team.engineer)

    response = client_for(other).delete(comment_url(comment))

    assert response.status_code == 403


def test_deleting_twice_is_a_business_error(client_for, team):
    ticket = TicketFactory(project=team.project)
    comment = CommentFactory(ticket=ticket, author=team.engineer, is_deleted=True)

    response = client_for(team.engineer).delete(comment_url(comment))

    assert response.status_code == 400
    assert error_code(response) == "already_deleted"


# ---------------------------------------------------------------------------
# Notifications on comments (FR-6.4)
# ---------------------------------------------------------------------------
def test_comment_notifies_audience_but_not_the_author(client_for, team):
    ticket = TicketFactory(project=team.project, reporter=team.reporter, assignee=team.engineer)

    client_for(team.manager).post(comments_url(ticket), {"body": "Please look"}, format="json")

    recipients = set(
        Notification.objects.filter(event_type=NotificationEvent.COMMENT_ADDED).values_list(
            "recipient__email", flat=True
        )
    )
    assert team.reporter.email in recipients
    assert team.engineer.email in recipients
    assert team.manager.email not in recipients  # never notified about their own action