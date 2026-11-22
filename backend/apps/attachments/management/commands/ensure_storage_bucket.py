"""``manage.py ensure_storage_bucket`` — create the S3 bucket if it is missing.

Why this is a Django command and not a separate container: the previous design used the MinIO
``mc`` image in an init container to create the bucket. That couples the stack to one vendor's
client image, needs shell-escaping tricks in compose (``$$``), and fails the whole stack if that
image is unavailable from the registry. The application already ships ``boto3`` (through
``django-storages``), so it can guarantee its own storage precondition with three lines of code and
no extra moving part.

The command is **idempotent** and safe to run on every container start:

* ``STORAGE_BACKEND=local`` → prints a note and does nothing (local development);
* bucket exists → reports it and exits 0;
* bucket missing → creates it and exits 0;
* endpoint unreachable → exits 1 with an actionable message, which is what you want at startup
  rather than a confusing ``NoSuchBucket`` on the first upload.

It never sets a bucket policy or ACL: the bucket is private by construction, and the only way to
read an object is the authorising download endpoint (ADR-010).
"""

from __future__ import annotations

import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the configured S3 bucket if it does not exist (no-op with local storage)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only print on failure (used by the container entrypoint).",
        )
        parser.add_argument(
            "--wait-seconds",
            type=int,
            default=60,
            help=(
                "How long to keep retrying while the endpoint is unreachable. The container stack "
                "starts the API next to its storage service, so a few seconds of patience remove the "
                "need for brittle startup ordering."
            ),
        )

    def handle(self, *args, **options):
        quiet: bool = options["quiet"]
        wait_seconds: int = options["wait_seconds"]

        backend = getattr(settings, "STORAGE_BACKEND", "local").lower()
        if backend != "s3":
            if not quiet:
                self.stdout.write(f"storage backend is '{backend}'; no bucket to create.")
            return

        bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
        endpoint = getattr(settings, "AWS_S3_ENDPOINT_URL", "") or "the default AWS endpoint"
        if not bucket:
            raise CommandError("AWS_STORAGE_BUCKET_NAME is not configured.")

        try:
            import boto3
            from botocore.exceptions import ClientError, EndpointConnectionError
        except ImportError as exc:  # pragma: no cover - boto3 comes with django-storages
            raise CommandError(
                "boto3 is required for STORAGE_BACKEND=s3; install django-storages[boto3]."
            ) from exc

        client_kwargs: dict = {"region_name": getattr(settings, "AWS_S3_REGION_NAME", "us-east-1")}
        if getattr(settings, "AWS_S3_ENDPOINT_URL", ""):
            client_kwargs["endpoint_url"] = settings.AWS_S3_ENDPOINT_URL
        if getattr(settings, "AWS_ACCESS_KEY_ID", ""):
            client_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            client_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
        client = boto3.client("s3", **client_kwargs)

        deadline = time.monotonic() + max(0, wait_seconds)
        attempt = 0
        while True:
            attempt += 1
            try:
                client.head_bucket(Bucket=bucket)
                if not quiet:
                    self.stdout.write(
                        self.style.SUCCESS(f"bucket '{bucket}' already exists at {endpoint}")
                    )
                return
            except EndpointConnectionError as exc:
                if time.monotonic() >= deadline:
                    raise CommandError(
                        f"cannot reach the object storage endpoint ({endpoint}) after "
                        f"{attempt} attempts: {exc}"
                    ) from exc
                if not quiet and attempt == 1:
                    self.stdout.write(f"waiting for the storage endpoint {endpoint} ...")
                time.sleep(3)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code not in {"404", "NoSuchBucket", "NotFound"}:
                    raise CommandError(
                        f"unexpected storage error while checking '{bucket}': {exc}"
                    ) from exc
                break

        client.create_bucket(Bucket=bucket)
        self.stdout.write(self.style.SUCCESS(f"created private bucket '{bucket}' at {endpoint}"))