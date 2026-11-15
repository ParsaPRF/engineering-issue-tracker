"""Project API views.

Pattern used throughout this file, and worth reading once because it repeats in every module:

* ``get_queryset`` returns an **already permission-scoped** queryset, so ``get_object()`` turns
  "exists but not yours" into a 404 automatically — one place to get right, no per-action checks;
* a *permitted* actor who still lacks the specific capability gets a 403 from the service, which is
  the right distinction for the UI ("you cannot edit this project" vs "there is no such project");
* writes always go through ``apps.projects.services``, never through ``serializer.save()``.
"""

from __future__ import annotations

import uuid

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.selectors import users as user_selectors
from apps.projects.api.serializers import (
    ComponentCreateSerializer,
    ComponentSerializer,
    ComponentUpdateSerializer,
    MembershipCreateSerializer,
    MembershipRoleUpdateSerializer,
    ProjectCreateSerializer,
    ProjectMembershipSerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
)
from apps.projects.models import Component, ProjectMembership
from apps.projects.selectors import projects as project_selectors
from apps.projects.services import components as component_services
from apps.projects.services import memberships as membership_services
from apps.projects.services import projects as project_services
from common.exceptions import ResourceNotFound


class ProjectViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """``/api/v1/projects/`` — list, create, retrieve, update, archive, members, components, stats.

    Built from explicit mixins rather than ``ModelViewSet``: there is no ``update`` (replaced by a
    validated ``partial_update``) and no ``destroy`` at all, because projects are archived, never
    deleted (FR-2.4).
    """

    serializer_class = ProjectSerializer
    filterset_fields = ("status", "key")
    search_fields = ("name", "key", "description")
    ordering_fields = ("name", "key", "created_at", "updated_at")
    ordering = ("-created_at",)

    def get_queryset(self):
        return project_selectors.projects_with_counts(self.request.user)

    # -- CRUD -----------------------------------------------------------------
    @extend_schema(responses={200: ProjectSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=ProjectCreateSerializer, responses={201: ProjectSerializer})
    def create(self, request, *args, **kwargs):
        serializer = ProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = project_services.create_project(
            actor=request.user,
            key=serializer.validated_data["key"],
            name=serializer.validated_data["name"],
            description=serializer.validated_data.get("description", ""),
            request=request,
        )
        return Response(
            ProjectSerializer(project, context={"request": request}).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(responses={200: ProjectSerializer})
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(request=ProjectUpdateSerializer, responses={200: ProjectSerializer})
    def partial_update(self, request, *args, **kwargs):
        serializer = ProjectUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        project = project_services.update_project(
            actor=request.user, project=self.get_object(), data=serializer.validated_data, request=request
        )
        return Response(ProjectSerializer(project, context={"request": request}).data)

    # -- Lifecycle ------------------------------------------------------------
    @extend_schema(request=None, responses={200: ProjectSerializer})
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        project = project_services.archive_project(actor=request.user, project=self.get_object(), request=request)
        return Response(ProjectSerializer(project, context={"request": request}).data)

    @extend_schema(request=None, responses={200: ProjectSerializer})
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        project = project_services.restore_project(actor=request.user, project=self.get_object(), request=request)
        return Response(ProjectSerializer(project, context={"request": request}).data)

    # -- Members --------------------------------------------------------------
    @extend_schema(responses={200: ProjectMembershipSerializer(many=True)})
    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, pk=None):
        project = self.get_object()

        if request.method == "GET":
            memberships = project_selectors.project_memberships(
                project, include_inactive=request.query_params.get("include_inactive") == "true"
            )
            return Response(ProjectMembershipSerializer(memberships, many=True).data)

        serializer = MembershipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = user_selectors.get_user_by_id(serializer.validated_data["user"])
        if user is None:
            raise ResourceNotFound("No such user.")
        membership, created = membership_services.add_member(
            actor=request.user,
            project=project,
            user=user,
            role=serializer.validated_data["role"],
            request=request,
        )
        return Response(
            ProjectMembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(
        parameters=[
            # Declared explicitly because ``membership_id`` is not a field of the Project model, so
            # drf-spectacular cannot infer its type from the viewset's queryset.
            OpenApiParameter("membership_id", uuid.UUID, OpenApiParameter.PATH),
        ],
        request=MembershipRoleUpdateSerializer,
        responses={200: ProjectMembershipSerializer},
    )
    @action(detail=True, methods=["patch", "delete"], url_path="members/(?P<membership_id>[^/.]+)")
    def member_detail(self, request, pk=None, membership_id=None):
        project = self.get_object()
        membership = (
            ProjectMembership.objects.filter(pk=membership_id, project=project).select_related("user").first()
        )
        if membership is None:
            raise ResourceNotFound("No such membership in this project.")

        if request.method == "DELETE":
            membership_services.remove_member(
                actor=request.user, project=project, membership=membership, request=request
            )
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = MembershipRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = membership_services.change_member_role(
            actor=request.user,
            project=project,
            membership=membership,
            role=serializer.validated_data["role"],
            request=request,
        )
        return Response(ProjectMembershipSerializer(membership).data)

    # -- Components -----------------------------------------------------------
    @extend_schema(responses={200: ComponentSerializer(many=True)})
    @action(detail=True, methods=["get", "post"], url_path="components")
    def components(self, request, pk=None):
        project = self.get_object()

        if request.method == "GET":
            components = project_selectors.project_components(
                project, include_inactive=request.query_params.get("include_inactive") == "true"
            )
            return Response(ComponentSerializer(components, many=True).data)

        serializer = ComponentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead = None
        if serializer.validated_data.get("lead"):
            lead = user_selectors.get_user_by_id(serializer.validated_data["lead"])
            if lead is None:
                raise ResourceNotFound("No such user.")

        component = component_services.create_component(
            actor=request.user,
            project=project,
            name=serializer.validated_data["name"],
            description=serializer.validated_data.get("description", ""),
            lead=lead,
            request=request,
        )
        return Response(ComponentSerializer(component).data, status=status.HTTP_201_CREATED)

    # -- Statistics -----------------------------------------------------------
    @extend_schema(responses={200: None}, description=_("Ticket statistics for one project."))
    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """Delegate to the reports module.

        The import is function-local on purpose: ``reports`` aggregates across projects, tickets and
        audit, so it sits *above* this module. Importing it at module level would make the
        dependency direction circular, and a cycle would only appear at runtime.
        """
        from apps.reports.selectors import project_statistics

        project = self.get_object()
        return Response(project_statistics(request.user, project))


class ComponentViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """``/api/v1/components/`` — detail operations for components.

    Listing and creation happen under their project (``/projects/<id>/components/``) because a
    component only makes sense inside a project; this viewset exists so a component can be updated
    or retired without repeating the project in the URL.
    """

    serializer_class = ComponentSerializer
    filterset_fields = ("project", "is_active")
    ordering_fields = ("name", "created_at")
    ordering = ("name",)

    def get_queryset(self):
        visible = project_selectors.projects_visible_to(self.request.user)
        return Component.objects.filter(project__in=visible).select_related("project", "lead")

    @extend_schema(responses={200: ComponentSerializer})
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(request=ComponentUpdateSerializer, responses={200: ComponentSerializer})
    def partial_update(self, request, *args, **kwargs):
        serializer = ComponentUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if "lead" in data and data["lead"] is not None:
            lead = user_selectors.get_user_by_id(data["lead"])
            if lead is None:
                raise ResourceNotFound("No such user.")
            data["lead"] = lead
        component = component_services.update_component(
            actor=request.user, component=self.get_object(), data=data, request=request
        )
        return Response(ComponentSerializer(component).data)

    @extend_schema(request=None, responses={200: ComponentSerializer})
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        component = component_services.deactivate_component(
            actor=request.user, component=self.get_object(), request=request
        )
        return Response(ComponentSerializer(component).data)
