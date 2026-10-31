# Historical meal budgets and recorded waste

These household-scoped read-only endpoints require authentication and return
`Cache-Control: no-store`. They do not call a provider, update prices, consume
stock or create waste events.

## Recipe budget

`POST /api/v1/meal-insights/recipes/{recipe_id}/budget`

```json
{
  "expected_recipe_revision": 1,
  "servings": "2",
  "include_optional": false
}
```

The endpoint loads the stored recipe and scales its ingredient requirements for
the requested servings. It also accepts the evaluation contract's diner and
explicit substitution fields. It returns a price estimate, not a recommendation
or allergy clearance. Recipe revision, source and ownership checks remain in
the recipe evaluation path.

For each canonical ingredient, pricing requires a verified direct mapping with
known composition and a supported unit conversion or explicit package factor.
Composite products do not supply a guessed component price. The service chooses
the latest recorded, nonfuture purchase with an available nonnegative unit price
among compatible mapped products. A zero recorded price is valid; a missing
price is unknown. It never derives a package conversion from a name or size hint.
Legacy batches do not capture a purchase-unit snapshot. If product metadata was
edited after a batch was created or after its recorded purchase timestamp, that price is excluded rather than
reinterpreted under a possibly changed unit. This conservative rule also excludes
prices after unrelated product edits until a later purchase record exists.
Backdating a newly entered batch does not establish its purchase-time unit.

The line exposes the source batch/product IDs, purchase timestamp, store when
recorded, native inventory unit, historical unit price and estimated ingredient
usage cost. An old or expired batch may provide historical price evidence; it
does not thereby become usable inventory. These are historical observations,
not current store quotes.

`known_cost_subtotal_php` sums priced ingredients. `estimated_total_php` is null
unless all included ingredient quantities have usable price evidence. Missing
lines include a reason. The comparison with `budget_goal_php` is also null when
the total or goal is unknown. The member's goal takes precedence over a shared
household goal. Prices follow the application's existing PHP convention; no
exchange rate or currency conversion is inferred.

Costs describe ingredient usage. They do not estimate package rounding, checkout
spend, discounts, delivery, additional purchases or savings. Money is rounded to
centavos with half-up rounding after the decimal calculation. A displayed
subtotal may differ from the sum of individually rounded lines by a centavo.

## Waste interval

`POST /api/v1/meal-insights/waste`

```json
{
  "start": "2026-10-01T00:00:00+08:00",
  "end": "2026-11-01T00:00:00+08:00"
}
```

The interval must have aware timestamps, positive duration and a maximum length
of 366 days. It includes the start and excludes the end.

Only recorded `DISCARDED` and `EXPIRED` inventory ledger events count. An expired
date alone does not create a waste event, and consumed quantities are excluded.
Responses report event count, priced/unpriced counts, known cost subtotal and
total loss only when every event has a recorded price. Null price never means
zero loss.

Quantities are grouped by normalized unit text. The report does not add grams,
milliliters and counts together or assume conversion for unknown units. Cost is
event quantity multiplied by its batch's recorded unit price. It reflects those
stored records, not a claim about replacement value or household savings.
If later product metadata makes the purchase unit ambiguous, the report marks
that event's unit and cost unknown and supplies `purchase_unit_history_unknown`.
It still reports the recorded quantity and event rather than dropping the waste.

The integrated report includes explicit `DISCARDED` leftover events separately
from inventory events. It exposes leftover and linked cooking-session IDs,
counts those events as unpriced, and reports `leftover_cost_not_recorded`.
Leftover `CONSUMED` events are excluded. Consumed raw ingredients are not counted
as waste when the later leftover is discarded. No savings baseline or efficiency
ratio is inferred from these records.

## Verification boundary

The initial inventory-only implementation through `05f0f31` passed 13 focused
PostgreSQL tests and the complete backend CI suite, **516 passed, one optional
historical-file skip**. Both backend and iOS
[passed on that commit](https://github.com/lucifron28/Provision/actions/runs/41066131363).
Those checks cover historical scaling, explicit package factors,
future/missing/zero prices, budget goals, interval boundaries, changed product
units, unit grouping, household isolation and authentication. The subsequent
leftover-waste and planning/privacy integrations require their own final
integrated suite and exact-head CI before they are considered verified.
