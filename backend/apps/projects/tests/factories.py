"""Project test factories.

Build a realistic, *permitted* object graph by default: ``ProjectFactory`` creates an owner who is
also an active manager, because that is the invariant the services establish. Tests that need a
weaker actor add a membership explicitly, which makes the test's permission premise visible.
"""

from __future__ import annotations

import factory

from apps.accounts.roles import SystemRole
from apps.accounts.tests.factories import UserFactory
from apps.projects.models import Component, Project, ProjectMembership, ProjectRole, ProjectStatus


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project
        django_get_or_create = ("key",)
        # The post-generation hook below performs its own writes, so factory_boy must not save the
        # instance again (that behaviour is deprecated in factory_boy 3.3+).
        skip_postgeneration_save = True

    key = factory.Sequence(lambda n: f"PRJ{n}")
    name = factory.Sequence(lambda n: f"Project {n}")
    description = "Seeded by ProjectFactory"
    status = ProjectStatus.ACTIVE
    # owner is NOT NULL, so it has to exist in the very first INSERT — a post-generation hook would
    # run too late and the insert would fail.
    owner = factory.SubFactory(UserFactory, system_role=SystemRole.PROJECT_MANAGER)

    @factory.post_generation
    def manager_membership(obj, create, extracted, **kwargs):  # noqa: N805 - factory_boy's hook
        """Give the owner the MANAGER membership the schema invariant requires (FR-2.1).

        Created here rather than inside the service because factories build *data*: a project whose
        owner has no membership is not a state the application can produce, so it should not be a
        state a test can produce either.
        """
        if not create:
            return
        ProjectMembership.objects.get_or_create(
            project=obj,
            user=obj.owner,
            defaults={"role": ProjectRole.MANAGER, "is_active": True},
        )


class ProjectMembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjectMembership

    project = factory.SubFactory(ProjectFactory)
    user = factory.SubFactory(UserFactory)
    role = ProjectRole.ENGINEER
    is_active = True


class ComponentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Component
        django_get_or_create = ("project", "name")

    project = factory.SubFactory(ProjectFactory)
    name = factory.Sequence(lambda n: f"Component {n}")
    description = "Seeded by ComponentFactory"
    is_active = True
