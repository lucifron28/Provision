# Cooking and leftovers API

These routes preview a recipe against verified household stock, record an
explicit cooking confirmation, and track leftover quantities through consume
and discard events. Requests require authentication and membership in the
selected household. Responses set `Cache-Control: no-store`.

## Cooking routes

| Method | Route | Behavior |
| --- | --- | --- |
| POST | `/api/v1/cooking/preview` | Calculate exact ingredient demand and FEFO batch allocations without writes. |
| POST | `/api/v1/cooking/confirm` | Deduct allocated stock and record a pinned cooking session after explicit confirmation. |
| GET | `/api/v1/cooking/sessions` | List recorded sessions in the selected household. |
| GET | `/api/v1/cooking/sessions/{cooking_session_id}` | Read one scoped session, its consumption rows and linked leftovers. |

### Preview

```json
{
  "recipe_id": 17,
  "expected_recipe_revision": 3,
  "servings": "4",
  "include_optional": false,
  "diner_user_ids": [12],
  "actual_amount_overrides": [
    {"requirement_index": 1, "amount": "25", "unit": "g"}
  ]
}
```

`servings` must be a finite positive decimal no greater than `10000`, with at
most four decimal places. The recipe must be active and at the requested
revision. `include_optional` defaults to `false`. `diner_user_ids` defaults to
all active household members; an explicit list must contain distinct active
members of the selected household.

Each `actual_amount_overrides` item refers to a zero-based index in the pinned
recipe's ingredient list. Its positive amount is the actual amount to cook with,
so the service does not scale that line again by servings. Other lines scale
from the recipe's saved servings. An override for an omitted optional line is
rejected. Amounts allow at most six decimal places. Ingredient units normalize
to `g`, `kg`, `ml`, `l` or `count`; conversions require compatible dimensions.
The service does not infer density or a product package size.

The service reads a PostgreSQL repeatable-read, read-only snapshot. A preview
does not reserve batches, create history or change the inventory revision.
Each required ingredient must resolve to a curated ingredient and have enough
usable stock through a current, verified `DIRECT` product mapping whose target
is exactly that ingredient. Verified package factors may convert a product's
native unit to ingredient quantity. Composite mappings are never deducted as
cooking stock. Products without a supported unit or verified factor do not
contribute usable stock.

Allocations follow FEFO order: earliest expiration first, then purchase time,
then batch ID. Batches with an expiration date before the household's current
Asia/Manila date are excluded. A batch expiring today remains eligible. Batches
without an expiration date sort after dated batches and appear in
`missing_expiry_batch_ids`.

Safety evaluation uses the selected diners' current profiles, current source
policy and current product labels. Every batch the cooking allocation would
consume must also appear in the safety evaluator's covered batch IDs for that
ingredient. If the evaluator covered a composite batch but cooking would use a
different direct batch, the preview requires review. A safety result of
`blocked` or `review_required` cannot be confirmed. An eligible result is not a
food-safety guarantee.

A preview response contains `preview_id`, `expires_at`, recipe identity and
revision, servings, the inventory revision, a `safety` result, one entry per
canonical ingredient in `requirements`, and `missing_expiry_batch_ids`. Each
requirement reports its source `requirement_indexes`, canonical name, requested
quantity and unit, optional status, and exact allocations. An allocation reports
batch and product IDs, native quantity and unit, ingredient quantity and unit,
storage location, expiration date and whether its expiration is unknown.

The recipe must declare `content_permission` as
`OWNED_OR_PERMISSION_GRANTED`. Active source references are rechecked against
current registry policy. The preview does not fetch pages or call an AI
provider. Unsupported mappings, insufficient verified direct stock, stale
recipe revisions, and unresolved safety questions return an error instead of a
partial cookable plan.

The signed `preview_id` expires after ten minutes and binds the actor, household,
request, inventory revision, missing-expiry batch IDs and a dependency
fingerprint. Treat it as request state, not as an authentication credential.

### Confirm

`POST /api/v1/cooking/confirm` accepts the preview token, an idempotency key,
the literal confirmation text and optional leftovers:

```json
{
  "preview_id": "the exact token returned by preview",
  "idempotency_key": "cook-request-unique-0001",
  "confirmation": "RECORD COOKING",
  "record_history": true,
  "acknowledged_missing_expiry_batch_ids": [],
  "leftovers": [
    {"name": "Rice portions", "quantity": "2", "unit": "portion", "portions": "2"}
  ]
}
```

`confirmation` must equal `RECORD COOKING`; `record_history` must be `true`.
The idempotency key is trimmed and must contain 8 to 128 characters. Send the
exact `missing_expiry_batch_ids` returned by preview in
`acknowledged_missing_expiry_batch_ids`, including an empty list when there
were none. An incomplete or extra acknowledgement returns
`422 MISSING_EXPIRY_ACKNOWLEDGEMENT_REQUIRED`.

