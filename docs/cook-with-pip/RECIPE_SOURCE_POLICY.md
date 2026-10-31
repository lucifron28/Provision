# Cook with Pip — Recipe Source Trust, Search and Content Policy

Status: **POLICY PROPOSAL / PUBLISHER CANDIDATES NOT YET APPROVED FOR FETCH/REUSE** | Reviewed: 2026-10-29 | Owner: Provision maintainers

Parent roadmap: [ROADMAP.md](./ROADMAP.md). Technical implementation: [TECHNICAL_SPEC.md](./TECHNICAL_SPEC.md).

## Goal and rule of precedence

Prioritize **publisher-reviewed Filipino recipe sources** for web discovery, while allowing explicitly labeled results from other websites. "Trusted" means the Provision maintainer reviewed the publisher and that the app follows a documented access/attribution policy; it does **not** mean a particular recipe, nutritional fact, ingredient label, allergen profile or food handling instruction is medically/culinarily guaranteed.

The **default search order**:
1. Household-owned saved/curated recipes already validated for current member allergies, taste/preferences and usable pantry stock.
2. Verified-in-registry Filipino publishers and approved recipe pages. Search constrained to their domains first; prefer Filipino-language synonyms and regional variants.
3. Other maintainer-reviewed recipe publishers when not Filipino-centric, if selected cuisine requires it or too few relevant results.
4. **Broader internet** only when user explicitly enables `Search other websites` or another clearly disclosed setting. Rank independent recipe pages higher than spam/aggregators; require explicit unverified label and extra inspection.
5. If none meet safety/quality thresholds: show clear empty state and user alternatives, never fabricate a recipe source URL or claim an unsafe match is acceptable.

**Hard constraints before rankings:** household authorization, declared allergy restrictions, food-safety/unknown-state rules, license/access policy and explicit discovery mode. Source priority NEVER overrides an allergen restriction or incorrectly declared stock.

## 1. Initial Filipino publisher candidates

The following are **confirmed existing publisher websites with Filipino recipe content**, not automatically approved for automated fetching, copying, image use, or embedding. Maintain a review record per host before enabling.

| Candidate publisher | Canonical host | Reason to prioritize | Proposed tier / initial status |
| --- | --- | --- | --- |
| Panlasang Pinoy | https://panlasangpinoy.com/ | Extensive Philippine dish archive and chicken/pork/vegetable/fish categories | Filipino priority / **pending terms & access review** |
| Kawaling Pinoy | https://www.kawalingpinoy.com/ | Filipino/Asian home cooking; categorized by meal, ingredient, method; publisher describes tested recipes | Filipino priority / **pending terms & access review** |
| Yummy.ph | https://www.yummy.ph/ | Philippine recipe publication with ingredient and serving information | Filipino priority / **pending terms & access review** |
| Ang Sarap | https://www.angsarap.net/ | Filipino dishes including regional and less-common recipes; owner-authored recipe archive | Filipino priority / **pending terms & access review** |

Only use these domains in the `site:` default search after a review has enabled the source. Review redirects and aliases (`www` variants) on a per-site basis. Add/remove hosts through admin config/seed migration, not arbitrary prompt text. The display should name the actual publisher, not "AI recommended website".

