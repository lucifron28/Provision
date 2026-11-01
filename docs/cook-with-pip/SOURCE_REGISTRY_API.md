# Recipe source registry and references

This backend records publisher policy, maintainer review history and household
recipe references. It does not search the web, fetch publisher pages, extract
recipes, cache publisher prose or reuse images. Provider credentials do not
automatically enable those operations.

The initial migration adds Panlasang Pinoy, Kawaling Pinoy, Yummy.ph and Ang Sarap
as disabled candidates. Their presence is not an approval, license or current
website-access verification. No real publisher was approved by these tests.

## Maintainer review

Registry changes have no household HTTP write endpoint. A maintainer with backend
database access applies an explicit review file:

```powershell
cd backend
uv run python scripts/review_recipe_source.py source-review.json
```

The reviewed educational TheMealDB API policy is in
`backend/source_reviews/themealdb_educational.json`. Apply it with the same
command from `backend/` using `source_reviews/themealdb_educational.json` as
the argument. It has an expiry and must be reviewed again when it expires. It
does not approve the publishers named by individual meal records.

The JSON document contains `canonical_host`, `publisher_name`, `reviewed_by`,
`policy` and, for updates, `expected_revision`. The initial candidates have
revision 1. The policy supports candidate, approved, suspended and rejected
states; Filipino-priority, reviewed-general and broader-web tiers; exact initial
and redirect host allowlists; link-only, metadata, structured and licensed modes.

Approval requires dated terms evidence, an audit date and a review expiry.
Extraction additionally requires robots and permission evidence and explicit
methods. Full-text permission cannot be inferred from a JSON-LD or link-only
review. Software validation checks that the declaration is complete; a maintainer
must actually perform and record the review. Do not put API keys or personal
allergy data in review files.

Writes use a PostgreSQL transaction advisory lock, optimistic revision checks,
host-overlap checks and an audit snapshot. Source approval expires. Suspension,
rejection and disabled approval cannot be bypassed with a broader-web flag.
Reviewing one alias does not approve all subdomains or `www` variants.

## Household API

All routes below require authorized household membership and use
`Cache-Control: no-store`.

| Method | Route under `/api/v1/recipe-sources` | Behavior |
| --- | --- | --- |
| GET | `/` | Read public registry status, not private review notes or license documents. |
| POST | `/discovery-plan` | Produce an offline query plan; execute nothing and return no search results. |
| POST | `/discover` | Search reviewed sources and optionally the broader web. |
| GET | `/wikibooks` | List currently reviewed Wikibooks recipe keys. |
| POST | `/wikibooks/{key}/preview` | Preview a reviewed Wikibooks recipe with attribution. |
| POST | `/wikibooks/{key}/adapt` | Return a review-only DeepSeek adaptation with source and license details. |
| POST | `/mealdb/discover` | Search a Filipino API listing and return review-required meal links. |
| POST | `/mealdb/{meal_id}/preview` | Read a permitted source recipe and its content digest for review. |
| POST | `/mealdb/{meal_id}/adapt` | Produce a review-only AI preview from a permitted TheMealDB recipe. |
| POST | `/mealdb/{meal_id}/assess` | Assess exact source measures against household stock and food restrictions. |
| GET | `/recipes/{id}/reference` | Read the household recipe's current reference or unlink marker. |
| PUT | `/recipes/{id}/reference` | Attach an external link with recipe/reference revision checks. |
| DELETE | `/recipes/{id}/reference?expected_revision=1` | Unlink and increment the reference revision. |

Use `currently_approved`, not just the stored review-state string, when displaying
an approval badge. A previously approved record may have expired or been disabled.
The registry's `live_fetch_enabled` field refers to general publisher webpage
ingestion, which remains disabled. It does not describe the fixed Wikibooks
page routes or TheMealDB API routes below.

The discovery route requires `MEALDB_ENABLED`, current household consent, and
an approved API source. It retrieves the Filipino listing and filters the entered
query locally; it sends no query text to TheMealDB. Results have not had their
original publishers or allergens reviewed.

The adaptation route is disabled unless both `MEALDB_ENABLED` and
`DEEPSEEK_ENABLED` are set. It requires current household consent, API approval,
and full-text approval for the original publisher. Its optional
`allow_broader_web` boolean defaults to false. The response credits TheMealDB,
links the original source, and labels the output `review_required`; ingredient
measures retain their source text. Explicit decimal amounts with `g`, `kg`,
`ml`, `l`, or `count` and their supported aliases are parsed without conversion;
other measures remain unknown. These values cannot authorize pantry or shopping
changes.
No original publishers are approved by default. Recipe text and AI steps remain
untrusted and require user review, including allergen review.
The backend rejects confirmed source-ingredient conflicts with household
allergies or diet restrictions before calling DeepSeek. An unrecognized or
ambiguous ingredient is not a safety clearance; the preview remains
`review_required` even when no conflict is detected.

