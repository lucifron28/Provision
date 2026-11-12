# Both base images are pinned to immutable multi-platform manifest digests.
FROM ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 AS uv

FROM python:3.13-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72 AS builder
COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-editable

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini

FROM python:3.13-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72 AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp

WORKDIR /app
COPY --from=builder --chown=10001:10001 /app/.venv ./.venv
COPY --from=builder --chown=10001:10001 /app/app ./app
COPY --from=builder --chown=10001:10001 /app/alembic ./alembic
COPY --from=builder --chown=10001:10001 /app/alembic.ini ./alembic.ini

USER 10001:10001
EXPOSE 10000

# Render terminates public TLS. This API does not need forwarded client metadata,
# so never let client-supplied X-Forwarded-* headers change request state.
# exec lets Uvicorn receive SIGTERM directly during Render shutdowns.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-10000}\" --no-proxy-headers"]
