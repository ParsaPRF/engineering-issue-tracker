"""Reports API: the dashboard, workload and activity feeds.

All numbers come from ``apps.reports.selectors``, which scopes every query to the caller's visible
projects. These views therefore contain no authorisation logic of their own — there is nothing to
authorise beyond "is authenticated", because the data simply does not exist for a caller who cannot
see the projects.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.selectors import recent_activity
from apps.projects.selectors.projects import user_project_ids
from apps.reports.selectors import dashboard, engineer_workload, my_workload


def _project_ids(request) -> list | None:
    """``?project=<uuid>&project=<uuid>`` → a list, or ``None`` when unfiltered."""
    values = request.query_params.getlist("project")
    return values or None


class DashboardView(APIView):
    """``GET /api/v1/reports/dashboard/`` — headline counts and breakdowns (FR-9.1, FR-9.2)."""

    @extend_schema(responses={200: None})
    def get(self, request):
        return Response(dashboard(request.user, project_ids=_project_ids(request)))


class WorkloadView(APIView):
    """``GET /api/v1/reports/workload/`` — open tickets per engineer (FR-9.3)."""

    @extend_schema(responses={200: None})
    def get(self, request):
        return Response({"results": engineer_workload(request.user, project_ids=_project_ids(request))})


class MyWorkloadView(APIView):
    """``GET /api/v1/reports/my-workload/`` — the signed-in user's own summary (FR-9.4)."""

    @extend_schema(responses={200: None})
    def get(self, request):
        return Response(my_workload(request.user))


class RecentActivityView(APIView):
    """``GET /api/v1/reports/recent-activity/`` — audit feed limited to visible projects (FR-9.4)."""

    @extend_schema(responses={200: None})
    def get(self, request):
        try:
            limit = min(int(request.query_params.get("limit", 20)), 100)
        except (TypeError, ValueError):
            limit = 20

        # Administrators see the whole installation, including events that have no project context
        # (logins, role changes). Narrowing an admin's feed to their own memberships would hide
        # exactly the security events the trail exists for.
        from apps.accounts.models import SystemRole

        project_ids = (
            None
            if request.user.system_role == SystemRole.ADMIN
            else user_project_ids(request.user)
        )

        events = recent_activity(request.user, limit=limit, project_ids=project_ids)
        return Response(
            {
                "results": [
                    {
                        "id": str(event.id),
                        "action": event.action,
                        "actor": event.actor.full_name if event.actor else None,
                        "project_key": event.project.key if event.project else None,
                        "ticket_key": event.ticket.key if event.ticket else None,
                        "metadata": event.metadata,
                        "created_at": event.created_at,
                    }
                    for event in events
                ]
            }
        )


class ProjectOptionsView(APIView):
    """``GET /api/v1/reports/projects/`` — projects and counts for the dashboard filter.

    A dedicated endpoint rather than reusing ``/projects/``: the dashboard only needs id, key, name and
    two counters, and this response stays small enough to cache client-side.
    """

    @extend_schema(responses={200: None})
    def get(self, request):
        from apps.projects.selectors.projects import projects_with_counts

        projects = projects_with_counts(request.user).order_by("name")
        return Response(
            {
                "results": [
                    {
                        "id": str(project.id),
                        "key": project.key,
                        "name": project.name,
                        "status": project.status,
                        "member_count": getattr(project, "member_count", None),
                        "ticket_count": getattr(project, "ticket_count", None),
                        "open_ticket_count": getattr(project, "open_ticket_count", None),
                    }
                    for project in projects
                ]
            }
        )