# Mac lab manual verification checklist

Updated 2026-11-18. Use synthetic data only. This checklist is for normal app use in Simulator, not production acceptance.

## Start the real app

- Open `/Users/maclab/cada/Provision/frontend/frontend.xcodeproj` in Xcode.
- Select scheme `frontend`, destination `iPhone 17` on iOS 26.5, then press `⌘R`.
- Normal launch uses `ContentView`. XCUITest screenshots use fictional Filipino household data that should look like ordinary household data, with fixture provenance kept in the screenshot manifest. No test or debug banner belongs in a screenshot.
- Xcode is 26.6 (17F113). `xcode-select -p` currently selects Command Line Tools; command-line Xcode operations should set `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`. Do not change machine-wide developer settings just for this checklist.
- Simulator default API URL: `http://127.0.0.1:8000/api/v1`. Confirm a local backend is running before login. For approved staging, add the non-secret Xcode Run environment variable `PROVISION_API_BASE_URL=https://provision-staging-04dt.onrender.com/api/v1`. Staging `/health` and `/ready` were reachable at revision `9958b62622085db12fc1ef128d31ccf30d47c2b2`; that was not an authenticated app test.
- Create a synthetic account from the login screen's **Create Account** flow. Use a unique `@example.test` email, a password of at least six characters, and an optional display name. Registration uses the normal API, signs in, and creates a private `Home` household. Choose credentials yourself; do not write them into this file, a scheme, or a shared-machine note. A household picker is only expected when the account has multiple memberships.
- The app's Debug scheme has no fixture arguments or staging URL set. Local backend data is disposable and initially empty; a new account has no seeded recipes. Pip Chat must remain non-billable: the local provider is disabled, and the staging mock is restricted to exact-pattern synthetic test accounts. Do not enable DeepSeek or add fixture tokens to Xcode.
- Optional deterministic-only UI path: run a focused `CookWithPipUITests` case through Xcode Test. These screens verify fixture behavior, not the normal connected app. Keep test setup and source details outside captured screens. Do not run the full screenshot gallery for this handoff.

## Record observations

For each section, select one status and record concrete evidence.

### 1. First launch and login

- [ ] PASS  [ ] FAIL  [ ] BLOCKED  [ ] NOT TESTED
- Check normal startup, sign-in, registration, error handling, and return to the private household.
- Observed issue:
- Steps to reproduce:
- Screenshot/evidence:

### 2. Five-tab navigation

- [ ] PASS  [ ] FAIL  [ ] BLOCKED  [ ] NOT TESTED
- Visit Home, Inventory, Scan, Shopping, and Analytics; verify selection and back/navigation transitions.
- Observed issue:
- Steps to reproduce:
- Screenshot/evidence:

### 3. Inventory and Quick Add

- [ ] PASS  [ ] FAIL  [ ] BLOCKED  [ ] NOT TESTED
- Add an existing product if available; create a new product with an explicitly selected unit; inspect quantity, optional expiration/location, and edit/update behavior. Check invalid quantities and missing required values.
- Observed issue:
- Steps to reproduce:
- Screenshot/evidence:

### 4. Receipt review

- [ ] PASS  [ ] FAIL  [ ] BLOCKED  [ ] NOT TESTED
- Use the Simulator's sample receipt. Confirm synthetic milk displays `Pantry - Shelf A`; open review, inspect edit/save controls, and check for location-loading errors. This sample does not verify physical camera or OCR behavior.
- Observed issue:
- Steps to reproduce:
- Screenshot/evidence:

### 5. Stock adjustments

- [ ] PASS  [ ] FAIL  [ ] BLOCKED  [ ] NOT TESTED
- Try partial consumption, finishing a count-based item, disposal with a reason, quantity correction, invalid amount, and a repeated action. Confirm remaining stock.
- Observed issue:
- Steps to reproduce:
- Screenshot/evidence:

### 6. Shopping and pantry reconciliation

- [ ] PASS  [ ] FAIL  [ ] BLOCKED  [ ] NOT TESTED
- Add an item, inspect pending/purchased filters, mark it purchased, review actual quantity and unit, then explicitly add it to pantry or exclude it. Check duplicate/retry/error states.
- Observed issue:
- Steps to reproduce:
- Screenshot/evidence:

### 7. Cook with Pip

- [ ] PASS  [ ] FAIL  [ ] BLOCKED  [ ] NOT TESTED
- Open Cook Now, Almost There, and My Recipes; inspect search, recipe details/instructions, ingredient quantities, availability, safety notices, missing ingredients, and shopping-preview navigation. Also open the Preferences and product-label management link. A new local household may show an empty recipe state.
- Observed issue:
- Steps to reproduce:
- Screenshot/evidence:

### 8. Substitutions

- [ ] PASS  [ ] FAIL  [ ] BLOCKED  [ ] NOT TESTED
- Choose a listed substitute, refresh evaluation, and confirm the selected substitute and recalculated amounts appear in preview without reintroducing the original ingredient. Keep final shopping confirmation explicit.
- Observed issue:
- Steps to reproduce:
- Screenshot/evidence:

### 9. Pip Chat

- [ ] PASS  [ ] FAIL  [ ] BLOCKED  [ ] NOT TESTED
- Check chat consent separately from allergy-sharing consent, recipe/product context, prompts/cards, and shopping-preview navigation. Use only an approved deterministic mock or fixture; do not send a live provider request.
- Observed issue:
- Steps to reproduce:
- Screenshot/evidence:

### 10. Visual quality and usability

- [ ] PASS  [ ] FAIL  [ ] BLOCKED  [ ] NOT TESTED
- Check light/dark mode, keyboard obstruction/dismissal, scrolling, Dynamic Type, readable warnings, and accessibility labels. Keep normal-app screenshots separate from fixture screenshots.
- Observed issue:
- Steps to reproduce:
- Screenshot/evidence:

## Physical-iPhone checks — NOT TESTED — PHYSICAL DEVICE REQUIRED

- Camera permission prompts and real barcode recognition.
- Physical receipt capture and OCR accuracy under different lighting.
- Scanner interruption, pause, and rearm behavior.
- On-device VoiceOver, Dynamic Type, keyboard behavior, and performance.
