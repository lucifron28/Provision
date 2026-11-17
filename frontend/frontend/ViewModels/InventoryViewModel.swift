import Foundation
import SwiftUI
import Combine

public enum InventoryQuickFilter: String, CaseIterable, Identifiable, Sendable {
    case all = "All"
    case expiringSoon = "Expiring Soon"
    case lowStock = "Low Stock"
    case outOfStock = "Out of Stock"
    
    public var id: String { rawValue }
    public var title: String { rawValue }
    
    public var icon: String {
        switch self {
        case .all: return "square.grid.2x2"
        case .expiringSoon: return "clock.badge.exclamationmark"
        case .lowStock: return "exclamationmark.triangle"
        case .outOfStock: return "archivebox"
        }
    }
}

public enum InventorySortOption: String, CaseIterable, Identifiable, Sendable {
    case nameAsc = "Name (A–Z)"
    case nameDesc = "Name (Z–A)"
    case expirationSoonest = "Expiration (Soonest)"
    case stockLowest = "Stock (Lowest)"
    case stockHighest = "Stock (Highest)"

    public var id: String { rawValue }
}

public protocol PendingManualInventoryIntakeStore {
    func readPendingManualInventoryIntake(scope: HouseholdScope) -> PendingManualInventoryIntakeReadResult
    @discardableResult func savePendingManualInventoryIntake(_ record: PendingManualInventoryIntakeRecord,
                                                              scope: HouseholdScope) -> Bool
    @discardableResult func deletePendingManualInventoryIntake(scope: HouseholdScope) -> Bool
}

extension KeychainStore: PendingManualInventoryIntakeStore {}

public protocol PendingInventoryActionStore {
    func readPendingInventoryAction(scope: HouseholdScope) -> PendingInventoryActionReadResult
    @discardableResult func savePendingInventoryAction(_ record: PendingInventoryActionRecord,
                                                        scope: HouseholdScope) -> Bool
    @discardableResult func deletePendingInventoryAction(scope: HouseholdScope) -> Bool
}

extension KeychainStore: PendingInventoryActionStore {}

@MainActor
public class InventoryViewModel: ObservableObject {
    @Published public var products: [Product] = []
    @Published public var locations: [StorageLocation] = []
    
    @Published public var searchText: String = ""
    @Published public var selectedCategory: String? = nil
    @Published public var selectedLocationId: Int? = nil
    @Published public var activeQuickFilter: InventoryQuickFilter = .all
    @Published public var sortOption: InventorySortOption = .nameAsc
    @Published public var productExpirations: [Int: Int] = [:]
    // Detail view state
    @Published public var selectedProduct: Product? = nil
    @Published public var productBatches: [InventoryBatch] = []
    
    @Published public var isLoading: Bool = false
    @Published public var isDetailLoading: Bool = false
    @Published public var isOffline: Bool = false
    @Published public var errorMessage: String? = nil
    @Published public var toastMessage: String? = nil
    @Published public private(set) var pendingManualIntakeRecord: PendingManualInventoryIntakeRecord?
    @Published public private(set) var pendingManualIntakeState: PendingManualInventoryIntakeReadResult = .missing
    @Published public private(set) var pendingInventoryActionRecord: PendingInventoryActionRecord?
    @Published public private(set) var pendingInventoryActionState: PendingInventoryActionReadResult = .missing
    @Published public private(set) var isRecoveringPendingInventoryAction = false
    private let client: APIClient
    private let pendingManualIntakeStore: any PendingManualInventoryIntakeStore
    private let pendingInventoryActionStore: any PendingInventoryActionStore
    public let scope: HouseholdScope?
    public var isPreview: Bool
    
    public init(client: APIClient = .shared, isPreview: Bool = false, scope: HouseholdScope? = nil,
                pendingManualIntakeStore: (any PendingManualInventoryIntakeStore)? = nil,
                pendingInventoryActionStore: (any PendingInventoryActionStore)? = nil) {
        self.client = client
        self.scope = scope
        self.isPreview = isPreview
        self.pendingManualIntakeStore = pendingManualIntakeStore ?? KeychainStore.shared
        self.pendingInventoryActionStore = pendingInventoryActionStore ?? KeychainStore.shared
    }
    
    public var categories: [String] {
        let cats = Set(products.compactMap { $0.category }).sorted()
        return cats
    }
    
