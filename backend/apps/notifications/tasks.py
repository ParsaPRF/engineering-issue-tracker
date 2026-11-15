"""Celery tasks for notification delivery.

The tasks are deliberately small: the **data model** carries the reliability properties (unique
``dedup_key``, ``is_sent`` flag), so a task only has to be safe to run twice. Both of them are:

* ``send_notification`` returns early if the row is missing or already dispatched;
* ``retry_unsent_notifications`` only re-enqueues work, and each re-enqueue is itself idempotent.

In tests ``CELERY_TASK_ALWAYS_EAGER`` is on, so these functions execute inline and their effects are
asserted directly instead of being mocked away.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.notifications.models import Notification

logger = logging.getLogger(__name__)

#: Age before an unsent notification is considered stuck (broker was down when it was created).
RETRY_AFTER = timedelta(minutes=5)


@shared_task(
    bind=True,
    name="apps.notifications.tasks.send_notification",
    max_retries=3,
    default_retry_delay=30,
    ignore_result=True,
)
def send_notification(self, notification_id: str) -> str:
    """Deliver one notification.

    Today "delivery" means marking the in-app notification as dispatched; the actual transport (email,
    webhook, chat) plugs in here behind the same idempotency guarantee. Keeping the seam explicit
    means adding email later is a local change, not a redesign.
    """
    notification = (
        Notification.objects.select_related("recipient").filter(pk=notification_id).first()
    )
    if notification is None:
        # The row was deleted (recipient removed) — nothing to do, and not an error worth retrying.
        return "missing"

    if notification.is_sent:
        return "already-sent"

    if not notification.recipient.is_active:
        return "recipient-inactive"

    # --- transport would go here -------------------------------------------------
    # send_email(notification) / post_webhook(notification) / ...
    notification.mark_sent()
    return "sent"


@shared_task(name="apps.notifications.tasks.retry_unsent_notifications", ignore_result=True)
def retry_unsent_notifications(batch_size: int = 200) -> int:
    """Re-enqueue notifications that were never dispatched (broker outage, worker crash).

    Scheduled by Celery beat every ten minutes. Bounded by ``batch_size`` so a long outage cannot
    produce an unbounded burst that starves interactive work.
    """
    cutoff = timezone.now() - RETRY_AFTER
    pending = list(
        Notification.objects.filter(is_sent=False, created_at__lt=cutoff)
        .order_by("created_at")
        .values_list("id", flat=True)[:batch_size]
    )
    for notification_id in pending:
        send_notification.delay(str(notification_id))

    if pending:
        logger.info("Re-enqueued %s unsent notifications.", len(pending))
    return len(pending)


@shared_task(name="apps.notifications.tasks.cleanup_read_notifications", ignore_result=True)
def cleanup_read_notifications(older_than_days: int = 90) -> int:
    """Drop notifications that were read a long time ago.

    Notifications are not audit records — the audit trail is. Keeping read notifications forever turns
    the inbox into an ever-growing list nobody reads, so retention is explicit.
    """
    cutoff = timezone.now() - timedelta(days=older_than_days)
    deleted, _ = Notification.objects.filter(is_read=True, read_at__lt=cutoff).delete()
    return deleted