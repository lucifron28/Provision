# Reviewed product labels

These endpoints record a household member's explicit review of an actual product
label. They do not fetch a URL, certify a product or guarantee safety. A quantity
mapping alone remains insufficient for allergen eligibility.

All routes require authorized household membership and use `Cache-Control:
no-store`. Reviews are shared product records in that household. The server
records the authenticated reviewer and timestamp.

| Method | Route under `/api/v1/food-safety` | Behavior |
| --- | --- | --- |
| GET | `/products/{product_id}/label` | Read the latest review or revocation, including whether it still matches the product and mapping. Returns 404 when no record exists. |
| PUT | `/products/{product_id}/label` | Append an explicit review against product and mapping versions. |
| DELETE | `/products/{product_id}/label?expected_revision=1` | Revoke the current review. |

## Review request

Read the product and its current ingredient mapping first. The mapping must be
verified, have known composition and contain direct or composite ingredient
targets. Copy the product's `updated_at` and mapping's `version` into the request.

```json
{
  "expected_product_updated_at": "2026-10-30T10:00:00Z",
  "expected_mapping_version": 1,
  "reviewed": true,
  "composition_known": true,
  "declared_allergens": ["soy"],
  "possible_allergens": ["wheat"],
  "custom_allergens": [],
  "source_reference": "Actual package ingredient and allergen declaration"
}
```

The timestamp above is illustrative. Use the actual product response.
`reviewed: true` is required. `composition_known` defaults to false. Declared and
possible allergens use the same nine codes as food profiles; custom declarations
accept up to 180 characters each. Duplicates, overlapping declared/possible codes,
blank sources, client-supplied reviewer IDs and household IDs are rejected.
Do not put personal medical notes into shared label source references.

The first review omits `expected_revision`. Later writes supply the current
review revision. A stale review receives `409 PRODUCT_LABEL_REVISION_CONFLICT`.
Changed product data receives `409 PRODUCT_CHANGED`; a changed mapping receives
`409 MAPPING_VERSION_CONFLICT`. Fetch the current context and review it again.
Do not automatically attach an old declaration to new product data.

## Staleness and revocation

Each review stores a server-computed fingerprint of product details and its
update timestamp, plus the exact mapping version. A later product edit makes
the old review stale, including when the edited field is changed back. Mapping
changes also invalidate the review. `current_for_product` reports this binding;
it does not mean composition is complete or that a meal is eligible.

Household and product row locks serialize writes with membership and mapping
changes. Every successful write appends a revision. Revocation also appends a
revision, records who revoked it and when, and removes the review from
consideration. GET then reports `revoked: true`. Read that revision before
recording a fresh review and supply it as `expected_revision`. Old revision
tokens and an old first-write request cannot restore a revoked review.

## Safety integration

The evaluator checks labels for every batch counted toward each requirement.
Declared conflicts block; possible conflicts and unknown composition require
review. It also inspects a composite product's mapped components. A rice amount
from a rice-and-pork product cannot bypass a no-pork restriction.

An exact, complete review can resolve a generic possible association only when
the submitted requirement is fully covered by reviewed stock. A partial amount
still needs review for the unfulfilled portion. A label cannot remove confirmed
conceptual conflicts, unresolved custom declarations, cross-contact concerns or
missing diner information. Separate certification checks such as halal and
gluten-free remain conservative when evidence is missing.

The recommendation and cooking integrations must preserve these gates. Their
implementation remains separate work. SwiftUI label-review screens, stale-form
handling and physical-package acceptance checks remain Mac/device tasks.
