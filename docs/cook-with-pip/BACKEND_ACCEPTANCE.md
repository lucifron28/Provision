# Windows backend acceptance

This audit covers the backend scope in the approved Cook with Pip objective.
The roadmap also contains provider, SwiftUI and device deliverables that this
Windows task explicitly defers. Live external calls remain disabled.

## Evidence by requirement

| Requirement | Implementation and verification sources |
| --- | --- |
| PostgreSQL 18 stabilization | `database_safety.py`, guarded SQLite import utility, Compose PostgreSQL 18 volume, `test_database_safety.py` and `test_postgresql_migrations.py`; historical CI evidence in roadmap prerequisites. |
| Household isolation | Membership authorization, composite ownership foreign keys, legacy quarantine, scoped existing routes and demo CLI; household, auth, privacy and intake tests. |
| Ingredient foundation | Versioned canonical catalog and aliases, reviewed product mappings/factors, exact unit conversion and expiry-aware availability; ingredient/unit/availability tests and 33 Filipino recipe fixtures. |
| Preferences and allergies | Private member/shared profiles, distinct unknown declarations, allergen derivatives, substitutions and versioned product-label reviews; profile/safety/label tests. |
| Recipes and deterministic recommendations | Typed household recipes, categories, region classification, immutable revisions, private bookmarks and local recommendation ranking; recipe/recommendation and Filipino acceptance tests. |
| Trusted source policy | Disabled publisher candidates, maintainer reviews, evidence expiry, exact host/URL policy, broader-web permission and revocation gates; registry, URL-security, review CLI and recommendation tests. No publisher is approved by seeding. |
| Smart shopping | Read-only snapshots, shortage/pending reconciliation, explicit confirmation, duplicate consolidation, household write serialization, stale-context checks and retry records; recipe/plan shopping and concurrency tests. |
| Weekly planning | Household Monday-based schedules, pinned recipe revisions, full-week optimistic replacement, archive/history and aggregate shopping; meal-plan tests include consistent concurrent reads. |
| Cooking and inventory | Read-only FEFO allocation, actual quantity overrides, explicit history/consumption authorization, current safety gates, native precision checks and atomic inventory events; cooking tests include concurrent confirmation and exact retries. |
| Leftovers | Household location/recipe links, user-verified dates, explicit consume/discard events, optimistic balance revisions, archive and consistent reads; leftover tests. |
| Budget and waste | Historical PHP ingredient-usage costs, purchase-time unit uncertainty, explicit inventory/leftover disposal and unknown-cost coverage; meal-insight and planning/privacy tests. No current quotes or inferred savings. |
| Export and deletion | Shared planning/cooking/leftover export is household-scoped. Member profile export excludes other members' private declarations. Deletion removes personal data and clears new actor references while retaining shared records; privacy and planning/privacy tests. |
| Provider configuration | `.env.example` has a marked key placeholder, settings load a secret value, and README explains setup. Credentials do not enable external calls. |
| Preservation | Full existing backend suite, migration cycle and the unchanged scanner XCTest workflow must pass on the published head. No SwiftUI files changed in this milestone. |

## Integrated verification

The foundation through `11e99fa` passed **568 tests, one optional historical-file
skip**, with two dependency deprecation warnings on local PostgreSQL 18.6.
Focused PostgreSQL
checks passed for plans/shopping/recipes/Filipino fixtures, cooking/leftovers,
pricing/batches/privacy, manual origin edits and history-preserving downgrade
refusal. Alembic upgrade and drift checks passed on the separate verification
database. CI verification and the final adaptation/canned-product acceptance
additions remain pending.

## Deferred work

Live DeepSeek generation, external search/fetch/extraction, provider credentials,
provider quotas/cost validation and publisher access reviews require the deferred
provider milestone. The current implementation makes no external recipe calls.

New SwiftUI screens, account-scoped offline caches, cooking timers, leftover
reminders/reuse presentation, accessibility and physical-device acceptance are
listed in [the Mac handoff](MAC_HANDOFF.md). Existing iOS CI verifies the existing
scanner client; it does not validate these future screens.

Plans do not reserve stock. Cooking revalidates and consumes current stock only
after confirmation. Leftovers do not become canonical ingredient stock, and
their cost remains unknown. Historical batch records have no purchase-unit
snapshot, so ambiguous prices are excluded. These limits are part of the API
contracts and must remain visible to clients.
