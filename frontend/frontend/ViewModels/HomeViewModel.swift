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