    public var filteredProducts: [Product] {
        let filtered = products.filter { product in
            let matchesSearch = searchText.isEmpty ||
                product.name.localizedCaseInsensitiveContains(searchText) ||
                (product.brand?.localizedCaseInsensitiveContains(searchText) ?? false) ||
                (product.category?.localizedCaseInsensitiveContains(searchText) ?? false) ||
                (product.barcode?.contains(searchText) ?? false)
            
            let matchesCategory = selectedCategory == nil || product.category == selectedCategory
            
            let daysUntilExp = product.daysUntilExpiration ?? productExpirations[product.id]
            let matchesQuickFilter: Bool
            switch activeQuickFilter {
            case .all:
                matchesQuickFilter = true
            case .expiringSoon:
                matchesQuickFilter = (daysUntilExp != nil && daysUntilExp! <= 7)
            case .lowStock:
                let stock = product.total_remaining_quantity ?? 0
                matchesQuickFilter = product.isLowStock || (stock > 0 && stock <= 2)
            case .outOfStock:
                let stock = product.total_remaining_quantity ?? 0
                matchesQuickFilter = product.isOutOfStock || stock <= 0
            }
            
            return matchesSearch && matchesCategory && matchesQuickFilter
        }

        return filtered.sorted { a, b in
            switch sortOption {
            case .nameAsc:
                return a.name.localizedCaseInsensitiveCompare(b.name) == .orderedAscending
            case .nameDesc:
                return a.name.localizedCaseInsensitiveCompare(b.name) == .orderedDescending
            case .expirationSoonest:
                let expA = a.daysUntilExpiration ?? productExpirations[a.id] ?? 9999
                let expB = b.daysUntilExpiration ?? productExpirations[b.id] ?? 9999
                return expA < expB
            case .stockLowest:
                let stockA = a.total_remaining_quantity ?? 0
                let stockB = b.total_remaining_quantity ?? 0
                return stockA < stockB
            case .stockHighest:
                let stockA = a.total_remaining_quantity ?? 0
                let stockB = b.total_remaining_quantity ?? 0
                return stockA > stockB
            }
        }
    }
    
    public func applyFilter(_ filter: InventoryQuickFilter) {
        self.activeQuickFilter = filter
    }
    
    public func loadData() async {
        if isPreview { return }
        isLoading = true
        errorMessage = nil
        do {
            async let prodsTask = client.fetchProducts(expectedScope: scope)
            async let locsTask = client.fetchLocations(expectedScope: scope)
            async let expiringTask = client.fetchExpiringSoon(days: 14, expectedScope: scope)
            
            let (prods, locs) = try await (prodsTask, locsTask)
            var expirations: [Int: Int] = [:]
            if let expiring = try? await expiringTask {
                for item in expiring {
                    if let existing = expirations[item.product_id] {
                        expirations[item.product_id] = min(existing, item.days_until_expiration)
                    } else {
                        expirations[item.product_id] = item.days_until_expiration
                    }
                }
            }
            self.productExpirations = expirations
            self.products = prods.map { prod in
                var p = prod
                if let days = expirations[prod.id] {
                    p.daysUntilExpiration = days
                }
                return p
            }
            self.locations = locs
        } catch {
            self.errorMessage = error.localizedDescription
        }
        self.isOffline = await client.isOfflineMode
        self.isLoading = false
    }
    
    public func selectProduct(_ product: Product) async {
        let current = products.first(where: { $0.id == product.id }) ?? product
        self.selectedProduct = current
        if isPreview { return }
        self.isDetailLoading = true
        do {
            let batches = try await client.fetchBatches(productId: current.id, activeOnly: true, expectedScope: scope)
            // Sort FEFO (Earliest expiration first)
            self.productBatches = batches.sorted {
                ($0.expiration_date ?? "9999-12-31") < ($1.expiration_date ?? "9999-12-31")
            }
        } catch {
            self.errorMessage = "Failed to load product batches: \(error.localizedDescription)"
        }
        
        self.isDetailLoading = false
    }
    
    public func consumeProduct(productId: Int, quantity: Double, reason: String? = "Household consumption") async -> Bool {
        if isPreview {
            self.toastMessage = "Successfully consumed \(String(format: "%.1f", quantity)) units"
            return true
        }
        let request = ConsumeRequest(product_id: productId, quantity: quantity, reason: reason)
        return await submitInventoryAction(.consume(request))
    }
    
