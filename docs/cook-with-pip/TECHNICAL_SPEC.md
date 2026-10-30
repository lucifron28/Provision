# Cook with Pip — Technical Implementation Specification

Status: **Windows backend foundations implemented; provider and SwiftUI work deferred.** Parent: [ROADMAP.md](./ROADMAP.md). Source rules: [RECIPE_SOURCE_POLICY.md](./RECIPE_SOURCE_POLICY.md). Last reviewed: 2026-10-30.

This is the engineering design for phases P0–P8. The roadmap records implementation and verification evidence. The feature-specific API documents describe current contracts; original route sketches below remain design proposals where they differ. Start by reading `backend/app/api/v1/api.py`, `backend/app/services/inventory.py`, `backend/app/api/v1/endpoints/shopping.py`, SwiftUI `ShoppingViewModel`, `HomeViewModel`, `ScanViewModel`, plus migrations/tests.

## 1. Principles and boundaries

- Source of truth: SQLAlchemy inventory batches + shopping rows with authorized household scope. No LLM-written SQL, no LLM-supplied stock numbers or automatic side effects.
- Treat DeepSeek as a replaceable **untrusted recipe generation / extraction / ranking assistant**. Trust boundaries: external recipe sites -> DeepSeek provider -> typed Pydantic validation -> local deterministic matching, policy gates and mutations.
- Enforce allergies and household auth in deterministic code independent of the LLM. Unknown ingredient composition means uncertain, not allergen-safe.
- PH-first: Filipino dishes, localized ingredient synonyms, PHP, `Asia/Manila` date boundaries, household-style units. Global cuisines remain available via filters and optional broader search.
- Read-only preview vs mutating confirm must be separate. No automatic grocery purchase, pantry consumption, or confirmed shopping mutation without deliberate user action.
- Prefer incremental migration and tests; avoid changing scanner commit behavior. Existing scanner pending-commit mechanism is for grocery intake and MUST NOT be reused as shopping mutation state without separate idempotency semantics.
- Use Decimal (or suitable exact decimal SQL types) for units/prices and explicit unit policies; don't rely on unrounded floats for atomic reconciliation.
- Default short-lived caching for recipe discovery; never cache private pantry or allergy profiles across households.
- No image hotlinking unless usage terms permit it. Link to credited publisher recipe pages where extraction/reuse is restricted.

## 2. Proposed modules

### Backend (add under `backend/app/`)
- `models/ingredient.py` — canonical ingredient, aliases, unit_conversion_reference, product-ingredient mapping, allergen graph.
- `models/recipe.py` — saved/curated recipe metadata, normalized recipe ingredients, categories, provenance, source registry, version.
- `models/preferences.py` — household/member diet preferences and allergen declarations, consent/retention.
- `models/meal_plan.py`, `models/cooking.py`, `models/leftover.py` hold weekly-plan revisions, explicit cooking records and leftover events. Their current contracts are in [meal plans](MEAL_PLANS_API.md) and [cooking/leftovers](COOKING_LEFTOVERS_API.md).
- `models/shopping.py` — extend existing shopping row with optional canonical `ingredient_id`, provenance, household scope and revision.
- `schemas/recipes.py`, `schemas/preferences.py`, `schemas/recipe_shopping.py` — Pydantic request/response validation, strict enums, bounds.
- `services/ingredient_matching.py` — alias resolution, confidence, composite packaging, verified conversions.
- `services/recipe_availability.py` — **deterministic** batch stock + shortfalls + expiry/timezone logic.
- `services/recipe_discovery.py` — source allowlist, DeepSeek Search/Fetch adapter, ranking, URL provenance.
- `services/recipe_ai.py` — typed provider abstraction, bounded DeepSeek calls, error handling, privacy minimization.
- `services/allergen_policy.py` — hard-block and review-required decisions, with reasons.
- `services/recipe_shopping.py` — preview/version, atomic shopping changes, idempotency and concurrency.
- `api/v1/endpoints/recipes.py`, `preferences.py`, `recipe_shopping.py`, `meal_plans.py`, `plan_shopping.py`, `cooking.py` and `leftovers.py`.

