# Mac lab handoff: Provision final project

Updated 2026-11-18

## Current state

- Repository: `lucifron28/Provision`
- Branch: `feat/pip-chat-foundation`
- Latest application-code checkpoint: `3ca1a8eeab59c8cf907fd134ebba47d3b7c59773` (the handoff commit adds documentation only)
- PR: [#11](https://github.com/lucifron28/Provision/pull/11)
- Staging: [provision-staging-04dt](https://provision-staging-04dt.onrender.com). Render auto-deploy is enabled and this commit is Live.
- The latest required CI run on the product commit is [44243830433](https://github.com/lucifron28/Provision/actions/runs/44243830433), still running when this handoff was written.
- The receipt-intake test failed on the previous code commit because its preview row omitted the fixture location from its accessibility label. Commit `3ca1a8e` fixes the preview location data and exposes a stable row identifier. Recheck it before presenting.
- The full gallery has 58 required scenarios and 9 supplemental captures. Run [44235560950](https://github.com/lucifron28/Provision/actions/runs/44235560950) captured its simulator shards, but the workflow did not finish successfully because the substitution-preview capture was missing from the manifest at that time. The manifest now includes it; the complete gallery has not yet passed on the current product commit.

## First check in the lab

On the Mac, fetch the branch and open `frontend/frontend.xcodeproj` in Xcode. Use the iPhone 17 simulator and run this focused test first:

```sh
xcodebuild test \
  -project frontend/frontend.xcodeproj \
  -scheme frontend \
  -destination 'platform=iOS Simulator,name=iPhone 17,OS=latest' \
  -only-testing:frontendUITests/CookWithPipUITests/testInventoryQuickAddOffersScannerAndMinimalManualEntry \
  CODE_SIGNING_ALLOWED=NO
```

In the receipt-intake screen, check that the sample milk row visibly shows `Pantry - Shelf A`, opens into its detail/review screen, and has no `Failed to load locations` message. The test should also find the row through its stable accessibility identifier. If it fails, save the `.xcresult` and note the exact failed assertion.

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