    public func discardBatch(batchId: Int, quantity: Double? = nil, reason: String? = "Spoiled / Expired",
                             expectedUpdatedAt: String? = nil) async -> Bool {
        if isPreview {
            self.toastMessage = "Batch discarded"
            if let quantity, let index = productBatches.firstIndex(where: { $0.id == batchId }) {
                productBatches[index].remaining_quantity = max(0, productBatches[index].remaining_quantity - quantity)
                if productBatches[index].remaining_quantity == 0 { productBatches.remove(at: index) }
            } else {
                self.productBatches.removeAll { $0.id == batchId }
            }
            return true
        }
        let request = DiscardRequest(reason: reason, quantity: quantity, expected_updated_at: expectedUpdatedAt)
        return await submitInventoryAction(.discard(batchID: batchId, request: request))
    }
    
    public func adjustBatch(batchId: Int, newQuantity: Double, reason: String = "Physical count adjustment",
                            expectedUpdatedAt: String? = nil) async -> Bool {
        if isPreview {
            self.toastMessage = "Batch adjusted to \(newQuantity)"
            if let idx = self.productBatches.firstIndex(where: { $0.id == batchId }) {
                self.productBatches[idx].remaining_quantity = newQuantity
            }
            return true
        }
        let request = AdjustmentRequest(new_remaining_quantity: newQuantity, reason: reason,
                                        expected_updated_at: expectedUpdatedAt)
        return await submitInventoryAction(.adjust(batchID: batchId, request: request))
    }

    public func loadPendingInventoryAction() {
        guard let scope else {
            updatePendingInventoryActionState(.missing)
            return
        }
        updatePendingInventoryActionState(pendingInventoryActionStore.readPendingInventoryAction(scope: scope))
    }

    public func retryPendingInventoryAction() async -> Bool {
        guard let scope else {
            errorMessage = "Choose a household before retrying this inventory action."
            return false
        }
        guard case .record(let record) = pendingInventoryActionStore.readPendingInventoryAction(scope: scope),
              record.scopeStorageKey == scope.storageKey else {
            loadPendingInventoryAction()
            errorMessage = "The saved inventory action could not be verified. No request was sent."
            return false
        }
        updatePendingInventoryActionState(.record(record))
        if await client.isOfflineMode {
            errorMessage = "You're offline. Reconnect before retrying the saved inventory action."
            return false
        }
        return await sendPendingInventoryAction(record, scope: scope)
    }

    private func submitInventoryAction(_ action: PendingInventoryAction) async -> Bool {
        guard let scope else {
            errorMessage = "A verified household is required before changing inventory."
            return false
        }
        if await client.isOfflineMode {
            errorMessage = "You're offline. Reconnect before changing inventory."
            return false
        }
        switch pendingInventoryActionStore.readPendingInventoryAction(scope: scope) {
        case .missing:
            break
        case .record(let record):
            updatePendingInventoryActionState(.record(record))
            errorMessage = "A saved inventory action needs an exact retry before another stock change."
            return false
        case .corrupt:
            updatePendingInventoryActionState(.corrupt)
            errorMessage = "A saved inventory action could not be read. No new request was sent."
            return false
        case .unavailable:
            updatePendingInventoryActionState(.unavailable)
            errorMessage = "Secure saved-request storage is unavailable. No stock change was sent."
            return false
        }
        let record = PendingInventoryActionRecord(scopeStorageKey: scope.storageKey, action: action)
        guard pendingInventoryActionStore.savePendingInventoryAction(record, scope: scope) else {
            loadPendingInventoryAction()
            errorMessage = "This device could not save a retry record, so inventory was not changed."
            return false
        }
        updatePendingInventoryActionState(.record(record))
        return await sendPendingInventoryAction(record, scope: scope)
    }

