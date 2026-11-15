"""Accounts domain: identity, authentication and system roles.

Importing the models here means the rest of the project can write ``from apps.accounts.models
import User, SystemRole`` without knowing the internal file layout. ``SystemRole`` itself lives in
``apps/accounts/roles.py`` (a leaf module) to keep the models↔managers import graph acyclic; it is
re-exported here because it belongs to this app's public surface.
"""

from apps.accounts.models.profile import UserProfile
from apps.accounts.models.user import User
from apps.accounts.roles import SystemRole

__all__ = ["SystemRole", "User", "UserProfile"]
