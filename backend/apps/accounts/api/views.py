"""Account API views: thin adapters over services and selectors.

Every view here does three things and nothing more: check endpoint-level permission, call a
service or selector, and serialise the result. Consequently the interesting behaviour
(credential checking, the last-admin rule, session invalidation) is testable without HTTP and is
shared with the admin and the seed command.
"""

from __future__ import annotations

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.serializers import (
    LoginSerializer,
    MeUpdateSerializer,
    PasswordChangeSerializer,
    RegisterSerializer,
    SystemRoleUpdateSerializer,
    UserSerializer,
    UserSummarySerializer,
)
from apps.accounts.models import SystemRole
from apps.accounts.selectors import users as user_selectors
from apps.accounts.services import auth as auth_services
from apps.accounts.services import users as user_services
from common.exceptions import AccessDenied
from common.permissions import IsAdmin


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfTokenView(APIView):
    """``GET /api/v1/auth/csrf/`` — sets the ``csrftoken`` cookie.

    Session-authenticated clients must send ``X-CSRFToken`` on unsafe methods. A browser SPA can
    read the cookie only after it exists, so this endpoint is the documented first call after a
    page load (ADR-003). It returns no body content, so it is safe to call anonymously.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        responses={200: OpenApiResponse(description="CSRF cookie set.")},
        description="Set the CSRF cookie required by session-authenticated writes.",
    )
    def get(self, request):
        return Response({"detail": "CSRF cookie set."})


@method_decorator(csrf_protect, name="dispatch")
class RegisterView(APIView):
    """``POST /api/v1/auth/register/`` — public self-registration.

    ``csrf_protect`` is applied explicitly. DRF's ``APIView`` is CSRF-exempt by default and
    ``SessionAuthentication`` only enforces CSRF once a session user exists, so without this
    decorator an anonymous POST would be unprotected — which is exactly the state a login/registration
    CSRF attack needs.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "auth"

    @extend_schema(
        request=RegisterSerializer,
        responses={201: UserSerializer, 400: OpenApiResponse(description="Validation error.")},
        description="Create an account with the least-privileged system role (REPORTER).",
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = user_services.register_user(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
            full_name=serializer.validated_data["full_name"],
            request=request,
        )
        return Response(UserSerializer(user, context={"request": request}).data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    """``POST /api/v1/auth/login/`` — start a session.

    CSRF-protected on purpose (see ``RegisterView``): without it, an attacker could log a victim
    into an account the attacker controls and observe what the victim does next.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "auth"

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: UserSerializer,
            400: OpenApiResponse(description="Invalid credentials."),
            403: OpenApiResponse(description="Account inactive."),
        },
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = auth_services.session_login(
            request=request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        return Response(UserSerializer(user, context={"request": request}).data)


class LogoutView(APIView):
    """``POST /api/v1/auth/logout/`` — end the session."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: OpenApiResponse(description="Session ended.")})
    def post(self, request):
        auth_services.session_logout(request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(RetrieveUpdateAPIView):
    """``GET``/``PATCH /api/v1/auth/me/`` — the caller's own account and profile.

    ``system_role`` and ``is_active`` are absent from the update serializer, so a user cannot
    promote themselves or reactivate their own disabled account (FR-1.5).
    """

    serializer_class = MeUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    @extend_schema(responses={200: UserSerializer})
    def get(self, request, *args, **kwargs):
        return Response(UserSerializer(request.user, context={"request": request}).data)

    @extend_schema(request=MeUpdateSerializer, responses={200: UserSerializer})
    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user
        if data.get("full_name"):
            user.full_name = data["full_name"]
            user.save(update_fields=["full_name", "updated_at"])
        if data.get("profile"):
            user_services.update_profile(
                actor=user,
                profile=user_services.ensure_profile(user),
                data=data["profile"],
                request=request,
            )

        user.refresh_from_db()
        return Response(UserSerializer(user, context={"request": request}).data)


class PasswordChangeView(APIView):
    """``POST /api/v1/auth/me/password/`` — self-service password change.

    Changing a password invalidates other sessions, which is what users expect after a suspected
    compromise; the current session is re-established so the caller is not logged out of the tab
    they are using.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(request=PasswordChangeSerializer, responses={204: OpenApiResponse(description="Password changed.")})
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        user_services.invalidate_user_sessions(user)
        from django.contrib.auth import login

        login(request, user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """Administrator user management under ``/api/v1/auth/users/``.

    Read-only as a viewset plus explicit ``@action`` methods, instead of a full ``ModelViewSet``:
    creating users through the admin API would need a different payload (invitations, initial
    password policy) and deleting them is not part of the lifecycle at all (UC-17).
    """

    serializer_class = UserSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ("system_role", "is_active")
    search_fields = ("email", "full_name")
    ordering_fields = ("full_name", "email", "date_joined")
    ordering = ("full_name",)

    def get_queryset(self):
        return user_selectors.user_queryset()

    @extend_schema(request=None, responses={200: UserSerializer})
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = user_services.set_user_active(actor=request.user, user=self.get_object(), is_active=True, request=request)
        return Response(UserSerializer(user, context={"request": request}).data)

    @extend_schema(request=None, responses={200: UserSerializer})
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = user_services.set_user_active(actor=request.user, user=self.get_object(), is_active=False, request=request)
        return Response(UserSerializer(user, context={"request": request}).data)

    @extend_schema(request=SystemRoleUpdateSerializer, responses={200: UserSerializer})
    @action(detail=True, methods=["patch"], url_path="role")
    def change_role(self, request, pk=None):
        serializer = SystemRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = user_services.change_system_role(
            actor=request.user,
            user=self.get_object(),
            system_role=serializer.validated_data["system_role"],
            request=request,
        )
        return Response(UserSerializer(user, context={"request": request}).data)

    @extend_schema(responses={200: UserSummarySerializer(many=True)})
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def directory(self, request):
        """People search used when adding project members (FR-2.5).

        Open to Admins and Project Managers — the roles that manage membership — and bounded to 20
        results. Engineers and Reporters do not get a browsable directory: least privilege, and an
        unbounded user list is an enumeration target.
        """
        if request.user.system_role not in {SystemRole.ADMIN, SystemRole.PROJECT_MANAGER}:
            raise AccessDenied("Only administrators and project managers may search the directory.")
        users = user_selectors.search_users(request.query_params.get("search", ""))
        return Response(UserSummarySerializer(users, many=True).data)