### SwiftUI (add under `frontend/frontend/`)
- `Models/Recipe.swift`, `RecipeAvailability.swift`, `FoodPreferences.swift`, `RecipeShoppingPreview.swift`.
- `ViewModels/CookWithPipViewModel.swift` and `RecipeShoppingViewModel.swift`.
- `Views/CookWithPipView.swift` (Cook Now / Almost There / Discover), `RecipeDetailView.swift`, `RecipeShoppingConfirmationView.swift`, `FoodPreferencesView.swift`.
- Later `WeeklyMealPlannerView.swift`, `SavedRecipesView.swift`, `CookingModeView.swift`, `LeftoversView.swift`.
- APIClient typed methods; keep credentials server-side and same existing auth handling. Entry from Home's Chef Pip; keep five tab destinations.

## 3. Data model sketch + constraints

### Backend implementation decisions, 2026-10-30

These decisions describe the implemented P0 backend contract. Verification
evidence is recorded in the roadmap and backend acceptance audit.

- Products are household-owned, including barcode uniqueness. Scanner create,
  lookup, edit and delete keep their existing route shapes. This avoids exposing
  custom product names or permitting edits to another household's catalog.
- New accounts receive a private household and owner membership atomically.
  An optional household context must pass a membership check. Client body IDs
  never grant access. Related product, location, batch and session references
  must belong to the same household.
- Existing rows without ownership evidence move into a restricted legacy
  household without memberships. Existing accounts receive private households.
  An operator must verify ownership before granting legacy access. Demo seeding
  explicitly owns its demo household and may only reset that household's data.
- Privacy consent defaults off and records a notice version. Granting consent
  does not enable DeepSeek. Future sharing requires current consent from every
  active household member whose household data would be shared.
- Account deletion reauthenticates and removes access while preserving shared
  inventory history. A sole owner with remaining members must transfer ownership
  first. Keep an inactive anonymized account tombstone for audit references.
  Tokens must also carry the immutable user ID and authentication must match it
  to the account. Email-subject tokens alone can revive access after email reuse.
  Existing tokens without the ID claim require login again after rollout.
- SwiftUI household cache keys, pending intake account binding, privacy screens
  and device acceptance remain Mac-dependent TODOs until implemented and tested.

All table names proposed; write Alembic migrations with explicit indexes, uniqueness, FK behavior, downgrade and demo migration.

| Table | Key fields / constraints |
| --- | --- |
| `households` / `household_members` | household ID; membership user ID; role; unique (household_id,user_id); context selected server-side with authorization |
| `ingredients` | stable ID, English canonical name, native Filipino name, ingredient family, default measurement dimension, status; normalized canonical name unique within catalog |
| `ingredient_aliases` | ingredient FK, normalized alias, language, region, confidence, reviewed_at; alias conflicts flagged rather than auto-selected |
| `product_ingredient_mappings` | product FK, ingredient FK, mapping_mode: direct/composite/unknown, confidence & verified_by, component amount/units if composite; product+mapping version uniqueness |
| `ingredient_allergens` | ingredient FK, allergen ID, relation direct/derivative/possible/unknown, evidence/provenance, checked_at |
| `food_preferences` | scoped member/household, cuisine/region categories, disliked foods, restrictions, cook time, spice, equipment, budget, servings, language; revisions |
| `food_allergies` | member/household, canonical allergen or custom text, severity optional, cross-contact concern, declared/unknown flag; encryption/privacy policy |
| `recipe_sources` | canonical host, publisher name, source_tier, verified_status, approved_methods, terms/robots review date, enabled flag |
| `recipes` | ID, title, short description, source_id/url, source_author, provenance: linked/curated/ai_original/ai_adapted, fetched_at, recipe_version, cuisine, PH region, category tags, duration, servings, review status |
| `recipe_ingredients` | recipe ID, canonical ingredient ID nullable, original display, amount, canonical unit, dimension, required/optional, allergen uncertainty, verified conversion |
| `saved_recipes` | household/member scoped recipe reference + favorite, edits/servings; separate copyright policy for text retention |
| `shopping_list_items` (extend existing) | scope + optional ingredient_id + quantity/unit, status, manual entry notes, origin_recipe_id / origin_plan_id optional, revision; do **not** blindly enforce unique product rows while historical bought entries remain |
| `shopping_mutation_requests` | (household_id,idempotency_key) unique, request hash, response snapshot, status, created_at; dedupe retries for same key+payload |
| `shopping_preview_snapshots` (or stateless signed token) | snapshot id, scope, recipe/version/servings, selected member prefs revision, inventory revision, shopping revision, expiry; no long-lived sensitive data |
| `meal_plans` / `planned_meals` | household scope, week/day/meal slot, recipe/version/servings, ingredient aggregation context |
| `leftovers` | household scope, recipe link optional, quantity/unit, location, prepared_at, entered use-by date, remaining portions and consume/discard event link |

