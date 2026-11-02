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
    @Published public var hasLoadedOnce: Bool = false
    @Published public var errorMessage: String? = nil
    private let client: APIClient
    private let scope: HouseholdScope?
    public var isPreview: Bool

    public init(client: APIClient = .shared, isPreview: Bool = false, scope: HouseholdScope? = nil) {
        self.client = client
        self.scope = scope
        self.isPreview = isPreview
    }

    public func loadAnalytics() async {
        if isPreview {
            hasLoadedOnce = true
            return
        }
        isLoading = true
        errorMessage = nil

        do {
            async let valTask = client.fetchValuation(expectedScope: scope)
            async let spendTask = client.fetchSpending(expectedScope: scope)
            async let wasteTask = client.fetchWaste(expectedScope: scope)
            async let expiringTask = client.fetchExpiringSoon(days: 14, expectedScope: scope)
            async let lowStockTask = client.fetchLowStock(threshold: 2.0, expectedScope: scope)

            let (val, spend, waste, expiring, lowStock) = try await (valTask, spendTask, wasteTask, expiringTask, lowStockTask)

            self.valuation = val
            self.spending = spend
            self.waste = waste
            self.expiringSoonItems = expiring
            self.lowStockItems = lowStock
            self.hasLoadedOnce = true
        } catch {
            self.errorMessage = error.localizedDescription
        }

        self.isLoading = false
    }

    public var isEmpty: Bool {
        valuation.total_active_batches == 0 &&
        valuation.total_active_products == 0 &&
        spending.sessions_count == 0 &&
        waste.total_waste_events == 0 &&
        expiringSoonItems.isEmpty &&
        lowStockItems.isEmpty
    }
}
