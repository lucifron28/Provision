# DeepSeek verification

On 2026-10-31 Asia/Shanghai, a bounded authentication check sent one request to
`GET https://api.deepseek.com/models` using the locally configured server key.
The API returned HTTP 200 and two model records. No key or response body was
recorded. This check did not generate a recipe or call search or fetch; token
usage and cost were not reported by this endpoint.

Two bounded original-recipe generation probes used `deepseek-flash` and no
household data. The first returned HTTP 200 but its content was not valid JSON;
its usage and finish reason were not captured. A second request explicitly
disabled thinking and capped output at 512 tokens. It returned HTTP 200 with a
valid JSON object containing title, servings, ingredients and steps. The finish
reason was `stop`; usage was 59 input tokens and 287 output tokens, for 346
total. The response did not provide a monetary cost. These are transport/format
probes, not evidence that the generated ingredients passed application safety
or inventory checks.

A later opt-in Docker smoke test used the application provider and validated
the returned recipe against `AIRecipeProposal`. It passed with model
`deepseek-flash`, 97 input and 224 output tokens (321 total). The API did not
report monetary cost. It sent no household data and did not assess inventory
or allergen safety.

An opt-in request through the generation API passed using an isolated test
household with current consent. The API returned the structured recipe and a
local safety assessment. The request used 125 input and 358 output tokens (483
total); monetary cost was not reported. Only synthetic dish text was sent.
One repeat returned HTTP 502 `INVALID_AI_RECIPE` after the model response
failed strict validation. The response's usage and cost were not captured.
The generation prompt was tightened afterward; model compliance is not
guaranteed, and malformed output remains rejected. A subsequent API smoke
test passed and confirmed no saved recipe or shopping item was created. It used
153 input and 372 output tokens (525 total); cost was not reported.
A later live API test used the PostgreSQL-backed budget in an isolated test
schema. It passed, recorded one budgeted request, and created no recipe or
shopping item. Usage was 153 input and 400 output tokens (553 total); the API
did not report a monetary cost.
A subsequent live API test exercised both global and household counters in an
isolated schema. It passed with 153 input and 422 output tokens (575 total);
monetary cost was not reported.

The opt-in authentication and generation smoke tests subsequently passed in a
Python 3.13/uv Docker container connected to the existing PostgreSQL 18
container: two passed. With the opt-in flag absent, the same two tests were
skipped. These checks sent no household data and did not test source fetching.
The existing recommendation and recipe-shopping focused tests also passed in
the container: 30 passed. These verify the established local flows and do not
yet prove integration with provider-generated recipes or live discovery.

An explicitly opted-in broader-web search smoke test queried `"chicken adobo"
recipe`, requested two metadata-only results, and passed through the DeepSeek
provider. The provider returned a successful 2xx response with these links:

