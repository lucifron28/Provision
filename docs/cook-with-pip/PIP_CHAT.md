# Pip Chat: Phases 1–3

Pip Chat is a consent-gated cooking conversation available from Cook with Pip,
Recipe Detail, and Product Detail. It reuses Provision's household, recipe,
allergy, inventory, and shopping services. The model writes conversational text;
Provision remains authoritative for household facts, safety decisions, recipe
references, and shopping changes.

## API and consent

- `POST /api/v1/pip/chat` accepts a typed message, optional recipe or product
  context, a bounded recent history, and recent recipe references.
- `GET`, `PUT`, and `DELETE /api/v1/privacy/pip-chat-consent` manage the active
  member's chat consent and separate allergy-sharing consent.
- The chat route requires authorization for the selected household and current
  consent from every active member. Revoking consent clears the stored consent
  and allergy-sharing state.
- Requests allow at most eight history turns and three recent recipe IDs. The
  client keeps conversation history in view state; it is not saved as a chat
  transcript in the household account.

## Context and safety

- Recipe and product IDs are resolved on the server within the active household.
  Client descriptions and quantities are not authoritative.
- Recipe context includes complete ingredients, quantities, instructions,
  substitutions, availability, missing amounts, allergy evaluation, and source
  permissions when those permissions allow the content to be shared. Restricted
  publisher content is withheld from the provider.
- Product context is built from current household batches, expiry data,
  ingredient mappings, and package-label review. Allergy labels are withheld
  unless the separate allergy-sharing consent is active.
- Inventory, unit conversions, availability, allergy decisions, and shopping
  quantities come from deterministic Provision services. Unknown allergy status,
  incomplete composition, or a known conflict is never described as safe.
- Model-proposed recipe IDs and actions are checked against server-built
  references. The chat endpoint does not mutate inventory, recipes, or shopping
  records.

## Integrated workflows

- Cook with Pip opens a general chat. Recipe Detail opens a recipe-scoped chat
  with **Ask Pip**; Product Detail opens a product-scoped chat with **Ask Pip**.
- Responses support English, Filipino, and Taglish. Bounded recent history keeps
  follow-up references tied to the current screen and household. A changed
  household gets a distinct view identity, and revoking consent clears the
  conversation state.
- Recipe cards carry backend-validated recipe references and server-computed
  availability and safety states. Opening a card uses the existing Recipe
  Detail route.
- A shopping action is available only for a validated recipe. It navigates to
  the existing shopping preview, which recomputes missing ingredients and
  quantities. The user must review and explicitly confirm through the existing
  revision-checked, idempotent shopping workflow.

## Provider and staging behavior

The provider is server-side and feature-configured. Routine CI and synthetic
staging use the deterministic staging mock, which accepts only exact-pattern
synthetic accounts and makes no network call. Keep DeepSeek disabled for routine
CI and staging validation. The staging E2E workflow checks the exact current PR
head, exercises API and iPhone Simulator routes, and removes run-owned fixture
households through token-gated, scope-checked cleanup. It does not reset the
shared staging database.

## Verification coverage

Backend tests cover household authorization, consent and revocation, separate
allergy sharing, source permissions, complete recipe context, product context,
substitution validation, multilingual safety guidance, bounded history,
server-validated recipe cards, shopping-preview actions, and read-only behavior.
Swift tests cover typed requests, household selection, bounded conversation
state, consent changes, and offline drafts. XCUITests cover Cook with Pip chat,
contextual Recipe Detail and Product Detail routes, back navigation, and the
existing shopping preview and confirmation behavior. The PR visual smoke retains
its 12 required screenshots; the complete gallery remains a separate manual or
scheduled workflow.
