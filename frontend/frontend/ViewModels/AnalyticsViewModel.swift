import Foundation
import SwiftUI
import Combine

@MainActor
public class AnalyticsViewModel: ObservableObject {
    @Published public var valuation: InventoryValuation = InventoryValuation()
    @Published public var spending: SpendingSummary = SpendingSummary()
    @Published public var waste: WasteSummary = WasteSummary()
    @Published public var expiringSoonItems: [ExpiringSoonItem] = []
    @Published public var lowStockItems: [LowStockItem] = []
    
    @Published public var isLoading: Bool = false
    @Published public var errorMessage: String? = nil
    
    private let client: APIClient
    
    public init(client: APIClient = .shared) {
        self.client = client
    }
    
    public func loadAnalytics() async {
        isLoading = true
        errorMessage = nil
        
        do {
            async let valTask = client.fetchValuation()
            async let spendTask = client.fetchSpending()
            async let wasteTask = client.fetchWaste()
            async let expiringTask = client.fetchExpiringSoon(days: 14)
            async let lowStockTask = client.fetchLowStock(threshold: 2.0)
            
            let (val, spend, waste, expiring, lowStock) = try await (valTask, spendTask, wasteTask, expiringTask, lowStockTask)
            
            self.valuation = val
            self.spending = spend
            self.waste = waste
            self.expiringSoonItems = expiring
            self.lowStockItems = lowStock
        } catch {
            self.errorMessage = error.localizedDescription
        }
        
        self.isLoading = false
    }
}
