import Combine
import Foundation

public protocol PendingRecipeShoppingStore {
    func readPendingRecipeShopping(scope: HouseholdScope) -> PendingRecipeShoppingReadResult
    @discardableResult func savePendingRecipeShopping(_ record: PendingRecipeShoppingRecord, scope: HouseholdScope) -> Bool
    @discardableResult func deletePendingRecipeShopping(scope: HouseholdScope) -> Bool
}

extension KeychainStore: PendingRecipeShoppingStore {}

@MainActor
public final class RecipeShoppingReviewViewModel: ObservableObject {
    @Published public private(set) var expirationPassed = false
    @Published public private(set) var preview: RecipeShoppingPreview?
    @Published public private(set) var pendingRecord: PendingRecipeShoppingRecord?
    @Published public private(set) var pendingStorageState: PendingRecipeShoppingReadResult = .missing
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
    private var expirationTask: Task<Void, Never>?

    public init(recipe: HouseholdRecipe, scope: HouseholdScope,
                service: (any CookWithPipWorkflowService)? = nil,
                pendingStore: (any PendingRecipeShoppingStore)? = nil) {
        self.recipe = recipe
        self.scope = scope
        self.service = service ?? APIClient.shared
        self.pendingStore = pendingStore ?? KeychainStore.shared
        servingsText = NSDecimalNumber(decimal: recipe.servings.value).stringValue
    }

    public var isPreviewCurrent: Bool {
        guard let preview, let servings = decimal(servingsText) else { return false }
        return preview.include_optional == includeOptional && preview.servings.value == servings
    }

    public var expirationDate: Date? { preview?.expirationDate }

    public var isExpired: Bool { expirationPassed || (preview?.isExpired ?? true) }

    public var canConfirm: Bool {
        guard pendingStorageState == .missing, pendingRecord == nil, let preview, isPreviewCurrent,
              !isExpired, !selectedIngredientIDs.isEmpty else { return false }
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
        await reloadPendingState()
    }

    public func reloadPendingState() async {
        errorMessage = nil
        switch pendingStore.readPendingRecipeShopping(scope: scope) {
        case .missing:
            pendingStorageState = .missing
            pendingRecord = nil
            statusMessage = nil
            if preview == nil { await refreshPreview() }
        case .record(let stored):
            pendingStorageState = .record(stored)
            pendingRecord = stored
            preview = nil
            statusMessage = "A confirmation is saved on this device. Retry the exact request to check its result."
        case .corrupt:
            pendingStorageState = .corrupt
            pendingRecord = nil
            preview = nil
            statusMessage = nil
            errorMessage = "A saved shopping confirmation could not be read. No new shopping changes can be sent from this screen. Check the saved request again later."
        case .unavailable:
            pendingStorageState = .unavailable
            pendingRecord = nil
            preview = nil
            statusMessage = nil
            errorMessage = "This device could not check for a saved shopping confirmation. No new shopping changes can be sent until storage is available. Check again later."
        }
    }

    public func refreshPreview() async {
        errorMessage = nil
        let storedState = pendingStore.readPendingRecipeShopping(scope: scope)
        pendingStorageState = storedState
        switch storedState {
        case .missing:
            pendingRecord = nil
            statusMessage = nil
        case .record(let stored):
            pendingRecord = stored
            expirationTask?.cancel()
            expirationPassed = false
            preview = nil
            statusMessage = "A confirmation is saved on this device. Retry the exact request to check its result."
            return
        case .corrupt:
            pendingRecord = nil
            preview = nil
            statusMessage = nil
            errorMessage = "A saved shopping confirmation could not be read. No new shopping changes can be sent from this screen. Check the saved request again later."
            return
        case .unavailable:
            pendingRecord = nil
            preview = nil
            statusMessage = nil
            errorMessage = "This device could not check for a saved shopping confirmation. No new shopping changes can be sent until storage is available. Check again later."
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
            expirationTask?.cancel()
            expirationPassed = response.expirationDate.map { $0 <= Date() } ?? true
            preview = response
            if let expirationDate = response.expirationDate, expirationDate > Date() {
                expirationTask = Task { [weak self] in
                    let delay = expirationDate.timeIntervalSinceNow
                    try? await Task.sleep(for: .seconds(delay))
                    guard !Task.isCancelled else { return }
                    self?.expirationPassed = true
                }
            }
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
        guard case .missing = pendingStore.readPendingRecipeShopping(scope: scope) else {
            await reloadPendingState()
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
            await reloadPendingState()
            if pendingStorageState == .missing {
                errorMessage = "This device could not save a retry record, so the shopping list was not changed."
            }
            return
        }
        pendingStorageState = .record(record)
        pendingRecord = record
        await send(record)
    }

    public func retryPendingConfirmation() async {
        guard let record = pendingRecord,
              record.scopeStorageKey == scope.storageKey else {
            errorMessage = "No saved confirmation matches the current household."
            return
        }
        guard case .record(let stored) = pendingStore.readPendingRecipeShopping(scope: scope),
              stored == record else {
            await reloadPendingState()
            errorMessage = "The saved confirmation changed or could not be checked. No request was sent."
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
                pendingStorageState = .missing
                pendingRecord = nil
                statusMessage = "Shopping list updated. Pantry quantities were not changed."
            } else {
                pendingStorageState = .record(record)
                statusMessage = "Shopping list updated. The saved retry record remains on this device; retrying it is idempotent."
            }
        } catch {
            if let apiError = error as? APIError, apiError.serverErrorCode == "STALE_PREVIEW" {
                if pendingStore.deletePendingRecipeShopping(scope: scope) {
                    pendingStorageState = .missing
                    pendingRecord = nil
                    preview = nil
                    statusMessage = "Inventory or shopping data changed. Load a fresh preview before confirming."
                } else {
                    pendingStorageState = .record(record)
                    errorMessage = "The preview is stale, and this device could not clear its saved request. Retry the same request or reload."
                }
            } else {
                errorMessage = "We couldn't confirm the result. The request is saved. Retry it without editing to avoid duplicate items."
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
