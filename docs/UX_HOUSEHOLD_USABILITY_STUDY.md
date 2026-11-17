# Provision household usability study

## Purpose

Evaluate whether everyday household members can keep pantry stock accurate, complete a grocery trip, and make a safe meal decision without coaching. This is a study plan only; no participant sessions or user results have been collected.

## Participants and setup

- Recruit 3–5 adults who shop or cook for a household. Include at least one person who uses larger text or VoiceOver if available.
- Use an iPhone with the release candidate and synthetic data in a dedicated test household. Do not use real household inventory, contact details, receipts, or provider credentials.
- Keep ordinary AI requests on deterministic mocks. Do not enable live DeepSeek for the study.
- Ask permission before recording. Prefer written notes; do not record names or account identifiers. Let participants stop at any time.
- Reset the synthetic household between participants and verify that no test rows remain afterward.

## Session script

Ask participants to think aloud while completing each task. Give only the task prompt; do not teach the controls. Record where they hesitate, correct data, or ask for help.

1. **Add groceries:** Add a familiar existing product with an actual quantity. Add a new product with a known unit, then reveal an optional expiration or location field and leave it unknown if the package gives no value.
2. **Review a receipt:** Scan a synthetic receipt, correct one uncertain product match, remove one false OCR line, and confirm only the entries that are understood.
3. **Maintain stock:** Record partial measured consumption, finish one count-based product, and discard part of another batch with a reason. Confirm the remaining quantity and event type.
4. **Find expiring food:** Find an approaching-expiration item and locate a recipe that uses it. Ask the participant to explain the availability and food-safety statuses separately.
5. **Reconcile a shopping trip:** Mark several list entries purchased, change the actual amount for one item, exclude an item from pantry tracking, and confirm. Retry the same confirmation after a simulated connection interruption.
6. **Choose a substitution:** Select an allowed substitute, review the updated safety and availability information, and inspect the resulting shopping quantity.
7. **Use Pip Chat:** Ask about a household recipe and product. Revoke consent while a mocked request is pending and confirm no private context is sent afterward. Show an explicitly unknown allergy declaration and ask what it means.
8. **Accessibility pass:** At the largest supported text size, use VoiceOver or direct observation to complete one stock action and one shopping review. Include the keyboard, focus order, labels, warning meaning, and recovery controls.

## Measures

For each task record:

- Completion without help, completion with help, or abandonment.
- Elapsed time from reading the prompt to the correct confirmed state.
- Number of taps/screens and data-entry corrections.
- Errors, repeated actions, and time spent recovering.
- Whether the final server state matches the intended product, quantity, household, and event.
- Whether the participant can explain what is known, unknown, stale, blocked, or awaiting review.

Report medians and completion counts per task, with a short list of observed friction points. Do not treat the small sample as statistically representative. Compare later sessions with this baseline before claiming improvement.

## Provisional targets

Validate these against actual sessions; they are not current results:

- At least 90% unassisted completion for familiar Quick Add and common shopping tasks.
- Familiar Quick Add typically takes less than 15 seconds after product selection.
- No duplicate pantry changes after a retry or relaunch.
- No model response overrides an allergy conflict or authorizes a write.
- Participants can distinguish pantry availability from food-safety status.

## Data handling and follow-up

Collect only task outcomes and anonymous notes. Do not add analytics SDKs or send usage telemetry. Delete session notes that include accidental personal information. Prioritize repeated errors and safety misunderstandings, then make focused changes and repeat the affected task before updating any success claim.
