# Meal plans API

This reference describes the household meal-plan and plan-shopping routes currently registered under `/api/v1`. They read and write local PostgreSQL records; they do not call a recipe provider or fetch publisher pages.

## Household and cache scope

All routes require an access token. The server selects the default household unless the request supplies `X-Household-ID`; it checks membership for either choice. Missing or invalid authentication returns `401`, and a user without membership in the selected household receives `403`.

Each route sets `Cache-Control: no-store`. Do not retain plan or preview responses across logout or household changes.

Plan list, detail, and history reads use one PostgreSQL repeatable-read, read-only snapshot per response. The plan revision, its entries, and pinned recipe titles therefore come from the same committed state. A plan-shopping preview reads the same fields inside its broader dependency snapshot.

New plan-shopping rows record their plan revision as the primary origin. Ordinary
manual quantity or note edits preserve that link. Explicitly setting
`origin_recipe_id` through the manual shopping API replaces the plan origin with
the selected household recipe revision; a row has one primary origin.

## Weekly plans

| Method and path | Behavior |
| --- | --- |
| `GET /meal-plans/` | List active plans, optionally filtered by inclusive `from_week` and `to_week` dates. |
| `GET /meal-plans/{plan_id}` | Read a plan by household-scoped ID, including an archived plan. |
| `GET /meal-plans/{plan_id}/history` | Read the stored plan revision snapshots in revision order. |
| `PUT /meal-plans/weeks/{week_start}` | Create or replace the entire week. |
| `DELETE /meal-plans/{plan_id}?expected_revision={revision}` | Archive the plan and append a history revision. |

`week_start`, `from_week`, and `to_week` must be Mondays. `GET /meal-plans/` returns active plans only. The ID and history routes can still read archived plans. The API has no unarchive operation; an archived week cannot be replaced through `PUT` because its household/week row remains reserved.

`PUT /weeks/{week_start}` creates a plan when `expected_revision` is omitted or `null`. To replace an existing plan, send its current revision. The request replaces every entry, so moving or removing a meal uses the same full-week request and optimistic revision check.

```json
{
  "expected_revision": null,
  "entries": [
    {
      "meal_date": "2026-10-26",
      "slot": "dinner",
      "position": 0,
      "recipe_id": 41,
      "recipe_revision": 2,
      "servings": "4"
    }
  ]
}
```

An entry date must fall within the seven days starting at `week_start`. `slot` is `breakfast`, `lunch`, `dinner`, or `merienda`. `position` is 0 through 9, defaulting to 0. Each date/slot/position must be unique. `servings` must be positive and at most 10,000, with at most four decimal places. A request can contain at most 140 entries. An empty list is a valid full reset and creates a history snapshot.

Each entry references a recipe revision in the selected household. The plan retains that revision when the recipe is edited. The read response contains the entry's pinned `recipe_revision` and title from that revision. History records the plan revision, timestamp, nullable author ID, and the complete plan read snapshot. Replacing or archiving a plan appends a new history revision; archiving increments the plan revision and keeps its entries available for history and reads.

Creating or replacing a plan requires the recipe to remain active. Both the pinned revision and the recipe's current content must declare `content_permission: "OWNED_OR_PERMISSION_GRANTED"`. This field is a recipe permission declaration; the plan API does not independently verify a license. An active source reference is checked against the current source registry. Suspended, rejected, or expired approved sources are unavailable even if broader-web permission was recorded. A non-approved reference can use broader-web policy only when its saved permission allows it and the current registry has not revoked that reference.

The planner does not consume or reserve inventory when a plan is created, moved, removed, read, or archived.

## Plan-shopping preview

`POST /plan-shopping/preview` accepts:

```json
{
  "plan_id": 12,
  "expected_plan_revision": 3,
  "diner_user_ids": [7, 8],
  "include_optional": false
}
```

`diner_user_ids` is optional. When omitted, safety evaluation uses all active members of the selected household. If provided, it must contain distinct active household member IDs. `include_optional` defaults to `false`.

The server reads one PostgreSQL repeatable-read, read-only snapshot and recalculates the plan from its pinned recipe revisions. It resolves recipe lines to active curated ingredients, converts compatible units to each ingredient's curated default unit, and aggregates exact serving-scaled quantities by ingredient and required/optional status before applying the 200 aggregated-requirement limit. It uses exact fractions until the aggregate is checked against the six-decimal quantity limit. It does not round a non-representable quantity.

The availability and shopping arithmetic runs once across the combined plan demand. For each canonical ingredient, `shortage = max(required - usable pantry, 0)`, `target = max(existing unbought pending quantity, shortage)`, and `additional = max(target - pending, 0)`. Expired, unverified, incompatible, ambiguous, and unlinked quantities are not guessed. They remain review-required or cause the preview to return `422 REVIEW_REQUIRED`.

