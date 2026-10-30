# Cook with Pip — Product Roadmap and Execution Checklist

Status: **PLANNED / NOT IMPLEMENTED** | Last reviewed: 2026-10-29 | Base: `feat/complete-ui-ux-refinement`

**Purpose.** Evolve Provision from pantry tracking into a Filipino-first household food assistant: discover credible recipes, identify what can be cooked from usable inventory, respect allergies and preferences, buy missing ingredients without duplicates, plan meals, track leftovers, and measure waste. This document is the actionable backlog, not evidence that features already exist.

**Read first:** [Implementation contract](./TECHNICAL_SPEC.md), [Recipe source governance](./RECIPE_SOURCE_POLICY.md), repository `AGENTS.md`. Keep these documents aligned; update checkboxes only after implementation + tests + green CI.

## Existing system and non-goals

Current technology: iOS SwiftUI; FastAPI + SQLAlchemy 2.0 + PostgreSQL 18 (via Docker Compose); JWT/Keychain; product/catalog, inventory batches with expiry and FEFO consumption, shopping list, price/waste analytics, camera/receipt intake, and Home's **heuristic** Chef Pip hints. Current `HomeViewModel.chefPipRecipeIdeas` is NOT AI recipe generation. Shopping has a `ShoppingListItem` (name, optional product_id, quantity, unit, is_bought, notes) and `POST /api/v1/shopping-list`. The README declares **one shared pantry across authenticated users**; there is no authorized user/household scope for personalized food data. The existing backend low-stock generator checks product ID, but general shopping entry creation does not prevent duplicates. The current catalog does not identify canonical culinary ingredients or reliable packaged-food allergen labels.

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

- [ ] Audit all authenticated API routes and caching for cross-user access; enumerate products vs household-owned entities. The router's `Depends(get_current_user)` authenticates but does **not** scope inventory or shopping queries.
- [ ] Define household and membership tables; permission policy for household access and role changes. Establish clearly owned records for batches, locations, sessions, shopping, preferences, meal plans, saved recipes, leftovers, events, and caches; globally shared catalog may remain read-only as appropriate.
- [ ] Add Alembic migrations and an explicit migration/seed strategy for existing shared-demo data; default new accounts must NOT see other users' pantry or private diet details.
- [ ] Enforce scoped queries and ownership checks in repository/service layer for every read/write, never rely on client-submitted `household_id`; add cross-household negative tests for ID guessing and list endpoints.
- [ ] Add scoped SwiftData/cache keys and clear caches on logout/household switch; avoid sensitive allergy/preference data in logs and analytics.
- [ ] Record consent/disclosure for sending minimized pantry and food preferences to DeepSeek; define retention, delete/export controls, API key rotation, usage quotas, and an opt-out/no-AI behavior.
- [ ] Fix demo credentials exposure in production-facing docs/build; separate demo from production configuration.
- [ ] Gate: No cross-household leakage; auth 401/403 tested; migration rollback plan reviewed; new AI endpoints disabled until this passes.

### P1 — Canonical ingredient and quantity foundation (deterministic; no AI dependency)

- [ ] Design `ingredients` taxonomy with normalized names, Filipino/English aliases (bawang/garlic, sibuyas/onion, calamansi, kangkong, etc.), food family, density/portion reference where reliable, and allergen declarations.
- [ ] Implement curated `product_ingredient_mappings`: a brand/item may map to one ingredient or an explicitly reviewed composite; store confidence, method, verifier, mapping version and unknown state. Never treat flavor/brand text as an allergy-safe label.
- [ ] Implement recipe ingredients (`required`/`optional`, quantity, unit, preparation, substitution candidates) and robust unit normalization (g/kg, mL/L, count; portion/package conversions only with authoritative product metadata). Reject unsupported count-to-mass conversions instead of guessing.
- [ ] Compute available amounts from household-scoped positive remaining batches; exclude expired-by-recorded-date batches from automatic availability, flag missing expiry information and freshness uncertainty; preserve FEFO for actual consumption.
- [ ] Make comparisons deterministic and testable: recipe required quantity, usable amount, shortfall, unknown/ambiguous conversion, partial availability, optional ingredient not required for Cook Now.
- [ ] Add 30+ fixtures: Filipino pantry names, brand synonyms, sauces/condiments, egg cartons, canned goods, count-vs-g, fraction servings, multiple batches, unknown expiry, and expiry boundary.
- [ ] Gate: identical request snapshot -> identical availability; no invented stock, implicit conversions, or expired-batch inclusion.

### P2 — Trusted recipe source registry and source discovery

