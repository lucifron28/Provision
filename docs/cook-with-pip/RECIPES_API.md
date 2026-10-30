# Household recipes and recommendations

These routes manage household-entered recipes and deterministic pantry
recommendations. They use no AI provider or web search. Manual entries have
`USER_ENTERED` provenance. They are not verified publisher recipes. Publisher
ingestion, source approval and link-out permissions remain separate work.

All routes require authentication and selected household membership. Recipe
responses use `Cache-Control: no-store`. Household members can read and edit
shared recipes. Saved bookmarks, favorites, serving overrides and notes belong
to the authenticated member and are private.

| Method | Route under `/api/v1/recipes` | Behavior |
| --- | --- | --- |
| GET | `/?query=rice&limit=50&offset=0` | List active household recipes. Search treats wildcard characters literally. |
| POST | `/` | Create a user-entered recipe and revision 1. |
| GET | `/{id}` | Read the current recipe, including archive state. |
| PUT | `/{id}` | Replace the recipe using `expected_revision`. |
| DELETE | `/{id}?expected_revision=1` | Archive the recipe and append a revision. |
| GET | `/{id}/versions/{revision}` | Read the immutable recipe snapshot at that revision. |
| POST | `/{id}/evaluate` | Evaluate stored ingredients against current diners, labels and stock. |
| GET | `/saved` | List your active bookmarks. |
| GET | `/{id}/saved` | Read your bookmark or unsave revision marker. |
| PUT | `/{id}/saved` | Save a specific current recipe revision with private preferences. |
| DELETE | `/{id}/saved?expected_revision=1` | Unsave and erase private notes and overrides. |
| POST | `/recommendations` | Filter and rank eligible stored recipes. |

## Recipe data and revisions

```json
{
  "title": "My garlic rice",
  "cuisine": "Filipino",
  "content_permission": "OWNED_OR_PERMISSION_GRANTED",
  "ph_regions": ["region_unknown"],
  "course_categories": ["breakfast"],
  "dish_types": ["rice"],
  "servings": 2,
  "prep_minutes": 5,
  "cook_minutes": 10,
  "ingredients": [
    {"display_name": "bigas", "amount": 100, "unit": "g"},
    {"display_name": "bawang", "amount": 5, "unit": "g", "preparation": "chopped"}
  ],
  "instructions": ["Prepare the measured ingredients.", "Cook the rice with garlic until done."]
}
```

The example is user-entered content, not a publisher attribution.
Content permission is an explicit member declaration. Its default is
`NOT_DECLARED`, which requires review before recommendation. See the
[source registry contract](SOURCE_REGISTRY_API.md) for link attribution and
maintainer approvals. Regional
classification is supplied by the author. `region_unknown` is the default and
cannot be combined with a claimed region. Supported regional labels are Ilocano,
Bicolano, Kapampangan, Tagalog, Visayan and Mindanao. Course and dish enums,
equipment, difficulty and spice level are defined in OpenAPI.

Ingredients accept exactly one canonical ID or display name. Recognized Filipino
aliases resolve to canonical IDs. Unresolved names remain explicit and require
safety review. Amounts must be positive finite decimals; units are not guessed.
Unsupported conversions remain unknown in evaluation. Optional ingredients and
explicit substitution proposals are retained. Recipe steps and fields have
length and count limits; clients cannot supply household ownership, publisher
verification or source URLs through this manual-entry route.

An update requires the current revision, otherwise it returns
`409 RECIPE_REVISION_CONFLICT`. Household and recipe row locks serialize writes
and membership changes. Each update retains the previous snapshot. Archive
removes the recipe from active browsing and recommendations while preserving
history. Archived recipes cannot be overwritten through PUT.

## Evaluation and private bookmarks

An evaluation provides `expected_recipe_revision`, desired `servings`, optional
`diner_user_ids` and optional indexed `substitutions`. The backend loads the
stored recipe requirements. Client-supplied shortages or replacement requirement
lists are rejected. Every substitution re-runs full meal safety and availability.
Replacement amounts describe the base recipe servings and scale with the meal.
`include_optional` defaults to true. Explicitly setting it to false omits optional
ingredients before safety evaluation. Substitution indexes always refer to the
original stored recipe; `included_requirement_indexes` maps the resulting meal
back to those indexes. An omitted ingredient cannot be used as evidence of a
conflict in the chosen meal.
Viewing or evaluating a recipe never consumes inventory.

Saving requires `expected_recipe_revision` and, after the first save, the current
bookmark `expected_revision`. Optional values are `favorite`, `servings` and
`notes`. A bookmark pins its chosen recipe revision; later shared edits do not
silently replace that selection. Unsave increments the bookmark revision and
erases its private values. GET returns that marker for a later explicit save.
An old first-save request cannot restore an unsaved bookmark.

Account export includes selected-household recipes and only the requesting
member's bookmarks. Account or membership deletion removes private bookmarks
through their membership foreign key. Shared recipes remain household history.

## Deterministic recommendations

```json
{
  "mode": "cook_now",
  "priority": "pantry_first",
  "servings": 2,
  "limit": 20
}
```

Each candidate passes the current server-side safety policy before ranking.
Blocked and review-required meals are excluded. Required quantities with unknown
conversion are also excluded. Responses report separate exclusion counts without
revealing another diner's notes or severity.

`cook_now` requires full required-ingredient coverage. `almost_there` requires
between one and `max_missing_ingredients` shortages. `all` includes eligible
recipes regardless of missing known quantities. Optional lines do not determine
the shortage count. All submitted optional ingredients still receive safety
checks.

Default ordering compares required-ingredient coverage fractions, shortage count,
counted batches inside the expiry window, cuisine preference, disliked ingredients,
cooking time, title and ID. It does not add quantities across different units.
`quick` prioritizes total time; `preferred_cuisine` prioritizes cuisine match.
The expiry window is configurable. Expired batches are excluded by availability;
missing expiry remains visible in the evaluation warnings.

Filters include query, cuisine, Philippine region, course, maximum total minutes
and available equipment. Time and equipment preferences can further restrict
candidates. Requested servings default to the requesting member's saved serving
count. Broader-web permission is unrelated to browsing household-entered recipes;
this endpoint performs no web discovery.

Evaluation uses an explicit candidate window ordered by recipe ID. The default
window is 100 and the maximum is 200. `candidate_offset` advances it and
`has_more_candidates` reports remaining candidates. Ranking applies within that
window. The output contains ingredient coverage, missing count, expiry count and
current safety/availability results, not fabricated AI confidence or savings.

Trusted publisher ingestion, smart shopping confirmation, plans, cooking,
leftovers and SwiftUI screens remain separate milestones.