The response includes a signed `preview_id` that expires after 10 minutes, `expires_at`, the plan and shopping/inventory revisions, the pinned entries, a `safety` result, shopping `lines`, and `unlinked_manual_items`. A line can be `ready` or `review_required`; a review-required line cannot be accepted during confirmation. The top-level `safety.decision` must be `eligible` for the preview to return `200`. A blocked or review-required safety decision returns `422` with its decision and reasons. Preview performs no writes and reserves no stock.

The preview checks current recipe activity, current and pinned content-permission declarations, and current source policy. A recipe edit that preserves permission does not replace the plan's pinned content. Withdrawing current permission makes a new preview return `422 REVIEW_REQUIRED`; archiving a recipe or revoking its active source after preview makes confirmation stale.

## Plan-shopping confirmation

`POST /plan-shopping/confirm` accepts the preview token, the `shopping_revision` returned by preview as `expected_revision`, a household-scoped `idempotency_key`, and optional accepted lines:

```json
{
  "preview_id": "<signed preview token>",
  "idempotency_key": "plan-confirm-2026-10-26-01",
  "expected_revision": 5,
  "accepted_lines": [
    {
      "ingredient_id": 19,
      "target_quantity": "5.000000",
      "consolidate_existing": false
    }
  ]
}
```

The key is trimmed and must contain 8 to 128 characters. `expected_revision` is the shopping revision returned by preview and must be nonnegative. `accepted_lines` defaults to empty, has a maximum of 200 entries, and cannot repeat an ingredient ID. Each target must be positive, no greater than `99,999,999.999999`, and have at most six decimal places. It cannot be lower than either the calculated shortage or current pending quantity. Omitting a line leaves it unchanged.

Confirmation locks the household, rechecks the preview and current dependencies, and writes accepted shopping changes and the idempotency response in one transaction. It never changes pantry batches. It does not overwrite a pending row's name, notes, or product; a new row records `origin_plan_id` and `origin_plan_revision`. Bought rows are excluded from pending totals and are never consolidated. Multiple compatible pending rows require `consolidate_existing: true` before an increase; the lowest ID remains, and removed-row snapshots are returned in `consolidated`.

The response contains `plan_id`, `plan_revision`, `shopping_revision`, and `created`, `updated`, `unchanged`, and `consolidated` lists. If no shopping row changes, confirmation records the idempotency result but does not increment `shopping_revision`.

Preview tokens last 10 minutes. After household authorization, confirmation checks its idempotency record before checking token expiry, so an exact retry by the same active member with the same household, workflow, key, and request body replays the stored response after expiry. A different body, actor, or workflow with the same household key returns `409 IDEMPOTENCY_KEY_REUSED`. Plan and recipe shopping share the household key namespace. The code assigns no expiry to stored idempotency rows, so replay duration depends on retaining that row.

Confirmation returns `409 STALE_PREVIEW` if the token expired, plan changed, inventory or shopping revision changed, source or permission gates changed, or the recomputed context differs. A failed confirmation must not be retried with a changed body under the same key.

Plan shopping does not reserve stock for future meals or aggregate separate plans against one another. Each preview evaluates one plan against current inventory and pending shopping rows.

## Status codes

| Status | Conditions |
| --- | --- |
| `200` | Successful reads, plan replacement, preview, or confirmation. |
| `204` | Successful plan archive. |
| `401` | Missing or invalid access token. |
| `403` | No membership in the selected household, or a diner ID is not an active household member. |
| `404` | Plan, recipe, or pinned recipe revision is not found in the selected household. |
| `409` | Plan revision conflict, archived plan, archived recipe or unavailable source during plan write, stale preview, or reused idempotency key with a different request. A recipe archived or permission-revoked after plan creation makes preview return `422 REVIEW_REQUIRED`; if that change happens after preview, confirmation returns `409 STALE_PREVIEW`. |
| `422` | Request validation failure, non-Monday week, entry outside the plan week, missing content-permission declaration, empty plan preview, requirement limit, safety review, or unrepresentable/unsupported quantity. |

For preview, safety failures return `422` with `detail.code = "REVIEW_REQUIRED"`, a `decision`, and `reasons`. For confirmation, changed dependencies return `409 STALE_PREVIEW`; a line that is not ready or a target below shortage/pending returns `422`.

## Verification boundary

Focused PostgreSQL verification from `backend/`:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://provision:provision@127.0.0.1:55432/provision_test'
uv run pytest tests/test_meal_plans.py tests/test_plan_shopping.py tests/test_recipe_shopping.py tests/test_recipes.py tests/test_filipino_recipe_acceptance.py -q
```

Result: 70 passed with 2 existing dependency deprecation warnings. This run includes the repeatable-read plan-response race regression and 33 synthetic Filipino recipe records persisted through the API. It does not include the full backend suite or CI, which Main owns.
