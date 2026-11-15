"""Django admin for the audit trail: read-only, and no delete action.

The admin is a convenience for operators; the guarantee comes from the model (`save`/`delete`
raise) and, in production, from revoked database privileges.
"""

from __future__ import annotations

from django.contrib import admin

from apps.audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "object_type", "project", "ip_address")
    list_filter = ("action", "object_type")
    search_fields = ("action", "object_type", "actor__email", "metadata")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]