Security: no user-supplied household id accepted without server membership check. Scope `InventoryBatch`/`StorageLocation`/`GrocerySession`/`InventoryEvent`/`ShoppingListItem`/`SavedRecipe`/`Preferences`/`MealPlan`/`Leftover`, and existing analytics endpoints. Inventory event relationships and migrations need explicit review. Catalog `Product` may be global read-only while stock records are scoped.

## 4. Structured recipe / provenance contract

Illustrative REST models (field spelling to be finalized in implementation):
- `RecipeCandidate`: `recipe_id` optional, `title`, `description`, `cuisine`, `region`, `categories[]`, `difficulty`, `prep_minutes`, `cook_minutes`, `servings`, `required_ingredients[]`, `optional_ingredients[]`, `instructions[]`, `provenance`, `source_url` nullable, `source_publisher` nullable, `source_tier`, `ai_adapted`, `last_verified_at`.
- Ingredient: `canonical_ingredient_id` nullable, `label`, `amount` decimal nullable, `unit` enum/normalized, `original_text`, `required`, `allergens[]`, `confidence`, `substitution_options[]`.
- Availability: `required_amount`, `usable_on_hand`, `shortfall`, `unit`, `covered_batch_ids[]`, `unmatched_products[]`, `match_status` (full/partial/missing/unknown), `expiry_warnings[]`, `allergen_decision` (eligible/blocked/review_required), `explanation`.
- Evidence: original source URL (never fabricated), publisher, factual extraction vs model adaptation, retrieval timestamp, restriction on reusing instructions/image.
- Strict Pydantic validation: minimum/maximum servings, ingredient count, max text lengths, bounded steps/tokens, positive finite numeric amounts, known enum values, no unexpected executable instructions.

**AI result handling:** It must NOT decide actual stock, unit-conversion constants, allergy safety, price, shopping target, or whether a household can access data. All are recomputed from trusted DB and policy, with unresolved fields explicitly marked. Reject or downgrade a candidate rather than silently fill missing safety-critical fields.

## 5. Ranking and source retrieval

Two distinct pathways:
1. **No-web pantry recommendation:** derive candidate recipes from saved/curated data; optionally use DeepSeek with *minimized, non-identifying* ingredient names and preference constraints to propose original recipes. Label them as AI-generated. Do not claim provenance.
2. **Web Discover:** query **approved** Filipino hosts via DeepSeek Search `site:`; retrieve only permitted recipe pages via Fetch; parse `schema.org/Recipe`/JSON-LD if available, validate; then rank. Broad-web fallback only by explicit user opt-in or a clearly labeled setting and only after insufficient approved results; strip dangerous/untrusted content.

Suggested search queries: `"sinigang na baboy" site:panlasangpinoy.com OR site:kawalingpinoy.com`; `"ginisang monggo" Filipino recipe`; `"tortang talong" lang:en`. DeepSeek Search supports `site:` and `OR`; **domain enforcement is performed by the backend on returned/fetched URLs, not by model instructions alone**.

