# Mac lab handoff: Provision final demo

Updated 2026-11-18

## Remote verification

- Repository: `lucifron28/Provision`
- Branch and PR: `feat/pip-chat-foundation`, [PR #11](https://github.com/lucifron28/Provision/pull/11). Leave the PR open.
- Last completed required CI before the current focused Cook with Pip copy fix: [run 44331090502](https://github.com/lucifron28/Provision/actions/runs/44331090502), commit `b18cbe3e50cdc7a5310dfe15339088c28d208b87`. It passed 1,077 backend cases (1,065 passed, 12 skipped), 60 Swift unit tests, 14 UI test methods, and all 12 mandatory screenshots plus one supplemental Needs Review screenshot in 16m30s.
- CI screenshot artifact: [12 required screenshots and supplemental Needs Review capture](https://github.com/lucifron28/Provision/actions/runs/44331090502/artifacts/14441510153). The manifest reports successful test attribution and capture integrity, with no missing, duplicate, or pixel-identical captures. Automated integrity checks do not replace visual review. The Needs Review image revealed that ingredient-mapping uncertainty was described like a quantity problem; a focused copy and UI assertion fix is now pending verification.
- Staging E2E: [run 44336835494](https://github.com/lucifron28/Provision/actions/runs/44336835494) passed on the same `b18cbe3` commit in 11m41s. It verified Render/Neon readiness, authenticated synthetic persistence, household isolation, four iPhone UI methods, screenshot upload, and cleanup of its own synthetic household. The [artifact](https://github.com/lucifron28/Provision/actions/runs/44336835494/artifacts/14442562472) contains the `.xcresult`, ten attributed PNGs, and manifest. I inspected the synthetic home and relaunch-recovery images; neither contains real household data.
- Render staging `provision-staging-04dt` served `b18cbe3` with `/health` and `/ready` passing after E2E cleanup. `STAGING_TEST_FIXTURES_ENABLED` and `STAGING_TEST_CHAT_MOCK_ENABLED` were returned to `false`. Render auto-deploys this branch, so check health after the pending PR commit is pushed.
- One genuine DeepSeek response succeeded for a consented synthetic account in [live smoke run 44322325337](https://github.com/lucifron28/Provision/actions/runs/44322325337), commit `50527bb5ac53481c5a9b29b0394ee4e43ea466e1`. Its [artifact](https://github.com/lucifron28/Provision/actions/runs/44322325337/artifacts/14436247352) contains the smoke evidence. No normal Ron-account request was made, and no additional billable request is needed for this handoff.
- These checks use synthetic staging data. They do not establish the exact reasons for exclusions in a personal household's recipes. Do not edit household records or infer missing allergy declarations from screenshots.
- This Windows host has no `xcodebuild`; PR CI runs Swift and Simulator checks on macOS.

## Final PR check

After the focused copy fix passes required CI, use the latest successful `tests.yml` run on PR #11 as the final simulator check. Download its `cook-with-pip-ios-screenshots` artifact and review the Needs Review image. The fix is not yet covered by the completed CI run above.

## Demo flow

Use the normal app and the demo account you control. If the simulator needs staging, set the non-secret Run environment variable `PROVISION_API_BASE_URL=https://provision-staging-04dt.onrender.com/api/v1`. Do not put account tokens or provider keys in Xcode settings.

1. Show Home and the pantry summary.
2. Open Cook with Pip. Compare Cook Now, Almost There, and My Recipes, then open an eligible recipe.
3. Show ingredients, food-safety status, and the recipe's instructions. Use Needs Review to explain why a recipe needs more information. Do not present a blocked recipe as safe to cook.
4. Open Pip Chat with consent enabled and ask about the selected recipe. Show the response and the validated route back to the shopping preview.
5. Review exact quantities and safety notices, then confirm the shopping change explicitly. Chat does not write pantry or shopping records by itself.

## Mac lab checks

These checks need local Xcode or physical hardware:

- Open the final PR commit in Xcode, build, and briefly spot-check Home, Cook with Pip, Needs Review, recipe details, Pip Chat, and shopping review.
- On an iPhone, check camera permission and barcode scanning.
- Capture a synthetic receipt, review OCR values, and test uncertain-value correction.
- Check keyboard layout at a larger text size and VoiceOver focus order.

Do not mark camera, barcode, receipt OCR, keyboard, or VoiceOver checks passed until they have been exercised on the device. Keep service credentials and real household data off shared computers.
