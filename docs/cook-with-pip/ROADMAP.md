# Cook with Pip — Product Roadmap and Execution Checklist

Status: **Windows backend foundations implemented; provider and Mac/client phases deferred** | Last reviewed: 2026-10-30 | Base: `feat/complete-ui-ux-refinement`

**Purpose.** Evolve Provision from pantry tracking into a Filipino-first household food assistant: discover credible recipes, identify what can be cooked from usable inventory, respect allergies and preferences, buy missing ingredients without duplicates, plan meals, track leftovers, and measure waste. This document is the actionable backlog, not evidence that features already exist.

**Read first:** [Backend acceptance audit](./BACKEND_ACCEPTANCE.md), [Implementation contract](./TECHNICAL_SPEC.md), [Recipe source governance](./RECIPE_SOURCE_POLICY.md), repository `AGENTS.md`. Keep these documents aligned; update checkboxes only after implementation + tests + green CI.

Final backend implementation `0e6977f` passed PostgreSQL 18
[PR backend CI](https://github.com/lucifron28/Provision/actions/runs/41084343660):
**578 passed, one optional historical-file skip**, with two dependency deprecation
warnings. The migration upgrade/drift/downgrade/re-upgrade checks passed.
[Draft PR #1](https://github.com/lucifron28/Provision/pull/1) records the current
published head and CI checks. No merge is authorized. Unchecked client/provider
items below remain deferred; backend completion does not complete those phases.

## Existing system and non-goals

Current technology: iOS SwiftUI; FastAPI + SQLAlchemy 2.0 + PostgreSQL 18 via Docker Compose; JWT/Keychain; product/catalog, inventory batches with expiry and FEFO consumption, shopping, analytics, camera/receipt intake, and Home's heuristic Chef Pip hints. `HomeViewModel.chefPipRecipeIdeas` is not AI recipe generation. Backend records now have household authorization, canonical ingredient mappings and explicit label-review records. Recipe-shopping confirmation reconciles compatible pending quantities; the general manual shopping API still permits deliberate separate entries. Label review records a member's declaration and does not certify food safety. Client household cache integration remains in the Mac handoff.

Preserve barcode acceptance/rearm, receipt OCR, pending commit persistence/reconciliation, FEFO, shopping manual entry, offline cache, and Pip artwork. Do not infer inventory from an AI response, auto-buy, silently consume stock, promise allergen safety, scrape disallowed sites, or put provider API keys on-device. Do not merge any branch without approval.

## Completed Prerequisites

### PostgreSQL stabilization audit, 2026-10-30

The original migration milestone below is historical evidence. Its safety claims
are under correction: the test fixture allowed a development URL and silent
SQLite fallback, and the transfer utility verified counts after committing.
Stabilization is complete for the audit scope, verified locally and in CI.

- `cfa8373`: corrected the PostgreSQL 18 volume mount to `/var/lib/postgresql`;
  loaded a secret DeepSeek key placeholder without enabling provider calls.
- `9b1efe7`: CI now checks schema drift and an upgrade/downgrade/re-upgrade cycle.
- Local PostgreSQL 18.6 on Windows, port 55432: upgrade to head, downgrade to
  base, re-upgrade and `alembic check` passed on a separate verification database.
- [CI for 9b1efe7](https://github.com/lucifron28/Provision/actions/runs/41024254918)
  passed both backend and iOS jobs. Backend recorded 89 passed and 1 skipped.
  These checks predate the safety patch.
- `6d278f9`: fail-closed PostgreSQL 18 test configuration, token-owned test
  schemas, guarded cleanup, read-only WAL-consistent legacy backups, locked
  empty-target protection, in-transaction value verification and transactional
  sequence restart. Executor verification recorded 14 focused tests passing and
  102 full-suite tests passing, with one optional legacy-file test skipped.
  `b1ec665` adds explicit CI test-database creation. Both backend and iOS jobs
  [passed on that SHA](https://github.com/lucifron28/Provision/actions/runs/41025491670).
  The backend job independently recorded 102 passed and one optional-file skip.
- Live DeepSeek/search integration is deferred until credentials are supplied.
  SwiftUI implementation and device acceptance remain Mac-dependent work.

- [x] **PostgreSQL 18 Backend Migration** (Completed: 2026-10-29, base: `feat/complete-ui-ux-refinement`)
  - Migrated backend from SQLite to PostgreSQL 18 containerized via Docker Compose (`compose.yaml`).
  - Preserved synchronous SQLAlchemy 2.0 architecture with `psycopg` (psycopg 3) and connection pooling (`pool_pre_ping=True`).
  - Full Alembic migrations verified against PostgreSQL 18 for both `upgrade head` and `downgrade base` cycles.
  - Safe SQLite data migration and rollback utility implemented (`backend/scripts/migrate_sqlite_to_postgres.py`) with automatic safety backup, sequence synchronization, and row-count verification.
  - Test suite migrated to isolated PostgreSQL test database (`provision_test`) with per-test table truncation and sequence reset; 90 tests passing.
  - GitHub Actions CI workflow updated with PostgreSQL 18 service container and migration verification.

## Agreed end-user journeys

1. **Cook Now:** see recipes whose *required* ingredients are covered by usable on-hand quantities; rank near-expiry stock higher only after food safety and allergy gates; show which batches/products are counted and label uncertain availability.
2. **Almost There:** show recipes needing a small number of shopping additions, clearly distinguishing available, partial, missing, optional, unknown, and substitution candidates.
3. **Discover:** browse/search dishes from Filipino-first approved recipe publishers, with optional broader-web fallback; display provenance, original URL, attribution, preparation time, servings, and trust/verification state.
4. **Customize:** filter by cuisine/region, course, meal time, main ingredient, cook time, difficulty, budget, equipment, spiciness, preferences, and user-declared allergies/dietary restrictions; support Filipino/English query terms.
5. **Buy Missing:** change servings -> compute shortages -> inspect a preview -> adjust/remove additions -> explicitly confirm -> atomically merge with unbought shopping entries, never create duplicates on retry.
6. **Cook:** show readable instructions and substitutions; after cooking, ask whether to record actual quantities consumed; do not automatically deduct stock on opening/finishing a recipe.
7. **Plan:** saved recipes, weekly meals, combined grocery shortages, pantry-first planning, leftovers, and optional insights for waste and spend.

## Release gates and phase-by-phase TODO

### P0 — Household data isolation and safety foundation (BLOCKS AI production rollout)

Backend implementation `c1adb03` is verified locally and in
[backend and iOS CI](https://github.com/lucifron28/Provision/actions/runs/41028424731).
It scopes all existing pantry routes and analytics, adds private signup households,
owner/member roles, scoped barcode and intake idempotency keys, database ownership
constraints, legacy quarantine, scoped demo resets, consent, self export and
reauthenticated account deletion. JWTs now bind to immutable user IDs; legacy
tokens require login again. Production demo seeding is blocked.

Evidence on PostgreSQL 18.6: full `uv run pytest -q` recorded **124 passed,
1 skipped**; migration checks recorded three passing tests and no Alembic drift;
privacy eight tests and household security six tests passed. The skip requires
the optional historical `backend/provision.db` file. Client cache/scanner account
binding and privacy UI are tracked
in [Mac handoff](MAC_HANDOFF.md). Live DeepSeek/search and their operational
quotas remain deferred; no consent grant enables external calls.

- [x] Audit authenticated API routes and caching for cross-user access; enumerate household-owned entities. Existing pantry APIs now enforce household context. Client cache remediation remains in the Mac handoff.
- [ ] Define household and membership tables; permission policy for household access and role changes. Establish clearly owned records for batches, locations, sessions, shopping, preferences, meal plans, saved recipes, leftovers, events, and caches; globally shared catalog may remain read-only as appropriate.
- [x] Add Alembic migrations and an explicit migration/seed strategy for existing shared-demo data; new accounts receive private households and unassignable legacy data is quarantined.
- [x] Enforce scoped queries and ownership checks for existing backend reads/writes; validate selected membership and related-record ownership; test ID guessing, collections, analytics and bulk shopping across households.
- [ ] Add scoped SwiftData/cache keys and clear caches on logout/household switch; avoid sensitive allergy/preference data in logs and analytics.
- [ ] Record consent/disclosure for sending minimized pantry and food preferences to DeepSeek; define retention, delete/export controls, API key rotation, usage quotas, and an opt-out/no-AI behavior.
- [x] Separate demo and production configuration: seed CLI requires `--demo`, production seeding is blocked, and public setup instructions omit demo passwords.
- [ ] Gate: No cross-household leakage; auth 401/403 tested; migration rollback plan reviewed; new AI endpoints disabled until this passes.

### P1 — Canonical ingredient and quantity foundation (deterministic; no AI dependency)

Backend progress through `5e075ef` includes the canonical catalog, Filipino and
English aliases, versioned household product mappings, explicit package factors,
and a read-only availability API. Both backend and iOS jobs
[passed for that commit](https://github.com/lucifron28/Provision/actions/runs/41036483959).
See [the API contract](INGREDIENT_API.md) for uncertainty rules and request shapes.
Later recipe persistence and allergen declarations have separate evidence below.
The 33 synthetic Filipino recipe fixtures and explicit canned-product package
factor cases passed [backend and iOS CI on `37ff2b4`](https://github.com/lucifron28/Provision/actions/runs/41081566487),
which recorded 570 passed and one skipped backend test.

- [x] Design `ingredients` taxonomy with normalized names, Filipino/English aliases (bawang/garlic, sibuyas/onion, calamansi, kangkong, etc.), food family, density/portion reference where reliable, and allergen declarations.
- [x] Implement curated `product_ingredient_mappings`: a brand/item may map to one ingredient or an explicitly reviewed composite; store confidence, method, verifier, mapping version and unknown state. Never treat flavor/brand text as an allergy-safe label.
- [x] Implement recipe ingredients (`required`/`optional`, quantity, unit, preparation, substitution candidates) and robust unit normalization (g/kg, mL/L, count; portion/package conversions only with authoritative product metadata). Reject unsupported count-to-mass conversions instead of guessing.
- [x] Compute available amounts from household-scoped positive remaining batches; exclude expired-by-recorded-date batches from automatic availability, flag missing expiry information and freshness uncertainty; preserve FEFO for actual consumption.
- [x] Make comparisons deterministic and testable: recipe required quantity, usable amount, shortfall, unknown/ambiguous conversion, partial availability, optional ingredient not required for Cook Now.
- [x] Add 30+ fixtures: Filipino pantry names, brand synonyms, sauces/condiments, egg cartons, canned goods, count-vs-g, fraction servings, multiple batches, unknown expiry, and expiry boundary.
- [x] Gate: identical request snapshot -> identical availability; no invented stock, implicit conversions, or expired-batch inclusion.

### P2 — Trusted recipe source registry and source discovery

The [registry API and maintainer workflow](SOURCE_REGISTRY_API.md) now implement
candidate records, dated review evidence, audit history, exact host policy,
household link references, source-aware recommendation gates and offline query
planning. Two Luna executors added URL-security, policy, CLI and concurrency
coverage. Local PostgreSQL verification recorded **469 passed, one optional-file
skip**, migration upgrade/downgrade tests and no Alembic drift. Backend and iOS
[passed on `361b8f1`](https://github.com/lucifron28/Provision/actions/runs/41048291822).
The four real publisher candidates remain disabled
and unapproved. No live fetch, search, content extraction or image reuse is
implemented or authorized by a registry flag.

- [x] Implement a reviewed `recipe_sources` registry with host allowlisting, source tier, ownership/publisher, cuisine tags, terms/robots review, permitted fetch/use mode, review date, and disable flag.
- [x] Seed **candidates** Panlasang Pinoy, Kawaling Pinoy, Yummy.ph, and Ang Sarap (see source policy); do NOT label them licensed/verified for ingestion until individually reviewed.
- [ ] Implement DeepSeek Search and Fetch as server-side adapters with configurable timeouts, limits, caching, dedup by canonical URL, SSRF/redirect protections and audit traces. Check live API docs during implementation.
- [ ] Search **approved Filipino sources first** using `site:` constraints and Filipino query aliases. Expand to other approved/general web results **only** when the user enables broader search or priority sources lack sufficient relevant results.
- [ ] Rank after hard allergy/food-safety gates; prefer approved publisher, recipe-specific page, matched cuisine, ingredient suitability, accurate structured ingredient data, freshness, and user preferences; do not confuse source reputation with recipe safety.
- [ ] Extract structured `schema.org/Recipe`/JSON-LD when permitted; use model extraction only as fallible fallback; validate typed quantities, yield, ingredients, dates, and source references.
- [ ] Always display source publisher, canonical link, `verified source` vs `other website` state, and `AI adapted` when applicable; never present fabricated URLs or model-generated recipes as publisher originals.
- [ ] Respect publisher permissions, robots, copyright/terms, image reuse rights, and link-out mode; don't retain third-party recipe prose/photos indiscriminately.
- [ ] Test blocked URLs, malicious page instructions, unrelated SEO results, duplicate URLs, revoked domains, offline/no-results, no-search/opt-out, provider failures, rate limits.
- [ ] Gate: only reviewed sources may be fetched under their approved policy; broad discovery always distinct in UI; no source can command DB writes.

### P3 — Preferences, dietary restrictions, and ALLERGIES (safety gate before personalized recommendations)

Profile storage and privacy through `327abd5` passed **292 backend tests with one
optional-file skip** on PostgreSQL 18.6, migration upgrade/downgrade checks, and
[backend and iOS CI](https://github.com/lucifron28/Provision/actions/runs/41038236046).
The API provides private member profiles, owner-managed shared profiles, explicit
allergy state, custom declarations, revision checks, reset and account export.
See [the profile contract](FOOD_PROFILES_API.md). Allergen graph evaluation and
explicit substitutions through `a86649d` passed **333 tests with one optional-file
skip**, migration checks, and
[backend and iOS CI](https://github.com/lucifron28/Provision/actions/runs/41039948431).
See [the safety contract](FOOD_SAFETY_API.md). Versioned package-label reviews
through `019b752` passed **352 tests with one optional-file skip**, migration
checks and [backend and iOS CI](https://github.com/lucifron28/Provision/actions/runs/41041904218).
Recommendation integration is not covered by that CI result. The overall phase
remains incomplete until the remaining implementation and acceptance checks pass.

- [x] Add household/member-scoped preferences: preferred cuisine (Filipino default, selectable regions), dislikes, diet patterns, ingredient exclusions, heat tolerance, equipment, time/budget goals, preferred language, serving count. Backend storage and scoped APIs are verified above; native editing remains in the Mac handoff.
- [x] Add **separate** allergen profile (not just a dislike): explicit allergens incl. milk, egg, fish, crustacean shellfish, tree nuts, peanuts, wheat, soy, sesame; custom allergens, other sensitivities, cross-contact concern, severity/notes optional. Don't treat this US list as exhaustive or as a substitute for Philippine-specific labels. Backend declarations are verified above.
- [ ] Require user to explicitly set allergies to `none declared` or `not provided`; unknown is never interpreted as allergy-free. Provide accessible editing and deletion; per-member vs household applicability must be clear.
- [x] Normalize ingredient/allergen synonym and derivative graph: dairy whey/casein, shrimp paste/bagoong alamang -> crustacean shellfish, patis -> fish, common soy/wheat sauces, nuts and sesame; retain unknown processing/packaging labels.
- [x] Hard filter explicit conflicts before ranking. Any incomplete/uncertain allergen composition -> `Requires label/manual review`, not `Safe for you`. Handle substitutions with fresh allergen validation.
- [x] Never allow generative text to override hard filters; show transparent reasons for blocked/unverified recipes; allow preference soft-ranking override but NOT silent removal of an allergy guard.
- [x] Add negative tests for hidden allergens, packaged foods with unknown labels, substitutions introducing allergens, cross-contact warnings, multi-member households, preference conflicts.
- [ ] Gate: ambiguous or potentially allergenic recipes cannot receive a confident safe label; accessibility and privacy reviewed.

### P4 — DeepSeek-backed Cook with Pip recipes

The [household recipe API](RECIPES_API.md) adds manual entries, typed categories,
regional classification, immutable revisions, private bookmarks and deterministic
recommendations. Local PostgreSQL verification recorded **379 tests passing and
one optional-file skip**. This does not complete the provider or SwiftUI phase.
DeepSeek and web calls remain disabled; no publisher provenance is asserted for
household-entered content. Both backend and iOS
[passed for `0454e72`](https://github.com/lucifron28/Provision/actions/runs/41044660011).
Source-policy integration has separate verified evidence in P2 above.

- [ ] Add provider interface `RecipeAIProvider` and server-side DeepSeek implementation; model, base URL, search feature flags, budgets, timeouts, and retries belong in env/config, NEVER app bundle.
- [ ] Use structured JSON/Pydantic DTOs for recipes; validate source attribution, recipe ID, title, description, cuisine/region, category tags, prep/cook duration, servings, ingredients, instructions, substitutions, uncertainty flags, provenance, and generated/adapted marker.
- [ ] Separate discovery from generation: prefer source-linked recipes with allowed extraction, else explicitly label AI-original proposals. Model may suggest ingredient mappings but only verified deterministic logic counts stock.
- [ ] Expose `Cook Now`, `Almost There`, and `Discover`, with filters, sort, refresh, empty/error/offline states. Show missing/partial/unknown ingredients, dietary warnings and provenance in detail.
- [ ] Rank: allergy eligibility first, inventory fit, fewer missing purchases, near-expiry use (not expired), personal preference, Filipino locality/source tier, prep time, budget estimate when reliable. Avoid made-up exact savings or food-safety claims.
- [ ] Build Chef Pip entry from Home; keep five-tab shell; use native SwiftUI search/filter/detail/navigation, accessibility, Dynamic Type, light/dark.
- [ ] Test stub provider with malformed JSON, prompt injections, irrelevant recipes, invalid ingredient units, unknown URLs, missing fields, excessive cost, cache invalidation when stock changes.
- [ ] Gate: outputs grounded, validated, attributable, no unapproved API exposure; tests/CI green.

### P5 — "Add Missing Ingredients to Shopping List" (primary integrated milestone)

The [recipe shopping contract](RECIPE_SHOPPING_API.md) implements shared household write serialization,
read-only snapshot previews and explicit idempotent confirmation. Local migration
tests and schema-drift verification pass. The final reviewed PostgreSQL suite
recorded **503 passed, one optional historical-file skip**. Independent review
found and corrected table-lock ordering, truncated alias matching, fingerprint
credential fields and stale cached rows. Backend and iOS
[passed on `3a0b57b`](https://github.com/lucifron28/Provision/actions/runs/41064764193), and
SwiftUI confirmation remains in the Mac handoff. This milestone stays unchecked
until the relevant remaining gates pass.

- [x] Implement `POST /api/v1/recipe-shopping/preview` for recipe/version/servings and selected household: server recomputes current usable stock and requested quantities (never trust AI supplied shortages).
- [x] Compute shortage = `max(required - usable pantry, 0)`; for shopping reconciliation compare with **existing unbought** quantities by canonical ingredient/product and compatible unit, not fuzzy display text alone. Proposed shopping target = `max(existing_pending, shortage)`; delta = `max(shortage - existing_pending, 0)`. Distinguish existing item increase vs creation vs no-op.
- [ ] Present confirmation sheet with per-ingredient existing stock, shortage, existing pending quantity, proposed delta/total, source recipe, selected servings, unknown conversions/allergen flags, selectable rows, quantity edits. **No write on preview.**
- [x] Implement `POST /api/v1/recipe-shopping/confirm` with unique idempotency key, short-lived preview/version, server-side recomputation, authorization and validation, concurrency control (SQLite-safe transaction/optimistic revision), atomic create/update and response specifying added/updated/unchanged.
- [x] Handle conflicts: inventory or shopping list changed since preview -> 409 and require fresh preview/confirmation. Never double-increase same shortage for repeated requests or multiple devices.
- [x] Preserve bought history, manually entered preferences and notes, user quantities; support multiple product equivalents but ask when ingredient mapping is ambiguous. Don't automatically buy or create new catalog products.
- [ ] Link successful confirmation to Shopping tab and show what changed; support recoverable failures and retries. Plan future combined weekly meal shortages with shared ingredients.
- [x] Cases: **4 eggs required, 2 usable, 1 already pending -> target pending 2, add 1 to existing entry**; 0 shortfall -> no-op; incompatible units -> needs review; partial pantry and duplicate existing entries -> deterministic merge strategy; interrupted response -> same idempotent result.
- [x] Gate: no duplicates/lost updates under concurrent taps; user consent to additions; transaction rolls back fully on error.

### P6 — Saved recipes, guided cooking, meal planner

The [plan API](MEAL_PLANS_API.md) and [cooking/leftover API](COOKING_LEFTOVERS_API.md)
now implement weekly revision history, pinned recipes, aggregate shopping,
read-only cooking previews, explicit consumption and audited leftovers. Two Luna
executors completed focused PostgreSQL runs of 70 and 23 tests, respectively.
Main's pricing/batch/privacy integration recorded 18 passing focused tests;
two new migration tests prove history-loss downgrades refuse atomically.
Alembic upgrade and schema-drift verification pass on the separate Windows
verification database. The foundation through `11e99fa` passed the complete
local suite, **568 passed, one optional historical-file skip**, with two existing
dependency deprecation warnings. Backend and the unchanged scanner XCTest job
[passed on `2a5a8cf`](https://github.com/lucifron28/Provision/actions/runs/41080845054).
CI independently recorded 568 passed and one skipped backend test. Subsequent
adaptation and canned-product acceptance additions have separate pending checks.
The canned-product tests subsequently passed on `37ff2b4` as recorded in P1.
The user-authored adaptation addition now pins same-household parent revisions,
keeps lineage on edits and rechecks ancestor permissions/source history across
evaluation, plans, shopping and cooking. Seven focused adaptation tests and 80
neighboring tests pass. The complete local suite through `57c1a64` recorded
**577 passed, one optional-file skip**, with two dependency deprecation warnings.
The subsequent large-household test passed separately with 60 pantry batches,
120 shopping rows and a foreign household row. It confirms an item beyond the
first 100 rows without altering unrelated entries or inventory. Exact-head CI
for all final backend additions is recorded in the 578-test result above.
Plans describe intended meals without reserving inventory; actual cooking
confirmation rechecks stock under the household write lock.

- [x] Backend save/unsave retains private portions and preferences. User adaptations pin an immutable household parent revision and revalidate current ancestor permissions/source history; full ingredient safety and stock checks still apply. Native bookmarking/editing flows remain in the Mac handoff.
- [ ] Guided Cooking mode: steps, timers where supported, serving adjustments, checklist, ingredients reviewed before cooking; never change inventory simply by viewing a recipe.
- [x] Backend explicit "Record Cooking" provides quantity overrides, a FEFO allocation preview, audited inventory consumption, stock revision checks and retry records. Native review/confirmation UI remains in the Mac handoff.
- [x] Backend weekly meal planner supports dates, breakfast/lunch/dinner/merienda and household servings. Combined ingredient demand subtracts current pantry and pending purchases once.
- [x] Backend batch shopping uses P5 reconciliation, preview/confirmation and plan revisions. Moving/removing meals preserves history and invalidates previews. Native planner/shopping screens remain deferred.
- [ ] Gate: no accidental auto-consumption; concurrent plans don't silently oversubscribe scarce stock; grocery consolidation correct.

### P7 — Leftovers, budget, food waste, and household insights

The initial [historical budget and waste API](MEAL_INSIGHTS_API.md) through
`05f0f31` passed 13 focused PostgreSQL tests and the complete backend CI suite,
**516 passed, one optional-file skip**. Both backend and iOS
[passed on that head](https://github.com/lucifron28/Provision/actions/runs/41066131363).
It reports price provenance, unknown costs and quantities grouped by unit.
Subsequent plan/cooking/leftover integration and its exact-head acceptance remain
pending; this phase is not complete.

- [x] Add leftovers (name/recipe, quantity, storage location, prepared_at, optional use-by guidance explicitly user-verified, portions); avoid pretending generated food-safety dates are guaranteed.
- [ ] Leftover reminders and reuse suggestions, respecting allergy/preference rules and user opt-in; no recommendation of spoiled/expired food.
- [x] Meal budget estimates using historical **available** prices with currency PHP, timestamps, store context, missing-price state; never portray estimated prices as current store quotes.
- [ ] Waste dashboards: recorded discard events, cost, time period, recipe-plan usage, pantry-to-shopping efficiency and clear baseline methodology. No unsupported claims of savings.
- [x] Optional household cooking preferences/history with consent, deletion, and correct member scoping.
- [ ] Gate: explainable metrics, opt-out, no sensitive-data leaks.

### P8 — Stabilization and release acceptance

- [ ] End-to-end tests across FastAPI, migrations, SwiftUI, DeepSeek mock, search/fetch mock, SKU mapping, allergy filters, snapshots, concurrent shopping commits, retry/idempotency, and offline.
- [ ] Real-device check: iPhone barcode/receipt flows unchanged, scanner pause/rearm, saved intake recovery, accessibility, VoiceOver, large text, light/dark, iPhone SE-sized viewport, 50+ pantry items, 100+ shopping items, 30+ scanned items.
- [x] Realistic PH recipe fixtures (adobo, sinigang, tinola, pancit, ginisang monggo, tortang talong, arroz caldo, lumpia, champorado) with region/category, common sauces, allergens, conditional quantities.
- [ ] Security: API auth/household isolation, external-site SSRF redirect chains, untrusted fetched page prompt injection, API key leakage, duplicate idempotency, retention/deletion, traffic/cost rate limiting.
- [ ] Update stale README midterm status and safe demo documentation. Record provider costs and capabilities **as of validation date**; never guarantee DeepSeek API feature permanence.
- [ ] Run full backend pytest + iOS XCTest + branch CI; inspect and fix failures without changing acceptance criteria merely to pass tests. Document any device/provider testing that was not actually run.
- [x] Opened [draft PR #1](https://github.com/lucifron28/Provision/pull/1) for review. It remains unmerged; merge requires explicit approval.

## Dependencies and development sequence

`Completed Prerequisites -> P0 -> P1 -> (P2 and P3 can run in parallel once scoped) -> P4 -> P5 -> P6 -> P7 -> P8`. P3 allergy gate must pass before enabling personalized recommendations to users. P1/P5 pure backend services should be built/tested before tying into AI. A vertical MVP may ship after P5 only with P0–P5 gates complete; P6/P7 are subsequent releases.

**Agent workflow for each phase:** inspect repository + official docs -> record small technical decisions -> make scoped change/migration -> negative/positive tests -> local tests -> push -> verify required GitHub Actions -> update checkbox and short evidence (commit SHA, tests, CI, caveats) -> continue to next unlocked milestone. "Done" means working code + verified acceptance criteria, never solely a plan.

## Future design decisions to record before coding

- Product catalog global vs household-specific data and migration behavior.
- Household allergy policy: strictest selected member vs whole household; default use **all selected diners** and show which person's restrictions apply without revealing unnecessary details.
- Source reuse permissions and whether deep-linked instructions stay publisher-hosted; never assume an approved publisher automatically grants reuse rights.
- Portion conversion reference data and manually verified product composition provenance.
- Recipe dedup/versioning across sources; local-language aliases and regional cuisines.
- Shopping duplicate policy: canonical ingredient ID vs product ID, mixed unit entries, legacy unlinked items, conflicting edits, and multi-plan shopping aggregation.
- DeepSeek contract/model/version, API rate limits, privacy, per-household quota, cold start, and fallbacks.

## References (implementation research, verify again before coding)

- DeepSeek Search/Fetch: https://api-docs.deepseek.com/guides/search/
- Google Recipe JSON-LD: https://developers.google.com/search/docs/appearance/structured-data/recipe
- Food allergen guidance: https://www.fda.gov/food/nutrition-food-labeling-and-critical-foods/food-allergies
- Source registry, tiers, provenance and acceptable reuse: [RECIPE_SOURCE_POLICY.md](./RECIPE_SOURCE_POLICY.md)
