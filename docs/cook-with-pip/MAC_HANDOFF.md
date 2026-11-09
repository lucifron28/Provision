# Mac-dependent Cook with Pip work

Status: Cook with Pip iOS milestones 1–3 were merged to `main` on 2026-11-10 via [PR #4](https://github.com/lucifron28/Provision/pull/4) (merge `d4d5105`). This document separates verified hosted CI from **remaining** Mac and physical-device acceptance. Preserve scanner behavior, the five-tab navigation, consent and publisher policies.

## Verified hosted CI and existing iOS workflows

- Tested feature head `465a3a8`: [push workflow](https://github.com/lucifron28/Provision/actions/runs/42696338465) and [PR workflow](https://github.com/lucifron28/Provision/actions/runs/42696352926) passed on GitHub-hosted macOS/iPhone 17 simulator; **38 iOS unit tests + 12 UI tests** and **938 backend tests passed, 12 skipped**.
- Home entry, Cook Now, Almost There, My Recipes, recipe details, preferences, allergy declarations, substitutions and product-label review are implemented with household-scoped API calls.
- Shopping preview requires explicit selection and confirmation, exact decimals, server revisions and Keychain-backed pending idempotent retries; test coverage includes relaunch recovery and corrupt/unavailable Keychain records.
- `cook-with-pip-ios-screenshots` contains 38 named **synthetic-fixture** simulator screenshots plus metadata; `cook-with-pip-xcresult` captures full test evidence. UI screenshots do **not** prove a connected simulator-to-FastAPI flow. Separately, FastAPI/PostgreSQL integration tests verify shopping operations and no inventory consumption during preview.
- [One approved live DeepSeek smoke run](https://github.com/lucifron28/Provision/actions/runs/42696338381) passed with `deepseek-flash` (544 tokens); the safety result was `review_required`, and no recipe was saved. Production provider access remains subject to existing authorization, consent and budgets; standard CI never makes billable calls.
- Scanner/OCR and camera acceptance, membership switching with actual device data, VoiceOver, smaller devices and on-device performance still require Mac lab validation.

## Household and account boundaries

- Decode the default household context returned by registration and `/auth/me`.
  Only send a selected household context after the server authorizes membership.
- Namespace SwiftData/offline cache records by account and household. Product
  metadata and stock projections both become household-specific.
- Bind persisted pending intake payloads and idempotency keys to their original
  account and household. Switching accounts must not replay another account's
  intake. Preserve the original payload for recovery after signing back in.
- Clear visible private state on logout, deletion and household switching.
- Handle reauthentication after deployment of immutable user-ID token claims.
  An expired or legacy token must not leave a stale household visible offline.
- Add consent, self export and account-deletion screens only after their backend
  contracts are verified. Deletion requires password reauthentication and an
  explicit confirmation. Preserve shared household history for remaining members.

## Recipe and shopping flows

- Add Home's Cook with Pip entry, Cook Now, Almost There and Discover screens.
  Keep the existing five destinations and distinguish heuristic hints from recipe
  records and any future provider output.
- Show required, optional, available, partial, missing and unknown quantities;
  reflect unsupported conversions without inventing package sizes.
- Add preferences and separate allergy declarations. Preserve the distinction
  between not provided and none declared. Display conflicts and manual-review
  states without promising allergy safety.
- Add explicit package-label review using [the label API](PRODUCT_LABELS_API.md).
  Preserve the product's exact `updated_at` value in the request, including its
  fractional seconds. Show stale product, mapping and review conflicts for fresh
  review. Do not replay an old approval after a change or revocation. Present
  member review as a recorded declaration, without implying certification.
- Display provenance, publisher link and access mode. Candidate publishers must
  not appear approved. Live DeepSeek and web search remain disabled until the
  separately deferred provider milestone is authorized with credentials.
- Implement shopping preview, reviewed edits and explicit confirmation. Handle
  stale previews by requesting review again and retries with the same key.
  Follow [the recipe shopping contract](RECIPE_SHOPPING_API.md), including
  explicit duplicate consolidation, six-place decimal quantities, omitted
  optional ingredients and refreshing the shopping list after confirmation.
  Keep a retry's exact payload and idempotency key. A changed selection requires
  a new key and a current preview.
- Implement saved recipes, weekly plans, cooking confirmation and leftovers
  against the final backend contracts. Viewing or completing a recipe screen
  must not consume inventory automatically.
- Weekly plans pin recipe revisions. Show the plan revision when editing and
  request a new combined shopping preview after any plan, pantry, shopping,
  diner, label, or source-policy change. Planned meals do not reserve stock.
- Cooking confirmation requires the literal `RECORD COOKING`, explicit history
  consent, a current preview, and acknowledgement of every batch with unknown
  expiry. Preserve the confirmation payload and retry key across interrupted
  responses. Show allocated batches and native quantities before recording.
- Leftover use-by dates require user verification. Display unknown dates and
  recorded expiry without generating a guaranteed safe date. Consumption and
  disposal require the current leftover revision and an explicit quantity.
- Budget and waste screens must show historical PHP prices, price timestamps,
  unknown costs, and separate quantity units. Leftover disposal has unknown cost;
  the API does not infer savings or treat all expired stock as recorded waste.

## Required acceptance on Mac and device

- Run the repository XCTest command from `AGENTS.md` against the supported
  simulator. Record the exact commit, command and result.
- Exercise two households with distinct offline data and pending intake requests.
  Verify membership revocation, logout, switching and recovery on both accounts.
- Recheck camera permission, barcode acceptance and rearm, receipt-camera
  suspension, explicit resume, repeated dismissals and interrupted intake.
- Test VoiceOver, large Dynamic Type, long Filipino ingredient names, light and
  dark appearances, and small phone layouts.
- Test at least 50 pantry rows, 100 shopping rows and 30 scanned items, including
  nil prices, unknown expiry and unsupported units.
- Record simulator screenshots and physical-device results separately. Green
  scanner CI for the existing client does not verify newly planned screens.

These are deferred client deliverables. None is marked complete by this document.
