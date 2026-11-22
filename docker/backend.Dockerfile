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

# No system packages are installed on purpose. ``psycopg[binary]`` ships a self-contained libpq, and
# the health check below uses the interpreter that is already in the image, so the build needs no
# Debian repository access at all: fewer moving parts, a smaller image, and a build that cannot fail
# because a mirror is slow.

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
    CMD python -c "import http.client,sys; c=http.client.HTTPConnection('127.0.0.1',8000,timeout=4); c.request('GET','/health/'); sys.exit(0 if c.getresponse().status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]