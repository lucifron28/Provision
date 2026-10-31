# Food safety evaluation

`POST /api/v1/food-safety/evaluate` requires authentication and selected household
membership. It evaluates structured ingredients against server-stored profiles,
then returns ingredient decisions and read-only quantity availability. It does
not consume stock or change shopping, profiles or recipes. Responses use
`Cache-Control: no-store`. No provider is involved.

```json
{
  "recipe_servings": 2,
  "servings": 4,
  "requirements": [
    {"display_name": "itlog", "amount": 2, "unit": "count"}
  ]
}
```

## Diners and decisions

Omitting `diner_user_ids` selects all active household members. An explicit list
selects only those diners, must be nonempty and must contain distinct active
members of the same household. The service combines their declarations with
shared household declarations and exclusions. A shared `NONE_DECLARED` profile
does not override missing personal information.

- `blocked` means a confirmed conflict or hard ingredient/diet restriction.
- `review_required` means missing allergy information, ambiguous identity,
  possible associations, unreviewed derivatives, cross-contact concerns, unknown
  composition, or missing product-label evidence.
- `eligible` means no known conflict under the recorded context. It is not a
  safety guarantee or a substitute for checking actual labels and preparation.

Reasons are general policy codes. Responses omit members' notes, severity and
the identity of the member whose declaration caused a conflict. Dislikes affect
future taste ranking, not hard allergy decisions. Ingredient exclusions remain
hard restrictions. Gluten-free and halal preferences need label or certification
review when the available data cannot establish suitability.

Every submitted ingredient is considered present, including optional lines.
Omit an optional ingredient from the request when explicitly leaving it out of
the meal. Quantity availability still treats optional lines separately.

## Derivatives and evidence

`ingredient_allergens` records direct, derivative, possible and unknown
associations with evidence references and review timestamps.
`ingredient_derivatives` records reviewed parent relationships. The evaluator
follows these relationships with cycle and traversal bounds. An unreviewed edge
can require review but cannot establish a confirmed conflict by itself.

The migration adds nine canonical allergen identities and a small derivative
catalog. References include the [FDA's allergen overview](https://www.fda.gov/food/buy-store-serve-safe-food/food-allergies-what-you-need-know),
the [Minnesota Department of Agriculture's ingredient reference](https://www.mda.state.mn.us/food-feed/food-ingredients-may-cause-allergies),
and this repository's Filipino derivative policy. These support conceptual
associations, not individual package clearance. The nine groups are not
exhaustive. Custom declarations resolve against the ingredient catalog; unresolved
custom declarations require review.

This curated graph is global and has no household write API. A product quantity
mapping, confidence score or brand name does not establish allergen-label review.
When stock is counted toward a requirement, the evaluator checks its
[reviewed product labels](PRODUCT_LABELS_API.md). Missing or stale records add
`product_allergen_label_not_reviewed`. A complete current review can resolve
generic possible associations for fully covered quantities. Confirmed conceptual
conflicts remain blocked. Composite product components are checked as well.

## Substitutions

An optional `substitutions` array replaces a distinct zero-based requirement
index with an explicit ingredient, amount and unit.

```json
{
  "requirement_index": 0,
  "replacement": {"display_name": "tokwa", "amount": 100, "unit": "g"}
}
```

The server preserves the original required/optional flag and evaluates the full
resulting list again. It recalculates quantity availability using the replacement
amounts. It does not infer a replacement ratio, invent a package size, or let a
caller supply safety verdicts or an `ignore_allergens` switch. This endpoint
checks an explicit proposal; it does not generate substitution suggestions.

## Remaining integration

Recipe persistence and recommendation ranking must call this policy before
offering candidates as suitable. Shopping confirmation must recheck the stored
recipe, diner/profile revisions, inventory and shopping state. Neither integration
is completed by this endpoint. The existing quantity API remains a quantity-only
comparison. SwiftUI editing and warning presentation remain Mac-dependent work.
