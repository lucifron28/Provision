# Mac-dependent Cook with Pip work

Status: pending implementation and acceptance. Backend work on Windows does not
prove that these client flows work. Preserve the existing scanner and five-tab
navigation while implementing them.

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
- Display provenance, publisher link and access mode. Candidate publishers must
  not appear approved. Live DeepSeek and web search remain disabled until the
  separately deferred provider milestone is authorized with credentials.
- Implement shopping preview, reviewed edits and explicit confirmation. Handle
  stale previews by requesting review again and retries with the same key.
- Implement saved recipes, weekly plans, cooking confirmation and leftovers
  against the final backend contracts. Viewing or completing a recipe screen
  must not consume inventory automatically.

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
