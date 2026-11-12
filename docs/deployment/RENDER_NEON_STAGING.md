# Render and Neon staging guide

This guide prepares a separate Provision staging service. It does not deploy production or reuse production data. An isolated Neon Free project has been created and validated. A Render Blueprint exists, but the Provision service has not been created: the current plan proposes one Free Docker service and is waiting for review and explicit approval before it is applied.

## Architecture

- Render runs the FastAPI backend from the root `Dockerfile`.
- Neon provides an isolated PostgreSQL 18 staging project in Singapore.
- The iOS app keeps its normal local API default. Debug and UI-test launches can opt into a validated Render HTTPS URL.
- GitHub Actions keeps routine PostgreSQL 18 and iOS tests local. The PR visual smoke captures 12 representative screens; a separate manual workflow retains the full screenshot gallery and `.xcresult`. Other manual workflows check staging and, after explicit confirmation, make one DeepSeek request.

The Blueprint in `render.yaml` names the service `provision-staging`, uses the free web plan, selects Singapore, disables auto deploys, and checks `/ready`. The service follows the Blueprint's Git branch so it builds from the branch that contains the root `Dockerfile`. The Blueprint currently points to the deployment PR branch. After that PR is merged, switch the Blueprint source branch to `main` and review the resulting plan before applying it. The plan has no database resource declaration, so applying it will not create or alter a Neon database. Render free services have limits and can spin down while idle. Keep this service for synthetic staging only. [Render free plan limits](https://render.com/docs/free)

## Build and run the container locally

From the repository root, with Docker Desktop running:

```powershell
docker build --pull --file Dockerfile --tag provision-backend:local .
```

Run the image with runtime settings from a local PostgreSQL database. Do not pass secrets as Docker build arguments or commit them in files. `DATABASE_URL` must use the `postgresql+psycopg` driver. The image binds to `$PORT` or port `10000`, and runs as UID `10001`.

Render terminates public TLS at its edge. The current API uses bearer authentication and does not build URLs or make authorization decisions from the forwarded client IP or scheme, so Uvicorn ignores `X-Forwarded-*` headers. Do not enable wildcard proxy trust. If the app later needs forwarded metadata, configure only verified proxy addresses first.

The routine GitHub Actions workflow builds the image, verifies startup fails without required production settings, then checks `/health`, database-backed `/ready`, non-root execution, and that test files and `.env` files are absent. It also runs all Swift unit tests and a focused UI smoke covering navigation, allergy blocks, offline retry, stale-shopping recovery, and Keychain-backed pending-confirmation recovery. The PR requires 12 named screenshots. **Cook with Pip full screenshot gallery** runs the complete existing UI suite on demand and uploads all scenarios plus the full `.xcresult`. The existing root `compose.yaml` remains the local PostgreSQL workflow.

## Isolated Neon staging

The isolated project `provision-staging` is on Neon Free, PostgreSQL 18, in Singapore (`aws-ap-southeast-1`), with a 0.25-CU compute cap. Its `provision_staging` database has separate migration-owner and application roles. Never use an existing project or branch belonging to another app, import a production backup, or run `backend/seed.py`.

