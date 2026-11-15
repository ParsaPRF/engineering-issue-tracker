"""Notification services: who gets told, what they are told, and why it cannot duplicate.

Design in one paragraph: the request path never talks to a broker for long. It creates a
``Notification`` row — cheap, transactional, visible in the UI immediately — and then *tries* to
enqueue a Celery task. If the broker is unavailable the request still succeeds, the row stays
``is_sent = False``, and a periodic task re-drives it (``tasks.retry_unsent_notifications``).
Duplication is prevented in the data model by a unique ``dedup_key`` that encodes
(recipient, event, subject), so at-least-once delivery cannot become at-least-twice notification
(ADR-009).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.notifications.models import Notification, NotificationEvent
from apps.projects.models import ProjectMembership, ProjectRole
from apps.tickets.models import TicketStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recipient computation
# ---------------------------------------------------------------------------
def project_manager_ids(project) -> set:
    """Active managers of a project — the people responsible for its queue."""
    return set(
        ProjectMembership.objects.filter(
            project=project, role=ProjectRole.MANAGER, is_active=True
        ).values_list("user_id", flat=True)
    )


def ticket_audience(ticket) -> set:
    """Everyone with a legitimate interest in a ticket: reporter, assignee, project managers."""
    audience: set = set()
    if ticket.reporter_id:
        audience.add(ticket.reporter_id)
    if ticket.assignee_id:
        audience.add(ticket.assignee_id)
    audience |= project_manager_ids(ticket.project)
    return audience


def _active_users(user_ids) -> list[User]:
    if not user_ids:
        return []
    return list(User.objects.filter(id__in=user_ids, is_active=True).only("id", "full_name", "email"))


# ---------------------------------------------------------------------------
# The single write primitive
# ---------------------------------------------------------------------------
def _dedup_key(*, event_type: str, recipient: User, subject: str, suffix: str = "") -> str:
    """Stable, bounded key: same recipient + same event + same subject ⇒ one notification.

    Including the recipient is essential — a key shared across recipients would let the first
    notification suppress everybody else's.
    """
    raw = f"{event_type}:{recipient.pk}:{subject}:{suffix}"
    return raw[:120]


@transaction.atomic
def notify(
    *,
    event_type: str,
    recipients,
    title: str,
    body: str = "",
    actor: User | None = None,
    ticket=None,
    project=None,
    payload: dict | None = None,
    subject: str = "none",
    suffix: str = "",
) -> list[Notification]:
    """Create one notification per recipient (idempotently) and try to enqueue delivery.

    Rules applied to every call, so event functions below stay declarative:

    * inactive recipients are skipped (they cannot log in);
    * the actor is never notified about their own action;
    * the same (recipient, event, subject, suffix) never produces a second row.
    """
    created: list[Notification] = []

    for recipient in recipients:
        if recipient is None or not recipient.is_active:
            continue
        if actor is not None and recipient.pk == actor.pk:
            continue

        key = _dedup_key(event_type=event_type, recipient=recipient, subject=subject, suffix=suffix)
        notification, was_created = Notification.objects.get_or_create(
            dedup_key=key,
            defaults={
                "recipient": recipient,
                "actor": actor,
                "event_type": event_type,
                "title": title,
                "body": body,
                "ticket": ticket,
                "project": project or (ticket.project if ticket is not None else None),
                "payload": payload or {},
            },
        )
        if not was_created:
            continue

        created.append(notification)
        _enqueue(notification)

    return created


def _enqueue(notification: Notification) -> None:
    """Best-effort hand-off to Celery.

    A broker outage must not fail the user's request: the notification row already exists, so the
    in-app inbox is correct, and the periodic retry task will dispatch it later. The failure is
    logged at warning level because it is operationally interesting, not fatal.
    """
    try:
        from apps.notifications.tasks import send_notification

        send_notification.delay(str(notification.pk))
    except Exception as exc:  # pragma: no cover - depends on infrastructure
        logger.warning("Could not enqueue notification %s: %s", notification.pk, exc)


# ---------------------------------------------------------------------------
# Event-specific helpers — the vocabulary other modules call
# ---------------------------------------------------------------------------
def notify_ticket_created(*, ticket, actor) -> list[Notification]:
    recipients = _active_users(project_manager_ids(ticket.project))
    return notify(
        event_type=NotificationEvent.TICKET_CREATED,
        recipients=recipients,
        actor=actor,
        ticket=ticket,
        subject=f"ticket:{ticket.pk}",
        title=_("New %(type)s: %(key)s") % {"type": ticket.get_type_display(), "key": ticket.key},
        body=ticket.title,
        payload={"ticket_id": str(ticket.pk), "key": ticket.key, "project_id": str(ticket.project_id)},
    )


def notify_ticket_assigned(*, ticket, actor, previous_assignee_id=None) -> list[Notification]:
    if ticket.assignee_id is None:
        return []
    event = (
        NotificationEvent.TICKET_REASSIGNED
        if previous_assignee_id
        else NotificationEvent.TICKET_ASSIGNED
    )
    recipients = _active_users({ticket.assignee_id})
    return notify(
        event_type=event,
        recipients=recipients,
        actor=actor,
        ticket=ticket,
        subject=f"ticket:{ticket.pk}",
        # The suffix encodes the transition (from → to). Encoding only the new assignee would
        # suppress the notification when a ticket goes A → B → A, which is a real handover.
        suffix=f"{previous_assignee_id or 'none'}->{ticket.assignee_id}",
        title=_("%(key)s assigned to you") % {"key": ticket.key},
        body=ticket.title,
        payload={"ticket_id": str(ticket.pk), "key": ticket.key},
    )


def notify_status_changed(
    *, ticket, actor, from_status: str, to_status: str, history_id: str = ""
) -> list[Notification]:
    if to_status == TicketStatus.RESOLVED:
        event = NotificationEvent.TICKET_RESOLVED
    elif to_status == TicketStatus.REOPENED:
        event = NotificationEvent.TICKET_REOPENED
    else:
        event = NotificationEvent.TICKET_STATUS_CHANGED

    return notify(
        event_type=event,
        recipients=_active_users(ticket_audience(ticket)),
        actor=actor,
        ticket=ticket,
        subject=f"ticket:{ticket.pk}",
        # Keyed on the history row: that row *is* the event, so the same transition can never notify
        # the same person twice, while a genuine repeat (reopened then resolved again) is not
        # suppressed.
        suffix=f"history:{history_id}" if history_id else f"{from_status}->{to_status}",
        title=_("%(key)s is now %(status)s")
        % {"key": ticket.key, "status": TicketStatus(to_status).label},
        body=ticket.title,
        payload={
            "ticket_id": str(ticket.pk),
            "key": ticket.key,
            "from_status": from_status,
            "to_status": to_status,
        },
    )


def notify_comment_added(*, comment, actor) -> list[Notification]:
    ticket = comment.ticket
    return notify(
        event_type=NotificationEvent.COMMENT_ADDED,
        recipients=_active_users(ticket_audience(ticket)),
        actor=actor,
        ticket=ticket,
        subject=f"ticket:{ticket.pk}",
        suffix=f"comment:{comment.pk}",
        title=_("New comment on %(key)s") % {"key": ticket.key},
        body=comment.body[:200],
        payload={"ticket_id": str(ticket.pk), "comment_id": str(comment.pk), "key": ticket.key},
    )


def notify_membership_added(*, project, user, actor) -> list[Notification]:
    return notify(
        event_type=NotificationEvent.MEMBERSHIP_ADDED,
        recipients=_active_users({user.pk}),
        actor=actor,
        project=project,
        subject=f"project:{project.pk}",
        suffix=str(user.pk),
        title=_("You were added to %(project)s") % {"project": project.name},
        body=_("Your role in this project is %(role)s.")
        % {"role": user.project_memberships.filter(project=project).values_list("role", flat=True).first()},
        payload={"project_id": str(project.pk), "project_key": project.key},
    )