- [Knorr Philippines: Authentic Filipino Chicken Adobo](https://www.knorr.com/ph/r/authentic-filipino-chicken-adobo-recipe-with-deep-garlicky-flavor.html/214369)
- [New York Times Cooking: Chicken Adobo](https://cooking.nytimes.com/recipes/1025489-chicken-adobo#1)

This was one successful search call. The response did not provide token usage or
monetary cost. The [DeepSeek Search and Fetch guide](https://api-docs.deepseek.com/guides/search/)
listed Search at $0.75 per 1,000 successful requests when checked on 2026-10-31,
which gives an estimated $0.00075 for this call before any taxes or other
account-specific charges. This is an estimate, not a billed amount. These
search results are not publisher approvals, and no page was fetched.

The Docker PostgreSQL backend suite passed with 622 tests and three skips before
the final discovery-route and ingredient-unit edits. Their focused follow-up
tests passed separately: 13 discovery tests, and five AI-recipe tests with three
live smoke tests skipped by default. Live search was separately opted in and
passed. The API provider now uses a PostgreSQL counter shared across workers
and restarts, with a global lifetime request cap and a one-minute request
window. Attempts consume the budget before the network call, including failures.
The global counter stores no prompts or household details. A separate counter
enforces a lifetime cap per household and is deleted with that household. The
caps do not reset automatically; an operator must explicitly raise them for
further requests. Downgrading refuses to discard a consumed counter. Other
production rollout gates remain unfinished.
Apply the Alembic migration before enabling the provider; if budget storage is
unavailable, the API rejects the request without contacting DeepSeek.
The budget change passed 637 backend tests with six skips in Docker. A separate
temporary PostgreSQL database passed upgrade, Alembic drift checks, downgrade
to base, and upgrade again. Concurrency and failed-request tests cover the
counter; the downgrade test protects an already consumed budget.
The subsequent household-quota change passed 649 backend tests with six skips,
including concurrent household requests and deletion of a household counter.
Its migration also passed upgrade, downgrade, and drift checks in a temporary
PostgreSQL database.

After the consent change, the full Docker PostgreSQL suite passed with 630
tests and five skips. Focused privacy and generation tests also passed.

The consent API now exposes a notice for submitted dish and search text and
requires policy version `2026-10-31`. Grants made under the earlier notice do
not authorize provider requests. All active household members must grant the
new version; the iOS consent screen still needs to present that notice and
submit the current version.

A separate seeded-household Docker test passed through Cook Now, Almost There,
mocked search of a synthetic approved publisher, and shopping preview and
confirmation. It does not exercise publisher page extraction or live search.

## Fetch policy constraint

The [DeepSeek Fetch API reference](https://api-docs.deepseek.com/api/fetch/)
documents a response containing `title` and Markdown `content`; it does not
document the final URL, redirect chain, or resolved destination IPs. The
project's source policy requires validation of redirects and destination IPs.
Passing an approved starting URL to that provider alone cannot establish that
those checks were performed on subsequent hops. The implementation must
retain the existing fail-closed policy until a compliant way to verify provider
fetch redirects is established. No live publisher page fetch has been performed.

On 2026-10-31, one separately opted-in Docker smoke test fetched an official
TheMealDB lookup endpoint with its educational test key. It returned HTTP 200
and the requested meal ID. No recipe text was sent to DeepSeek or saved. The
new API client is internal; it does not itself authorize use of third-party
recipe content, enforce publisher request limits, or expose an application
route. TheMealDB terms and record provenance are reviewed in the source policy.
The Docker PostgreSQL suite passed with 760 tests and six skips. After the
transport's JSON accept header was added, its focused tests and the new client
tests passed with 65 tests and one live-test skip.
The source policy now distinguishes `api_json` from webpage extraction. An
internal reviewed lookup checks current household consent, API approval, and
permission for the original publisher before returning untrusted content. It
requires a caller-supplied budget; no public route is implemented yet. The
PostgreSQL budget serializes requests across workers, retains a lifetime count,
and honors valid `Retry-After` values. A failed or interrupted request, or an
unusable retry value, leaves the budget paused for operator review; it does not
resume automatically. Review the provider status and any retry deadline before
an operator clears that pause. The subsequent Docker suite passed 768 tests with seven
skips, including the opt-in live checks.
After the durable TheMealDB limiter was added, the full Docker PostgreSQL suite
passed 776 tests with seven skips. An isolated database passed upgrade,
downgrade, re-upgrade, and Alembic drift checks. The local application database
was upgraded to revision `f56c9a214e0b`; the limiter is still not connected to a
public recipe endpoint.

A separate direct HTTPS transport and a Wikibooks robots policy check are under
development. They pin each connection to a validated public IP, check robots
rules before each page request, and require an identifying operator User-Agent.
The focused Docker test run passed 117 tests covering these components and the
fetch authorization boundary. This transport is not wired into a public route,
does not replace DeepSeek Fetch, and does not approve Wikibooks for reuse. A
publisher review, attribution handling, rate limiting, and a permitted live
fetch still need verification before it can be enabled.
The full backend suite subsequently passed in Docker with PostgreSQL: 747
passed and six live tests skipped.

The initial publisher records remain candidates. Publisher approval and
permitted fetching require maintainer review; the authentication check does not
grant either. Integration, opt-in generation/search/fetch smoke tests, and CI
acceptance remain in progress.
