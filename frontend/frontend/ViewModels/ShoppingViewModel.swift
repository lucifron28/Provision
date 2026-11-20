import Foundation
import SwiftUI
import Combine

public enum ShoppingFilter: String, CaseIterable, Identifiable {
    case pending = "To Buy"
    case completed = "Purchased"
    case all = "All"

    public var id: String { rawValue }
}

public enum PurchasedGroceriesChoice: String, CaseIterable, Identifiable, Sendable {
    case unresolved
    case addToPantry
    case exclude

    public var id: String { rawValue }
}

public struct PurchasedGroceriesDraft {
    public var choice: PurchasedGroceriesChoice = .unresolved
    public var productSelection = ""
    public var newProductName = ""
    public var newProductUnit = ""
    public var quantity = ""
    public var storageLocationID: Int?
    public var hasExpirationDate = false
    public var expirationDate = Date()

    public init(item: ShoppingItem, products: [Product]) {
        newProductName = item.name
        if let linkedID = item.product_id, products.contains(where: { $0.id == linkedID }) {
            productSelection = String(linkedID)
        }
    }
}

public protocol PendingPurchasedGroceriesStore {
    func readPendingPurchasedGroceries(scope: HouseholdScope) -> PendingPurchasedGroceriesReadResult
    @discardableResult func savePendingPurchasedGroceries(
        _ record: PendingPurchasedGroceriesRecord,
        scope: HouseholdScope
    ) -> Bool
    @discardableResult func deletePendingPurchasedGroceries(scope: HouseholdScope) -> Bool
}

extension KeychainStore: PendingPurchasedGroceriesStore {}

@MainActor
public class ShoppingViewModel: ObservableObject {
    @Published public var items: [ShoppingItem] = []
    @Published public var filter: ShoppingFilter = .pending
    @Published public var newItemName: String = ""
    @Published public var newItemQuantity: Double = 1.0
    @Published public var products: [Product] = []
    @Published public var locations: [StorageLocation] = []
    @Published public var purchasedGroceriesDrafts: [Int: PurchasedGroceriesDraft] = [:]
    @Published public private(set) var pendingPurchasedGroceriesRecord: PendingPurchasedGroceriesRecord?
    @Published public private(set) var pendingPurchasedGroceriesState: PendingPurchasedGroceriesReadResult = .missing
    @Published public var isPreparingPurchasedReview = false
    @Published public var isReconcilingPurchasedGroceries = false

    @Published public var isLoading: Bool = false
    @Published public var isGenerating: Bool = false
    @Published public var errorMessage: String? = nil
    @Published public var toastMessage: String? = nil
    private var toastDismissTask: Task<Void, Never>? = nil

