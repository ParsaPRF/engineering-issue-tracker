"""Comment test factories."""

from __future__ import annotations

import factory

from apps.comments.models import Comment
from apps.tickets.tests.factories import TicketFactory


class CommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Comment

    ticket = factory.SubFactory(TicketFactory)
    author = factory.SelfAttribute("ticket.reporter")
    body = factory.Sequence(lambda n: f"Comment number {n}")
    is_deleted = False