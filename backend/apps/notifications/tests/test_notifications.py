"""Notification tests (FR-7.1 … FR-7.5, ADR-009).

Two properties are being protected here:

* **the right people** are notified (audience computation), and the actor never is;
* **nobody is notified twice** for the same event — enforced by a unique ``dedup_key`` in the data
  model rather than by hoping the task runs once.

Celery runs eagerly in tests (``config.settings.test``), so the task really executes and its effect
(``is_sent``) is asserted instead of being mocked.
"""

from __future__ import annotations

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.notifications.models import Notification, NotificationEvent
from apps.notifications.services import notify
from apps.notifications.tasks import retry_unsent_notifications, send_notification
from apps.tickets.models import TicketStatus
from apps.tickets.tests.factories import TicketFactory

pytestmark = pytest.mark.django_db


def recipients_of(event_type: str) -> set[str]:
    return set(
        Notification.objects.filter(event_type=event_type).values_list("recipient__email", flat=True)
    )


# ---------------------------------------------------------------------------
# Audience
# ---------------------------------------------------------------------------
def test_ticket_creation_notifies_project_managers(client_for, team):
    payload = {
        "project": str(team.project.id),
        "title": "Printer on fire",
        "description": "It is on fire",
        "type": "BUG",
        "priority": "CRITICAL",
        "severity": "CRITICAL",
    }

    client_for(team.reporter).post("/api/v1/tickets/", payload, format="json")

    assert team.manager.email in recipients_of(NotificationEvent.TICKET_CREATED)
    assert team.reporter.email not in recipients_of(NotificationEvent.TICKET_CREATED)


def test_assignment_notifies_the_assignee(client_for, team):
    ticket = TicketFactory(project=team.project)

    client_for(team.manager).post(f"/api/v1/tickets/{ticket.id}/assign/", {"assignee": str(team.engineer.id)}, format="json")

    assert team.engineer.email in recipients_of(NotificationEvent.TICKET_ASSIGNED)


def test_reassignment_notifies_the_new_assignee(client_for, team):
    ticket = TicketFactory(project=team.project, assignee=team.manager)

    client_for(team.manager).post(f"/api/v1/tickets/{ticket.id}/assign/", {"assignee": str(team.engineer.id)}, format="json")

    assert team.engineer.email in recipients_of(NotificationEvent.TICKET_REASSIGNED)


def test_status_change_notifies_reporter_and_assignee_but_not_the_actor(client_for, team):
    ticket = TicketFactory(project=team.project, reporter=team.reporter, assignee=team.engineer)

    client_for(team.manager).post(
        f"/api/v1/tickets/{ticket.id}/transitions/", {"to_status": TicketStatus.TRIAGED}, format="json"
    )

    recipients = recipients_of(NotificationEvent.TICKET_STATUS_CHANGED)
    assert team.reporter.email in recipients
    assert team.engineer.email in recipients
    assert team.manager.email not in recipients


def test_resolution_produces_a_specific_event_type(client_for, team):
    from django.utils import timezone

    ticket = TicketFactory(
        project=team.project,
        status=TicketStatus.IN_REVIEW,
        reporter=team.reporter,
        assignee=team.engineer,
    )

    client_for(team.manager).post(
        f"/api/v1/tickets/{ticket.id}/transitions/",
        {"to_status": TicketStatus.RESOLVED, "comment": "Shipped in 2.4.1"},
        format="json",
    )

    assert recipients_of(NotificationEvent.TICKET_RESOLVED)
    assert not Notification.objects.filter(event_type=NotificationEvent.TICKET_STATUS_CHANGED).exists()
    assert timezone.now() is not None


def test_membership_addition_notifies_the_new_member(client_for, team):
    newcomer = UserFactory()

    client_for(team.manager).post(
        f"/api/v1/projects/{team.project.id}/members/",
        {"user": str(newcomer.id), "role": "ENGINEER"},
        format="json",
    )

    assert newcomer.email in recipients_of(NotificationEvent.MEMBERSHIP_ADDED)


