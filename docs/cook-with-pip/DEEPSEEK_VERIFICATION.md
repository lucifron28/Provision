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

This was one search call. The response did not provide token usage or monetary
cost. These search results are not publisher approvals, and no page was fetched.

The Docker PostgreSQL backend suite passed with 622 tests and three skips before
the final discovery-route and ingredient-unit edits. Their focused follow-up
tests passed separately: 13 discovery tests, and five AI-recipe tests with three
live smoke tests skipped by default. Live search was separately opted in and
passed. The API provider now uses a PostgreSQL counter shared across workers
and restarts, with a global lifetime request cap and a one-minute request
window. Attempts consume the budget before the network call, including failures.
The counter stores no prompts or household details. Per-household quotas and
the remaining production rollout gates are still unfinished. The lifetime cap
does not reset automatically; an operator must explicitly raise it for further
requests. Downgrading the migration refuses to discard a consumed counter.
Apply the Alembic migration before enabling the provider; if budget storage is
unavailable, the API rejects the request without contacting DeepSeek.
The budget change passed 637 backend tests with six skips in Docker. A separate
temporary PostgreSQL database passed upgrade, Alembic drift checks, downgrade
to base, and upgrade again. Concurrency and failed-request tests cover the
counter; the downgrade test protects an already consumed budget.

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
fetch redirects is established. No live publisher fetch has been performed.

The initial publisher records remain candidates. Publisher approval and
permitted fetching require maintainer review; the authentication check does not
grant either. Integration, opt-in generation/search/fetch smoke tests, and CI
acceptance remain in progress.
