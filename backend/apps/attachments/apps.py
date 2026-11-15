"""Django application configuration for the `attachments` module."""

from django.apps import AppConfig


class AttachmentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.attachments"
    label = "attachments"
    verbose_name = "Attachments"
