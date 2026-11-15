"""Upload validation (NFR-1.8, NFR-1.9).

Three independent checks, because each defeats a different attack:

1. **Size** — a bounded upload cannot exhaust memory or fill the bucket.
2. **Extension** against an allow-list — the primary guard. ``svg`` and ``html`` are excluded on
   purpose: both execute script when opened from our origin, which would turn an attachment into
   stored XSS.
3. **Declared content type** against an allow-list — defence in depth. It is *client-provided* and
   therefore never trusted alone; the download endpoint additionally forces
   ``Content-Disposition: attachment`` and a neutral content type so nothing is ever rendered inline.

The original filename is never used as a storage key (see ``attachment_upload_to``); validation only
decides whether the upload is acceptable at all.
"""

from __future__ import annotations

import hashlib
import os

from django.conf import settings

from common.exceptions import InvariantViolation

#: Extensions that are refused with an explicit reason, so the error message can explain *why*
#: rather than just "not allowed".
DANGEROUS_EXTENSIONS = frozenset({"svg", "svgz", "html", "htm", "xhtml", "js", "mjs", "swf", "exe", "bat", "cmd", "ps1", "sh"})


def get_extension(filename: str) -> str:
    _, extension = os.path.splitext(filename or "")
    return extension.lower().lstrip(".")


def human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def validate_upload(uploaded_file) -> str:
    """Validate an uploaded file and return its extension.

    Raises:
        InvariantViolation: ``attachment_too_large``, ``empty_attachment``,
            ``dangerous_file_type`` or ``unsupported_file_type``.
    """
    max_bytes = int(getattr(settings, "ATTACHMENT_MAX_BYTES", 10 * 1024 * 1024))
    allowed_extensions = set(getattr(settings, "ATTACHMENT_ALLOWED_EXTENSIONS", []))
    allowed_types = set(getattr(settings, "ATTACHMENT_ALLOWED_CONTENT_TYPES", []))

    size = int(getattr(uploaded_file, "size", 0) or 0)
    if size <= 0:
        raise InvariantViolation(
            "The uploaded file is empty.",
            code="empty_attachment",
            fields={"file": ["This file is empty."]},
        )
    if size > max_bytes:
        raise InvariantViolation(
            f"Files may be at most {human_size(max_bytes)}; this one is {human_size(size)}.",
            code="attachment_too_large",
            fields={"file": [f"Maximum size is {human_size(max_bytes)}."]},
        )

    extension = get_extension(getattr(uploaded_file, "name", ""))
    if extension in DANGEROUS_EXTENSIONS:
        raise InvariantViolation(
            "This file type can execute code in a browser and is not accepted.",
            code="dangerous_file_type",
            fields={"file": [f"'.{extension}' files are not allowed."]},
        )
    if extension not in allowed_extensions:
        raise InvariantViolation(
            "This file type is not allowed.",
            code="unsupported_file_type",
            fields={"file": [f"Allowed types: {', '.join(sorted(allowed_extensions))}."]},
        )

    content_type = (getattr(uploaded_file, "content_type", "") or "").split(";")[0].strip().lower()
    if content_type and content_type not in allowed_types:
        raise InvariantViolation(
            "This file's declared content type is not allowed.",
            code="unsupported_content_type",
            fields={"file": [f"Content type '{content_type}' is not allowed."]},
        )

    return extension


def compute_sha256(uploaded_file, *, chunk_size: int = 64 * 1024) -> str:
    """Stream the upload through SHA-256, then rewind it for storage.

    Streaming matters: reading a 10 MB file into memory to hash it would be a needless allocation
    per upload, and the same helper can later be used to detect duplicate attachments.
    """
    digest = hashlib.sha256()
    for chunk in iter(lambda: uploaded_file.read(chunk_size), b""):
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()