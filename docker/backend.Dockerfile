# Backend image: Django + gunicorn.
#
# Design choices:
#   * ``python:3.14-slim`` matches the interpreter the project was developed and tested on.
#   * Dependencies are installed from a pinned requirements file **before** the source is copied, so a
#     code change does not invalidate the dependency layer.
#   * ``collectstatic`` and ``migrate`` run at *startup*, not at build time: both need the real
#     environment (secret key, database), and running migrations during a build is a classic way to
#     deploy a schema nobody reviewed.
#   * The container runs as a non-root user.

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# libpq is needed by psycopg at runtime; curl is used by the compose healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements /app/requirements
RUN pip install --upgrade pip && pip install -r requirements/production.txt

COPY backend /app

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appuser /app
USER appuser

COPY --chown=appuser:appuser docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health/ || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]