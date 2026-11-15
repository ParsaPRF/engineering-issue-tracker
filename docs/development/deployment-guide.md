# Deployment Guide

## 1. Topology

```
Internet → TLS termination → Nginx (port 80/443)
                               ├── /                     → SPA static files (built image)
                               ├── /assets/              → hashed bundles, immutable cache
                               ├── /static/              → Django static (admin, API docs UI)
                               ├── /media/               → public media only
                               ├── /api/, /admin/, /health/ → gunicorn → Django
                               └── (internal) PostgreSQL, Redis, MinIO, Celery worker, Celery beat
```

One origin for the SPA and the API is deliberate: session cookies and CSRF behave exactly as Django
expects (ADR-003). Attachments are **not** served from `/media` — they go through the authorising
download endpoint (ADR-010).

## 2. Compose services

| Service | Image | Purpose | Health check |
| --- | --- | --- | --- |
| `db` | `postgres:17-alpine` | Data store | `pg_isready` |
| `redis` | `redis:7-alpine` | Broker, result backend, cache | `redis-cli ping` |
| `minio` | `minio/minio` | S3-compatible object storage (console on :9001) | `GET /minio/health/live` |
| `minio-init` | `minio/mc` | Creates the private bucket once | exits 0 |
| `backend` | built from `docker/backend.Dockerfile` | gunicorn + Django | `GET /health/` |
| `worker` | same image | Celery worker | `celery inspect ping` |
| `beat` | same image | Periodic retry of unsent notifications | — |
| `web` | built from `docker/frontend.Dockerfile` | Nginx + SPA | `GET /` |

## 3. First deployment

```bash
# 1. Configuration (never commit .env)
cp .env.example .env
python - <<'PY'                # or edit by hand
import secrets; print(secrets.token_urlsafe(64))   # DJANGO_SECRET_KEY
PY
# set at minimum: DJANGO_SECRET_KEY (>=32 chars), DJANGO_ALLOWED_HOSTS,
# DJANGO_CSRF_TRUSTED_ORIGINS, POSTGRES_PASSWORD, AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY

# 2. Build and start
docker compose up --build -d

# 3. Apply migrations — an explicit release step, never automatic at boot
docker compose exec backend python manage.py migrate

# 4. Create the first administrator
docker compose exec backend python manage.py createsuperuser

# 5. Optional demo data (development only)
docker compose exec backend python manage.py seed_demo
```

Then open `http://localhost:8080` (or your public hostname). Verify:

```bash
curl -fsS http://localhost:8080/health/            # {"status":"ok",...}
curl -fsS http://localhost:8080/api/schema/ >/dev/null   # schema served
```

## 4. Production settings that matter

`config/settings/production.py` fails fast and hardens transport:

| Setting | Value | Why |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | required, ≥32 chars | refuses to start with the development default |
| `SECURE_SSL_REDIRECT` | `True` | HTTP is redirected, not silently accepted |
| `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | `True` | cookies never travel over plain HTTP |
| `SECURE_HSTS_SECONDS` | 30 days | with subdomains + preload once you are certain about the domain |
| `SECURE_PROXY_SSL_HEADER` | `X-Forwarded-Proto` | correct scheme behind Nginx |
| `SECURE_CONTENT_TYPE_NOSNIFF` / `X_FRAME_OPTIONS=DENY` | on | basic browser hardening |
| `DEBUG` | `False` | no stack traces to clients |

Behind Nginx the container's own TLS is not used; terminate TLS at your edge (Nginx, a load balancer,
or Cloudflare). Nginx forwards `X-Forwarded-Proto`.

## 5. Static files and the SPA

* `collectstatic` runs in the backend container entrypoint (`COLLECTSTATIC=1`) and writes to the
  `static_data` volume, which `web` mounts read-only at `/staticfiles`.
* The SPA is compiled into the `web` image at build time; `VITE_API_BASE_URL=/api/v1` keeps every call
  relative.
* `client_max_body_size 12m` in `nginx.conf` leaves headroom over the 10 MB attachment limit.

## 6. Caching and background work

| Item | Setting |
| --- | --- |
| Django cache | Redis DB 2 (`CACHE_BACKEND=redis`) |
| Celery broker | Redis DB 0 |
| Celery results | Redis DB 1 |
| Beat schedule | `retry-unsent-notifications` every 10 minutes |
| Worker concurrency | 2 by default; raise with load, keep prefetch at 1 (already configured) |

Notifications are safe under retries: `Notification.dedup_key` is unique and the task re-checks
`is_sent`, so at-least-once delivery cannot become duplicate messages (ADR-009).

## 7. Backups

```bash
# PostgreSQL
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > backup-$(date +%F).sql.gz

