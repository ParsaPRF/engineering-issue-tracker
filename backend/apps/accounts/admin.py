"""Django admin registrations for accounts.

The admin is an operational tool, not the product. It is still hardened: no password is ever
displayed, role changes are audited by the service layer when made through the API, and the
admin does not allow deleting users (the lifecycle is deactivation — UC-17).
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import UserProfile
from apps.accounts.models.user import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Read-mostly user administration."""

    ordering = ("email",)
    list_display = ("email", "full_name", "system_role", "is_active", "is_staff", "date_joined")
    list_filter = ("system_role", "is_active", "is_staff")
    search_fields = ("email", "full_name")
    readonly_fields = ("id", "last_login", "date_joined", "created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        (_("Identity"), {"fields": ("full_name", "system_role")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "system_role", "password1", "password2"),
            },
        ),
    )

    def has_delete_permission(self, request, obj=None) -> bool:
        """Accounts are deactivated, never deleted, so history keeps its author."""
        return False


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "job_title", "timezone")
    search_fields = ("user__email", "user__full_name")
    readonly_fields = ("id", "created_at", "updated_at")
