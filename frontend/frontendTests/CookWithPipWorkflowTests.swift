import Foundation
import XCTest
@testable import frontend

private final class MemoryPendingRecipeShoppingStore: PendingRecipeShoppingStore {
    private var records: [String: PendingRecipeShoppingRecord] = [:]

    func readPendingRecipeShopping(scope: HouseholdScope) -> PendingRecipeShoppingRecord? {
        records[scope.storageKey]
    }

    @discardableResult
    func savePendingRecipeShopping(_ record: PendingRecipeShoppingRecord, scope: HouseholdScope) -> Bool {
        guard record.scopeStorageKey == scope.storageKey else { return false }
        records[scope.storageKey] = record
        return true
    }

    @discardableResult
    func deletePendingRecipeShopping(scope: HouseholdScope) -> Bool {
        records.removeValue(forKey: scope.storageKey)
        return true
    }
}

@MainActor
final class CookWithPipWorkflowTests: XCTestCase {
    private let scope = HouseholdScope(userID: 41, householdID: 52, serverID: "https://provision.test/api/v1")

    func testShoppingRetryUsesSavedExactRequestAndHouseholdScopedStore() async throws {
        let service = CookWithPipUITestService(scenario: "shopping-retry")
        let recipe = try await service.fetchRecipe(id: 301, scope: scope)
        let store = MemoryPendingRecipeShoppingStore()
        let viewModel = RecipeShoppingReviewViewModel(recipe: recipe, scope: scope,
                                                       service: service, pendingStore: store)

        await viewModel.load()
        viewModel.targetQuantityTexts[901] = "100.123456"
        viewModel.consolidateIngredientIDs.insert(914)
        await viewModel.confirmSelectedLines()

        let pending = try XCTUnwrap(store.readPendingRecipeShopping(scope: scope))
        XCTAssertEqual(pending.confirmation.accepted_lines.first?.target_quantity.value,
                       Decimal(string: "100.123456"))
        XCTAssertEqual(pending.confirmation.accepted_lines.first(where: { $0.ingredient_id == 914 })?.consolidate_existing,
                       true)
        XCTAssertTrue(viewModel.errorMessage?.contains("Network connection failed") == true)
        XCTAssertNil(store.readPendingRecipeShopping(scope: HouseholdScope(
            userID: 41, householdID: 53, serverID: "https://provision.test/api/v1"
        )))

        await viewModel.retryPendingConfirmation()

        XCTAssertNotNil(viewModel.confirmationResult)
        XCTAssertNil(store.readPendingRecipeShopping(scope: scope))
        let requests = await service.recordedConfirmations()
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests[0], requests[1])
    }

    func testStaleShoppingPreviewClearsSavedRequestAndRequiresRefresh() async throws {
        let service = CookWithPipUITestService(scenario: "shopping-stale")
        let recipe = try await service.fetchRecipe(id: 301, scope: scope)
        let store = MemoryPendingRecipeShoppingStore()
        let viewModel = RecipeShoppingReviewViewModel(recipe: recipe, scope: scope,
                                                       service: service, pendingStore: store)

        await viewModel.load()
        await viewModel.confirmSelectedLines()

        XCTAssertNil(viewModel.pendingRecord)
        XCTAssertNil(store.readPendingRecipeShopping(scope: scope))
        XCTAssertNil(viewModel.preview)
        XCTAssertTrue(viewModel.statusMessage?.contains("Load a fresh preview") == true)
        XCTAssertFalse(viewModel.canConfirm)

        await viewModel.refreshPreview()
        XCTAssertNotNil(viewModel.preview)
    }

    func testShoppingSafetyBlocksUnknownAndRequiresReviewAcknowledgement() async throws {
        let blockedService = CookWithPipUITestService(scenario: "shopping-blocked")
        let blockedRecipe = try await blockedService.fetchRecipe(id: 301, scope: scope)
        let blocked = RecipeShoppingReviewViewModel(recipe: blockedRecipe, scope: scope,
                                                     service: blockedService,
                                                     pendingStore: MemoryPendingRecipeShoppingStore())
        await blocked.load()
        XCTAssertFalse(blocked.canConfirm)

        let reviewService = CookWithPipUITestService(scenario: "shopping-review-required")
        let reviewRecipe = try await reviewService.fetchRecipe(id: 301, scope: scope)
        let review = RecipeShoppingReviewViewModel(recipe: reviewRecipe, scope: scope,
                                                    service: reviewService,
                                                    pendingStore: MemoryPendingRecipeShoppingStore())
        await review.load()
        XCTAssertFalse(review.canConfirm)
        review.safetyReviewAcknowledged = true
        XCTAssertTrue(review.canConfirm)
    }

    func testPreferencesAndProductLabelReviewKeepServerRevisions() async throws {
        let service = CookWithPipUITestService()
        let preferences = CookWithPipPreferencesViewModel(scope: scope, service: service)
        await preferences.load()
        XCTAssertEqual(preferences.profile?.revision, 2)
        preferences.preferences.preferred_regions = ["Bicol"]
        await preferences.save()
        XCTAssertEqual(preferences.profile?.revision, 3)
        XCTAssertEqual(preferences.profile?.preferences.preferred_regions, ["Bicol"])

        let labels = ProductLabelReviewViewModel(productID: 9903, scope: scope, service: service)
        await labels.load()
        XCTAssertEqual(labels.mapping?.version, 1)
        labels.searchText = "kangkong"
        await labels.searchIngredients()
        XCTAssertEqual(labels.searchResults.first?.id, 9202)
        labels.mappingMode = .composite
        labels.selectedIngredientIDs = [9201, 9202]
        labels.mappingVerified = true
        labels.mappingCompositionKnown = true
        let didSaveMapping = await labels.saveMapping()
        XCTAssertTrue(didSaveMapping)
        XCTAssertEqual(labels.mapping?.version, 2)
        XCTAssertEqual(labels.mapping?.component_ingredient_ids, [9201, 9202])
        labels.sourceReference = "Package label, ingredients panel"
        labels.setAllergen(.milk, disposition: "declared")
        labels.labelCompositionKnown = true
        let didSaveLabel = await labels.saveLabel()
        XCTAssertTrue(didSaveLabel)
        XCTAssertEqual(labels.label?.mapping_version, 2)
        XCTAssertEqual(labels.label?.revision, 1)
        XCTAssertEqual(labels.label?.declared_allergens, ["milk"])
        XCTAssertTrue(labels.label?.current_for_product == true)
    }
}
