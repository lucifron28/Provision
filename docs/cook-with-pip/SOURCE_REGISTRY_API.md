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
| GET | `/recipes/{id}/reference` | Read the household recipe's current reference or unlink marker. |
| PUT | `/recipes/{id}/reference` | Attach an external link with recipe/reference revision checks. |
| DELETE | `/recipes/{id}/reference?expected_revision=1` | Unlink and increment the reference revision. |

Use `currently_approved`, not just the stored review-state string, when displaying
an approval badge. A previously approved record may have expired or been disabled.
Every response reports live fetching as disabled.

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

## URL and future transport boundary

URL checks require HTTPS, an ASCII public hostname, no user information, no IP
literal and no custom port. Category/search pages, unsafe escapes, local names
and credential-bearing queries are rejected. Canonicalization removes fragments
and common tracking parameters and provides a stable deduplication key.

The offline redirect validator checks exact reviewed initial/redirect hosts, hop
limits and every supplied DNS address. Private, special-use and transition
addresses are denied. It opens no sockets and performs no DNS lookup. A future
transport must resolve safely, pin the validated destination addresses, preserve
TLS hostname validation and validate every redirect. These pure tests are not
an end-to-end verification of a live fetch implementation.

Publisher terms/robots review, permission acquisition, live provider adapters,
content extraction, cache/purge enforcement and actual network verification
remain deferred. Do not infer any of those from a passing URL-policy test.
