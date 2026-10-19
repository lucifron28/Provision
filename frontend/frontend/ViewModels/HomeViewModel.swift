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

    // MARK: - Pip Mascot & Contextual Guidance
    
    public var pipMascotAssetName: String {
        if !expiringSoonItems.isEmpty {
            return "pip_concerned"
        } else if !lowStockItems.isEmpty {
            return "pip_grocery"
        } else if valuation.total_active_batches == 0 && valuation.total_active_products == 0 {
            return "pip_guardian"
        } else {
            return "pip_proud"
        }
    }
    
    public var pipGuidanceTitle: String {
        if !expiringSoonItems.isEmpty {
            return "Expiring Soon"
        } else if !lowStockItems.isEmpty {
            return "Restock Needed"
        } else if valuation.total_active_batches == 0 && valuation.total_active_products == 0 {
            return "Pantry Ready"
        } else {
            return "All Fresh"
        }
    }
    
    public var pipGuidanceMessage: String {
        let expiringCount = expiringSoonItems.count
        let lowStockCount = lowStockItems.count
        
        if expiringCount > 0 {
            if expiringCount == 1 {
                return "1 item expiring soon — check it before it spoils!"
            } else {
                return "\(expiringCount) items expiring soon — check them before they spoil!"
            }
        } else if lowStockCount > 0 {
            if lowStockCount == 1 {
                return "1 pantry essential is running low."
            } else {
                return "\(lowStockCount) pantry essentials are running low."
            }
        } else if valuation.total_active_batches == 0 && valuation.total_active_products == 0 {
            return "Your pantry is empty. Scan grocery receipts or barcodes to begin tracking freshness."
        } else {
            return "All pantry stock is fresh! No urgent items need your attention."
        }
    }
    
    // MARK: - Chef Pip Recipe Suggestions
    
    public var chefPipRecipeIdeas: [String] {
        guard !expiringSoonItems.isEmpty else {
            return [
                "Your pantry is well-stocked and fresh! Plan your week's meals with ingredients on hand."
            ]
        }
        
        var ideas: [String] = []
        let topExpiring = Array(expiringSoonItems.prefix(2))
        
        for item in topExpiring {
            let name = item.product_name
            let lower = name.lowercased()
            
            if lower.contains("milk") {
                ideas.append("Make breakfast oats, pancakes, or creamy champorado with \(name).")
            } else if lower.contains("bread") {
                ideas.append("Toast \(name) for french toast, cheesy garlic slices, or homemade croutons.")
            } else if lower.contains("egg") {
                ideas.append("Whip up a quick vegetable scramble, tortang talong, or soft-boiled topping using \(name).")
            } else if lower.contains("tuna") {
                ideas.append("Toss \(name) into garlic aglio olio pasta or prepare a savory tuna spread.")
            } else if lower.contains("corned beef") || lower.contains("beef") {
                ideas.append("Sauté \(name) with diced potatoes and onions for hearty morning sinangag.")
            } else if lower.contains("cheese") {
                ideas.append("Melt \(name) over toasted bread or fold into a warm pasta dish.")
            } else if lower.contains("canton") || lower.contains("noodle") {
                ideas.append("Pair \(name) with a fried egg and fresh greens for a quick lunch.")
            } else if lower.contains("rice") {
                ideas.append("Turn \(name) into flavorful garlic fried rice or comforting arroz caldo.")
            } else if lower.contains("sauce") || lower.contains("soy") {
                ideas.append("Use \(name) as a savory marinade base for your next stir-fry or adobo.")
            } else {
                ideas.append("Incorporate \(name) into tonight's skillet or meal prep before expiration.")
            }
        }
        
        return ideas
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
            _ = try await client.createShoppingItem(createItem)
            showToast("Added \(item.product_name) to Shopping List")
        } catch {
            self.errorMessage = "Failed to add to shopping list: \(error.localizedDescription)"
        }
    }

    public func quickConsumeExpiringItem(_ item: ExpiringSoonItem, quantity: Double = 1.0) async {
        if isPreview {
            showToast("Consumed \(item.product_name)")
            self.expiringSoonItems.removeAll { $0.batch_id == item.batch_id }
            return
        }
        do {
            _ = try await client.consumeProduct(
                productId: item.product_id,
                quantity: quantity,
                reason: "Quick consumption from Home screen"
            )
            showToast("Consumed \(item.product_name)")
            await loadDashboard()
        } catch {
            self.errorMessage = "Failed to consume item: \(error.localizedDescription)"
        }
    }
}
