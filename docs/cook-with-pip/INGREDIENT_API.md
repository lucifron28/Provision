# Ingredient foundation API

All routes below require authentication and authorized household membership.
The ingredient catalog is shared curated vocabulary. Product mappings and
availability are household-scoped. Live AI and web search remain disabled.

| Method | Route under `/api/v1` | Behavior |
| --- | --- | --- |
| GET | `/ingredients/?query=bawang&limit=50` | Search catalog names and aliases. Ambiguous exact aliases remain marked ambiguous even when the limit truncates results. |
| GET | `/ingredients/products/{product_id}/mapping` | Read the current mapping for an accessible product. Missing mapping or inaccessible product returns 404. |
| PUT | `/ingredients/products/{product_id}/mapping` | Record a new mapping version and conversion evidence. |
| POST | `/ingredients/availability` | Compare requested quantities with usable inventory without changing stock or shopping rows. |

## Recording mappings

Use `DIRECT` with `ingredient_id`, `COMPOSITE` with distinct component IDs, or
`UNKNOWN` without ingredient claims. The first mapping omits `expected_version`;
later writes must supply the current version. Stale versions return
`409 MAPPING_VERSION_CONFLICT`. The product row lock serializes mapping updates.
Historical versions remain stored.

`verified` is an explicit member declaration about the mapping. The server
records the authenticated verifier and time. It is not a reviewed allergen label
or a medical safety assertion. `unknown_composition` defaults to true and keeps
availability uncertain until the composition is explicitly reviewed.

Package factors require a verified mapping, a nonblank `source_reference`, and
an ingredient belonging to that mapping. `inventory_unit` must match the product
inventory unit. `ingredient_amount` and `ingredient_unit` describe the ingredient
amount per one inventory unit. A carton containing 12 eggs needs an explicit
factor of 12 count per carton. Neither `package_size` nor a product name supplies
this factor automatically.

## Availability request

```json
{
  "recipe_servings": 2,
  "servings": 4,
  "requirements": [
    {"display_name": "itlog", "amount": 2, "unit": "count", "required": true}
  ]
}
```

Provide exactly one of `ingredient_id` and `display_name` per requirement. Amounts
must be finite and positive. Requirements scale by servings. Duplicate required
lines for one ingredient aggregate before stock comparison. Optional lines use
stock remaining after required demand and do not block the overall result.

The service includes positive batches belonging to the selected household and
excludes recorded expiry dates before the current Asia/Manila date. A missing
expiry date remains visible in `missing_expiry_batch_ids`; it is not a freshness
guarantee. `covered_batch_ids` follow expiry, purchase-time and ID order.

Mass, volume and count conversions stay within their measurement dimension.
Unsupported units or mappings yield `unknown`, with reasons and no invented
shortfall. Known stock yields `full`, `partial` or `missing`. Quantity coverage
does not establish allergy eligibility; that remains a separate safety milestone.

## Verification boundary

Tests cover mapping version conflicts, foreign product IDs, explicit egg-carton
conversion, exact quantity shortfalls, expired stock, unknown mapping/unit states,
alias ambiguity and request validation. Concurrency stress tests, additional
multi-product/composite scenarios, and the final P1 acceptance audit remain
pending. Do not treat this reference as evidence that P1 is complete.
