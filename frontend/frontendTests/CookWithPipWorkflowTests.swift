import Foundation
import XCTest
import Security
@testable import frontend

private final class MemoryPendingRecipeShoppingStore: PendingRecipeShoppingStore {
    private var records: [String: PendingRecipeShoppingRecord] = [:]

    func readPendingRecipeShopping(scope: HouseholdScope) -> PendingRecipeShoppingReadResult {
        records[scope.storageKey].map(PendingRecipeShoppingReadResult.record) ?? .missing
    }

    @discardableResult
    func savePendingRecipeShopping(_ record: PendingRecipeShoppingRecord, scope: HouseholdScope) -> Bool {
        guard record.scopeStorageKey == scope.storageKey, records[scope.storageKey] == nil else { return false }
        records[scope.storageKey] = record
        return true
    }

    @discardableResult
    func deletePendingRecipeShopping(scope: HouseholdScope) -> Bool {
        records.removeValue(forKey: scope.storageKey)
        return true
    }
}

private final class FixedStatePendingRecipeShoppingStore: PendingRecipeShoppingStore {
    var state: PendingRecipeShoppingReadResult
    private(set) var saveCalls = 0

    init(_ state: PendingRecipeShoppingReadResult) { self.state = state }

    func readPendingRecipeShopping(scope: HouseholdScope) -> PendingRecipeShoppingReadResult { state }

    func savePendingRecipeShopping(_ record: PendingRecipeShoppingRecord, scope: HouseholdScope) -> Bool {
        saveCalls += 1
        return false
    }

    func deletePendingRecipeShopping(scope: HouseholdScope) -> Bool { false }
}

@MainActor
final class CookWithPipWorkflowTests: XCTestCase {
    private let scope = HouseholdScope(userID: 41, householdID: 52, serverID: "https://provision.test/api/v1")

