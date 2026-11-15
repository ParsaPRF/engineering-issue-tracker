"""Attachment test factories."""

from __future__ import annotations

import factory
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.attachments.models import Attachment
from apps.tickets.tests.factories import TicketFactory


class AttachmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Attachment
        skip_postgeneration_save = True

    ticket = factory.SubFactory(TicketFactory)
    uploader = factory.SelfAttribute("ticket.reporter")
    file = factory.LazyAttribute(lambda o: SimpleUploadedFile("evidence.txt", b"factory contents", content_type="text/plain"))
    original_name = "evidence.txt"
    content_type = "text/plain"
    size_bytes = 16
    sha256 = "0" * 64
    is_deleted = False