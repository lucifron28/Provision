import Foundation
import SwiftUI
import Combine

@MainActor
public class HomeViewModel: ObservableObject {
    @Published public var valuation: InventoryValuation = InventoryValuation()
    @Published public var spending: SpendingSummary = SpendingSummary()
    @Published public var expiringSoonItems: [ExpiringSoonItem] = []
    @Published public var lowStockItems: [LowStockItem] = []

    @Published public var isLoading: Bool = false
    @Published public var hasLoadedOnce: Bool = false
    @Published public var errorMessage: String? = nil
    @Published public var alertMessage: String? = nil
    @Published public private(set) var pendingInventoryActionRecord: PendingInventoryActionRecord?
    @Published public private(set) var pendingInventoryActionState: PendingInventoryActionReadResult = .missing
    @Published public private(set) var isRecoveringPendingInventoryAction = false
    private var toastDismissTask: Task<Void, Never>? = nil

    public func showToast(_ message: String) {
        self.alertMessage = message
        toastDismissTask?.cancel()
        toastDismissTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 3_500_000_000)
            if !Task.isCancelled && self.alertMessage == message {
                self.alertMessage = nil
            }
        }
    }

    private let client: APIClient
    private let scope: HouseholdScope?
    private let pendingInventoryActionStore: any PendingInventoryActionStore
    public var isPreview: Bool

    public init(client: APIClient = .shared, isPreview: Bool = false, scope: HouseholdScope? = nil,
                pendingInventoryActionStore: (any PendingInventoryActionStore)? = nil) {
        self.client = client
        self.scope = scope
        self.isPreview = isPreview
        self.pendingInventoryActionStore = pendingInventoryActionStore ?? KeychainStore.shared
    }

    public func loadDashboard() async {
        if isPreview {
            hasLoadedOnce = true
            return
        }
        isLoading = true
        errorMessage = nil

        do {
            async let valTask = client.fetchValuation(expectedScope: scope)
            async let spendTask = client.fetchSpending(expectedScope: scope)
            async let expiringTask = client.fetchExpiringSoon(days: 7, expectedScope: scope)
            async let lowStockTask = client.fetchLowStock(threshold: 2.0, expectedScope: scope)

            let (val, spend, expiring, lowStock) = try await (valTask, spendTask, expiringTask, lowStockTask)

            self.valuation = val
            self.spending = spend
            self.expiringSoonItems = expiring
            self.lowStockItems = lowStock
            self.hasLoadedOnce = true
        } catch {
            self.errorMessage = error.localizedDescription
        }

        self.isLoading = false
    }

    public var isPantryEmpty: Bool {
        valuation.total_active_batches == 0 && valuation.total_active_products == 0
    }

    /// Batches whose recorded expiration date has strictly passed (days_until_expiration < 0).
    public var expiredItems: [ExpiringSoonItem] {
        expiringSoonItems.filter { $0.days_until_expiration < 0 }
    }

    /// Batches approaching expiration within the horizon but not yet expired (days_until_expiration >= 0).
    public var approachingExpirationItems: [ExpiringSoonItem] {
        expiringSoonItems.filter { $0.days_until_expiration >= 0 }
    }

    public enum PantryHealthStatus {
        case empty
        case expired
        case urgent
        case attention
        case healthy

        public var title: String {
            switch self {
            case .empty: return "Pantry Empty"
            case .expired: return "Items Expired"
            case .urgent: return "Expiring Today"
            case .attention: return "Needs Attention"
            case .healthy: return "Pantry Healthy"
            }
        }

        public var icon: String {
            switch self {
            case .empty: return "tray.fill"
            case .expired: return "exclamationmark.octagon.fill"
            case .urgent: return "exclamationmark.triangle.fill"
            case .attention: return "clock.fill"
            case .healthy: return "checkmark.circle.fill"
            }
        }

        public var color: Color {
            switch self {
            case .empty: return ProvisionTheme.textSecondary
            case .expired: return ProvisionTheme.redAlert
            case .urgent: return ProvisionTheme.redAlert
            case .attention: return ProvisionTheme.amberWarning
            case .healthy: return ProvisionTheme.provisionGreen
            }
        }
    }

    public var pantryStatus: PantryHealthStatus {
        if isPantryEmpty {
            return .empty
        }
        if !expiredItems.isEmpty {
            return .expired
        }
        if approachingExpirationItems.contains(where: { $0.days_until_expiration <= 1 }) {
            return .urgent
        }
        if !approachingExpirationItems.isEmpty || !lowStockItems.isEmpty {
            return .attention
        }
        return .healthy
    }

    // MARK: - Pip Mascot & Contextual Guidance
    
    public var pipMascotAssetName: String {
        if isPantryEmpty {
            return "pip_guardian"
        } else if !expiredItems.isEmpty {
            return "pip_concerned"
        } else if !approachingExpirationItems.isEmpty {
            return "pip_concerned"
        } else if !lowStockItems.isEmpty {
            return "pip_grocery"
        } else {
            return "pip_proud"
        }
    }
    
    public var pipGuidanceTitle: String {
        if isPantryEmpty {
            return "Welcome to Provision"
        } else if !expiredItems.isEmpty {
            return "Check Expired Items"
        } else if !approachingExpirationItems.isEmpty {
            return "Expiring Soon"
        } else if !lowStockItems.isEmpty {
            return "Restock Needed"
        } else {
            return "Pantry Healthy"
        }
    }
    
    public var pipGuidanceMessage: String {
        let expiredCount = expiredItems.count
        let approachingCount = approachingExpirationItems.count
        let lowStockCount = lowStockItems.count
        
        if isPantryEmpty {
            return "Your pantry has no active stock. Scan grocery receipts or barcodes to begin tracking freshness."
        } else if expiredCount > 0 {
            if expiredCount == 1 {
                return "1 item has passed its recorded date. Review date labeling and safety guidelines before use."
            } else {
                return "\(expiredCount) items have passed their recorded dates. Review date labeling and safety guidelines before use."
            }
        } else if approachingCount > 0 {
            if approachingCount == 1 {
                return "1 item expiring soon — prioritize using it this week!"
            } else {
                return "\(approachingCount) items expiring soon — prioritize using them this week!"
            }
        } else if lowStockCount > 0 {
            if lowStockCount == 1 {
                return "1 pantry essential is running low."
            } else {
                return "\(lowStockCount) pantry essentials are running low."
            }
        } else {
            return "All tracked pantry items are well within their dates! No urgent items need attention."
        }
    }
    
    // MARK: - Chef Pip Recipe Suggestions
    
    /// Suggests zero-waste ideas using ONLY unexpired ingredients approaching expiration.
    /// Never recommends items that have already expired (days_until_expiration < 0).
    public var chefPipRecipeIdeas: [String] {
        if isPantryEmpty {
            return []
        }
        
        // When only expired items exist, never claim all items are in date; return no recipe suggestions
        if !expiredItems.isEmpty && approachingExpirationItems.isEmpty {
            return []
        }
        
        let usableExpiring = approachingExpirationItems
        guard !usableExpiring.isEmpty else {
            // Stocked pantry with no expiring items
            return [
                "All tracked items are well within date. Plan your meals using ingredients currently on hand."
            ]
        }
        var ideas: [String] = []
        let topExpiring = Array(usableExpiring.prefix(2))
        
        for item in topExpiring {
            let name = item.product_name
            let lower = name.lowercased()
            
            if lower.contains("milk") {
                ideas.append("Use \(name) in breakfast oats, pancakes, or creamy champorado (supply staples as needed).")
            } else if lower.contains("bread") {
                ideas.append("Toast \(name) for savory slices, french toast, or homemade croutons.")
            } else if lower.contains("egg") {
                ideas.append("Whip up a quick scramble, tortang talong, or egg topping with \(name).")
            } else if lower.contains("tuna") {
                ideas.append("Fold \(name) into a quick pasta aglio olio or savory sandwich spread.")
            } else if lower.contains("corned beef") || lower.contains("beef") {
                ideas.append("Sauté \(name) with diced onions for hearty sinangag or hash.")
            } else if lower.contains("cheese") {
                ideas.append("Melt \(name) over toasted bread or incorporate into a warm skillet.")
            } else if lower.contains("canton") || lower.contains("noodle") {
                ideas.append("Prepare \(name) with available pantry toppings for a quick meal.")
            } else if lower.contains("rice") {
                ideas.append("Turn \(name) into savory garlic fried rice or warm arroz caldo.")
            } else if lower.contains("sauce") || lower.contains("soy") {
                ideas.append("Use \(name) as a savory marinade base for your next skillet.")
            } else {
                ideas.append("Incorporate \(name) into your next meal before its expiration date.")
            }
        }
        
        return ideas
    }

    /// Distinct date-safety guidance for expired items (never treated as recipe ingredients).
    public var chefPipDateSafetyNotice: String? {
        guard !expiredItems.isEmpty else { return nil }
        let count = expiredItems.count
        if count == 1 {
            return "1 item is past its recorded date. Check package labeling, date code, and storage guidelines. When in doubt regarding perishables, discard safely."
        } else {
            return "\(count) items are past their recorded dates. Verify date labeling and food safety guidelines before deciding whether to use or discard."
        }
    }

    public func addLowStockToShoppingList(_ item: LowStockItem) async {
        if isPreview {
            showToast("Added \(item.product_name) to Shopping List")
            return
        }
        do {
            let createItem = ShoppingItemCreate(
                name: item.product_name,
                product_id: item.product_id,
                quantity: 1.0,
                unit: item.unit,
                notes: "Auto-added from Restock Needed"
            )
            _ = try await client.createShoppingItem(createItem, expectedScope: scope)
            showToast("Added \(item.product_name) to Shopping List")
        } catch {
            self.errorMessage = "Failed to add to shopping list: \(error.localizedDescription)"
        }
    }

    public func loadPendingInventoryAction() {
        guard let scope else {
            updatePendingInventoryActionState(.missing)
            return
        }
        updatePendingInventoryActionState(pendingInventoryActionStore.readPendingInventoryAction(scope: scope))
    }

    public func retryPendingInventoryAction() async -> Bool {
        guard let scope,
              case .record(let record) = pendingInventoryActionStore.readPendingInventoryAction(scope: scope),
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

    @discardableResult
    public func quickConsumeExpiringItem(_ item: ExpiringSoonItem, quantity: Double = 1.0) async -> Bool {
        if isPreview {
            showToast("Consumed \(item.product_name)")
            self.expiringSoonItems.removeAll { $0.batch_id == item.batch_id }
            return true
        }
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
            errorMessage = "Retry the saved inventory action before starting another stock change."
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
        let request = ConsumeRequest(product_id: item.product_id, quantity: quantity,
                                     reason: "Quick consumption from Home screen")
        let record = PendingInventoryActionRecord(scopeStorageKey: scope.storageKey, action: .consume(request))
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
                _ = try await client.consumeProduct(
                    productId: request.product_id, quantity: request.quantity, reason: request.reason,
                    notes: request.notes, idempotencyKey: request.idempotency_key, expectedScope: scope
                )
                showToast("Consumption saved")
            case .discard(let batchID, let request):
                _ = try await client.discardBatch(
                    batchId: batchID, reason: request.reason, notes: request.notes, quantity: request.quantity,
                    expectedUpdatedAt: request.expected_updated_at, idempotencyKey: request.idempotency_key,
                    expectedScope: scope
                )
                showToast("Discarded stock saved")
            case .adjust(let batchID, let request):
                _ = try await client.adjustBatch(
                    batchId: batchID, newQuantity: request.new_remaining_quantity, reason: request.reason,
                    notes: request.notes, expectedUpdatedAt: request.expected_updated_at,
                    idempotencyKey: request.idempotency_key, expectedScope: scope
                )
                showToast("Stock adjustment saved")
            }
            if pendingInventoryActionStore.deletePendingInventoryAction(scope: scope) {
                updatePendingInventoryActionState(.missing)
            } else {
                updatePendingInventoryActionState(.record(record))
                showToast("Inventory changed. Retry the saved action to confirm it safely.")
            }
            isRecoveringPendingInventoryAction = false
            await loadDashboard()
            return true
        } catch {
            if Self.isDefinitiveNoWriteFailure(error),
               pendingInventoryActionStore.deletePendingInventoryAction(scope: scope) {
                updatePendingInventoryActionState(.missing)
                errorMessage = "The server rejected this request before changing stock. Refresh the batch and try again."
            } else {
                updatePendingInventoryActionState(.record(record))
                errorMessage = "We couldn't confirm the result. Retry this exact saved action before editing it."
            }
            isRecoveringPendingInventoryAction = false
            return false
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
}
