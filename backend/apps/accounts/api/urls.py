"""Account routes. The module owns the ``auth/`` prefix."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.accounts.api.views import (
    CsrfTokenView,
    LoginView,
    LogoutView,
    MeView,
    PasswordChangeView,
    RegisterView,
    UserViewSet,
)

router = DefaultRouter()
router.register("auth/users", UserViewSet, basename="user")

urlpatterns = [
    path("auth/csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/me/password/", PasswordChangeView.as_view(), name="auth-password-change"),
    *router.urls,
]