Confirmation takes the household write lock, rechecks active membership, source
and safety policy, recipe revision, stock, mappings, labels and the fingerprint.
It locks allocated batches in ID order and rejects any native deduction that
cannot be represented exactly in hundredths. `inventory_batches.remaining_quantity`
and `inventory_events.quantity` remain `Numeric(10,2)`. The service does not
round a package-factor inverse; a quantity such as `0.333...` returns
`422 REVIEW_REQUIRED` with no partial writes.

A successful confirmation commits the batch deductions, `CONSUMED`
`InventoryEvent` rows, `CookingConsumption` rows, pinned `CookingSession`,
optional leftovers and idempotency snapshot in one transaction. It increments
the household inventory revision once. Any failure rolls back all of those
changes. Viewing a recipe or previewing a cook never consumes stock.

The session pins `recipe_id` and `recipe_revision`, servings, the inventory
revision and available source reference/revision evidence. It does not store
diner IDs, food profiles or allergy notes. Session reads include canonical
ingredient quantities and the linked inventory event IDs. `GET /sessions` and
`GET /sessions/{cooking_session_id}` are household-scoped.

Retry the exact request body with the same key to receive the stored response,
even after preview expiry. When a leftover omits `prepared_at`, the first
successful request stores its generated timestamp with the result, and the
omitted field remains stable for request hashing on retries. Reusing the key
with changed request content returns `409 IDEMPOTENCY_KEY_REUSED`. Changed
stock, recipe, profiles, labels, source policy or household date invalidates a
preview with `409 STALE_PREVIEW`.

Common preview or confirmation failures include `404` for a recipe outside the
selected household, `409 RECIPE_REVISION_CONFLICT`, `409 STALE_PREVIEW`, and
`422 REVIEW_REQUIRED` for a safety, conversion, stock or precision review.

## Leftovers

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/api/v1/leftovers?include_archived=false` | List active household leftovers; archived rows are omitted by default. |
| GET | `/api/v1/leftovers/{leftover_id}` | Read one scoped leftover and its events. |
| POST | `/api/v1/leftovers` | Create a leftover. Returns `201`. |
| PATCH | `/api/v1/leftovers/{leftover_id}` | Update its editable details using `expected_revision`. |
| DELETE | `/api/v1/leftovers/{leftover_id}?expected_revision=1` | Archive the row and preserve its history. Returns `204`. |
| POST | `/api/v1/leftovers/{leftover_id}/consume` | Append a `CONSUMED` event and reduce remaining quantity. |
| POST | `/api/v1/leftovers/{leftover_id}/discard` | Append a `DISCARDED` event and reduce remaining quantity. |

Create and event requests use positive decimal quantities with at most six
decimal places. Supported units are `g`, `kg`, `ml`, `l`, `count` and `portion`.
The service does not convert between leftover units. Optional `portions` use at
most four decimal places.

`prepared_at` defaults to the current aware timestamp. A supplied timestamp must
include a timezone and cannot be in the future. `use_by_date` is optional. If
provided, send `use_by_date_verified: true` to confirm that a person supplied
the date. The API never generates a use-by date or storage-duration advice.

Recipe ID and recipe revision must be supplied together and must identify a
revision in the same household. A linked cooking session must also belong to
that household. When confirmation creates a leftover, the service links it to
the new cooking session and its pinned recipe revision; caller-supplied links
must match those values. A storage location must belong to the selected
household.

`LeftoverRead` reports initial and remaining quantity, optional initial and
remaining portions, revision, location, prepared and verified use-by dates,
archive timestamp, expiration state and ordered events. `PATCH` may change the
name, storage location or the paired `use_by_date` and
`use_by_date_verified` fields. It does not replace quantities, units or
`prepared_at`; use consume/discard events to reduce remaining quantity. To clear
a use-by date, send both date fields as `null` and `false`.

Each consume or discard request includes `expected_revision`, a positive
`quantity`, and optional `portions` and `reason`. The quantity cannot exceed
the remaining amount. If the leftover tracks portions, each event must include
a positive portion amount, and quantity and portions must reach zero together.
If portions were not set, event requests must omit `portions`. A consume request
for a leftover whose verified use-by date is earlier than the current
Asia/Manila date returns `409 LEFTOVER_EXPIRED`. Discard remains available for
expired leftovers. Reaching zero automatically archives the leftover; its
events remain readable when `include_archived=true`.

Updates, archive and events require the current `expected_revision`; stale
requests return `409 LEFTOVER_REVISION_CONFLICT`. Archived leftovers cannot be
updated or receive more events. Event history records `CONSUMED` and `DISCARDED`
separately. These events carry quantities and units, not cooked-food prices.
Cooking previews do not treat leftovers as ingredient stock, and this API does
not make leftover recommendations.

## Verification boundary

Twenty-three focused PostgreSQL tests passed for this lane. They cover read-only
previews and consistent cooking-session/leftover read snapshots, FEFO and expiry,
safety coverage matching, bounded serving scales
(nonrepresentable or over-limit quantities return `422 REVIEW_REQUIRED`),
precision rollback, idempotent retry, concurrent confirms, scoped references,
leftover events and optimistic revisions. The integrated backend suite and
Alembic drift check remain with the main executor.