# ---------------------------------------------------------------------------
# Idempotency and delivery
# ---------------------------------------------------------------------------
def test_the_same_event_does_not_produce_a_second_row(team):
    first = notify(
        event_type=NotificationEvent.TICKET_STATUS_CHANGED,
        recipients=[team.reporter],
        actor=team.manager,
        ticket=TicketFactory(project=team.project),
        subject="ticket:duplicate-test",
        suffix="same-event",
        title="Once",
    )
    second = notify(
        event_type=NotificationEvent.TICKET_STATUS_CHANGED,
        recipients=[team.reporter],
        actor=team.manager,
        ticket=TicketFactory(project=team.project),
        subject="ticket:duplicate-test",
        suffix="same-event",
        title="Once",
    )

    assert len(first) == 1
    assert second == []  # deduplicated: same recipient + event + subject + suffix


def test_the_actor_is_never_notified_about_their_own_action(team):
    created = notify(
        event_type=NotificationEvent.COMMENT_ADDED,
        recipients=[team.manager],
        actor=team.manager,
        subject="ticket:self",
        title="Self",
    )

    assert created == []


def test_inactive_recipients_are_skipped(team):
    team.engineer.is_active = False
    team.engineer.save(update_fields=["is_active"])

    created = notify(
        event_type=NotificationEvent.TICKET_ASSIGNED,
        recipients=[team.engineer],
        actor=team.manager,
        subject="ticket:inactive",
        title="Nope",
    )

    assert created == []


def test_delivery_marks_the_row_as_sent(team):
    notification = notify(
        event_type=NotificationEvent.TICKET_CREATED,
        recipients=[team.reporter],
        actor=team.manager,
        subject="ticket:sent-check",
        title="Sent",
    )[0]

    # Celery runs eagerly in tests, so the task has already executed.
    notification.refresh_from_db()
    assert notification.is_sent is True
    assert notification.sent_at is not None


def test_running_the_task_twice_is_a_no_op(team):
    notification = notify(
        event_type=NotificationEvent.TICKET_CREATED,
        recipients=[team.reporter],
        actor=team.manager,
        subject="ticket:twice",
        title="Twice",
    )[0]

    assert send_notification(str(notification.id)) == "already-sent"
    assert Notification.objects.filter(recipient=team.reporter).count() == 1


def test_missing_notification_is_handled_gracefully():
    assert send_notification("00000000-0000-0000-0000-000000000000") == "missing"


def test_retry_task_redrives_unsent_notifications(team):
    from datetime import timedelta

    from django.utils import timezone

    notification = Notification.objects.create(
        recipient=team.reporter,
        actor=team.manager,
        event_type=NotificationEvent.TICKET_CREATED,
        title="Stuck",
        dedup_key="retry-test",
    )
    Notification.objects.filter(pk=notification.pk).update(created_at=timezone.now() - timedelta(hours=1))

    count = retry_unsent_notifications()

    notification.refresh_from_db()
    assert count == 1
    assert notification.is_sent is True


# ---------------------------------------------------------------------------
# Inbox API (FR-7.4, FR-7.5)
# ---------------------------------------------------------------------------
def test_inbox_only_contains_my_notifications(client_for, team):
    Notification.objects.create(recipient=team.engineer, event_type="ticket.created", title="Mine")
    Notification.objects.create(recipient=team.reporter, event_type="ticket.created", title="Theirs")

    response = client_for(team.engineer).get("/api/v1/notifications/")

    assert response.status_code == 200
    assert [row["title"] for row in response.data["results"]] == ["Mine"]


def test_unread_count_and_mark_read(client_for, team):
    notification = Notification.objects.create(recipient=team.engineer, event_type="ticket.created", title="Unread")
    client = client_for(team.engineer)

    assert client.get("/api/v1/notifications/unread-count/").data == {"unread": 1}
    assert client.post(f"/api/v1/notifications/{notification.id}/read/").status_code == 200
    assert client.get("/api/v1/notifications/unread-count/").data == {"unread": 0}

    notification.refresh_from_db()
    assert notification.is_read is True and notification.read_at is not None


def test_mark_all_read(client_for, team):
    for index in range(3):
        Notification.objects.create(recipient=team.engineer, event_type="ticket.created", title=f"N{index}")

    response = client_for(team.engineer).post("/api/v1/notifications/read-all/")

    assert response.status_code == 200
    assert response.data["marked_read"] == 3


@pytest.mark.security
def test_cannot_read_someone_elses_notification(client_for, team):
    notification = Notification.objects.create(recipient=team.reporter, event_type="ticket.created", title="Private")

    response = client_for(team.engineer).get(f"/api/v1/notifications/{notification.id}/")

    assert response.status_code == 404