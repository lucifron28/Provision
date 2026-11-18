# Mac lab handoff: Provision final project

Updated 2026-11-18

## Current state

- Repository: `lucifron28/Provision`
- Branch: `feat/pip-chat-foundation`
- PR head observed at the start of this preparation: `9958b62622085db12fc1ef128d31ccf30d47c2b2`; local branch also contained two test-only commits.
- Latest application-code checkpoint: `3ca1a8eeab59c8cf907fd134ebba47d3b7c59773`.
- PR: [#11](https://github.com/lucifron28/Provision/pull/11)
- Staging: [provision-staging-04dt](https://provision-staging-04dt.onrender.com). On 2026-11-18, `/health` returned deployment `staging` at revision `9958b62622085db12fc1ef128d31ccf30d47c2b2`; `/ready` returned `{"status":"ready"}`. This was a health/readiness check, not an authenticated app workflow.
- Latest required CI run on `9958b62` is [44244226820](https://github.com/lucifron28/Provision/actions/runs/44244226820); it completed successfully.
- The receipt-intake regression was fixed in `3ca1a8e`. The focused test passed locally on `a0a6cf4` (application code from `9958b62`) with ad-hoc simulator signing; camera/OCR hardware was not tested.
- The full gallery has 58 required scenarios and 9 supplemental captures. Run [44235560950](https://github.com/lucifron28/Provision/actions/runs/44235560950) captured its simulator shards, but the workflow did not finish successfully because the substitution-preview capture was missing from the manifest at that time. The manifest now includes it; the complete gallery has not yet passed on the current product commit.

## First check in the lab

- Open `frontend/frontend.xcodeproj` in Xcode, select scheme `frontend` and iPhone 17 / iOS 26.5.
- First use Product > Run (`⌘R`) for the normal app. It should show the Provision login screen with no `UI TEST FIXTURES` banner.
- The Simulator defaults to `http://127.0.0.1:8000/api/v1`. For approved staging, add the non-secret Run environment variable `PROVISION_API_BASE_URL=https://provision-staging-04dt.onrender.com/api/v1`; never add staging tokens or provider credentials to Xcode.
- Then run this focused receipt and Quick Add test:

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
xcodebuild test \
  -project frontend/frontend.xcodeproj \
  -scheme frontend \
  -destination 'platform=iOS Simulator,id=B1BB04CE-7E3E-4D4E-BA0E-CBCDD5DC65C6' \
  -only-testing:frontendUITests/CookWithPipUITests/testInventoryQuickAddOffersScannerAndMinimalManualEntry \
  -resultBundlePath /tmp/Provision-pr11-receipt.xcresult \
  CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=-
```

On the receipt-intake screen, verify that the synthetic milk row visibly shows `Pantry - Shelf A`, opens into its detail/review screen, and has no `Failed to load locations` message. The current focused run passed 1/1 and captured the resolved location. The simulator sample receipt does not test physical camera or OCR behavior. `CODE_SIGNING_ALLOWED=NO` made Keychain recovery unavailable in this Mac's simulator; ad-hoc identity `-` required no Apple signing and passed.

## Short presentation flow

Use synthetic household data. Keep the demo focused on what Provision does:

1. Show Home and the pantry summary.
2. Open Cook with Pip, compare Cook Now with Almost There, and open a recipe.
3. Show the recipe's ingredients, food-safety review, and actual instructions.
4. Open Pip Chat with consent enabled, ask about the selected recipe, and show the validated recipe action returning to Provision's shopping review.
5. Review exact shopping quantities and safety notices, then confirm explicitly. Show that chat itself does not write inventory or shopping data.
6. If time allows, show receipt intake and the resolved storage location.

## Physical-device checks

Only mark these complete after trying them on an iPhone with synthetic examples:

- Camera permission prompt and barcode scanning.
- Receipt capture and OCR, including review of uncertain values.
- Keyboard behavior and layout at a larger text size.
- VoiceOver focus order and spoken control labels.

Do not use real household data or display service credentials during the demo. Do not send live DeepSeek requests as part of the routine walkthrough.

## Remaining remote checks

- Finish the required PR check on the current product commit.
- Run the corrected complete 58-scenario gallery once and inspect the generated screenshots and `.xcresult`.
- Run staging E2E against the exact current PR commit, verify cleanup, and then turn off staging fixture and chat-mock switches.
- Update PR #11 with the resulting artifacts and test counts. Leave it unmerged.

Keep the gallery and staging checks remote; the Mac session is for the focused screen check, presentation practice, and hardware-only acceptance above.
