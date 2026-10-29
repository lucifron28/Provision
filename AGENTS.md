# Provision — Agent Entry Point

Before changing code, read `README.md` and these three documents in order:

1. [Cook with Pip roadmap and phased TODOs](docs/cook-with-pip/ROADMAP.md)
2. [Cook with Pip technical implementation specification](docs/cook-with-pip/TECHNICAL_SPEC.md)
3. [Filipino-first recipe source governance and trust registry](docs/cook-with-pip/RECIPE_SOURCE_POLICY.md)

**Current status:** Cook with Pip is planned, NOT implemented. Existing Home Chef Pip hints are heuristic, not DeepSeek recipe results. Do not mark milestones done without code, tests, CI, and acceptance evidence.

## How to execute the roadmap

- Begin with P0 household/user data isolation and privacy; do not send pantry data or allergy profiles to DeepSeek before scoping and consent are implemented.
- Work in dependency order, one independently tested, reviewable milestone at a time. Avoid giant unreviewable implementation passes.
- Use DeepSeek only through the FastAPI backend. Verify its current API docs at implementation time; API keys must stay server-side.
- Filipino recipe publishers have **candidate** status until permissions/source review is completed. Prefer approved Filipino publishers; search other sites only with explicit broader-web permission. Respect source attribution, access policy and prompt-injection boundaries.
- Build ingredient quantity, allergy guardrails and shopping deduplication deterministically. Generative output never authorizes database writes.
- Preserve scanner lifecycle, pending intake recovery, FEFO, shopping manual edits, existing Pip branding and native SwiftUI design. Do not mutate inventory while previewing a recipe.
- Shopping list changes require explicit user confirmation, optimistic revision check, transactional atomicity, deduplication and idempotency; never fabricate ingredient conversions.
- Prefer official documentation and existing repo patterns. Record architecture choices, schema migrations, and meaningful unit/integration/UI tests in the same changeset.
- Run `cd backend && uv run pytest` and the applicable Xcode XCTest suite; after push, verify required GitHub Actions. Don't rewrite tests to accommodate incorrect behavior. If device or live provider verification is missing, report it.
- Update the roadmap checkbox + commit SHA/CI evidence upon true completion; keep source review records current.
- Never merge feature work into `main` without explicit approval.

**Requested future capabilities:** Cook Now, Almost There, Discover with DeepSeek Search/Fetch, Filipino/regional cuisine categories, food preferences and allergens, source-ranked recommendations, shopping-list shortages/deduplication, saved recipes, cooking mode, weekly plans, leftovers, budget/waste insights and scoped household profiles.