    private func sendPendingInventoryAction(_ record: PendingInventoryActionRecord,
                                            scope: HouseholdScope) async -> Bool {
        guard record.scopeStorageKey == scope.storageKey else {
            errorMessage = "The saved inventory action belongs to a different household."
            return false
        }
        isRecoveringPendingInventoryAction = true
        errorMessage = nil
        do {
            switch record.action {
            case .consume(let request):
                let result = try await client.consumeProduct(
                    productId: request.product_id, quantity: request.quantity, reason: request.reason,
                    notes: request.notes, idempotencyKey: request.idempotency_key, expectedScope: scope
                )
                toastMessage = "Consumed \(String(format: "%.2f", result.total_consumed)) units"
            case .discard(let batchID, let request):
                _ = try await client.discardBatch(
                    batchId: batchID, reason: request.reason, notes: request.notes, quantity: request.quantity,
                    expectedUpdatedAt: request.expected_updated_at, idempotencyKey: request.idempotency_key,
                    expectedScope: scope
                )
                toastMessage = "Discarded stock was recorded"
            case .adjust(let batchID, let request):
                _ = try await client.adjustBatch(
                    batchId: batchID, newQuantity: request.new_remaining_quantity, reason: request.reason,
                    notes: request.notes, expectedUpdatedAt: request.expected_updated_at,
                    idempotencyKey: request.idempotency_key, expectedScope: scope
                )
                toastMessage = "Stock count adjustment saved"
            }
            if pendingInventoryActionStore.deletePendingInventoryAction(scope: scope) {
                updatePendingInventoryActionState(.missing)
            } else {
                updatePendingInventoryActionState(.record(record))
                toastMessage = "Inventory changed. Retry the saved action to confirm it safely."
            }
            await refreshInventoryAfterStockChange()
            isRecoveringPendingInventoryAction = false
            return true
        } catch {
            if Self.isDefinitiveNoWriteFailure(error),
               pendingInventoryActionStore.deletePendingInventoryAction(scope: scope) {
                updatePendingInventoryActionState(.missing)
                errorMessage = "The server rejected this request before changing stock. Refresh the batch and try again. \(error.localizedDescription)"
            } else {
                updatePendingInventoryActionState(.record(record))
                errorMessage = "We couldn't confirm the result. Retry this exact saved action before editing it."
            }
            isRecoveringPendingInventoryAction = false
            return false
        }
    }

    private func refreshInventoryAfterStockChange() async {
        await loadData()
        if let selectedProduct, let updated = products.first(where: { $0.id == selectedProduct.id }) {
            await selectProduct(updated)
        }
    }

    private func updatePendingInventoryActionState(_ state: PendingInventoryActionReadResult) {
        pendingInventoryActionState = state
        if case .record(let record) = state {
            pendingInventoryActionRecord = record
        } else {
            pendingInventoryActionRecord = nil
        }
    }

    private static func isDefinitiveNoWriteFailure(_ error: Error) -> Bool {
        guard case APIError.http(let status, _, _) = error else { return false }
        return [400, 404, 409, 422].contains(status)
    }
    
    public func updateProductMetadata(productId: Int, update: ProductUpdate) async -> Bool {
        if isPreview {
            if var sel = selectedProduct, sel.id == productId {
                if let n = update.name { sel.name = n }
                if let b = update.brand { sel.brand = b }
                if let c = update.category { sel.category = c }
                if let u = update.unit { sel.unit = u }
                self.selectedProduct = sel
            }
            if let idx = products.firstIndex(where: { $0.id == productId }) {
                if let n = update.name { products[idx].name = n }
                if let b = update.brand { products[idx].brand = b }
                if let c = update.category { products[idx].category = c }
                if let u = update.unit { products[idx].unit = u }
            }
            self.toastMessage = "Product updated successfully"
            return true
        }
        do {
            let updated = try await client.updateProduct(id: productId, update: update, expectedScope: scope)
            self.toastMessage = "Product updated successfully"
            
            await loadData()
            await selectProduct(updated)
            return true
        } catch {
            self.errorMessage = error.localizedDescription
            return false
        }
    }
    
    public func createManualInventory(product: ProductCreate?, productId: Int?, batch: InventoryBatchCreate) async -> Bool {
        if isPreview {
            self.toastMessage = "Inventory added successfully"
            return true
        }
        let request = ManualInventoryIntakeRequest(
            productID: product == nil ? productId : nil,
            newProduct: product,
            storageLocationID: batch.storage_location_id,
            purchasedAt: batch.purchased_at,
            expirationDate: batch.expiration_date,
            quantity: batch.original_quantity,
            unitPrice: batch.unit_price
        )
        return await submitManualInventoryIntake(request)
    }

    public func loadPendingManualInventoryIntake() {
        guard let scope else { return }
        updatePendingManualInventoryIntakeState(pendingManualIntakeStore.readPendingManualInventoryIntake(scope: scope))
    }

    public func retryPendingManualInventoryIntake() async -> Bool {
        guard let scope,
              case .record(let record) = pendingManualIntakeStore.readPendingManualInventoryIntake(scope: scope),
              record == pendingManualIntakeRecord,
              record.scopeStorageKey == scope.storageKey else {
            loadPendingManualInventoryIntake()
            errorMessage = "The saved inventory request changed or could not be verified. No request was sent."
            return false
        }
        return await sendManualInventoryIntake(record, scope: scope)
    }

