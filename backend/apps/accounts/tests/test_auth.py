"""Authentication API tests (FR-1.1 … FR-1.8).

These tests go through HTTP rather than calling services directly where the *HTTP contract* is what
we are asserting: status codes, the error envelope, cookies and session behaviour.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from apps.accounts.models import SystemRole, User
from apps.accounts.tests.factories import TEST_PASSWORD, UserFactory
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db

REGISTER_URL = "/api/v1/auth/register/"
LOGIN_URL = "/api/v1/auth/login/"
LOGOUT_URL = "/api/v1/auth/logout/"
ME_URL = "/api/v1/auth/me/"
CSRF_URL = "/api/v1/auth/csrf/"
PASSWORD_URL = "/api/v1/auth/me/password/"


def error_code(response) -> str:
    return response.data["error"]["code"]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def test_register_creates_reporter_with_profile_and_audit_event(api_client):
    response = api_client.post(
        REGISTER_URL,
        {
            "email": "New.User@Example.com",
            "full_name": "New User",
            "password": "Str0ng-Passw0rd!",
            "password_confirm": "Str0ng-Passw0rd!",
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    user = User.objects.get(email="new.user@example.com")
    # FR-1.1: least privilege by default, email normalised to lower case.
    assert user.system_role == SystemRole.REPORTER
    assert user.is_active is True
    assert user.profile is not None
    assert AuditEvent.objects.filter(action=AuditAction.USER_REGISTERED, actor=user).exists()
    # The response must never contain the password or its hash.
    assert "password" not in response.data


def test_register_rejects_duplicate_email_case_insensitively(api_client):
    UserFactory(email="taken@example.com")

    response = api_client.post(
        REGISTER_URL,
        {
            "email": "TAKEN@example.com",
            "full_name": "Copy Cat",
            "password": "Str0ng-Passw0rd!",
            "password_confirm": "Str0ng-Passw0rd!",
        },
        format="json",
    )

    assert response.status_code == 400
    assert error_code(response) == "email_taken"
    assert User.objects.filter(email__iexact="taken@example.com").count() == 1


def test_register_rejects_weak_password(api_client):
    response = api_client.post(
        REGISTER_URL,
        {
            "email": "weak@example.com",
            "full_name": "Weak Password",
            "password": "password",
            "password_confirm": "password",
        },
        format="json",
    )

    assert response.status_code == 400
    assert error_code(response) == "validation_error"
    assert not User.objects.filter(email="weak@example.com").exists()


def test_register_rejects_mismatched_confirmation(api_client):
    response = api_client.post(
        REGISTER_URL,
        {
            "email": "mismatch@example.com",
            "full_name": "Mismatch",
            "password": "Str0ng-Passw0rd!",
            "password_confirm": "Str0ng-Passw0rd?",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "password_confirm" in response.data["error"]["fields"]


@override_settings(ALLOW_SELF_REGISTRATION=False)
def test_registration_can_be_disabled_by_configuration(api_client):
    response = api_client.post(
        REGISTER_URL,
        {
            "email": "closed@example.com",
            "full_name": "Closed Shop",
            "password": "Str0ng-Passw0rd!",
            "password_confirm": "Str0ng-Passw0rd!",
        },
        format="json",
    )

    assert response.status_code == 403
    assert error_code(response) == "registration_disabled"


# ---------------------------------------------------------------------------
# Login / logout / session
# ---------------------------------------------------------------------------
def test_login_creates_session_and_returns_current_user(api_client):
    user = UserFactory(email="login@example.com")

    response = api_client.post(LOGIN_URL, {"email": "login@example.com", "password": TEST_PASSWORD}, format="json")

    assert response.status_code == 200, response.data
    assert response.data["email"] == "login@example.com"
    assert response.data["system_role"] == user.system_role

    # The session is real: a follow-up request authenticates through the cookie.
    me = api_client.get(ME_URL)
    assert me.status_code == 200
    assert me.data["id"] == str(user.id)
    assert AuditEvent.objects.filter(action=AuditAction.USER_LOGGED_IN, actor=user).exists()


def test_login_with_wrong_password_is_generic(api_client):
    UserFactory(email="wrongpass@example.com")

    response = api_client.post(
        LOGIN_URL, {"email": "wrongpass@example.com", "password": "not-the-password"}, format="json"
    )

    assert response.status_code == 400
    assert error_code(response) == "invalid_credentials"


def test_login_for_unknown_email_is_indistinguishable_from_wrong_password(api_client):
    response = api_client.post(
        LOGIN_URL, {"email": "nobody@example.com", "password": "not-the-password"}, format="json"
    )

    assert response.status_code == 400
    assert error_code(response) == "invalid_credentials"


def test_inactive_account_is_reported_only_when_the_password_is_correct(api_client):
    user = UserFactory(email="inactive@example.com", is_active=False)

    # Correct password: safe to disclose the account state, because the caller proved possession.
    response = api_client.post(
        LOGIN_URL, {"email": "inactive@example.com", "password": TEST_PASSWORD}, format="json"
    )
    assert response.status_code == 403
    assert error_code(response) == "account_inactive"

    # Wrong password: no information about the account leaks.
    response = api_client.post(LOGIN_URL, {"email": "inactive@example.com", "password": "wrong"}, format="json")
    assert response.status_code == 400
    assert error_code(response) == "invalid_credentials"
    assert user.is_active is False


def test_logout_ends_the_session(client_for):
    user = UserFactory()
    client = client_for(user)
    assert client.get(ME_URL).status_code == 200

    response = client.post(LOGOUT_URL)

    assert response.status_code == 204
    assert client.get(ME_URL).status_code == 403  # session gone
    assert AuditEvent.objects.filter(action=AuditAction.USER_LOGGED_OUT, actor=user).exists()


def test_me_requires_authentication(api_client):
    # Session authentication offers no WWW-Authenticate challenge, so DRF reports the missing
    # credentials as 403 rather than 401. Documented in docs/api/api-overview.md.
    assert api_client.get(ME_URL).status_code == 403


def test_deactivated_user_with_a_live_session_is_rejected(client_for):
    user = UserFactory()
    client = client_for(user)
    assert client.get(ME_URL).status_code == 200

    user.is_active = False
    user.save(update_fields=["is_active"])

    assert client.get(ME_URL).status_code == 403


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
def test_me_patch_updates_name_and_profile(client_for):
    user = UserFactory(full_name="Old Name")
    client = client_for(user)

    response = client.patch(
        ME_URL,
        {"full_name": "New Name", "profile": {"job_title": "Staff Engineer", "timezone": "Asia/Tehran"}},
        format="json",
    )

    assert response.status_code == 200, response.data
    user.refresh_from_db()
    user.profile.refresh_from_db()
    assert user.full_name == "New Name"
    assert user.profile.job_title == "Staff Engineer"
    assert user.profile.timezone == "Asia/Tehran"


def test_me_patch_cannot_escalate_privileges(client_for):
    user = UserFactory(system_role=SystemRole.REPORTER)
    client = client_for(user)

    response = client.patch(
        ME_URL,
        {"full_name": "Sneaky", "system_role": "ADMIN", "is_active": True, "profile": {"job_title": "x"}},
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.system_role == SystemRole.REPORTER  # silently ignored, never honoured
    assert user.is_staff is False


def test_me_patch_rejects_unknown_timezone(client_for):
    client = client_for(UserFactory())

    response = client.patch(ME_URL, {"profile": {"timezone": "Mars/Olympus"}}, format="json")

    assert response.status_code == 400
    assert "profile.timezone" in response.data["error"]["fields"]


def test_password_change_replaces_the_credential_and_kills_other_sessions(client_for):
    user = UserFactory(email="change@example.com")
    other_session = client_for(user)
    current_session = client_for(user)
    assert other_session.get(ME_URL).status_code == 200

    response = current_session.post(
        PASSWORD_URL,
        {
            "current_password": TEST_PASSWORD,
            "new_password": "An0ther-Str0ng-Pass!",
            "new_password_confirm": "An0ther-Str0ng-Pass!",
        },
        format="json",
    )

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.check_password("An0ther-Str0ng-Pass!")
    # Every session except the one that made the change is revoked.
    assert other_session.get(ME_URL).status_code == 403
    assert current_session.get(ME_URL).status_code == 200


def test_password_change_requires_the_current_password(client_for):
    client = client_for(UserFactory())

    response = client.post(
        PASSWORD_URL,
        {
            "current_password": "wrong-current",
            "new_password": "An0ther-Str0ng-Pass!",
            "new_password_confirm": "An0ther-Str0ng-Pass!",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "current_password" in response.data["error"]["fields"]


# ---------------------------------------------------------------------------
# CSRF (FR-1.2, NFR-1.4)
# ---------------------------------------------------------------------------
def test_login_requires_a_csrf_token_when_csrf_is_enforced(client_for):
    UserFactory(email="csrf@example.com")
    client = client_for(enforce_csrf=True)

    # The documented first call: it sets the cookie the SPA reads and echoes back.
    assert client.get(CSRF_URL).status_code == 200
    token = client.cookies["csrftoken"].value

    unprotected = client.post(LOGIN_URL, {"email": "csrf@example.com", "password": TEST_PASSWORD}, format="json")
    assert unprotected.status_code == 403  # Django rejects the unsafe request

    protected = client.post(
        LOGIN_URL,
        {"email": "csrf@example.com", "password": TEST_PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert protected.status_code == 200


def test_session_cookie_is_not_readable_from_javascript(api_client, settings):
    """The session cookie must be HttpOnly, so XSS cannot exfiltrate the session (ADR-003)."""
    assert settings.SESSION_COOKIE_HTTPONLY is True
    # The CSRF cookie must stay JS-readable: the SPA has to echo it in X-CSRFToken.
    assert settings.CSRF_COOKIE_HTTPONLY is False
