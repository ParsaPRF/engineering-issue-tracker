"""Component services: project structure, managed by managers.

Components are what make a ticket routable ("Billing API" vs "Mobile App"), so the rules are simple
and strict: unique name inside the project, and an optional lead who must actually be a member of
that project — a lead who cannot see the tickets would be a trap.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.db import transaction

from apps.audit.actions import AuditAction
from apps.audit.services import record as audit_record
from apps.projects.models import Component, Project
from apps.projects.permissions import can_manage_components, is_active_member
from common.exceptions import AccessDenied, InvariantViolation

COMPONENT_EDITABLE_FIELDS = frozenset({"name", "description", "lead", "is_active"})


@transaction.atomic
def create_component(
    *, actor, project: Project, name: str, description: str = "", lead=None, request=None
) -> Component:
    """Create a component (FR-2.6)."""
    if not can_manage_components(actor, project):
        raise AccessDenied("You cannot manage the components of this project.")

    name = (name or "").strip()
    if not name:
        raise InvariantViolation(
            "A component name is required.", code="validation_error", fields={"name": ["This field is required."]}
        )
    if Component.objects.filter(project=project, name__iexact=name).exists():
        raise InvariantViolation(
            "This project already has a component with that name.",
            code="duplicate_component_name",
            fields={"name": ["A component with this name already exists in the project."]},
        )
    if lead is not None and not is_active_member(lead, project):
        raise InvariantViolation(
            "The component lead must be an active member of the project.",
            code="ineligible_lead",
            fields={"lead": ["This user is not an active member of the project."]},
        )

    component = Component(project=project, name=name, description=description or "", lead=lead)
    component.full_clean(exclude=["project"])
    component.save()

    audit_record(
        action=AuditAction.COMPONENT_CREATED,
        actor=actor,
        obj=component,
        project=project,
        metadata={"name": component.name, "lead_id": str(lead.pk) if lead else None},
        request=request,
    )
    return component


@transaction.atomic
def update_component(*, actor, component: Component, data: Mapping[str, Any], request=None) -> Component:
    """Update a component's mutable fields."""
    if not can_manage_components(actor, component.project):
        raise AccessDenied("You cannot manage the components of this project.")

    changed: dict[str, Any] = {}
    for field, value in data.items():
        if field not in COMPONENT_EDITABLE_FIELDS:
            continue
        if field == "name" and isinstance(value, str):
            value = value.strip()
            if (
                Component.objects.filter(project=component.project, name__iexact=value)
                .exclude(pk=component.pk)
                .exists()
            ):
                raise InvariantViolation(
                    "This project already has a component with that name.",
                    code="duplicate_component_name",
                    fields={"name": ["A component with this name already exists in the project."]},
                )
        if field == "lead" and value is not None and not is_active_member(value, component.project):
            raise InvariantViolation(
                "The component lead must be an active member of the project.",
                code="ineligible_lead",
                fields={"lead": ["This user is not an active member of the project."]},
            )
        if getattr(component, field) != value:
            changed[field] = str(value) if field == "lead" else value
            setattr(component, field, value)

    if not changed:
        return component

    component.full_clean(exclude=["project"])
    component.save()

    audit_record(
        action=AuditAction.COMPONENT_UPDATED,
        actor=actor,
        obj=component,
        project=component.project,
        metadata={"changed": changed},
        request=request,
    )
    return component


@transaction.atomic
def deactivate_component(*, actor, component: Component, request=None) -> Component:
    """Retire a component without touching the tickets that reference it.

    Tickets keep their ``component`` foreign key (``SET_NULL`` only applies to deletion), so history
    stays intact; the component simply stops being offered for new tickets.
    """
    if not can_manage_components(actor, component.project):
        raise AccessDenied("You cannot manage the components of this project.")
    if not component.is_active:
        raise InvariantViolation("This component is already inactive.", code="already_inactive")

    component.is_active = False
    component.save(update_fields=["is_active", "updated_at"])

    audit_record(
        action=AuditAction.COMPONENT_DEACTIVATED,
        actor=actor,
        obj=component,
        project=component.project,
        request=request,
    )
    return component