    public func showToast(_ message: String) {
        self.toastMessage = message
        toastDismissTask?.cancel()
        toastDismissTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 3_500_000_000)
            if !Task.isCancelled && self.toastMessage == message {
                self.toastMessage = nil
            }
        }
    }

    private let client: APIClient
    private let purchasedGroceriesStore: any PendingPurchasedGroceriesStore
    public let scope: HouseholdScope?
    public var isPreview: Bool
    public init(client: APIClient = .shared, isPreview: Bool = false, scope: HouseholdScope? = nil,
                purchasedGroceriesStore: (any PendingPurchasedGroceriesStore)? = nil) {
        self.client = client
        self.scope = scope
        self.isPreview = isPreview
        self.purchasedGroceriesStore = purchasedGroceriesStore ?? KeychainStore.shared
    }

    public var filteredItems: [ShoppingItem] {
        switch filter {
        case .all:
            return items
        case .pending:
            return items.filter { !$0.is_bought }
        case .completed:
            return items.filter { $0.is_bought }
        }
    }

    public var pendingCount: Int {
        items.filter { !$0.is_bought }.count
    }

    public var purchasedCount: Int {
        items.filter { $0.is_bought }.count
    }

    public var purchasedItemsNeedingReview: [ShoppingItem] {
        items.filter { $0.is_bought && $0.reconciliationStatus == "pending" }
    }

    public var reviewedPurchasedCount: Int {
        items.filter { $0.is_bought && $0.reconciliationStatus != "pending" }.count
    }

    public var canReviewPurchasedItems: Bool {
        !purchasedItemsNeedingReview.isEmpty && pendingPurchasedGroceriesState == .missing
    }

    public func loadItems() async {
        if isPreview { return }
        isLoading = true
        errorMessage = nil
        do {
            self.items = try await client.fetchShoppingList(expectedScope: scope)
        } catch {
            self.errorMessage = error.localizedDescription
        }

        self.isLoading = false
    }

    public func refreshFromServer() async {
        guard !isPreview else { return }
        guard let scope else {
            await loadItems()
            return
        }
        isLoading = true
        errorMessage = nil
        do {
            items = try await client.fetchShoppingListFromServer(scope: scope)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    public func addItem() async {
        let name = newItemName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }

        if isPreview {
            let mockItem = ShoppingItem(
                id: (items.map { $0.id }.max() ?? 0) + 1,
                name: name,
                product_id: nil,
                quantity: newItemQuantity,
                unit: "pcs",
                is_bought: false,
                notes: nil
            )
            self.items.insert(mockItem, at: 0)
            self.newItemName = ""
            self.newItemQuantity = 1.0
            showToast("Added \(name) to list")
            return
        }

        let createItem = ShoppingItemCreate(
            name: name,
            quantity: newItemQuantity,
            unit: "unit"
        )

        do {
            let item = try await client.createShoppingItem(createItem, expectedScope: scope)
            self.items.insert(item, at: 0)
            self.newItemName = ""
            self.newItemQuantity = 1.0
            showToast("Added \(item.name) to list")
        } catch {
            self.errorMessage = "Failed to add item: \(error.localizedDescription)"
        }
    }
    public func toggleItem(_ item: ShoppingItem) async {
        if isPreview {
            if let idx = items.firstIndex(where: { $0.id == item.id }) {
                items[idx].is_bought.toggle()
            }
            return
        }
        // Optimistic UI update
        if let idx = items.firstIndex(where: { $0.id == item.id }) {
            items[idx].is_bought.toggle()
        }

        do {
            let updated = try await client.toggleShoppingItem(id: item.id, expectedScope: scope)
            if let idx = items.firstIndex(where: { $0.id == item.id }) {
                items[idx] = updated
            }
        } catch {
            // Revert optimistic update
            if let idx = items.firstIndex(where: { $0.id == item.id }) {
                items[idx].is_bought.toggle()
            }
            self.errorMessage = "Failed to update item: \(error.localizedDescription)"
        }
    }

    public func deleteItem(_ item: ShoppingItem) async {
        if isPreview {
            items.removeAll { $0.id == item.id }
            showToast("Item deleted")
            return
        }
        let original = items
        items.removeAll { $0.id == item.id }
        do {
            try await client.deleteShoppingItem(id: item.id, expectedScope: scope)
            showToast("Item deleted")
        } catch {
            self.items = original
            self.errorMessage = "Failed to delete item: \(error.localizedDescription)"
        }
    }

    public func clearCompleted() async {
        if isPreview {
            items.removeAll { $0.is_bought && $0.reconciliationStatus != "pending" }
            showToast("Reviewed purchases cleared")
            return
        }
        do {
            try await client.clearCompletedShoppingItems(expectedScope: scope)
            showToast("Reviewed purchases cleared")
            await refreshFromServer()
        } catch {
            self.errorMessage = "Failed to clear completed items: \(error.localizedDescription)"
        }
    }

    public func loadPendingPurchasedGroceries() {
        guard let scope else {
            pendingPurchasedGroceriesRecord = nil
            pendingPurchasedGroceriesState = .missing
            return
        }
        pendingPurchasedGroceriesState = purchasedGroceriesStore.readPendingPurchasedGroceries(scope: scope)
        if case .record(let record) = pendingPurchasedGroceriesState {
            pendingPurchasedGroceriesRecord = record
        } else {
            pendingPurchasedGroceriesRecord = nil
        }
    }

    public func preparePurchasedReview() async {
        guard !isPreview else {
            loadPendingPurchasedGroceries()
            prepareDraftsForPendingPurchases()
            return
        }
        guard let scope else {
            errorMessage = "Choose a household before reviewing purchased groceries."
            return
        }
        isPreparingPurchasedReview = true
        errorMessage = nil
        do {
            async let serverItems = client.fetchShoppingListFromServer(scope: scope)
            async let householdProducts = client.fetchProducts(expectedScope: scope)
            async let householdLocations = client.fetchLocations(expectedScope: scope)
            let (freshItems, knownProducts, knownLocations) = try await (serverItems, householdProducts, householdLocations)
            items = freshItems
            products = knownProducts
            locations = knownLocations
            loadPendingPurchasedGroceries()
            prepareDraftsForPendingPurchases()
        } catch {
            errorMessage = "Unable to refresh purchased groceries: \(error.localizedDescription)"
        }
        isPreparingPurchasedReview = false
    }

    public func prepareDraftsForPendingPurchases() {
        for item in purchasedItemsNeedingReview where purchasedGroceriesDrafts[item.id] == nil {
            purchasedGroceriesDrafts[item.id] = PurchasedGroceriesDraft(item: item, products: products)
        }
        purchasedGroceriesDrafts = purchasedGroceriesDrafts.filter { id, _ in
            purchasedItemsNeedingReview.contains(where: { $0.id == id })
        }
    }

    public func submitPurchasedGroceries(_ request: ReconcilePurchasedItemsRequest) async {
        guard !isReconcilingPurchasedGroceries else { return }
        if isPreview {
            for resolution in request.items {
                guard let index = items.firstIndex(where: { $0.id == resolution.shopping_item_id }) else { continue }
                items[index].reconciliation_status = resolution.action == "add" ? "added_to_pantry" : "excluded"
            }
            purchasedGroceriesDrafts.removeAll()
            showToast("Purchase review saved")
            return
        }
        guard let scope else {
            errorMessage = "Choose a household before adding purchases to the pantry."
            return
        }
        loadPendingPurchasedGroceries()
        guard pendingPurchasedGroceriesState == .missing else {
            errorMessage = "Finish the saved pantry update before confirming a new purchase review."
            return
        }
        let record = PendingPurchasedGroceriesRecord(scopeStorageKey: scope.storageKey, request: request)
        guard purchasedGroceriesStore.savePendingPurchasedGroceries(record, scope: scope) else {
            loadPendingPurchasedGroceries()
            errorMessage = "The exact purchase review could not be saved securely. No pantry changes were sent."
            return
        }
        pendingPurchasedGroceriesRecord = record
        pendingPurchasedGroceriesState = .record(record)
        await sendPendingPurchasedGroceries(record, scope: scope)
    }

    public func retryPendingPurchasedGroceries() async {
        guard let scope,
              case .record(let record) = purchasedGroceriesStore.readPendingPurchasedGroceries(scope: scope),
              record.scopeStorageKey == scope.storageKey else {
            loadPendingPurchasedGroceries()
            return
        }
        pendingPurchasedGroceriesRecord = record
        pendingPurchasedGroceriesState = .record(record)
        await sendPendingPurchasedGroceries(record, scope: scope)
    }

    private func sendPendingPurchasedGroceries(_ record: PendingPurchasedGroceriesRecord,
                                               scope: HouseholdScope) async {
        guard record.scopeStorageKey == scope.storageKey else {
            errorMessage = "The saved pantry update belongs to a different household."
            return
        }
        isReconcilingPurchasedGroceries = true
        errorMessage = nil
        do {
            _ = try await client.reconcilePurchasedGroceries(record.request, scope: scope)
            guard purchasedGroceriesStore.deletePendingPurchasedGroceries(scope: scope) else {
                loadPendingPurchasedGroceries()
                errorMessage = "The pantry update was accepted. Retry the saved request to verify its result."
                isReconcilingPurchasedGroceries = false
                await refreshFromServer()
                return
            }
            pendingPurchasedGroceriesRecord = nil
            pendingPurchasedGroceriesState = .missing
            purchasedGroceriesDrafts.removeAll()
            showToast("Purchased groceries added to pantry review")
            await refreshFromServer()
        } catch let error as APIError {
            if case .http(let status, _, _) = error, [404, 409, 422].contains(status) {
                _ = purchasedGroceriesStore.deletePendingPurchasedGroceries(scope: scope)
                pendingPurchasedGroceriesRecord = nil
                pendingPurchasedGroceriesState = .missing
                errorMessage = "The purchase review was rejected because household data changed. Refresh and review it again."
                await refreshFromServer()
            } else {
                loadPendingPurchasedGroceries()
                errorMessage = "The pantry update result is unknown. Retry the saved request before starting another review."
            }
        } catch {
            loadPendingPurchasedGroceries()
            errorMessage = "The pantry update result is unknown. Retry the saved request before starting another review."
        }
        isReconcilingPurchasedGroceries = false
    }

    public func autoGenerateSuggestions() async {
        if isPreview {
            showToast("Generated 2 low-stock suggestions")
            return
        }
        isGenerating = true
        errorMessage = nil

        do {
            let suggestions = try await client.generateShoppingSuggestions(threshold: 2.0, expectedScope: scope)
            showToast("Generated \(suggestions.count) low-stock suggestions")
            await loadItems()
        } catch {
            self.errorMessage = "Failed to generate suggestions: \(error.localizedDescription)"
        }

        self.isGenerating = false
    }
}
