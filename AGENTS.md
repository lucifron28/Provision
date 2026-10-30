# Provision — Agent & Developer Guide

Before changing code, read `README.md` and these three documents in order:

1. [Cook with Pip roadmap and phased TODOs](docs/cook-with-pip/ROADMAP.md)
2. [Cook with Pip technical implementation specification](docs/cook-with-pip/TECHNICAL_SPEC.md)
3. [Filipino-first recipe source governance and trust registry](docs/cook-with-pip/RECIPE_SOURCE_POLICY.md)

**Current status:** Cook with Pip is planned, NOT implemented. Existing Home Chef Pip hints are heuristic, not DeepSeek recipe results. Do not mark milestones done without code, tests, CI, and acceptance evidence.

## System Overview

Provision is a household pantry and food inventory management system consisting of:
- **Frontend:** Native iOS SwiftUI app (Deployment Target: iOS 26.5+) in `frontend/`.
- **Backend:** FastAPI + SQLAlchemy 2.0 synchronous REST API in `backend/`.
- **Database:** PostgreSQL 18 containerized via Docker Compose (`compose.yaml`).

---

## Development Environment & Workflow

### 1. Database Infrastructure
PostgreSQL 18 runs containerized via Docker Compose on macOS:
```bash
# Start PostgreSQL 18 (localhost:5432)
docker compose up -d

# Verify container health
docker compose ps

# Stop PostgreSQL 18
docker compose down
```
- **Volume:** `postgres_data` mounts to `/var/lib/postgresql`; PostgreSQL 18 stores its cluster in `/var/lib/postgresql/18/docker`.
- **Port:** Localhost-only port binding `127.0.0.1:5432:5432`.
- **Credentials:** Configured via `.env` (defaults: `provision` / `provision`).

### 2. Backend Development (`backend/`)
The FastAPI server runs locally on the host via `uv` (never inside Docker for dev):
```bash
cd backend

# Sync dependencies (Python 3.13+)
uv sync

# Apply Alembic migrations
uv run alembic upgrade head

# Seed Philippine demo supermarket data
uv run python seed.py

# Run backend test suite (against PostgreSQL test database)
uv run pytest

# Launch local server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Database Migrations (`backend/alembic/`)
- All database schema updates must be committed as Alembic migrations in `backend/alembic/versions/`.
- Ensure migrations are compatible with PostgreSQL 18 (e.g. handling PostgreSQL ENUM types and foreign key constraint naming).
- Always verify both upgrade and downgrade cycles:
  ```bash
  uv run alembic downgrade base && uv run alembic upgrade head
  ```

### 4. SQLite Data Migration (`backend/scripts/`)
For environments with legacy SQLite `provision.db` files:
```bash
# Dry run
uv run python scripts/migrate_sqlite_to_postgres.py --sqlite-path provision.db --dry-run

# Run migration (creates timestamped backup)
uv run python scripts/migrate_sqlite_to_postgres.py --sqlite-path provision.db
```

### 5. Frontend Development & Testing (`frontend/`)
- Build and test via Xcode or command-line `xcodebuild`:
  ```bash
  xcodebuild test -project frontend/frontend.xcodeproj -scheme frontend -destination "platform=iOS Simulator,name=iPhone 17,OS=latest" CODE_SIGNING_ALLOWED=NO
  ```
- All new features and UI components must preserve WCAG AA contrast, Dynamic Type adaptability, and scanner hardware acceptance gate invariants.

---

## How to execute the Cook with Pip roadmap

- Begin with P0 household/user data isolation and privacy; do not send pantry data or allergy profiles to DeepSeek before scoping and consent are implemented.
- Work in dependency order, one independently tested, reviewable milestone at a time. Avoid giant unreviewable implementation passes.
- Use DeepSeek only through the FastAPI backend. Verify its current API docs at implementation time; API keys must stay server-side.
- Filipino recipe publishers have **candidate** status until permissions/source review is completed. Prefer approved Filipino publishers; search other sites only with explicit broader-web permission. Respect source attribution, access policy and prompt-injection boundaries.
- Build ingredient quantity, allergy guardrails and shopping deduplication deterministically. Generative output never authorizes database writes.
- Preserve scanner lifecycle, pending intake recovery, FEFO, shopping manual edits, existing Pip branding and native SwiftUI design. Do not mutate inventory while previewing a recipe.
- Shopping list changes require explicit user confirmation, optimistic revision check, transactional atomicity, deduplication and idempotency; never fabricate ingredient conversions.
- Prefer official documentation and existing repo patterns. Record architecture choices, schema migrations, and meaningful unit/integration/UI tests in the same changeset.
- Run `cd backend && uv run pytest` and the applicable Xcode XCTest suite; after push, verify required GitHub Actions. Don't rewrite tests to accommodate incorrect behavior. If device or live provider verification is missing, report it.
- Update the roadmap checkbox + commit SHA/CI evidence upon true completion; keep source review records current.
- Never merge feature work into `main` without explicit approval.
