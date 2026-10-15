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
    
    private let client: APIClient
    public var isPreview: Bool

    public init(client: APIClient = .shared, isPreview: Bool = false) {
        self.client = client
        self.isPreview = isPreview
    }

    public func loadDashboard() async {
        if isPreview {
            hasLoadedOnce = true
            return
        }
        isLoading = true
        errorMessage = nil

        do {
            async let valTask = client.fetchValuation()
            async let spendTask = client.fetchSpending()
            async let expiringTask = client.fetchExpiringSoon(days: 7)
            async let lowStockTask = client.fetchLowStock(threshold: 2.0)

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

    public enum PantryHealthStatus {
        case healthy
        case attention
        case urgent
        case empty

        public var title: String {
            switch self {
            case .healthy: return "Healthy"
            case .attention: return "Needs Attention"
            case .urgent: return "Action Needed"
            case .empty: return "No Stock"
            }
        }

        public var icon: String {
            switch self {
            case .healthy: return "checkmark.circle.fill"
            case .attention: return "clock.fill"
            case .urgent: return "exclamationmark.triangle.fill"
            case .empty: return "tray.fill"
            }
        }

        public var color: Color {
            switch self {
            case .healthy: return ProvisionTheme.provisionGreen
            case .attention: return ProvisionTheme.amberWarning
            case .urgent: return ProvisionTheme.redAlert
            case .empty: return ProvisionTheme.textSecondary
            }
        }
    }

    public var pantryStatus: PantryHealthStatus {
        if valuation.total_active_batches == 0 && valuation.total_active_products == 0 {
            return .empty
        }
        if expiringSoonItems.contains(where: { $0.days_until_expiration <= 1 }) {
            return .urgent
        }
        if !expiringSoonItems.isEmpty || !lowStockItems.isEmpty {
            return .attention
        }
        return .healthy
    }

    public func addLowStockToShoppingList(_ item: LowStockItem) async {
        if isPreview {
            self.alertMessage = "Added \(item.product_name) to Shopping List"
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
            _ = try await client.createShoppingItem(createItem)
            self.alertMessage = "Added \(item.product_name) to Shopping List"
        } catch {
            self.errorMessage = "Failed to add to shopping list: \(error.localizedDescription)"
        }
    }

    public func quickConsumeExpiringItem(_ item: ExpiringSoonItem, quantity: Double = 1.0) async {
        if isPreview {
            self.alertMessage = "Consumed \(item.product_name)"
            self.expiringSoonItems.removeAll { $0.batch_id == item.batch_id }
            return
        }
        do {
            _ = try await client.consumeProduct(
                productId: item.product_id,
                quantity: quantity,
                reason: "Quick consumption from Home screen"
            )
            self.alertMessage = "Consumed \(item.product_name)"
            await loadDashboard()
        } catch {
            self.errorMessage = "Failed to consume item: \(error.localizedDescription)"
        }
    }
}
