import Combine
import Foundation

public protocol PendingRecipeShoppingStore {
    func readPendingRecipeShopping(scope: HouseholdScope) -> PendingRecipeShoppingRecord?
    @discardableResult func savePendingRecipeShopping(_ record: PendingRecipeShoppingRecord, scope: HouseholdScope) -> Bool
    @discardableResult func deletePendingRecipeShopping(scope: HouseholdScope) -> Bool
}

extension KeychainStore: PendingRecipeShoppingStore {}

@MainActor
public final class RecipeShoppingReviewViewModel: ObservableObject {
    @Published public private(set) var preview: RecipeShoppingPreview?
    @Published public private(set) var pendingRecord: PendingRecipeShoppingRecord?
    @Published public private(set) var confirmationResult: RecipeShoppingConfirmationResult?
    @Published public var includeOptional = false
    @Published public var servingsText: String
    @Published public var selectedIngredientIDs: Set<Int> = []
    @Published public var targetQuantityTexts: [Int: String] = [:]
    @Published public var consolidateIngredientIDs: Set<Int> = []
    @Published public var safetyReviewAcknowledged = false
    @Published public private(set) var isLoading = false
    @Published public private(set) var isConfirming = false
    @Published public private(set) var hasLoaded = false
    @Published public private(set) var errorMessage: String?
    @Published public private(set) var statusMessage: String?

    private let recipe: HouseholdRecipe
    private let scope: HouseholdScope
    private let service: any CookWithPipWorkflowService
    private let pendingStore: any PendingRecipeShoppingStore

    public init(recipe: HouseholdRecipe, scope: HouseholdScope,
                service: any CookWithPipWorkflowService = APIClient.shared,
                pendingStore: any PendingRecipeShoppingStore = KeychainStore.shared) {
        self.recipe = recipe
        self.scope = scope
        self.service = service
        self.pendingStore = pendingStore
        servingsText = NSDecimalNumber(decimal: recipe.servings.value).stringValue
    }

    public var isPreviewCurrent: Bool {
        guard let preview, let servings = decimal(servingsText) else { return false }
        return preview.include_optional == includeOptional && preview.servings.value == servings
    }

    public var canConfirm: Bool {
        guard pendingRecord == nil, let preview, isPreviewCurrent,
              !selectedIngredientIDs.isEmpty else { return false }
        switch preview.safety.decision {
        case "eligible": break
        case "review_required" where safetyReviewAcknowledged: break
        default: return false
        }
        return selectedIngredientIDs.allSatisfy { id in
            guard let line = preview.lines.first(where: { $0.ingredient_id == id }),
                  line.status == "ready",
                  line.target_quantity != nil,
                  let text = targetQuantityTexts[id], let target = decimal(text),
                  target > 0, hasAtMostScale(target, places: 6),
                  target <= Decimal(string: "99999999.999999")! else { return false }
            let shortage = line.shortage?.value ?? 0
            let pending = line.pending_quantity?.value ?? 0
            return target >= shortage && target >= pending
        }
    }

    public func load() async {
        guard !hasLoaded else { return }
        hasLoaded = true
        if let stored = pendingStore.readPendingRecipeShopping(scope: scope) {
            pendingRecord = stored
            statusMessage = "A confirmation is saved on this device. Retry the exact request to check its result."
            return
        }
        await refreshPreview()
    }

