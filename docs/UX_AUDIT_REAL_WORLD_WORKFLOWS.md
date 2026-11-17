# Real-world UX audit and acceptance matrix

Audit baseline: `d825f5c920c1dc04f25986c045acd995ea38c9de` on 2026-11-17.

This audit records behavior confirmed in the SwiftUI views, ViewModels, backend routes, schemas, and tests. It distinguishes missing workflow support from risks that need further verification. The five existing tabs remain Home, Inventory, Scan, Shopping, and Analytics.

## Evidence reviewed

- Reviewed the inventory, product detail, shopping, Home, Cook with Pip, recipe detail, substitution editor, Pip Chat, preferences, and product-label review flows.
- The full-gallery workflow at [run 43959940708](https://github.com/lucifron28/Provision/actions/runs/43959940708) reports 55/55 required scenarios captured, no missing or duplicate captures, and passed capture integrity at `f59455c545119847bec0c4d4d29ec3d3b07cdf08`.
- Inspected `Cook_Now.png`, `Recipe_Detail_Substitution_Applied.png`, and `Shopping_Preview_Ready.png` from that artifact. This is a small visual sample, not a manual review of every image.
- The gallery manifest correctly leaves complete visual review unclaimed. The gallery does not currently cover Quick Add or purchased-to-pantry reconciliation.

## Confirmed findings

| Priority | Workflow | Observed behavior | User impact | Acceptance condition |
| --- | --- | --- | --- | --- |
| P1 | Add inventory | The advanced form requires a storage location even though the API accepts one as optional. Product creation and batch creation are separate requests, so a lost response between them can leave a product without stock. | Routine groceries take more work, and retrying a partial add can create confusing state. | Add a familiar item with only identity and quantity; keep detailed fields available; commit new product and initial stock atomically; exact retries do not duplicate either record. |
| P1 | Maintain stock | Product detail accepts a quantity and the backend consumes FEFO batches, but the consume request has no idempotency key. Disposal is batch-wide, while quantity correction is a separate operation. | A timed-out consume can be repeated, and partial disposal requires manual correction. | Consumption, disposal, and correction have distinct audit semantics, safe exact retries, clear feedback, and quantity validation. |
| P1 | Shopping to pantry | Shopping items store `is_bought`; the bought filter shows them as “Purchased.” Clearing completed items deletes those rows. There is no review step that records actual quantities as pantry stock. | Purchased amounts can diverge from planned amounts, and clearing loses the path to stock intake. | Purchased items remain reviewable; users can correct, substitute, exclude, and confirm a batch; replay and concurrent confirmation cannot add stock twice. |
| P2 | Recipe substitutions | Recipe detail stores server-evaluated selections and renders them, but the shopping preview request contains no substitutions. The preview explicitly says it uses stored recipe ingredients. | Shopping quantities can describe the original ingredient after the user chose a substitute. | Implemented on this branch. Backend tests pass for replacement safety and quantity recalculation and rejection of unlisted replacements. UI verification is queued with the branch check. |
| P2 | Expiring food | Home offers a one-unit “Consume” action for an expiring item; the product detail screen has a quantity entry flow. | The shortcut cannot record partial measured use or a multi-unit use. | Home provides quantity-aware actions while retaining backend validation and recovery. |
| P3 | Trust and accessibility | Pip Chat has separate chat and allergy-sharing consent; preferences explain that missing allergy declarations are not treated as allergy-free. Label review is a separate guided flow. Gallery coverage exercises large text and safety states. | These are useful foundations; remaining work should focus on clarity and real-device behavior rather than replacing them. | Preserve server consent and safety decisions; test VoiceOver, large text, keyboard, camera, and barcode behavior on real hardware before claiming those checks. |

## Prioritized work and verification

| Slice | Focused evidence required | Status |
| --- | --- | --- |
| Quick Add | SwiftUI flow tests for minimal existing-product add, optional details, new product, scan entry, and validation; backend atomicity and retry tests. | In progress |
| Stock actions | Backend tests for partial consume, partial discard, correction, stale writes, and idempotent replay; UI tests for amount and reason. | Not started |
| Purchase reconciliation | Backend tests for household scope, exact request replay, corrected quantities, exclusions, duplicates, and overlapping confirmations; UI recovery test. | Not started |
| Substitution continuity | Backend preview tests for allowed replacement, safety recomputation, shortage quantities, and rejection of unlisted replacements; UI test verifies the preview names the selected substitution. | Backend focused tests pass; UI verification pending |
| Supporting screens | Focused UI tests for home actions, preferences, label review, empty/error states, large text, and dark mode. | Not started |
| Device acceptance | Camera permission, barcode scan, receipt OCR, VoiceOver, keyboard, and iPhone layout with synthetic data. | Requires Mac lab / physical iPhone |

Do not count a screenshot as visually verified solely because it was captured. Keep capture integrity, XCTest success, and human visual review as separate evidence.