Eligibility gates **before score**: correct household scope; recorded expiration; dietary restriction and allergen decision; parseable ingredient list. Suggested **configurable** priority weights (not hardcoded magic or fabricated certainties): 35% usable ingredient coverage, 20% few missing items, 15% source approval/tier, 10% Filipino/regional fit, 10% near-expiry use, 5% user taste, 5% time. Apply stronger customization only after test fixtures; don't boost sources into bypassing allergy checks. Dedup canonical URL, normalized title + author, variant family; disclose source state visibly.

Examples of category taxonomy:
- Meal/occasion: breakfast, lunch, dinner, merienda, dessert, snack, drink, baon, Noche Buena/fiesta.
- Dish type: ulam/main, sabaw/soup, noodles/pancit, rice/silog, gulay, seafood, grilled, fried, stew, baked, no-cook.
- Cuisine/region: Filipino default; Ilocano, Bicolano, Kapampangan, Tagalog, Visayan, Mindanao and explicit `region_unknown`; international categories.
- Primary ingredient: chicken, pork, beef, fish, shrimp, vegetables, tofu, eggs, noodles, rice.
- Effort: quick (<= 15m), <= 30m, <= 60m, slow; beginner/intermediate/advanced; equipment and spice level.
- Dietary tags are **not** inferred from a publisher label alone; backend validated/unknown.

## 6. Allergy and preference decision pipeline

Data policy:
- Unspecified allergy information = `not provided`, distinguish explicit `none declared`.
- Determine diners selected for this meal; strict union of their hard allergies for eligibility. Household preference ≠ personal allergy. Show context and missing labels without exposing a member's private medical detail unnecessarily.
- Start with nine common allergen groups (milk, egg, fish, crustacean shellfish, tree nuts, peanuts, wheat, soy, sesame) **plus arbitrary user-defined allergens and local derivatives**; this is not an exhaustive global list.
- Derived ingredients: bagoong alamang -> crustacean shellfish; fish sauce/patis -> fish; wheat/soy in some sauces (specific label required); cheese/whey/casein -> milk; optional substitutions may introduce new conflicts.
- Outcomes: `blocked` (verified conflicting allergen; not offered as suitable), `review_required` (unverified composite/unknown brand ingredient or cross-contact; visibly warned, no allergen-safe assurance), `eligible` (no known conflict, with reminder to check actual labels/preparation). Never use "guaranteed safe".
- Hard-block before personalization. Model "ignore allergens" text cannot change flags. If recipe step/source differs from structured ingredients, recheck.
- Minimize sharing of exact allergy profiles with external provider: local backend filters and passes only necessary exclusion labels if consented; never usernames, tokens, email, household IDs.
- Every substitute re-runs allergen, ingredient and quantity matching.

## 7. Missing ingredient arithmetic and shopping

Definitions, for a **single recipe and user-adjusted servings**:
- `required_i`: normalized required amount per canonical ingredient i; optional omitted unless user opts in.
- `usable_i`: same-unit sum from authorized, positive inventory batches with expiry policy applied; no speculative conversion.
- `shortage_i = max(0, required_i - usable_i)`.
- `pending_i`: valid unbought entries for same canonical ingredient or verified equivalent products, **only** where units are convertible and entries are scoped to household.
- `target_i = max(pending_i, shortage_i)`, `delta_i = max(0, target_i - pending_i)`. This definition means a recipe adds just enough for its shortage; it does not reserve stock. For a multi-meal plan, aggregate all planned requirements **once**, then subtract usable_i and pending_i **once**.
- Example: recipe 4 eggs, pantry 2 eggs, To Buy 1 egg -> shortage 2, target 2, delta 1. Preview "Increase existing eggs from 1 to 2" (not "add 2" and not a new row).
- When a pantry package says 12 eggs but inventory unit says "pack": need verified pack_size=12 before using 1 pack to represent 12 eggs. Treat incompatible units as `needs_manual_confirmation`; don't convert cups -> g without a documented ingredient-specific conversion.
- If multiple pending rows for one ingredient, choose deterministic consolidation: retain one primary row, preserve other notes/source history, propose merge and removal only with explicit confirmation; if incompatible or manual notes conflict, ask user to resolve. Never silently combine purchased rows.
- Explicit new recipe shopping entries should track `origin_recipe` and use configured idempotency/transaction unique constraints. Do not overwrite user-edited quantities automatically on future recipe previews.