- [ ] Implement a reviewed `recipe_sources` registry with host allowlisting, source tier, ownership/publisher, cuisine tags, terms/robots review, permitted fetch/use mode, review date, and disable flag.
- [ ] Seed **candidates** Panlasang Pinoy, Kawaling Pinoy, Yummy.ph, and Ang Sarap (see source policy); do NOT label them licensed/verified for ingestion until individually reviewed.
- [ ] Implement DeepSeek Search and Fetch as server-side adapters with configurable timeouts, limits, caching, dedup by canonical URL, SSRF/redirect protections and audit traces. Check live API docs during implementation.
- [ ] Search **approved Filipino sources first** using `site:` constraints and Filipino query aliases. Expand to other approved/general web results **only** when the user enables broader search or priority sources lack sufficient relevant results.
- [ ] Rank after hard allergy/food-safety gates; prefer approved publisher, recipe-specific page, matched cuisine, ingredient suitability, accurate structured ingredient data, freshness, and user preferences; do not confuse source reputation with recipe safety.
- [ ] Extract structured `schema.org/Recipe`/JSON-LD when permitted; use model extraction only as fallible fallback; validate typed quantities, yield, ingredients, dates, and source references.
- [ ] Always display source publisher, canonical link, `verified source` vs `other website` state, and `AI adapted` when applicable; never present fabricated URLs or model-generated recipes as publisher originals.
- [ ] Respect publisher permissions, robots, copyright/terms, image reuse rights, and link-out mode; don't retain third-party recipe prose/photos indiscriminately.
- [ ] Test blocked URLs, malicious page instructions, unrelated SEO results, duplicate URLs, revoked domains, offline/no-results, no-search/opt-out, provider failures, rate limits.
- [ ] Gate: only reviewed sources may be fetched under their approved policy; broad discovery always distinct in UI; no source can command DB writes.

### P3 — Preferences, dietary restrictions, and ALLERGIES (safety gate before personalized recommendations)

- [ ] Add household/member-scoped preferences: preferred cuisine (Filipino default, selectable regions), dislikes, diet patterns, ingredient exclusions, heat tolerance, equipment, time/budget goals, preferred language, serving count.
- [ ] Add **separate** allergen profile (not just a dislike): explicit allergens incl. milk, egg, fish, crustacean shellfish, tree nuts, peanuts, wheat, soy, sesame; custom allergens, other sensitivities, cross-contact concern, severity/notes optional. Don't treat this US list as exhaustive or as a substitute for Philippine-specific labels.
- [ ] Require user to explicitly set allergies to `none declared` or `not provided`; unknown is never interpreted as allergy-free. Provide accessible editing and deletion; per-member vs household applicability must be clear.
- [ ] Normalize ingredient/allergen synonym and derivative graph: dairy whey/casein, shrimp paste/bagoong alamang -> crustacean shellfish, patis -> fish, common soy/wheat sauces, nuts and sesame; retain unknown processing/packaging labels.
- [ ] Hard filter explicit conflicts before ranking. Any incomplete/uncertain allergen composition -> `Requires label/manual review`, not `Safe for you`. Handle substitutions with fresh allergen validation.
- [ ] Never allow generative text to override hard filters; show transparent reasons for blocked/unverified recipes; allow preference soft-ranking override but NOT silent removal of an allergy guard.
- [ ] Add negative tests for hidden allergens, packaged foods with unknown labels, substitutions introducing allergens, cross-contact warnings, multi-member households, preference conflicts.
- [ ] Gate: ambiguous or potentially allergenic recipes cannot receive a confident safe label; accessibility and privacy reviewed.

### P4 — DeepSeek-backed Cook with Pip recipes

- [ ] Add provider interface `RecipeAIProvider` and server-side DeepSeek implementation; model, base URL, search feature flags, budgets, timeouts, and retries belong in env/config, NEVER app bundle.
- [ ] Use structured JSON/Pydantic DTOs for recipes; validate source attribution, recipe ID, title, description, cuisine/region, category tags, prep/cook duration, servings, ingredients, instructions, substitutions, uncertainty flags, provenance, and generated/adapted marker.
- [ ] Separate discovery from generation: prefer source-linked recipes with allowed extraction, else explicitly label AI-original proposals. Model may suggest ingredient mappings but only verified deterministic logic counts stock.
- [ ] Expose `Cook Now`, `Almost There`, and `Discover`, with filters, sort, refresh, empty/error/offline states. Show missing/partial/unknown ingredients, dietary warnings and provenance in detail.
- [ ] Rank: allergy eligibility first, inventory fit, fewer missing purchases, near-expiry use (not expired), personal preference, Filipino locality/source tier, prep time, budget estimate when reliable. Avoid made-up exact savings or food-safety claims.
- [ ] Build Chef Pip entry from Home; keep five-tab shell; use native SwiftUI search/filter/detail/navigation, accessibility, Dynamic Type, light/dark.
- [ ] Test stub provider with malformed JSON, prompt injections, irrelevant recipes, invalid ingredient units, unknown URLs, missing fields, excessive cost, cache invalidation when stock changes.
- [ ] Gate: outputs grounded, validated, attributable, no unapproved API exposure; tests/CI green.

### P5 — "Add Missing Ingredients to Shopping List" (primary integrated milestone)

