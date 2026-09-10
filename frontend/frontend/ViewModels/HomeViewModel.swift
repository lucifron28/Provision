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
    @Published public var errorMessage: String? = nil
    @Published public var alertMessage: String? = nil
    
    private let client: APIClient
    
    public init(client: APIClient = .shared) {
        self.client = client
    }
    
    public func loadDashboard() async {
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
        } catch {
            self.errorMessage = error.localizedDescription
        }
        
        self.isLoading = false
    }
    
    public func addLowStockToShoppingList(_ item: LowStockItem) async {
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