### Suggested two-step API

`POST /api/v1/recipe-shopping/preview` (authenticated, household scoped):
Input `recipe_id`, `recipe_version`, `servings`, `diners[]`, optional selected ingredient IDs, `include_optional`. Server re-fetches stock, prefs, recipe and pending shopping; computes and returns:
- `preview_id`, `expires_at`, `inventory_revision`, `shopping_revision`, `preferences_revision`, `recipe_version`.
- `lines[]` with normalized requested, usable, shortage, pending, target, delta, `action` create/update/noop/needs_review, matched existing row ids, warnings.
- No writes. User may deselect or edit proposed lines, and each edit needs server-side validation if it changes semantic quantities.

`POST /api/v1/recipe-shopping/confirm`:
Input `preview_id`, `idempotency_key`, `accepted_lines[]` (identifier + reviewed target quantity), `expected_revision`. Verify membership and all scope keys; verify same preview and same content hash; re-evaluate stock/shopping/preference versions in one DB write transaction. If stale, return `409 STALE_PREVIEW` with no writes and a regenerate action. If unverified units, return `422 REVIEW_REQUIRED`. On success update/create in one transaction and return `created[]`, `updated[]`, `unchanged[]` with persisted IDs and quantities.

The current PostgreSQL 18 implementation serializes household writes using a household row lock and checks stock/list revisions plus the preview context. Read-only previews use a repeatable-read snapshot. A unique scope/key entry with a request digest yields the stored result on an exact retry; the same key with a different body returns 409. Stock and shopping revisions increment on relevant mutations. Stale previews require a fresh review instead of silently changing planned quantities. SQLite remains a legacy import source, not the execution database for these workflows.

**Do not** rely on client state or DeepSeek response for authorization, matching, stock, allergen guard, or write operation. Never silently mutate shopping while generating recipes. Post-confirm should refresh existing `ShoppingViewModel`.

### Pseudo-code (authoritative intent, not executable)

    preview(recipe, servings, scope, diners):
      validate_membership_and_allergies(scope, diners)
      requirements = normalize_recipe_ingredients(scale(recipe, servings))
      pantry = load_usable_stock(scope, recipe_ingredients)
      pending = load_unbought_shopping(scope)
      for required in requirements:
        if required.optional and not requested: continue
        if conversion_unknown or ingredient_ambiguous: mark review_required
        shortage = max(0, required - pantry_usable)
        pending_compatible = sum_or_resolve_existing_pending(...)
        target = max(pending_compatible, shortage)
        propose create/update/noop with delta = max(0, target - pending_compatible)
      return signed_or_persisted_preview_with_revisions()

    confirm(preview_id, idempotency_key, accepted):
      authenticate_and_authorize()
      validate_key_and_preview()
      begin PostgreSQL transaction and acquire household write lock
      if repeated exact request: return saved response
      recheck revisions, dietary guard, canonical mapping and unit policy
      if stale: rollback and return 409
      create or update accepted pending rows without dupes
      write idempotency response, audit and revisions
      commit; return exact changes

## 8. API and UX milestone list

Proposed routes (version under `/api/v1`; confirm names before implementation):
- `GET /food-preferences`, `PUT /food-preferences`, `DELETE /food-preferences`; `GET/PUT /food-allergies` with member-level authorization.
- `GET /recipe-categories`, `GET /recipe-sources` (public-facing publisher summaries only).
- `POST /recipes/recommendations` (Cook Now/Almost There), `POST /recipes/discover` (search/filter, opt-in broad-web), `GET /recipes/{id}`.
- `GET/POST/DELETE /recipes/saved`; versioned adapted recipes.
- `POST /recipe-shopping/preview`, `POST /recipe-shopping/confirm` as above.
- Current additional foundations: `/meal-plans`, `/plan-shopping`, `/leftovers`, `/cooking/preview`, `/cooking/confirm`, `/cooking/sessions`, and `/meal-insights`. See the corresponding API documents for exact contracts; the route sketches above describe the original design.