On 2026-10-31, the [Kawaling Pinoy terms](https://www.kawalingpinoy.com/privacy-policy/)
were reviewed for the proposed fetch workflow. They request written consent for
use of site content and restrict copying recipes and photos. No written consent
has been supplied, so this source remains a disabled candidate. This review does
not grant fetch, extraction, retention, or reuse rights.

### Open-license candidate: Wikibooks

On 2026-10-31, a manual review located Filipino recipes on
[Wikibooks](https://en.wikibooks.org/wiki/Cookbook:Adobo_Chicken_(Philippine)).
The page says its text is available under Creative Commons Attribution-ShareAlike;
attribution, share-alike, and any additional terms must be reviewed for the
intended use. Images may have separate terms. The
[Wikimedia robot policy](https://wikitech.wikimedia.org/wiki/Robot_policy)
requires an identifiable user agent, compliance with robots.txt, and rate limits.
Its [robots.txt](https://en.wikibooks.org/robots.txt) contains agent-specific
rules. The documented [DeepSeek Fetch API](https://api-docs.deepseek.com/api/fetch/)
does not expose caller-controlled fetch headers, destination IPs, or redirect
history. Therefore this is a candidate for a compliant reviewed fetch adapter,
not approval to send Wikibooks pages through DeepSeek Fetch. Keep the existing
fetch gate closed until those requirements and attribution are verified.

### API candidate: TheMealDB

On 2026-10-31, [TheMealDB API documentation](https://www.themealdb.com/api.php)
was reviewed. The test key is available for development and educational use;
public app-store release requires paid access. The [terms](https://www.themealdb.com/terms_of_use.php)
permit use of content returned by official API endpoints and prohibit scraping
the website. They also place a separate restriction on third-party content.
For example, the API's Filipino eggplant adobo record identifies an external
source and does not provide a Creative Commons confirmation. The source URL
alone is not evidence that the underlying recipe may be copied or sent to a
model. Preserve attribution and notices, and review rights per record before
reusing third-party text or images. This review does not approve the source for
recipe-text extraction or model submission.
Three more Filipino lookup records checked during this review pointed to
Panlasang Pinoy or Kawaling Pinoy and had no Creative Commons confirmation.
TheMealDB's API availability does not override those publishers' restrictions.

The robot policy reviewed on 2026-10-31 applies its limits across Wikimedia
properties, not separately per host. For website requests it sets fewer than
10 concurrent requests and an average below 20 requests per second. It also
requires honoring `Retry-After` on HTTP 429. Provision's direct transport does
not yet enforce a shared limit or a shared retry delay, so do not enable it for
live traffic. The operator's User-Agent must include a way to contact the
operator; a syntactically valid placeholder is not sufficient. These are
additional conditions, not approval to reproduce page content.

Publisher evidence checked 2026-10-29:
- Panlasang Pinoy https://panlasangpinoy.com/categories/recipes/filipino-recipes/
- Kawaling Pinoy https://www.kawalingpinoy.com/about/ and https://www.kawalingpinoy.com/
- Yummy.ph example https://www.yummy.ph/recipe/tuyo-pasta-recipe
- Ang Sarap https://www.angsarap.net/category/filipino/ and https://www.angsarap.net/about/

### Proposed registry (maintainer reviewed, not user-modifiable)

    source_id
    publisher_name
    canonical_host
    allowed_hosts[] / allowed_redirect_hosts[]
    tier: filipino_priority | reviewed_general | broad_web
    review_status: candidate | approved | suspended | rejected
    access: search_link_only | metadata_only | structured_recipe_fetch | licensed_full
    approved_extraction_methods[] // json_ld, api_json, or full_text, with separate permission
    robots_reviewed_at
    terms_reviewed_at
    owner_contact/license_reference
    region/cuisine tags[]
    last_audited_at
    disabled_reason
    source_reliability_notes

**Never conflate approval for indexing/linking with permission to reproduce recipe text or photos.** If publisher terms do not authorize automated fetch/reuse, use search result metadata and link out to original recipe; request permission or a licensed feed for deeper integration. Cached output expiry and purging must respect source policy. Save source metadata, user adjustments, link and citation even in link-only mode.

## 2. Web discovery algorithm

### Query construction

Use server-side bounded query templates, not arbitrary user model prompts. Query examples:
- `"sinigang na baboy" Filipino recipe site:panlasangpinoy.com OR site:kawalingpinoy.com`
- `"tinolang manok" site:panlasangpinoy.com OR site:kawalingpinoy.com`
- `"ginisang monggo" site:yummy.ph OR site:angsarap.net`
- `"tortang talong" eggplant Filipino recipe` (broader internet **only with permission**)

Support Filipino/English aliases (patis/fish sauce, luya/ginger, pechay/bok choy, sitaw/yardlong beans), meal categories and region cues. Keep DeepSeek's current `query` length bound (docs currently 1–128 Unicode chars), and partition site clauses into multiple requests when necessary.

### Provider API (server only)

As checked 2026-10-29, DeepSeek documents:
- `POST https://api.deepseek.com/v1/tools/search` for structured web search
- `POST https://api.deepseek.com/v1/tools/fetch` for a page as Markdown
- Search operators include `site:`, `-site:`, quoted terms, `OR`, `lang:`.

References: https://api-docs.deepseek.com/guides/search/ and https://api-docs.deepseek.com/api/search/. Verify capability, availability, authentication, pricing and request schema again during implementation; maintain an adapter so provider changes don't break FastAPI.

Backend MUST:
- Search prioritized hosts independently and apply **post-search domain validation**; model/search filters alone are not a security boundary.
- Normalize canonical URLs; follow redirects under explicit allowed-host policy, HTTPS only, reject IP literals and local/private/loopback/metadata endpoints, restrict DNS rebinding, response size, content type and fetch duration.
- Prefer actual `Recipe` pages with publisher and recipe-specific title; reject tag/category pages disguised as single recipes.
- Validate source permissions before Fetch; if disallowed, return link-only result rather than attempting scraping.
- Parse `schema.org/Recipe` / JSON-LD fields if accessible/permitted: `name`, `author`, `recipeIngredient`, `recipeInstructions`, `recipeCuisine`, `recipeCategory`, `recipeYield`, `prepTime`, `cookTime`; map into typed DTO with provenance and quality checks.
- Deduplicate canonical URL, authorship, translated variants; collect retrieved_at, content/version hash when legally allowed.
- Enforce provider rate limit, per-household budget, caching, timeouts, content sanitization and safe logs.
- Keep retrieved content as **untrusted data**. Ignore instructions in web pages directing the agent to change model policies, leak keys, make purchases, query other accounts, or modify endpoints.
- Preserve source-link-out when details/instructions may not be stored or displayed; no image hotlinking without rights.
- When a page lacks details or conflicts with user constraints, show `not enough verified ingredient information` rather than assuming.

## 3. Source-tier ranking and UI labeling

**First:** allergy and dietary hard constraints, valid recipe metadata, household scope, source usage rights. Then apply relevance and trust scoring.

| Tier | Eligibility | UI disclosure |
| --- | --- | --- |
| `filipino_priority` | Explicitly approved publisher + approved use mode + recipe page passes validation | "Preferred Filipino source" + publisher + link |
| `reviewed_general` | Manually reviewed publisher not necessarily PH-centric, approved use mode | "Reviewed recipe source" + publisher + link |
| `broad_web` | User opted in, provenance captured, basic quality/safety checks passed, not maintainer-approved | "Other website · verify details" + publisher/domain + link |
| `ai_original` | Created by DeepSeek, no retrieved publisher recipe | "AI-created recipe · review ingredients" (NO source attribution claim) |
| `ai_adapted` | AI changed a publisher-linked recipe | "AI-adapted from [publisher]" + original link; clearly separate adapted ingredients from source |

Source approval is not a rating for food-allergy safety. Never show "allergen-free guaranteed" or "verified safe". Prefer the published recipe **before** a model adaptation if it already meets constraints. When adaptation changes allergens/ingredients, run all checks on the final version and retain exact labels used.

Quality gates:
- Recognizable recipe dish and publisher.
- Coherent ingredient list, amounts/servings and instructions (or link-only mode).
- No obvious SEO affiliate-only page/roundup masquerading as recipe.
- No recipe URL hallucination, keyword-stuffed content, duplicated scraped recipe farms.
- Source timestamp and recipe version available when possible.
- User preferences influence ranking only after hard restrictions.
- Verified matching of packaged ingredients and regional aliases; unverified ingredients remain marked.

## 4. Filter/category system

Persist categories independently of product catalog `category` (pantry product category != recipe category). Suggested normalized facets:

| Facet | Seed values |
| --- | --- |
| Cuisine | Filipino (default), other Asian, Mediterranean, Western, other; user configurable |
| Philippine regional cuisine | Tagalog, Ilocano, Kapampangan, Bicolano, Visayan, Mindanao, others, unknown; avoid unsourced regional claims |
| Course | breakfast, lunch, dinner, merienda, snack, dessert, beverage |
| Dish type | ulam/main, sabaw, stew, soup, vegetable, rice/silog, pancit/noodles, salad, baked, grilled, steamed, fried |
| Main ingredient | chicken, pork, beef, fish, shrimp, tofu, egg, rice, noodles, legumes, vegetables, fruits |
| Preparation time | ≤15, ≤30, ≤60, >60 minutes, unknown |
| Difficulty | beginner, intermediate, advanced, unknown |
| Equipment | stovetop, oven, microwave, air fryer, pressure cooker, no-cook |
| Taste | mild, spicy, sour, sweet, savory; labels must reflect actual recipe evidence |
| Dietary | vegetarian, vegan, no-pork, halal-preference, low-spice, dairy avoidance, etc; **validate ingredients**, do not infer religious/medical certification |
| Planning | pantry-only, almost-there, budget-friendly, leftover-friendly, expiring-soon prioritization |

Categories can be many-to-many; one recipe may be Filipino, Bicolano, lunch, soup, spicy, seafood. Users should have searchable filter chips + clear filters. Avoid presenting mutually exclusive categories when multiple apply. Do not infer "halal certified" from no-pork ingredients alone.

## 5. Allergies, labels and hard stops

Recipe websites are **not** reliable evidence that a branded pantry item contains no allergens. Source trust and recipe safety are separate.

- Accept declared allergens including at least common milk, egg, fish, crustacean shellfish, tree nut, peanut, wheat, soy, sesame and custom terms. Keep explicit `not provided` vs `none declared`. Require user confirmation before using an allergy-sensitive recommendation.
- Track ingredients/components/derivatives; Filipino sauces and pastes deserve particular scrutiny (fish sauce/patis, bagoong, oyster sauce, peanut-based kare-kare, noodles/soy sauce, dairy-based desserts). Confirm specific packaged label, manufacturer and handling; no safe assumptions from a brand name.
- Cross-contact is distinct from intentional ingredients. `Possibly contains` and unknown kitchen environment should trigger manual verification, not a confident clearance.
- Hard conflict = ineligible for the selected diners. Unknown composite ingredient/uncertain label = review required. Allergy restrictions are NOT overridden by preferences, model output, or website tags.
- Show clear readable warning and route to actual product packaging/source for verification. Log policy reason codes (without recording sensitive raw user profiles).
- DeepSeek may suggest substitutions; all substitutions re-run the same checks and require user selection/confirmation.
- Don't supply nutritional/medical assurance. Display a respectful advisory to verify labels, ingredients and cross-contact in food preparation.

Reference guidance: https://www.fda.gov/food/nutrition-food-labeling-and-critical-foods/food-allergies (US regulatory categories are a starting reference, not exhaustive/global authority). Keep Philippine labeling guidance under review before launch.

## 6. Content and legal policy

- A search result's existence, public URL, SEO markup, or permissive robots.txt is **not** a blanket license to reproduce article text, photographs, or editorial directions.
- Record permission and usage mode for every publisher. Maintain a simple publisher-contact/license log and review after terms change.
- Use attribution with source name, author if present, canonical URL, timestamp and "adapted" tag. For link-only sources display metadata and original link, not a copied full article.
- If allowed to store structured ingredient data, retain minimum necessary and obey cache/purge terms. Preserve actual publisher instructions via link when full reuse isn't granted.
- No forged source, image, review score, or attribution. Avoid presenting model-edited instructions as original publisher prose. Dedup reposts and cross-posted syndications.
- Server-side robots and Terms checks, fetch rate limits, ethical crawling, origin security; no unauthorized bypass of anti-bot/login/payment restrictions.
- User-added recipes: explicit ownership/permission state; don't automatically redistribute externally sourced instructions.
- Legal references may vary by jurisdiction; obtain appropriate advice before commercial launch.

## 7. Review process / owner checklist

**For each publisher before enabling:**
- [ ] Confirm legal publisher domain and contact.
- [ ] Verify the content really contains recipe pages, with coherent authorship and dates.
- [ ] Review current Terms, robots, rate limits and any API/licensing options; record URL and date.
- [ ] Decide access mode: search/link only, metadata, structured-fetch, or explicit full-content license.
- [ ] Test canonical hostname and allowed redirects, blocked/private URLs, content errors.
- [ ] Verify whether photos may be displayed; if uncertain, do not reuse.
- [ ] Test 5 representative recipes (including common allergens and regional dishes) with typed ingredient extraction, reasonable servings and source links.
- [ ] Add approved source ID, access policy and last_reviewed_at to registry; keep disabled until complete.
- [ ] Re-review periodically and on failure, complaints, robots/terms change.

**System acceptance tests:**
- [ ] Filipino-priority query yields approved-host sources before broad sources; results preserve title/author/link and correct tier.
- [ ] Source unavailable -> fallback to another approved host, not fabricated URL.
- [ ] Broad web disabled -> no nonapproved website fetch.
- [ ] Broad web enabled -> show explicit "Other website" badge and provenance; safety still enforced.
- [ ] Malicious instructions in page body do not change system behavior.
- [ ] If license/robots disallows fetch -> metadata/link-only, no stored body/image.
- [ ] If meal contains allergen or ingredient unknown -> block/review gate regardless of trusted source or model confidence.
- [ ] All searches have timeouts, limits and source/usage logging without leaking personal household info.

## 8. References and maintenance

- DeepSeek Search and Fetch: https://api-docs.deepseek.com/guides/search/
- DeepSeek Search API: https://api-docs.deepseek.com/api/search/
- Recipe structured data: https://developers.google.com/search/docs/appearance/structured-data/recipe
- Publisher websites: https://panlasangpinoy.com/ | https://www.kawalingpinoy.com/ | https://www.yummy.ph/ | https://www.angsarap.net/
- Food allergen safety considerations: https://www.fda.gov/food/nutrition-food-labeling-and-critical-foods/food-allergies

**Maintainer note:** When approving new sources or changing tiers, update this document and checked registry records in the same PR. Verification is a manual review state, not an automatic internet truthfulness judgment.