The application connection uses Neon pooling; the migration connection uses the direct endpoint. Both require TLS and the `postgresql+psycopg://` scheme. The migration guard requires the URLs to resolve to the same Neon endpoint and database, rejects pooled migration URLs, and requires `staging` in the database name. Neon runs pooled connections through PgBouncer transaction mode, so schema migrations use the direct endpoint. [Neon pooled and direct connections](https://neon.com/docs/connect/connection-pooling)

The backend uses bounded SQLAlchemy pools, stale-connection checks, and disables psycopg automatic prepared statements for Neon pooled endpoints. The project is Free and restricted to synthetic staging. Its current quota is 100 compute-hours and 1 GB storage per project; verify current limits before relying on them. [Neon pricing](https://neon.com/pricing)

## Migration validation and future changes

The initial migration was applied to the isolated Neon database and `alembic check` passed at revision `9c31f410ab82`, the current Alembic head. A pooled application-role `SELECT 1` and a synthetic transaction insert/update/delete also passed. The database contains the migration-created schema and quarantine household, with no user accounts or imported household data.

Render's pre-deploy command is unavailable on the free web plan, so this setup uses one guarded migration run from a trusted Windows workstation before deploying each schema change. The migration guard requires the direct Neon endpoint to match the application endpoint and database, TLS, a database name containing `staging`, and an explicit confirmation value. Online PostgreSQL migrations also take a session advisory lock and wait up to ten minutes for another migration to finish. [Render pre-deploy command availability](https://render.com/docs/deploys)

Set these values in a short-lived PowerShell process from a password manager. Do not echo them, put them in shell profiles, or save them on a shared Mac:

```text
ENVIRONMENT=production
DEPLOYMENT_ENVIRONMENT=staging
DATABASE_URL=<pooled staging URL>
MIGRATION_DATABASE_URL=<direct staging URL>
JWT_SECRET_KEY=<unique random value of at least 32 characters>
```

Then, from `backend/`, run:

```powershell
$env:PROVISION_CONFIRM_STAGING_MIGRATION = "MIGRATE_PROVISION_STAGING"
uv run --frozen alembic upgrade head
uv run --frozen alembic check
Remove-Item Env:PROVISION_CONFIRM_STAGING_MIGRATION
```

Use this guarded sequence for future schema changes only after checking the project, region, host, and database name. The advisory lock prevents overlapping Alembic operators from applying schema changes at the same time. Do not run `alembic downgrade base` against staging.

## Configure Render staging

The Render Blueprint already exists with auto-sync disabled. Its plan proposes one Docker web service on the Free plan in Singapore, with auto deploy off and `/ready` as its health check. Review the [Render Blueprint](https://dashboard.render.com/blueprint/exs-dbqqubd6e07s738163ng) and its latest sync plan before applying it. Applying the plan creates the web service; no Neon resource is part of that plan. Do not upgrade a plan.

When the plan is approved:

1. Supply the pooled and direct Neon URLs requested by Render. The Blueprint asks Render to generate the JWT and fixture-token secrets. Verify these environment variables in the service dashboard:

   - `ENVIRONMENT=production`
   - `DEPLOYMENT_ENVIRONMENT=staging`
   - `DATABASE_URL` using the pooled staging URL
   - `MIGRATION_DATABASE_URL` using the direct staging URL
   - `JWT_SECRET_KEY` generated by Render and unique to staging
   - `STAGING_TEST_FIXTURE_TOKEN` generated by Render and kept separate from the JWT secret
   - `DEEPSEEK_ENABLED=false`
   - `STAGING_TEST_FIXTURES_ENABLED=false` until the ordinary staging checks are ready

   The Neon URLs use `sync: false`, so Render prompts for them during initial setup. Render's `generateValue: true` creates a random secret when `JWT_SECRET_KEY` and `STAGING_TEST_FIXTURE_TOKEN` do not exist. Copy the generated fixture token from Render into the GitHub `staging` environment secret only when you configure the manual staging workflow. [Render Blueprint secret variables](https://render.com/docs/blueprint-spec)
2. Deploy the intended commit manually from the Render Deploys page. The Blueprint leaves auto deploys off. Render's **Deploy a specific commit** action accepts a commit SHA and disables automatic deploys for that service. [Deploy a specific commit](https://render.com/docs/deploys)
3. Confirm `GET /health` returns `deployment: staging` and the expected `revision`. Confirm `GET /ready` returns `{"status":"ready"}`. `/ready` runs `SELECT 1` and returns no database diagnostics.
4. After ordinary staging works, enable `STAGING_TEST_FIXTURES_ENABLED=true` only if you plan to run the staging E2E workflow. The endpoint still requires a run-owned synthetic account and the matching fixture token. It refuses to delete an account if its household has records or its scope has changed.

Render reports the service's deployed commit as `RENDER_GIT_COMMIT`. The E2E workflow checks that value before creating a test account. [Render default environment variables](https://render.com/docs/environment-variables)

The Free plan does not provide an automatic migration hook here. Do not put migrations in the container start command or run them from each web process. For later schema changes, review the migration and target, take the normal database backup available to the plan, then run the guarded direct migration once from a trusted workstation before deploying the matching app commit.

## Configure GitHub staging tests

Create a GitHub Actions environment named `staging` and add:

- Variable `PROVISION_STAGING_API_BASE_URL`, set to the Render HTTPS URL ending in `/api/v1`.
- Secret `PROVISION_STAGING_FIXTURE_TOKEN`, set to the fixture token generated by Render for the staging service.
- Leave variable `PROVISION_LIVE_DEEPSEEK_ENABLED` unset or set to `false` until the separate live-AI checks are approved.

GitHub only accepts `workflow_dispatch` for workflows present on the repository's default branch. Because this PR does not merge itself, these manual workflows become runnable after an approved merge to the default branch. A run must select a full commit SHA reachable from `main`; the job verifies that before exposing any staging secret, then checks Render is serving that same SHA. [GitHub manual workflow requirements](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)

The standard PR workflow does not contact Render or Neon. Run **Provision staging E2E** manually with the full commit SHA currently deployed to Render. Each account-creating, authenticated, and cleanup script first checks that the URL belongs to `*.onrender.com`, the health and readiness endpoints pass, and Render serves the requested commit. It then registers run-unique synthetic households through the normal API and checks household selection and isolation, product edits and label review, batch expiration and quantity, recipe detail and pantry availability, allergy review and blocking, provider-disabled recommendations, and explicit idempotent shopping confirmation. The workflow removes only the unique single-member synthetic households it created, including their household-scoped data, after checking that the accounts have no references outside those households. The iPhone 17 Simulator tests staging login, Keychain relaunch, logout, and login recovery, then runs deterministic offline and stale-shopping retry scenarios against the local UI-test fixtures. The workflow uploads the staging `.xcresult` and exported screenshots for 14 days.

The staging smoke uses the public API, checks that Cook with Pip keeps the provider disabled and that missing allergy information requires review, and does not reset a shared database. The repository has synthetic label-review data and reference screenshots, but no suitable receipt or product-label input photos; image/OCR processing is therefore not claimed as covered. A failed cleanup is reported as a failure and leaves records intact for inspection. Run only one staging workflow at a time.

## Run the optional live DeepSeek smoke

Keep DeepSeek disabled for all routine tests and initial staging validation. The live workflow stays disabled unless the GitHub `staging` environment variable `PROVISION_LIVE_DEEPSEEK_ENABLED` is exactly `true`. Set it only after the deployed backend, fixtures, and consent behavior have passed manual review. To authorize one live request:

1. Confirm that `provision-staging` is healthy, uses the isolated Neon project, and has the fixture cleanup token configured.
2. Add the DeepSeek API key only to the Render staging service. Never put it in GitHub, the iOS app, a Mac lab account, or a screenshot.
3. Set `DEEPSEEK_ENABLED=true` on Render staging and configure the strict budget values already listed in `render.yaml`.
4. Manually run **Provision staging live DeepSeek smoke** with the deployed commit SHA and the exact phrase `RUN_ONE_SYNTHETIC_DEEPSEEK_REQUEST`.
5. Confirm the output reports one synthetic request, valid proposal schema and provenance, a deterministic safety result, and no inventory, recipe, or shopping writes. The workflow does not configure automatic retries.
6. Turn `DEEPSEEK_ENABLED` off, set `PROVISION_LIVE_DEEPSEEK_ENABLED=false`, and remove or rotate the staging provider key after the check.

This workflow is not a Pip Chat test. Pip Chat is not part of this deployment-preparation change.

## Inspect results and recover

The 12 PR smoke screenshots appear in the routine workflow artifacts. The full screenshot set and `.xcresult` appear on **Cook with Pip full screenshot gallery** runs; staging artifacts appear on the manual staging run. Download them from the relevant GitHub Actions run page and open the `.xcresult` on a Mac with Xcode. Simulator runs do not verify physical camera, barcode scanner, or receipt-capture hardware.

If a deploy fails, Render keeps the previous successful deploy running. With auto deploy disabled, inspect the failed build and service logs, correct configuration or deploy a known-good commit manually, and recheck `/health` and `/ready`. Do not run destructive migrations to recover. [Render deploy failure behavior](https://render.com/docs/deploys)

## Rotate credentials and protect shared Macs

- Rotate `JWT_SECRET_KEY` only with a planned staging session reset because existing staging tokens will stop working.
- For a leaked Neon credential, rotate the staging role password in Neon, update both Render URLs, and rerun the smoke checks. Do not use production database roles.
- For a leaked fixture token, replace it in both Render and the GitHub `staging` environment, then rerun E2E cleanup checks.
- For a leaked DeepSeek key, revoke it with the provider, remove it from Render, and issue a replacement only for another approved live check.
- Shared Mac lab machines need no cloud credentials. The workflow receives only the Render base URL, a fixture-cleanup token, and a short-lived synthetic account created during that run. Do not add cloud secrets to Xcode schemes or local `.env` files on those machines.

## Current verification boundary

The Docker build and local container HTTP/readiness smoke have passed. Focused deployment, migration-guard, health, and cleanup tests have passed. Neon migration and connection compatibility have been verified on the isolated Free project. The Render plan is ready but not applied, so deployed API checks, the manual staging workflow, and the live provider call have not run. The GitHub `staging` environment still needs the Render URL and fixture token after the Render service is approved and configured.
