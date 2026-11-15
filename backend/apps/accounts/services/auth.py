"""Authentication services: session login/logout and their audit trail.

Why the login logic lives here rather than in the serializer: authenticating a user has
side effects (session creation, audit event) and one subtle security decision (below). Keeping it
in a service means the API view is a thin adapter and the behaviour is unit-testable without HTTP.

The security decision — **telling a user their account is inactive only after they proved they
know the password**:

* Returning "account inactive" for any email that exists, before checking the password, turns the
  login form into an account-existence oracle.
* Returning a generic "invalid credentials" for everything is safe but unhelpful to a legitimate
  user whose account was deactivated.
* Checking the password first and only then disclosing the inactive state leaks nothing: the
  caller already demonstrated possession of the credential.
"""

from __future__ import annotations

from django.contrib.auth import authenticate, login, logout

from apps.accounts.models import User
from apps.accounts.selectors import users as user_selectors
from apps.audit.actions import AuditAction
from apps.audit.services import record as audit_record
from common.exceptions import DomainError, InvariantViolation


def session_login(*, request, email: str, password: str) -> User:
    """Authenticate ``email``/``password`` and start a session.

    Raises:
        InvariantViolation: ``account_inactive`` (403) when the password is correct but the
            account is deactivated; ``invalid_credentials`` (400) otherwise.
    """
    user = authenticate(request=request, username=(email or "").strip(), password=password)

    if user is None:
        candidate = user_selectors.get_user_by_email(email)
        if candidate and candidate.check_password(password) and not candidate.is_active:
            raise InvariantViolation(
                "This account is inactive. Contact an administrator.",
                code="account_inactive",
                status_code=403,
            )
        raise DomainError(
            "Email or password is incorrect.",
            code="invalid_credentials",
            status_code=400,
        )

    # Django's login() cycles the session key, which closes the session-fixation window: a
    # pre-set session id cannot be promoted into an authenticated session.
    login(request, user)

    audit_record(
        action=AuditAction.USER_LOGGED_IN,
        actor=user,
        obj=user,
        metadata={"email": user.email},
        request=request,
    )
    return user


def session_logout(*, request) -> None:
    """End the session and record it.

    The audit event is written *before* flushing, otherwise the actor is already gone from the
    request by the time the record is built.
    """
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        audit_record(
            action=AuditAction.USER_LOGGED_OUT,
            actor=user,
            obj=user,
            metadata={"email": user.email},
            request=request,
        )
    logout(request)
