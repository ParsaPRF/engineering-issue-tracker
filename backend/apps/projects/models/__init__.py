"""Project domain: the container for all work, its members and its components.

Three models, three responsibilities:

* ``Project`` — identity and lifecycle (active/archived).
* ``ProjectMembership`` — who may work in the project, and in which project role. This is the
  pivot that makes object-level authorisation possible (ADR-012).
* ``Component`` — an optional sub-area inside a project used to route and filter tickets.
"""

from apps.projects.models.component import Component
from apps.projects.models.membership import ProjectMembership, ProjectRole, eligible_assignee_roles
from apps.projects.models.project import Project, ProjectStatus

__all__ = [
    "Component",
    "Project",
    "ProjectMembership",
    "ProjectRole",
    "ProjectStatus",
    "eligible_assignee_roles",
]