    private func submitManualInventoryIntake(_ request: ManualInventoryIntakeRequest) async -> Bool {
        guard let scope else {
            errorMessage = "A verified household is required before adding inventory."
            return false
        }
        switch pendingManualIntakeStore.readPendingManualInventoryIntake(scope: scope) {
        case .missing:
            break
        case .record(let record):
            updatePendingManualInventoryIntakeState(.record(record))
            errorMessage = "A saved inventory request needs an exact retry before another item can be added."
            return false
        case .corrupt:
            updatePendingManualInventoryIntakeState(.corrupt)
            errorMessage = "A saved inventory request could not be read. No new request was sent."
            return false
        case .unavailable:
            updatePendingManualInventoryIntakeState(.unavailable)
            errorMessage = "Saved request storage is unavailable. No new request was sent."
            return false
        }
        let record = PendingManualInventoryIntakeRecord(scopeStorageKey: scope.storageKey, request: request)
        guard pendingManualIntakeStore.savePendingManualInventoryIntake(record, scope: scope) else {
            loadPendingManualInventoryIntake()
            errorMessage = "This device could not save a retry record, so inventory was not changed."
            return false
        }
        updatePendingManualInventoryIntakeState(.record(record))
        return await sendManualInventoryIntake(record, scope: scope)
    }

    private func sendManualInventoryIntake(_ record: PendingManualInventoryIntakeRecord,
                                           scope: HouseholdScope) async -> Bool {
        errorMessage = nil
        do {
            let result = try await client.createManualInventoryIntake(record.request, expectedScope: scope)
            await LocalCacheStore.shared.recordRecentlyUsedProduct(result.product_id, scope: scope)
            let deleted = pendingManualIntakeStore.deletePendingManualInventoryIntake(scope: scope)
            if deleted {
                updatePendingManualInventoryIntakeState(.missing)
                toastMessage = result.replayed
                    ? "Inventory was already added. The exact retry was confirmed."
                    : "Inventory added successfully"
            } else {
                updatePendingManualInventoryIntakeState(.record(record))
                toastMessage = "Inventory added. Its saved retry is still available and safe to repeat."
            }
            await loadData()
            if let selectedProduct, selectedProduct.id == result.product_id,
               let updated = products.first(where: { $0.id == result.product_id }) {
                await selectProduct(updated)
            }
            return true
        } catch {
            if Self.isDefinitiveNoWriteFailure(error),
               pendingManualIntakeStore.deletePendingManualInventoryIntake(scope: scope) {
                updatePendingManualInventoryIntakeState(.missing)
                errorMessage = "The server rejected this request before adding inventory. Correct the details and try again. \(error.localizedDescription)"
            } else {
                updatePendingManualInventoryIntakeState(.record(record))
                errorMessage = "We couldn't confirm the result. Retry this exact saved request before editing or adding another item."
            }
            return false
        }
    }

    private static func isDefinitiveNoWriteFailure(_ error: Error) -> Bool {
        guard case APIError.http(let status, _, _) = error else { return false }
        if status == 404 || status == 422 { return true }
        return status == 409 && (error as? APIError)?.serverErrorCode == "PRODUCT_BARCODE_ALREADY_EXISTS"
    }

    private func updatePendingManualInventoryIntakeState(_ state: PendingManualInventoryIntakeReadResult) {
        pendingManualIntakeState = state
        if case .record(let record) = state {
            pendingManualIntakeRecord = record
        } else {
            pendingManualIntakeRecord = nil
        }
    }
    
    public func restockProduct(productId: Int, batch: InventoryBatchCreate) async -> Bool {
        return await createManualInventory(product: nil, productId: productId, batch: batch)
    }
    
    public func updateBatchMetadata(batchId: Int, updates: [String: Any]) async -> Bool {
        if isPreview {
            self.toastMessage = "Batch updated successfully"
            return true
        }
        do {
            _ = try await client.updateBatchMetadata(batchId: batchId, updates: updates, expectedScope: scope)
            self.toastMessage = "Batch updated successfully"
            
            await loadData()
            if let sel = selectedProduct, let updated = products.first(where: { $0.id == sel.id }) {
                await selectProduct(updated)
            }
            return true
        } catch {
            self.errorMessage = error.localizedDescription
            return false
        }
    }
}
