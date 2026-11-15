"""Ticket test factories.

``TicketFactory`` allocates its key through the **real** allocator. That is deliberate: a factory
that invented keys of its own could produce rows the application would never create, and tests would
then pass against a data shape that cannot occur in production. Tests that assert the allocator
itself call it directly on a project the factory has not touched.
"""

from __future__ import annotations

import factory

from apps.accounts.tests.factories import UserFactory
from apps.projects.tests.factories import ComponentFactory, ProjectFactory
from apps.tickets.models import Label, Priority, Severity, Ticket, TicketStatus, TicketType


class TicketFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Ticket
        # The assignee hook in AssignedTicketFactory saves explicitly.
        skip_postgeneration_save = True

    project = factory.SubFactory(ProjectFactory)
    title = factory.Sequence(lambda n: f"Ticket number {n}")
    description = "Steps to reproduce:\n1. do the thing\n2. observe the problem"
    type = TicketType.BUG
    status = TicketStatus.NEW
    priority = Priority.MEDIUM
    severity = Severity.MAJOR
    reporter = factory.SubFactory(UserFactory)
    assignee = None
    component = None
    due_date = None

    @factory.lazy_attribute
    def key(self):
        """Allocate through the production allocator (see the module docstring)."""
        from apps.tickets.services.keys import allocate_ticket_key

        return allocate_ticket_key(self.project)

    @factory.post_generation
    def initial_history(obj, create, extracted, **kwargs):  # noqa: N805 - factory_boy's hook
        """Open the timeline, exactly as ``create_ticket`` does.

        The application never produces a ticket without a creation entry, so the factory must not
        either: otherwise tests assert against a state that cannot occur in production, and timeline
        assertions would silently be missing their first row.
        """
        if not create:
            return
        from apps.workflows.models import TicketStatusHistory

        TicketStatusHistory.objects.create(
            ticket=obj,
            from_status=None,
            to_status=obj.status,
            changed_by=obj.reporter,
            comment="Created by TicketFactory.",
        )


class AssignedTicketFactory(TicketFactory):
    """A ticket already given to an engineer, in ``IN_PROGRESS``.

    Built through the service layer is *not* done here on purpose: factories create data, services
    enforce rules, and tests that need the rule use the service. This keeps factory use cheap and
    side-effect free apart from the row itself.
    """

    status = TicketStatus.IN_PROGRESS

    @factory.post_generation
    def assign_engineer(obj, create, extracted, **kwargs):  # noqa: N805
        if not create:
            return
        from apps.projects.models import ProjectMembership, ProjectRole

        engineer = extracted or UserFactory()
        ProjectMembership.objects.get_or_create(
            project=obj.project, user=engineer, defaults={"role": ProjectRole.ENGINEER, "is_active": True}
        )
        obj.assignee = engineer
        obj.save(update_fields=["assignee"])


class LabelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Label
        django_get_or_create = ("project", "name")

    project = factory.SubFactory(ProjectFactory)
    name = factory.Sequence(lambda n: f"label-{n}")
    color = "#2563eb"


class ComponentBoundTicketFactory(TicketFactory):
    """A ticket that carries a component belonging to its own project."""

    @factory.lazy_attribute
    def component(self):
        return ComponentFactory(project=self.project)