    public func refreshPreview() async {
        guard pendingRecord == nil else {
            errorMessage = "Retry the saved confirmation before requesting another preview."
            return
        }
        guard let servings = decimal(servingsText), servings > 0, servings <= 10_000,
              hasAtMostScale(servings, places: 4) else {
            errorMessage = "Enter servings greater than 0 and at most 10,000, with at most four decimal places."
            return
        }
        isLoading = true
        errorMessage = nil
        statusMessage = nil
        confirmationResult = nil
        safetyReviewAcknowledged = false
        do {
            let request = RecipeShoppingPreviewRequest(
                recipeID: recipe.id, revision: recipe.revision,
                servings: ExactQuantity(servings), includeOptional: includeOptional
            )
            let response = try await service.previewRecipeShopping(request, scope: scope)
            guard response.recipe_id == recipe.id,
                  response.recipe_revision == recipe.revision,
                  response.servings.value == servings,
                  response.include_optional == includeOptional else {
                throw APIError.invalidResponse(502, "Shopping preview did not match the requested recipe version")
            }
            preview = response
            selectedIngredientIDs = Set(response.lines.compactMap { line in
                guard line.status == "ready", (line.additional_quantity?.value ?? 0) > 0 else { return nil }
                return line.ingredient_id
            })
            var quantities: [Int: String] = [:]
            for line in response.lines {
                guard let id = line.ingredient_id, let target = line.target_quantity else { continue }
                quantities[id] = NSDecimalNumber(decimal: target.value).stringValue
            }
            targetQuantityTexts = quantities
            consolidateIngredientIDs = []
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    public func confirmSelectedLines() async {
        guard canConfirm, let preview else {
            errorMessage = "Refresh the preview and review every selected line before confirming."
            return
        }
        let lines = preview.lines.compactMap { line -> RecipeShoppingAcceptedLine? in
            guard let id = line.ingredient_id, selectedIngredientIDs.contains(id),
                  let text = targetQuantityTexts[id], let value = decimal(text) else { return nil }
            let consolidate = (line.pending_item_ids.count > 1) && consolidateIngredientIDs.contains(id)
            return RecipeShoppingAcceptedLine(ingredientID: id, target: ExactQuantity(value), consolidateExisting: consolidate)
        }
        guard !lines.isEmpty else {
            errorMessage = "Select at least one ready ingredient line."
            return
        }
        let confirmation = RecipeShoppingConfirmation(
            previewID: preview.preview_id,
            idempotencyKey: UUID().uuidString,
            revision: preview.shopping_revision,
            acceptedLines: lines
        )
        let displayLines = lines.compactMap { accepted -> PendingRecipeShoppingLine? in
            guard let line = preview.lines.first(where: { $0.ingredient_id == accepted.ingredient_id }) else { return nil }
            return PendingRecipeShoppingLine(name: line.display_name,
                                             targetQuantity: accepted.target_quantity,
                                             unit: line.unit)
        }
        let record = PendingRecipeShoppingRecord(scopeStorageKey: scope.storageKey,
                                                 recipeTitle: recipe.title,
                                                 lines: displayLines,
                                                 confirmation: confirmation)
        guard pendingStore.savePendingRecipeShopping(record, scope: scope) else {
            errorMessage = "This device could not save a retry record, so the shopping list was not changed."
            return
        }
        pendingRecord = record
        await send(record)
    }

    public func retryPendingConfirmation() async {
        guard let record = pendingRecord,
              record.scopeStorageKey == scope.storageKey else {
            errorMessage = "No saved confirmation matches the current household."
            return
        }
        await send(record)
    }

    private func send(_ record: PendingRecipeShoppingRecord) async {
        isConfirming = true
        errorMessage = nil
        statusMessage = nil
        do {
            confirmationResult = try await service.confirmRecipeShopping(record.confirmation, scope: scope)
            if pendingStore.deletePendingRecipeShopping(scope: scope) {
                pendingRecord = nil
                statusMessage = "Shopping list updated. Pantry quantities were not changed."
            } else {
                statusMessage = "Shopping list updated. The saved retry record remains on this device; retrying it is idempotent."
            }
        } catch {
            if let apiError = error as? APIError, apiError.serverErrorCode == "STALE_PREVIEW" {
                if pendingStore.deletePendingRecipeShopping(scope: scope) {
                    pendingRecord = nil
                    preview = nil
                    statusMessage = "Inventory or shopping data changed. Load a fresh preview before confirming."
                } else {
                    errorMessage = "The preview is stale, and this device could not clear its saved request. Retry the same request or reload."
                }
            } else {
                errorMessage = "The server did not confirm the result. The exact request is saved; retry it without editing to avoid duplicate items. (\(error.localizedDescription))"
            }
        }
        isConfirming = false
    }

    private func decimal(_ value: String) -> Decimal? {
        Decimal(string: value.trimmingCharacters(in: .whitespacesAndNewlines), locale: Locale(identifier: "en_US_POSIX"))
    }

    private func hasAtMostScale(_ value: Decimal, places: Int) -> Bool {
        var source = value
        var rounded = Decimal()
        NSDecimalRound(&rounded, &source, places, .plain)
        return rounded == value
    }
}