- [ ] Implement `POST /api/v1/recipe-shopping/preview` for recipe/version/servings and selected household: server recomputes current usable stock and requested quantities (never trust AI supplied shortages).
- [ ] Compute shortage = `max(required - usable pantry, 0)`; for shopping reconciliation compare with **existing unbought** quantities by canonical ingredient/product and compatible unit, not fuzzy display text alone. Proposed shopping target = `max(existing_pending, shortage)`; delta = `max(shortage - existing_pending, 0)`. Distinguish existing item increase vs creation vs no-op.
- [ ] Present confirmation sheet with per-ingredient existing stock, shortage, existing pending quantity, proposed delta/total, source recipe, selected servings, unknown conversions/allergen flags, selectable rows, quantity edits. **No write on preview.**
- [ ] Implement `POST /api/v1/recipe-shopping/confirm` with unique idempotency key, short-lived preview/version, server-side recomputation, authorization and validation, concurrency control (SQLite-safe transaction/optimistic revision), atomic create/update and response specifying added/updated/unchanged.
- [ ] Handle conflicts: inventory or shopping list changed since preview -> 409 and require fresh preview/confirmation. Never double-increase same shortage for repeated requests or multiple devices.
- [ ] Preserve bought history, manually entered preferences and notes, user quantities; support multiple product equivalents but ask when ingredient mapping is ambiguous. Don't automatically buy or create new catalog products.
- [ ] Link successful confirmation to Shopping tab and show what changed; support recoverable failures and retries. Plan future combined weekly meal shortages with shared ingredients.
- [ ] Cases: **4 eggs required, 2 usable, 1 already pending -> target pending 2, add 1 to existing entry**; 0 shortfall -> no-op; incompatible units -> needs review; partial pantry and duplicate existing entries -> deterministic merge strategy; interrupted response -> same idempotent result.
- [ ] Gate: no duplicates/lost updates under concurrent taps; user consent to additions; transaction rolls back fully on error.

### P6 — Saved recipes, guided cooking, meal planner

- [ ] Save/unsave recipe references and user adaptations with provenance, default portions, categories and household scope; allow revalidation after source/stock changes.
- [ ] Guided Cooking mode: steps, timers where supported, serving adjustments, checklist, ingredients reviewed before cooking; never change inventory simply by viewing a recipe.
- [ ] On **explicit** "Record Cooking", present consumed ingredient quantities and FEFO allocation preview; user adjusts quantities, then use existing inventory service/ledger for audited consumption, stock revision guards and retries.
- [ ] Weekly meal planner (calendar days, breakfast/lunch/dinner/merienda, household servings). Combine ingredient demands across meals before subtracting available pantry and pending purchases, rather than per-recipe naive addition.
- [ ] Batch "add missing for plan" uses same P5 preview-confirm pipeline; changing a plan invalidates previews. Save planning history and allow moving/removing meals.
- [ ] Gate: no accidental auto-consumption; concurrent plans don't silently oversubscribe scarce stock; grocery consolidation correct.

### P7 — Leftovers, budget, food waste, and household insights

- [ ] Add leftovers (name/recipe, quantity, storage location, prepared_at, optional use-by guidance explicitly user-verified, portions); avoid pretending generated food-safety dates are guaranteed.
- [ ] Leftover reminders and reuse suggestions, respecting allergy/preference rules and user opt-in; no recommendation of spoiled/expired food.
- [ ] Meal budget estimates using historical **available** prices with currency PHP, timestamps, store context, missing-price state; never portray estimated prices as current store quotes.
- [ ] Waste dashboards: recorded discard events, cost, time period, recipe-plan usage, pantry-to-shopping efficiency and clear baseline methodology. No unsupported claims of savings.
- [ ] Optional household cooking preferences/history with consent, deletion, and correct member scoping.
- [ ] Gate: explainable metrics, opt-out, no sensitive-data leaks.

### P8 — Stabilization and release acceptance

- [ ] End-to-end tests across FastAPI, migrations, SwiftUI, DeepSeek mock, search/fetch mock, SKU mapping, allergy filters, snapshots, concurrent shopping commits, retry/idempotency, and offline.
- [ ] Real-device check: iPhone barcode/receipt flows unchanged, scanner pause/rearm, saved intake recovery, accessibility, VoiceOver, large text, light/dark, iPhone SE-sized viewport, 50+ pantry items, 100+ shopping items, 30+ scanned items.
- [ ] Realistic PH recipe fixtures (adobo, sinigang, tinola, pancit, ginisang monggo, tortang talong, arroz caldo, lumpia, champorado) with region/category, common sauces, allergens, conditional quantities.
- [ ] Security: API auth/household isolation, external-site SSRF redirect chains, untrusted fetched page prompt injection, API key leakage, duplicate idempotency, retention/deletion, traffic/cost rate limiting.
- [ ] Update stale README midterm status and safe demo documentation. Record provider costs and capabilities **as of validation date**; never guarantee DeepSeek API feature permanence.
- [ ] Run full backend pytest + iOS XCTest + branch CI; inspect and fix failures without changing acceptance criteria merely to pass tests. Document any device/provider testing that was not actually run.
- [ ] Open PR for review; **do not merge** without approval.

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