    func testShoppingRetryUsesSavedExactRequestAndHouseholdScopedStore() async throws {
        let service = CookWithPipUITestService(scenario: "shopping-retry")
        let recipe = try await service.fetchRecipe(id: 305, scope: scope)
        let store = MemoryPendingRecipeShoppingStore()
        let viewModel = RecipeShoppingReviewViewModel(recipe: recipe, scope: scope,
                                                       service: service, pendingStore: store)

        await viewModel.load()
        viewModel.targetQuantityTexts[901] = "100.123456"
        viewModel.consolidateIngredientIDs.insert(914)
        await viewModel.confirmSelectedLines()

        guard case .record(let pending) = store.readPendingRecipeShopping(scope: scope) else {
            return XCTFail("Expected the exact confirmation to remain saved")
        }
        XCTAssertEqual(pending.confirmation.accepted_lines.first?.target_quantity.value,
                       Decimal(string: "100.123456"))
        XCTAssertEqual(pending.confirmation.accepted_lines.first(where: { $0.ingredient_id == 914 })?.consolidate_existing,
                       true)
        XCTAssertTrue(viewModel.errorMessage?.contains("Network connection failed") == true)
        XCTAssertEqual(store.readPendingRecipeShopping(scope: HouseholdScope(
            userID: 41, householdID: 53, serverID: "https://provision.test/api/v1"
        )), .missing)

        await viewModel.retryPendingConfirmation()

        XCTAssertNotNil(viewModel.confirmationResult)
        XCTAssertEqual(viewModel.confirmationResult?.created.compactMap(\.origin_recipe_id), [305, 305])
        XCTAssertEqual(store.readPendingRecipeShopping(scope: scope), .missing)
        let requests = await service.recordedConfirmations()
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests[0].idempotency_key, requests[1].idempotency_key)
        XCTAssertEqual(requests[0].preview_id, requests[1].preview_id)
        XCTAssertEqual(requests[0], requests[1])
    }

    func testStaleShoppingPreviewClearsSavedRequestAndRequiresRefresh() async throws {
        let service = CookWithPipUITestService(scenario: "shopping-stale")
        let recipe = try await service.fetchRecipe(id: 305, scope: scope)
        let store = MemoryPendingRecipeShoppingStore()
        let viewModel = RecipeShoppingReviewViewModel(recipe: recipe, scope: scope,
                                                       service: service, pendingStore: store)

        await viewModel.load()
        await viewModel.confirmSelectedLines()

        XCTAssertNil(viewModel.pendingRecord)
        XCTAssertEqual(store.readPendingRecipeShopping(scope: scope), .missing)
        XCTAssertNil(viewModel.preview)
        XCTAssertTrue(viewModel.statusMessage?.contains("Load a fresh preview") == true)
        XCTAssertFalse(viewModel.canConfirm)

        await viewModel.refreshPreview()
        XCTAssertNotNil(viewModel.preview)
    }

    func testShoppingSafetyBlocksUnknownAndRequiresReviewAcknowledgement() async throws {
        let blockedService = CookWithPipUITestService(scenario: "shopping-blocked")
        let blockedRecipe = try await blockedService.fetchRecipe(id: 305, scope: scope)
        let blocked = RecipeShoppingReviewViewModel(recipe: blockedRecipe, scope: scope,
                                                     service: blockedService,
                                                     pendingStore: MemoryPendingRecipeShoppingStore())
        await blocked.load()
        XCTAssertFalse(blocked.canConfirm)

        let reviewService = CookWithPipUITestService(scenario: "shopping-review-required")
        let reviewRecipe = try await reviewService.fetchRecipe(id: 305, scope: scope)
        let review = RecipeShoppingReviewViewModel(recipe: reviewRecipe, scope: scope,
                                                    service: reviewService,
                                                    pendingStore: MemoryPendingRecipeShoppingStore())
        await review.load()
        XCTAssertFalse(review.canConfirm)
        review.safetyReviewAcknowledged = true
        XCTAssertTrue(review.canConfirm)
    }
    func testExpiredAndMalformedShoppingPreviewsCannotPersistOrSend() async throws {
        for scenario in ["shopping-expired", "shopping-malformed-expiry"] {
            let service = CookWithPipUITestService(scenario: scenario)
            let recipe = try await service.fetchRecipe(id: 305, scope: scope)
            let store = MemoryPendingRecipeShoppingStore()
            let viewModel = RecipeShoppingReviewViewModel(recipe: recipe, scope: scope,
                                                            service: service, pendingStore: store)

            await viewModel.load()
            XCTAssertNotNil(viewModel.preview)
            XCTAssertTrue(viewModel.isExpired)
            XCTAssertFalse(viewModel.canConfirm)
            await viewModel.confirmSelectedLines()

            XCTAssertEqual(store.readPendingRecipeShopping(scope: scope), .missing)
            let confirmations = await service.recordedConfirmations()
            XCTAssertTrue(confirmations.isEmpty)
        }
    }
    func testOpenPreviewBecomesNonConfirmableWhenItExpires() async throws {
        let service = CookWithPipUITestService(scenario: "shopping-expiring-soon")
        let recipe = try await service.fetchRecipe(id: 305, scope: scope)
        let store = MemoryPendingRecipeShoppingStore()
        let viewModel = RecipeShoppingReviewViewModel(recipe: recipe, scope: scope,
                                                        service: service, pendingStore: store)

        await viewModel.load()
        XCTAssertTrue(viewModel.canConfirm)

        try await Task.sleep(for: .seconds(2.2))

        XCTAssertTrue(viewModel.isExpired)
        XCTAssertFalse(viewModel.canConfirm)
        await viewModel.confirmSelectedLines()
        XCTAssertEqual(store.readPendingRecipeShopping(scope: scope), .missing)
        let confirmations = await service.recordedConfirmations()
        XCTAssertTrue(confirmations.isEmpty)
    }


    func testCorruptAndUnavailablePendingStorageBlockNewShoppingRequests() async throws {
        let service = CookWithPipUITestService()
        let recipe = try await service.fetchRecipe(id: 305, scope: scope)

        for state in [PendingRecipeShoppingReadResult.corrupt, .unavailable] {
            let store = FixedStatePendingRecipeShoppingStore(state)
            let viewModel = RecipeShoppingReviewViewModel(recipe: recipe, scope: scope,
                                                           service: service, pendingStore: store)
            await viewModel.load()
            XCTAssertNil(viewModel.preview)
            XCTAssertFalse(viewModel.canConfirm)

            await viewModel.refreshPreview()
            await viewModel.confirmSelectedLines()

            XCTAssertNil(viewModel.preview)
            XCTAssertEqual(store.saveCalls, 0)
            let confirmations = await service.recordedConfirmations()
            XCTAssertTrue(confirmations.isEmpty)
        }

        let recoveringStore = FixedStatePendingRecipeShoppingStore(.unavailable)
        let recovering = RecipeShoppingReviewViewModel(recipe: recipe, scope: scope,
                                                        service: service, pendingStore: recoveringStore)
        await recovering.load()
        recoveringStore.state = .missing
        await recovering.reloadPendingState()
        XCTAssertEqual(recovering.pendingStorageState, .missing)
        XCTAssertNotNil(recovering.preview)
    }

    func testMemoryPendingStoreNeverReplacesAnExistingConfirmation() throws {
        let store = MemoryPendingRecipeShoppingStore()
        let first = PendingRecipeShoppingRecord(
            scopeStorageKey: scope.storageKey,
            recipeTitle: "First request",
            lines: [],
            confirmation: RecipeShoppingConfirmation(previewID: "preview-a", idempotencyKey: "key-a",
                                                    revision: 3, acceptedLines: [])
        )
        let second = PendingRecipeShoppingRecord(
            scopeStorageKey: scope.storageKey,
            recipeTitle: "Second request",
            lines: [],
            confirmation: RecipeShoppingConfirmation(previewID: "preview-b", idempotencyKey: "key-b",
                                                    revision: 4, acceptedLines: [])
        )

        XCTAssertTrue(store.savePendingRecipeShopping(first, scope: scope))
        XCTAssertFalse(store.savePendingRecipeShopping(second, scope: scope))
        guard case .record(let saved) = store.readPendingRecipeShopping(scope: scope) else {
            return XCTFail("Expected the first request to remain stored")
        }
        XCTAssertEqual(saved, first)
    }

    func testKeychainPendingConfirmationIsAddOnlyAndHouseholdScoped() throws {
        let scope = HouseholdScope(userID: Int.random(in: 1_000_000...2_000_000_000),
                                   householdID: Int.random(in: 2_000_000_001...2_100_000_000),
                                   serverID: UUID().uuidString)
        let store = KeychainStore.shared
        defer { _ = store.deletePendingRecipeShopping(scope: scope) }
        let first = makePendingRecord(scope: scope, previewID: "preview-original", key: "original-key-0001")
        let replacement = makePendingRecord(scope: scope, previewID: "preview-replacement", key: "replacement-key-0001")

        XCTAssertEqual(store.readPendingRecipeShopping(scope: scope), .missing)
        XCTAssertTrue(store.savePendingRecipeShopping(first, scope: scope))
        XCTAssertFalse(store.savePendingRecipeShopping(replacement, scope: scope))
        XCTAssertEqual(store.readPendingRecipeShopping(scope: scope), .record(first))
        XCTAssertEqual(store.readPendingRecipeShopping(scope: HouseholdScope(
            userID: scope.userID, householdID: scope.householdID + 1, serverID: scope.serverID
        )), .missing)
    }

    func testCorruptKeychainConfirmationIsNotReportedAsMissing() {
        let scope = HouseholdScope(userID: Int.random(in: 1_000_000...2_000_000_000),
                                   householdID: Int.random(in: 2_000_000_001...2_100_000_000),
                                   serverID: UUID().uuidString)
        let identity: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "mseuf.edu.ph.provision.auth",
            kSecAttrAccount as String: "pendingRecipeShopping-\(scope.storageKey)",
        ]
        var corruptItem = identity
        corruptItem[kSecValueData as String] = Data([0xFF, 0x00, 0xFE])
        corruptItem[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        XCTAssertEqual(SecItemAdd(corruptItem as CFDictionary, nil), errSecSuccess)
        defer { SecItemDelete(identity as CFDictionary) }

        XCTAssertEqual(KeychainStore.shared.readPendingRecipeShopping(scope: scope), .corrupt)
    }

    func testKeychainReadSeparatesMissingCorruptAndUnavailableStatuses() throws {
        let scope = HouseholdScope(userID: 41, householdID: 52, serverID: "keychain-status-test")
        let record = makePendingRecord(scope: scope, previewID: "preview-status", key: "status-key-0001")
        let data = try JSONEncoder().encode(record)

        XCTAssertEqual(KeychainStore.pendingRecipeShoppingReadResult(
            status: errSecItemNotFound, data: nil, scope: scope
        ), .missing)
        XCTAssertEqual(KeychainStore.pendingRecipeShoppingReadResult(
            status: errSecInteractionNotAllowed, data: nil, scope: scope
        ), .unavailable)
        XCTAssertEqual(KeychainStore.pendingRecipeShoppingReadResult(
            status: errSecSuccess, data: nil, scope: scope
        ), .unavailable)
        XCTAssertEqual(KeychainStore.pendingRecipeShoppingReadResult(
            status: errSecSuccess, data: Data([0xFF]), scope: scope
        ), .corrupt)
        XCTAssertEqual(KeychainStore.pendingRecipeShoppingReadResult(
            status: errSecSuccess, data: data, scope: scope
        ), .record(record))
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

    private func makePendingRecord(scope: HouseholdScope, previewID: String,
                                   key: String) -> PendingRecipeShoppingRecord {
        PendingRecipeShoppingRecord(
            scopeStorageKey: scope.storageKey,
            recipeTitle: "Synthetic garlic rice",
            lines: [],
            confirmation: RecipeShoppingConfirmation(
                previewID: previewID, idempotencyKey: key, revision: 1, acceptedLines: []
            )
        )
    }
}
