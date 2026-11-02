# Recipe shopping preview and confirmation

This workflow computes shortages on the server, presents a read-only preview and
changes shopping only after explicit confirmation. It does not reserve or consume
inventory. Live AI and web search remain disabled.

Both endpoints require authentication and authorized household membership. A
preview belongs to the member and household that requested it. Responses use
`Cache-Control: no-store`.

## Preview

`POST /api/v1/recipe-shopping/preview`

```json
{
  "recipe_id": 1,
  "expected_recipe_revision": 1,
  "servings": "2",
  "include_optional": false
}
```

The request may also select `diner_user_ids`. Omission selects active household
members. Optional recipe ingredients are omitted by default. Explicit inclusion
adds their quantities and safety checks to the meal.

The service reads a PostgreSQL repeatable-read, read-only snapshot in a separate
session. It loads the stored recipe, current pantry interpretation, diner
profiles, package labels, source policy and pending shopping rows. It recomputes
safety and quantity availability without changing stock or shopping rows.
Blocked or review-required meal safety returns `422 REVIEW_REQUIRED`.

For each canonical ingredient, the preview reports requested quantity, usable
pantry, shortage, pending purchases, target and additional quantity. All values
use the ingredient's reporting unit.

```text
shortage = max(requested - usable pantry, 0)
target = max(existing pending, shortage)
additional = target - existing pending
```

Only unbought rows contribute pending quantities. Matching requires an explicit
canonical ingredient or a verified direct product mapping with a supported unit
conversion or explicit package factor. Display names alone do not authorize a
merge. Unlinked potential aliases and incompatible units require review rather
than silently creating duplicate purchases or inventing conversions.

The signed `preview_id` expires after ten minutes. It binds the request to its
actor, household, recipe revision, shopping and inventory revisions, and a
fingerprint of the calculation's dependencies. The response includes
`shopping_revision`, `inventory_revision`, `expires_at`, per-line review reasons
and included recipe indexes. Treat the token as request state; do not log it or
reuse it as an authentication credential.

## Confirmation

`POST /api/v1/recipe-shopping/confirm`

```json
{
  "preview_id": "the exact token returned by preview",
  "idempotency_key": "a-client-generated-unique-request-key",
  "expected_revision": 0,
  "accepted_lines": [
    {"ingredient_id": 1, "target_quantity": "2", "consolidate_existing": false}
  ]
}
```

Use the preview's actual revision, ingredient IDs and units. An accepted target
must cover the previewed shortage and preserve existing pending quantity. The
member may deselect a line or explicitly increase its target. Units and ownership
come from server data. Accepted quantities must fit six decimal places without
silent rounding.

Confirmation takes the shared household write lock, rechecks membership and
reloads the preview's dependencies. Changed stock, shopping, mappings, recipes,
profiles, labels, source policy or household date invalidates the old preview.
`409 STALE_PREVIEW` requires a fresh preview and review. Confirmation never
silently substitutes new amounts for those the member accepted.

Confirmation changes only selected pending rows. Bought rows remain untouched.
One matching pending row is increased in place in its existing unit. If the
conversion back to that unit cannot be represented exactly, confirmation requires
review instead of creating a second row or rounding the target.
When duplicate pending rows are consolidated, the member must explicitly select
`consolidate_existing`. The response preserves removed rows' notes and provenance
in the consolidation audit. Existing manual names and notes are retained on the
kept row. New rows record their originating recipe and revision.
Consolidation also retains the kept row's product link, native unit and original
recipe provenance. Removed rows are recorded in the persisted result.

A successful response reports created, updated and unchanged items, any explicit
consolidations, and the resulting shopping revision. All selected changes and
the retry record commit together. Retrying the exact body with the same actor
and household key returns the stored result, including after preview expiry.
Reusing a key with different content returns `409 IDEMPOTENCY_KEY_REUSED`.

## Write guards and compatibility

Online shopping mutations and pantry/product interpretation writes share a
household transaction lock. Inventory and shopping revisions advance with their
respective changes. Existing scanner intake recovery and FEFO remain in their
existing services; preview and confirmation do not call consumption.
The demo seeder, legacy importer and direct SQL are offline maintenance paths.
Stop application writes and discard outstanding previews before running them.
They do not participate in the online write-guard protocol.

Shopping storage now supports six decimal places. Existing read responses retain
numeric JSON quantities for client compatibility. Manual duplicate rows remain
allowed. Recipe confirmation does not imply that manual deletes or clearing
completed items keep a permanent history.

The migration refuses a downgrade that would lose quantity precision, recipe
metadata, retry records or nonzero revisions. Back up and explicitly reconcile
that data before downgrading; do not truncate a development pantry to pass a
migration check.

## Verification status

The reviewed implementation passed 503 PostgreSQL tests with one optional
historical-file skip. Coverage includes confirmation retries, single-row updates,
explicit consolidation, full rollback, stale dependencies, household isolation,
read-only previews, cached-session refresh and concurrent source review. Migration
upgrade/downgrade and schema-drift checks passed. Exact-head CI is pending.
SwiftUI preview, selection, stale-state handling and confirmation screens remain
Mac-dependent.
