# Mac lab handoff: real staging verification

Updated 2026-11-20

## Start here

- Repository: `lucifron28/Provision`
- Branch: `feat/pip-chat-foundation`
- PR: [#11](https://github.com/lucifron28/Provision/pull/11), open and unmerged.
- Code under test: `bc7f56df1a6ba3b3a893a3c4972c214b8ff6e4f8` (`Wait for imported receipt in Photos picker`).
- Render staging serves that commit. `/health` reports `ok`; `/ready` reports `ready`.
- No demo credentials or tokens belong in this file, Xcode settings, screenshots, or logs.

## Check the active run first

[Staging run 44649332128](https://github.com/lucifron28/Provision/actions/runs/44649332128) is testing the same real demo household on the iPhone 17 simulator. At handoff it was still running its real-account UI step. Check its final result before starting another run or touching inventory. Do not test receipt intake concurrently against this household.

The latest run builds the current commit, imports the receipt into Photos, runs real-account login/barcode lookup and receipt intake, then runs the production receipt parser regression. If it passes receipt intake, inspect its artifact and verify the persisted batches before doing anything else.

## What is already verified

- Windows API login, household access, inventory reads, and shopping-list reads succeed.
- The live barcode endpoint returned Century Tuna Flakes in Oil, 180 g, for barcode `4800016644818`.
- A previous Apple Vision run recognized and quantity-checked 8 of 9 receipt lines, but did not confirm the intake.
- The prior picker screenshot showed the system photo library still loading. A later UI hierarchy contained the imported photo. Commit `bc7f56d` changes the wait for that actual thumbnail from 10 to 30 seconds. It still needs a successful simulator result.
- One genuine Pip Chat request returned HTTP 200 from `deepseek-flash`. A context-aware follow-up returned HTTP 429, `request_budget_exhausted`. No chat request is needed for receipt verification; do not use a mock as a substitute.
- Sinigang evaluation is `review_required`: pork 700 g needed / 850 g available; eggplant 150/400 g; onion 100/300 g; rice 300/800 g; tomato 200/450 g; kangkong 120/120 g. Fish sauce is short by 30 mL. Tamarind soup base (40 g), daikon (200 g), and water (1,500 mL) have unresolved ingredient mappings. Product allergen labels remain unreviewed. The shopping list is unchanged at 10 rows. Do not bypass the review gate or mark package labels verified without the actual panels.

## If the active run fails before receipt confirmation

Use the Mac simulator for one focused run. Pull the branch first, confirm the checked-out SHA, and make sure the Actions run above has finished.

1. In Xcode, open `frontend/frontend.xcodeproj` and select an iPhone 17 simulator.
2. Import the attached receipt once:
   ```sh
   xcrun simctl addmedia booted frontend/frontendUITests/Resources/Provision_Receipt_OCR_Demo.jpg
   ```
3. Supply the real demo credentials only in the local terminal prompt. Do not put them in a command, file, project setting, screenshot, or log. Xcode forwards test variables with the `TEST_RUNNER_` prefix:
   ```sh
   export TEST_RUNNER_PROVISION_API_BASE_URL='https://provision-staging-04dt.onrender.com/api/v1'
   export TEST_RUNNER_PROVISION_REAL_DEMO_ACCOUNT_TEST=true
   read -r 'TEST_RUNNER_PROVISION_STAGING_TEST_EMAIL?Demo account email: '
   read -rs 'TEST_RUNNER_PROVISION_STAGING_TEST_PASSWORD?Demo account password: '
   printf '\n'
   export TEST_RUNNER_PROVISION_STAGING_TEST_EMAIL TEST_RUNNER_PROVISION_STAGING_TEST_PASSWORD
   ```
4. Run only the real receipt journey:
   ```sh
   mkdir -p artifacts
   xcodebuild test \
     -project frontend/frontend.xcodeproj \
     -scheme frontend \
     -destination 'platform=iOS Simulator,name=iPhone 17,OS=latest' \
     -only-testing:frontendUITests/CookWithPipUITests/testRealDemoAccountReceiptOCRIntake \
     -resultBundlePath artifacts/real-demo-receipt.xcresult \
     -parallel-testing-enabled NO \
     CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=-
   ```
5. In the app, review the OCR lines, correct uncertain quantities, choose storage locations, and confirm once. Then verify the expected inventory batches through staging. Do not repeat confirmation if the UI reports an uncertain result; refresh and reconcile first.
6. Report the exact XCTest result and actual before/after inventory quantities. If the test fails, save the `.xcresult` and one screenshot of the failing screen. Do not launch repeated runs without a specific fix.

Do not seed fictional stock, alter allergy declarations, or claim receipt intake succeeded without seeing persisted inventory.

## Other results and limits

The context-aware DeepSeek request is currently blocked by the provider's request budget. The user approved billable calls, but the 429 shows a provider limit, so do not retry now. The successful earlier response was genuine but did not give useful recipe recommendations.

Do not confirm recipe shopping until the unresolved mapping and product-label review issues are genuinely resolved. No production deployment or PR merge is authorized.

Physical camera and barcode scanning still require a real iPhone. The simulator can verify manual barcode entry and receipt picker/OCR flows, not camera hardware behavior.