SwiftUI screen requirements:
- Home: concise Chef Pip CTA ("Cook with Pip") without new tab; keep status alerts and branding.
- Landing: filter chips (Cook Now, Almost There, Discover), native search, cuisine/category/time/diet/preferences, source tier filter, sorting, skeleton/error/retry.
- Recipe card: authentic title, short preview, time/servings, ingredient coverage, missing count, publisher URL/tier, AI-generated vs adapted tag, allergy warning state.
- Detail: ingredients grouped as available/partial/missing/unknown, per-line amounts, batch validity, recipe steps if permitted, source CTA, adjustable servings. Show member/allergen warning before cooking actions.
- Shopping review sheet: show 4 columns semantically (needed, pantry, already listed, planned shopping total), edit quantity, toggle line, unresolved conversions, and confirm button with explicit label. Successful commit -> Shopping tab and toast. Retry must not duplicate.
- Preferences: native multi-selection of food/cuisine, searchable exclusions/allergens, "not supplied" distinction, private data notice, edit/delete. High Dynamic Type, VoiceOver, light/dark, small iPhone.
- Existing Home `chefPipRecipeIdeas` remains fallback until Cook with Pip is released; do not misleadingly label heuristic ideas as verified internet recipes.

## 9. Test matrix / release gates

**Ingredient math:** 4/2/1 eggs example; 0 shortfall; unknown stock; two near-expiry batches; expired only; null expiry; same product in multiple locations; 12 pcs/1 pack; incompatible count/g; required vs optional; precise decimals; serving scale; duplicate alias collision.

**Shopping transaction:** repeated idempotency key, concurrent identical/different requests, prior bought entries, existing manual entry and notes, unlinked legacy name match uncertain, stale stock/list/prefs, stale preview, changed recipe version, partial failure full rollback, repeated button taps, API retry after lost response.

**Allergy:** direct egg/milk/shellfish; fish sauce, bagoong, soy/wheat sauce derivative labels; sesame; substituted ingredients; custom allergen; hidden composite and unknown brand labels; union diners; "not provided" vs "none declared"; privacy/authorization; prompt attempts to remove allergen guard.

**Search/source:** trusted Filipino domain first, blocked/fallback sources; host canonicalization and redirects, SSRF (`localhost`, private ranges, cloud metadata), third-party injected text, source misattribution, no results, unreachable site, robots restriction, licensing/link-out, dedup, JSON-LD malformed, API 429/500/timeout.

**UX:** real UI tests for opening and dismissing recipe/source/shopping screens; filters and servings; optimistic stale-preview review; navigates to purchased/pending appropriately; VoiceOver/Dynamic Type/long Filipino names; light/dark; nil pricing.

**Security/ops:** household A cannot read/mutate B via IDs, query params, cached prefs, AI logs, shopping; no API key in iOS; DeepSeek request timeout/rate limits/quotas/circuit breaker; provider mock deterministic tests; admin publisher audit; tests and CI.

**Evidence for milestone DONE:** migrations and downgrade; backend pytest; iOS XCTest; contract integration test; 100+ mixed pantry/shopping fixture; test with 2 households and allergy variants; source/permission review; screenshots from simulator or real iPhone; exact CI run URL and SHA. Report unperformed real-device/provider-live checks honestly.

## 10. Source, privacy and technical references

- DeepSeek Search & Fetch (verified docs, 2026-10-29): https://api-docs.deepseek.com/guides/search/ (`POST /v1/tools/search`; `POST /v1/tools/fetch`; `site:` supported)
- DeepSeek API reference: https://api-docs.deepseek.com/api/deepseek-api/
- Google Recipe structured data: https://developers.google.com/search/docs/appearance/structured-data/recipe
- U.S. FDA allergen reference (non-exhaustive for Philippine users): https://www.fda.gov/food/nutrition-food-labeling-and-critical-foods/food-allergies
- Source registry and acceptable reuse: [RECIPE_SOURCE_POLICY.md](./RECIPE_SOURCE_POLICY.md)
