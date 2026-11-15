"""Factories for accounts tests.

Why factories instead of fixtures with hard-coded objects: tests need *many* users with slightly
different roles, and a factory expresses "a valid user" once. Sequences keep emails unique across a
test session without random values, so failures are reproducible.
"""

from __future__ import annotations

import factory
from django.db.models.signals import post_save

from apps.accounts.models import User, UserProfile
from apps.accounts.roles import SystemRole

#: Password used by every factory-created user. Tests that log in use this constant so the
#: credential is defined in exactly one place.
TEST_PASSWORD = "TestPass!2345"


@factory.django.mute_signals(post_save)
class UserFactory(factory.django.DjangoModelFactory):
    """A valid, active user with a profile attached."""

    class Meta:
        model = User
        django_get_or_create = ("email",)
        # Both post-generation hooks below persist what they change, so factory_boy does not need
        # to save the instance again (and must not: that is deprecated behaviour).
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Sequence(lambda n: f"Test User {n}")
    system_role = SystemRole.REPORTER
    is_active = True

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):  # noqa: N805 - factory_boy's hook signature
        """Hash and persist a usable password.

        Going through ``set_password`` guarantees the factory cannot produce a user whose password
        does not actually authenticate — a class of test that passes for the wrong reason.
        """
        obj.set_password(extracted or TEST_PASSWORD)
        if create:
            obj.save(update_fields=["password"])

    @factory.post_generation
    def profile(obj, create, extracted, **kwargs):  # noqa: N805 - factory_boy's hook signature
        """Create the one-to-one profile.

        ``UserManager.create_user`` normally does this, but ``DjangoModelFactory`` goes through
        ``objects.create``, so the factory performs the same step to keep objects realistic.
        """
        if not create:
            return
        defaults = {"job_title": "Engineer", **(extracted or {})}
        defaults.update(kwargs)
        UserProfile.objects.get_or_create(user=obj, defaults=defaults)


class AdminUserFactory(UserFactory):
    system_role = SystemRole.ADMIN
    is_active = True
    is_staff = True


class ManagerUserFactory(UserFactory):
    system_role = SystemRole.PROJECT_MANAGER


class EngineerUserFactory(UserFactory):
    system_role = SystemRole.ENGINEER


class ReporterUserFactory(UserFactory):
    system_role = SystemRole.REPORTER
