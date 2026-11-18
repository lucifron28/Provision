# Mac lab handoff: Provision final project

Updated 2026-11-18

## Current state

- Repository: `lucifron28/Provision`
- Branch: `feat/pip-chat-foundation`
- PR: [#11](https://github.com/lucifron28/Provision/pull/11)
- Before this Windows demo-readiness update, PR #11 and Render staging were on `cefb016279c2e9194196fb9e3f532df03fb329bd`. The branch push updates the existing PR; Render auto-deploys that branch.
- The last required CI on that baseline is [run 44268190421, attempt 2](https://github.com/lucifron28/Provision/actions/runs/44268190421). Backend, 47 Swift unit tests, all 11 UI methods, and all 12 mandatory screenshot scenarios passed. A new `Needs Review` capture is supplemental, so the required count stays 12.
- The 12-screen artifact from that run was downloaded and its manifest reports passed capture integrity, synthetic fixtures, and no live data. I inspected one representative Cook with Pip image. Automated capture status does not mean all images received human review. That baseline artifact predates the supplemental Needs Review capture; inspect it in the latest post-push PR artifact.
- Focused local verification for this update passed 12 recommendation and visual-smoke configuration tests, plus all 12 screenshot-organizer tests. Windows has no Xcode; the latest PR checks are the authority for Swift compilation and simulator behavior.
- Render was still reporting baseline `cefb016` as live. Direct `/health` and `/ready` requests timed out during this check, so current HTTP and database readiness were not confirmed. The repository config keeps DeepSeek disabled; Render's secret values and the key's presence were not readable through the connected service view. No paid provider request or authenticated Ron-account workflow was run.
- The full gallery remains a separate manual workflow. Do not run its 58 required scenarios for the presentation handoff.

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