# Object storage (attachments are ext4 files inside MinIO's volume)
docker run --rm -v eng-tracker_miniodata:/data -v "$PWD":/backup alpine \
  tar czf /backup/minio-$(date +%F).tar.gz -C /data .

# Restore (PostgreSQL)
gunzip -c backup-2026-11-15.sql.gz | docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB"
```

The two backups **must be taken together**: an attachment row without its object (or vice versa) is a
broken ticket. Redis is disposable; Celery beat state is re-creatable.

## 8. Hardening the audit trail

`AuditEvent` refuses updates and deletes in Python. For defence in depth, revoke the privileges from
the application role at the database level:

```sql
-- connect as a superuser to the application database
REVOKE UPDATE, DELETE ON TABLE audit_auditevent FROM eng_tracker;
-- optional, stricter: only SELECT + INSERT
REVOKE TRUNCATE ON TABLE audit_auditevent FROM eng_tracker;
```

Then confirm the application still works (it only inserts and selects) and that a manual
`DELETE FROM audit_auditevent;` fails. Re-grant only for a documented, audited maintenance window.

## 9. Upgrades

```bash
git pull
docker compose build backend web
docker compose up -d
docker compose exec backend python manage.py migrate      # review the migrations first
docker compose exec backend python manage.py check --deploy
```

`check --deploy` is worth running on every release: it flags missing security settings.

## 10. Operations checklist

* [ ] `DJANGO_SECRET_KEY` is unique per environment and ≥32 chars
* [ ] `.env` is not in version control (`git check-ignore -v .env`)
* [ ] `DJANGO_ALLOWED_HOSTS` lists real hostnames only
* [ ] `DJANGO_CSRF_TRUSTED_ORIGINS` matches the public origin exactly (scheme included)
* [ ] HTTPS redirect works and HSTS is on
* [ ] Login (`/api/v1/auth/login/`) succeeds and `Set-Cookie` shows `HttpOnly` + `Secure`
* [ ] Upload > 10 MB is rejected with `attachment_too_large`
* [ ] A non-member gets `404` for a foreign ticket (not `403`)
* [ ] `/health/` is green and `docker compose ps` shows all healthy
* [ ] Backups run and **have been restored once** into a scratch database
* [ ] Audit privileges revoked; `UPDATE`/`DELETE` fail
* [ ] Celery worker log shows the notification tasks

## 11. Known unverified items (be explicit)

| Item | Status |
| --- | --- |
| `docker compose up` executed end-to-end | **Not executed on the delivery workstation** (no Docker daemon). CI does build both images, render the compose file, and boot the backend container against a real PostgreSQL with a green `/health/`. |
| MinIO bucket creation (`minio-init`) | Not executed; script reviewed. Covered by the manual checklist. |
| MinIO healthcheck using `curl` | Standard for the official image, but not verified against a pulled tag here. If a tag lacks `curl`, replace with the `mc ready local` probe. |
| Nginx + built SPA served together | The SPA image builds in CI; serving it behind Nginx in a live stack is unexercised. |
| PostgreSQL-only behaviour | **Verified**: CI runs the full suite on PostgreSQL 17 (229 passed, 0 skipped). It also caught a real `FOR UPDATE` + nullable-join bug — see the testing guide. |
| Redis / Celery against a real broker | Not verified; tests run eager. |

Treat the first `docker compose up` as an installation step with its own verification pass against
the checklist above — not as something this document can promise on its behalf.

## 12. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `backend` restarts in a loop, log says `DJANGO_SECRET_KEY must be at least 32 characters` | Placeholder secret still in `.env` |
| `Compose` refuses to start: `POSTGRES_PASSWORD is missing a value` | `:?` guards in `docker-compose.yml` require the variable — set it in `.env` |
| Login returns 403 from the browser | Missing `X-CSRFToken`, or `VITE_API_BASE_URL` pointing at another origin |
| Uploads fail with `NoSuchBucket` | `minio-init` did not complete: `docker compose logs minio-init` |
| Notifications never marked sent | Worker down or broker unreachable: `docker compose logs worker`; the periodic task re-drives them |
| 404 on every API call through Nginx | `proxy_pass http://backend_api;` must not have a trailing slash/URI, or paths are rewritten |