Assessment requires the `content_digest` returned by source preview as
`source_digest`, plus `confirmed_recipe_servings` and `requested_servings`; the
former is a user-confirmed basis because TheMealDB does not provide a reliable
servings field. Every source ingredient must have an exact supported measure or
an explicit `confirmed_measures` entry containing its zero-based index, amount,
and supported unit. A confirmation cannot replace an already exact source
measure. Otherwise the endpoint returns `SOURCE_MEASURES_REQUIRE_REVIEW` with
the missing indexes and does not fabricate a quantity. The response preserves
the source text and reports user-confirmed measures separately. Assessment
consumes an API request budget but does not change pantry or shopping records. Known
conflicts remain blocked; all other source recipes remain `review_required`,
even when stock is sufficient.
If the source text, measures, notices, or an approved review revision changes
after preview, assessment returns `SOURCE_RECIPE_CHANGED`. A revoked approval
is rejected; either case requires a new review.

For example, after reviewing an unknown first ingredient, an assessment body is:

```json
{
  "source_digest": "<content_digest from preview>",
  "confirmed_recipe_servings": "2",
  "requested_servings": "1",
  "confirmed_measures": [{"ingredient_index": 0, "amount": "10", "unit": "g"}]
}
```

An offline plan accepts `query`, `include_reviewed_general` and
`allow_broader_web`. Only currently approved Filipino hosts enter the priority
queries. General reviewed hosts require the corresponding explicit request.
An unconstrained query is included only with broader-web permission. Queries
are bounded and domain scope must still be checked after any future search.
This is preparation data, not evidence that a provider ran or found a recipe.

## References and provenance

```json
{
  "expected_recipe_revision": 1,
  "url": "https://publisher.example.com/recipe/example-dish",
  "allow_broader_web": true
}
```

The URL is illustrative. A first reference omits `expected_revision`; updates
and reattachment after unlink require the current reference revision. Optional
`author` metadata is entered by the member and is not independently verified.

Without broader permission, an external reference requires a currently approved
registry host. Broader permission permits unreviewed public links with an
`Other website, verify details` label. It does not authorize a page fetch or
override suspension, expired approval or a removed bound alias. The flag applies
to this reference, not to future provider requests or the whole household.

References remain references. A link to an approved host does not turn household
text into a verified publisher recipe. The recipe keeps `USER_ENTERED`
provenance, and no publisher body or image is copied by the linking operation.
Link timestamps describe app records, not retrieval from a publisher.

Manual recipes must explicitly declare
`content_permission: "OWNED_OR_PERMISSION_GRANTED"` before recommendation.
Old or unspecified declarations remain `NOT_DECLARED` and require review.
This records the member's declaration; it does not itself obtain a publisher's
permission. Do not enter externally owned instructions without the relevant
permission.

An active unavailable reference makes evaluation require review and excludes the
recipe from recommendations. Source preference is applied only after allergy,
dietary, quantity and permission gates. Publisher reputation cannot remove a
conflict or establish product-label safety.

## Wikibooks recipe preview

`GET /api/v1/recipe-sources/wikibooks` lists currently approved keys. Use
`adobo` or `sinigang` with `POST /api/v1/recipe-sources/wikibooks/{key}/preview`.
The route requires `WIKIBOOKS_ENABLED=true`, the source reviews in
`backend/source_reviews/wikibooks_adobo.json` and `wikibooks_sinigang.json`
applied in that order, and current consent from all household members. Apply the
latest database migration first. The fetch policy rejects other Wikibooks pages.
Existing local databases that applied the earlier sinigang review at revision 2
can apply `wikibooks_sinigang_revision3.json` to bind its permission evidence
to the sinigang page. Fresh databases do not need that extra revision.

The response includes source and CC BY-SA 4.0 links, unmodified source
ingredient and preparation text, and `safety: review_required`. It makes no
inventory or shopping changes and does not send the page to DeepSeek. Clients
must show the attribution and license when displaying or sharing the text.

`POST /api/v1/recipe-sources/wikibooks/{key}/adapt` additionally requires
`DEEPSEEK_ENABLED=true` and uses the server-side DeepSeek budget. It checks
known source ingredient conflicts locally before sending source text to the
model. The response labels generated steps as adapted under CC BY-SA 4.0 and
requires review. Unknown ingredients and generated text are not guaranteed
safe, and neither endpoint saves a recipe or modifies inventory or shopping.

## URL and future transport boundary

URL checks require HTTPS, an ASCII public hostname, no user information, no IP
literal and no custom port. Category/search pages, unsafe escapes, local names
and credential-bearing queries are rejected. Canonicalization removes fragments
and common tracking parameters and provides a stable deduplication key.

The redirect validator checks reviewed hosts, hop limits and supplied DNS
addresses. The pinned transport resolves and connects to a validated public
address, verifies the TLS hostname, and checks each redirect. A passing URL
policy test alone does not approve a publisher or its content.
