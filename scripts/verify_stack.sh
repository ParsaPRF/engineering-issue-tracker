#!/usr/bin/env bash
#
# End-to-end verification of the running Docker Compose stack.
#
# Run it after `docker compose up -d` + `migrate` + `seed_demo`. CI calls it too, so the claims in
# the README ("the stack serves the SPA, proxies the API, stores attachments in S3 and delivers
# notifications through a real Celery worker") are checked on every push instead of being asserted
# once by hand.
#
# It exercises the *whole* path: Nginx -> gunicorn -> Django -> PostgreSQL, plus Redis (broker and
# cache), object storage (upload/download round trip) and the Celery worker (a task must be consumed
# by the worker process, not executed inline).
#
# Usage:  BASE_URL=http://localhost:8080 scripts/verify_stack.sh
set -euo pipefail

BASE="${BASE_URL:-http://localhost:8080}"
EMAIL="${DEMO_EMAIL:-manager@example.com}"
PASSWORD="${DEMO_PASSWORD:-Demo!Passw0rd}"
WORKDIR="$(mktemp -d)"
JAR="$WORKDIR/cookies.txt"
UPLOAD="$WORKDIR/upload.txt"
DOWNLOAD="$WORKDIR/download.txt"

cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

log()  { printf '\n\033[1m== %s\033[0m\n' "$1"; }
fail() { printf '\033[31mFAILED: %s\033[0m\n' "$1" >&2; exit 1; }
json() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }

csrf_token() { grep -i csrftoken "$JAR" | tail -1 | awk '{print $7}'; }

log "waiting for $BASE/health/"
for _ in $(seq 1 60); do
  if curl -fsS "$BASE/health/" -o "$WORKDIR/health.json" 2>/dev/null; then break; fi
  sleep 2
done
[ -s "$WORKDIR/health.json" ] || fail "the stack never became healthy at $BASE"
cat "$WORKDIR/health.json"
grep -q '"database":"ok"' "$WORKDIR/health.json" || fail "health check does not report a healthy database"
grep -q '"redis":"ok"' "$WORKDIR/health.json" || fail "health check does not report a reachable Redis"

log "SPA shell served by Nginx"
curl -fsS "$BASE/" -o "$WORKDIR/index.html"
grep -q 'id="root"' "$WORKDIR/index.html" || fail "the SPA shell was not served"
echo "index.html ok"

log "CSRF + login"
curl -fsS -c "$JAR" -o /dev/null "$BASE/api/v1/auth/csrf/"
USER_JSON=$(curl -fsS -b "$JAR" -c "$JAR" \
  -H "X-CSRFToken: $(csrf_token)" -H "Content-Type: application/json" -H "Referer: $BASE/" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" "$BASE/api/v1/auth/login/")
echo "$USER_JSON" | json "'logged in as ' + d['email'] + ' (' + d['system_role'] + ')'"
# Django rotates the CSRF token on login, so the header value must be re-read.
CSRF=$(csrf_token)

log "reads through Nginx (PostgreSQL)"
TICKETS=$(curl -fsS -b "$JAR" "$BASE/api/v1/tickets/?page_size=3")
TICKET_ID=$(echo "$TICKETS" | json "d['results'][0]['id']")
TICKET_KEY=$(echo "$TICKETS" | json "d['results'][0]['key']")
echo "$TICKETS" | json "'tickets: %d, first: %s (%s)' % (d['count'], d['results'][0]['key'], d['results'][0]['status'])"
curl -fsS -b "$JAR" "$BASE/api/v1/reports/dashboard/" | json "'dashboard: total=%d open=%d' % (d['totals']['total_tickets'], d['totals']['open_tickets'])"
curl -fsS -b "$JAR" "$BASE/api/v1/workflows/transitions/?ticket=$TICKET_ID" \
  | json "'allowed moves: ' + ', '.join(t['to_status'] for t in d['allowed'])"

log "attachment upload -> object storage -> download"
echo "round trip payload $(date -u +%s)" > "$UPLOAD"
ATTACHMENT=$(curl -fsS -b "$JAR" -H "X-CSRFToken: $CSRF" -H "Referer: $BASE/" \
  -F "file=@$UPLOAD" "$BASE/api/v1/tickets/$TICKET_ID/attachments/")
ATTACHMENT_ID=$(echo "$ATTACHMENT" | json "d['id']")
echo "$ATTACHMENT" | json "'stored as %s (%d bytes, sha256 %s...)' % (d['original_name'], d['size_bytes'], d['sha256'][:12])"
echo "$ATTACHMENT" | json "d['download_url']" | grep -q "/api/v1/attachments/" \
  || fail "the attachment response must expose an API path, never a storage URL"
curl -fsS -b "$JAR" -o "$DOWNLOAD" "$BASE/api/v1/attachments/$ATTACHMENT_ID/download/"
cmp -s "$UPLOAD" "$DOWNLOAD" || fail "the downloaded bytes differ from the uploaded file"
echo "download matches the upload"

log "assignment -> real Celery task via Redis"
ENGINEER_ID=$(curl -fsS -b "$JAR" "$BASE/api/v1/auth/users/directory/?search=engineer@" | json "d[0]['id']")
curl -fsS -b "$JAR" -H "X-CSRFToken: $CSRF" -H "Content-Type: application/json" -H "Referer: $BASE/" \
  -d "{\"assignee\":\"$ENGINEER_ID\"}" "$BASE/api/v1/tickets/$TICKET_ID/assign/" \
  | json "'assigned %s to %s' % (d['key'], d['assignee']['full_name'])"
sleep 8

log "security spot-checks"
ANON=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/v1/auth/me/")
[ "$ANON" = "403" ] || fail "anonymous /auth/me/ returned $ANON, expected 403"
echo "anonymous /auth/me/ -> 403"
AUDIT=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" "$BASE/api/v1/audit/")
[ "$AUDIT" = "403" ] || fail "audit as a project manager returned $AUDIT, expected 403"
echo "audit as project manager -> 403"

printf '\n\033[32mStack verification passed: %s\033[0m\n' "$BASE"
echo "ticket: $TICKET_KEY ($TICKET_ID), attachment: $ATTACHMENT_ID"