# Food profiles API

Profiles store food preferences and explicit allergy declarations. They do not
yet establish recipe eligibility. The allergen graph, dietary checks and
substitution validation remain separate work. Live provider calls remain disabled.

All routes require authentication and an authorized household context. Responses
use `Cache-Control: no-store`. A member can access their own private profile.
Household profiles are visible to members and editable only by owners. There is
no API for reading another member's private declarations or notes.

| Method | Route under `/api/v1/food-profiles` | Behavior |
| --- | --- | --- |
| GET | `/me` | Read your member profile in the selected household. |
| PUT | `/me` | Replace your preferences and allergy declarations. |
| DELETE | `/me?expected_revision=1` | Remove declarations and reset preferences. |
| GET | `/household` | Read the shared household profile. |
| PUT | `/household` | Replace the shared profile, requires an owner. |
| DELETE | `/household?expected_revision=1` | Reset the shared profile, requires an owner. |

## Explicit allergy state

A profile starts with `NOT_PROVIDED`, an empty declarations list and a null
revision. A write must choose `NOT_PROVIDED`, `NONE_DECLARED` or `DECLARED`.
Only `DECLARED` accepts declarations, and it requires at least one. Dislikes and
diet patterns do not become allergy declarations.

```json
{
  "allergy_status": "DECLARED",
  "allergies": [
    {"allergen_code": "fish", "cross_contact_concern": true}
  ],
  "preferences": {
    "preferred_cuisines": ["Filipino"],
    "preferred_regions": ["Bicol"],
    "diet_patterns": ["no_pork"],
    "servings": "2.5",
    "meal_budget_php": "150.50"
  }
}
```

Each declaration provides either `allergen_code` or `custom_text`. Canonical codes
are `milk`, `egg`, `fish`, `crustacean_shellfish`, `tree_nuts`, `peanuts`, `wheat`,
`soy` and `sesame`. This list is not exhaustive. Custom declarations can record
other allergens or sensitivities. Optional severity and notes record what the
member supplies. They do not constitute a diagnosis.

Preferences also accept dislikes, active canonical ingredient exclusions, heat
tolerance, equipment, maximum cooking minutes and preferred language. Unknown
fields, duplicate selections and unsupported diet enums are rejected. Decimal
values must be finite and fit the documented schema bounds in OpenAPI.

## Revisions and privacy

The first write omits `expected_revision`. Later writes must provide the revision
returned by GET or PUT. A stale request receives
`409 FOOD_PROFILE_REVISION_CONFLICT`. A household row lock serializes writes and
membership changes; the server rechecks membership and owner permission after
acquiring that lock.

DELETE removes allergy rows and resets preferences to defaults and allergy state
to `NOT_PROVIDED`. It retains scope and an incremented revision so a stale update
cannot restore deleted declarations. GET returns that new revision for the next
write. Deleting an account or its membership removes its private profile through
the membership foreign key. Shared household settings remain shared records.

The existing account export includes only the requesting member's profile and
the selected household's shared profile. It omits other members' private profiles.
Database storage relies on deployment disk encryption and access controls; these
fields do not have application-level encryption. Do not log declaration bodies.

SwiftUI editing, cache isolation and accessibility checks remain in the Mac
handoff. No mobile interface is implemented by these backend routes.
