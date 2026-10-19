import Foundation
import SwiftUI

// MARK: - Home, Inventory & Pip Guidance Unit Tests
// Scoped verification for adaptive UI/UX, Pip mascot insight,
// Chef Pip recipe ideas, and InventoryQuickFilter behavior.

@MainActor
public struct HomeInventoryAndPipTests {

    struct TestFailure: Error {
        let message: String
    }

    private static func assertTrue(_ condition: Bool, _ message: String) throws {
        if !condition {
            throw TestFailure(message: "ASSERTION FAILED: \(message)")
        }
    }

    private static func assertEquals<T: Equatable>(_ actual: T, _ expected: T, _ message: String) throws {
        if actual != expected {
            throw TestFailure(message: "EQUALS FAILED: expected '\(expected)', got '\(actual)'. \(message)")
        }
    }

    public static func runAllTests() async throws {
        print("=== RUNNING HOME, INVENTORY & PIP TESTS ===")
        try testPipMascotSelection()
        try testPipGuidanceMessage()
        try testChefPipRecipeIdeasWithRealExpiringProducts()
        try testInventoryQuickFilterAll()
        try testInventoryQuickFilterExpiringSoon()
        try testInventoryQuickFilterLowStock()
        try testInventoryQuickFilterOutOfStock()
        try testInventoryFilterCombinedWithSearchAndCategory()
        print("=== ALL HOME, INVENTORY & PIP TESTS PASSED ===")
    }

    // MARK: - Home & Pip Tests

    public static func testPipMascotSelection() throws {
        let vm = HomeViewModel(isPreview: true)

        // 1. Empty pantry -> pip_guardian
        vm.valuation = InventoryValuation(total_value: 0, total_active_batches: 0, total_active_products: 0)
        vm.expiringSoonItems = []
        vm.lowStockItems = []
        try assertEquals(vm.pipMascotAssetName, "pip_guardian", "Empty pantry should use pip_guardian")
        try assertEquals(vm.pipGuidanceTitle, "Pantry Ready", "Empty pantry guidance title")

        // 2. Expiring soon items exist -> pip_concerned
        vm.valuation = InventoryValuation(total_value: 5000, total_active_batches: 10, total_active_products: 8)
        vm.expiringSoonItems = PreviewData.expiringSoonItems
        try assertEquals(vm.pipMascotAssetName, "pip_concerned", "Expiring soon should use pip_concerned")
        try assertEquals(vm.pipGuidanceTitle, "Expiring Soon", "Expiring soon guidance title")

        // 3. No expiring items, but low stock items exist -> pip_grocery
        vm.expiringSoonItems = []
        vm.lowStockItems = PreviewData.lowStockItems
        try assertEquals(vm.pipMascotAssetName, "pip_grocery", "Low stock should use pip_grocery")
        try assertEquals(vm.pipGuidanceTitle, "Restock Needed", "Restock needed guidance title")

        // 4. Fully stocked and fresh -> pip_proud
        vm.lowStockItems = []
        try assertEquals(vm.pipMascotAssetName, "pip_proud", "Healthy pantry should use pip_proud")
        try assertEquals(vm.pipGuidanceTitle, "All Fresh", "All fresh guidance title")
    }

    public static func testPipGuidanceMessage() throws {
        let vm = HomeViewModel(isPreview: true)
        vm.valuation = InventoryValuation(total_value: 12000, total_active_batches: 20, total_active_products: 15)

        // Expiring items
        vm.expiringSoonItems = Array(PreviewData.expiringSoonItems.prefix(2))
        try assertTrue(vm.pipGuidanceMessage.contains("2 items expiring soon"), "Guidance message includes count")

        // 1 item expiring
        vm.expiringSoonItems = Array(PreviewData.expiringSoonItems.prefix(1))
        try assertTrue(vm.pipGuidanceMessage.contains("1 item expiring soon"), "Singular form for 1 item expiring")

        // No expiring, 3 low stock
        vm.expiringSoonItems = []
        vm.lowStockItems = PreviewData.lowStockItems
        try assertTrue(vm.pipGuidanceMessage.contains("pantry essentials are running low"), "Low stock guidance message")

        // Fresh
        vm.lowStockItems = []
        try assertTrue(vm.pipGuidanceMessage.contains("All pantry stock is fresh!"), "Fresh pantry message")
    }

    public static func testChefPipRecipeIdeasWithRealExpiringProducts() throws {
        let vm = HomeViewModel(isPreview: true)
        vm.expiringSoonItems = PreviewData.expiringSoonItems // Magnolia Milk, Gardenia Bread, Bounty Eggs

        let ideas = vm.chefPipRecipeIdeas
        try assertTrue(!ideas.isEmpty, "Chef Pip should generate recipe ideas")
        try assertTrue(ideas.count <= 2, "Chef Pip should highlight 1-2 top ideas")

        // First expiring item is Magnolia Fresh Milk
        let firstIdea = ideas[0]
        try assertTrue(firstIdea.contains("Magnolia Fresh Milk"), "Idea must reference real product name Magnolia Fresh Milk")
        try assertTrue(firstIdea.contains("oats") || firstIdea.contains("pancakes") || firstIdea.contains("champorado"), "Idea tailored to milk")

        // Second expiring item is Gardenia Classic White Bread
        if ideas.count > 1 {
            let secondIdea = ideas[1]
            try assertTrue(secondIdea.contains("Gardenia Classic White Bread"), "Idea must reference real product name Gardenia Classic White Bread")
            try assertTrue(secondIdea.contains("toast") || secondIdea.contains("croutons"), "Idea tailored to bread")
        }
    }

    // MARK: - Inventory Quick Filter Tests

    public static func testInventoryQuickFilterAll() throws {
        let vm = PreviewData.makeInventoryViewModel()
        vm.applyFilter(.all)

        try assertEquals(vm.activeQuickFilter, .all, "Active filter should be .all")
        try assertEquals(vm.filteredProducts.count, vm.products.count, "All filter should return all products")
    }

    public static func testInventoryQuickFilterExpiringSoon() throws {
        let vm = PreviewData.makeInventoryViewModel()
        vm.applyFilter(.expiringSoon)

        try assertEquals(vm.activeQuickFilter, .expiringSoon, "Active filter should be .expiringSoon")
        let filtered = vm.filteredProducts
        try assertTrue(!filtered.isEmpty, "Should find expiring soon products from preview data")

        for product in filtered {
            let days = product.daysUntilExpiration ?? vm.productExpirations[product.id]
            try assertTrue(days != nil && days! <= 7, "Product \(product.name) must expire in <= 7 days (got \(String(describing: days)))")
        }

        // Magnolia Milk (expires in 1d) and Gardenia Bread (expires in 2d) must be included
        try assertTrue(filtered.contains(where: { $0.id == 5 }), "Magnolia Milk must be in expiring soon")
        try assertTrue(filtered.contains(where: { $0.id == 7 }), "Gardenia Bread must be in expiring soon")
    }

    public static func testInventoryQuickFilterLowStock() throws {
        let vm = PreviewData.makeInventoryViewModel()
        vm.applyFilter(.lowStock)

        try assertEquals(vm.activeQuickFilter, .lowStock, "Active filter should be .lowStock")
        let filtered = vm.filteredProducts
        try assertTrue(!filtered.isEmpty, "Should find low stock products")

        for product in filtered {
            let stock = product.total_remaining_quantity ?? 0
            try assertTrue(product.isLowStock || (stock > 0 && stock <= 2), "Product \(product.name) stock \(stock) must be low stock")
        }
    }

    public static func testInventoryQuickFilterOutOfStock() throws {
        let vm = PreviewData.makeInventoryViewModel()
        vm.applyFilter(.outOfStock)

        try assertEquals(vm.activeQuickFilter, .outOfStock, "Active filter should be .outOfStock")
        let filtered = vm.filteredProducts

        for product in filtered {
            let stock = product.total_remaining_quantity ?? 0
            try assertTrue(product.isOutOfStock || stock <= 0, "Product \(product.name) stock \(stock) must be out of stock")
        }
    }

    public static func testInventoryFilterCombinedWithSearchAndCategory() throws {
        let vm = PreviewData.makeInventoryViewModel()
        
        // Filter by expiring soon AND search "Milk"
        vm.applyFilter(.expiringSoon)
        vm.searchText = "Milk"
        
        let filtered = vm.filteredProducts
        try assertEquals(filtered.count, 1, "Only Magnolia Milk matches expiring soon + 'Milk'")
        try assertEquals(filtered.first?.id, 5, "Magnolia Milk id is 5")

        // Reset search, apply category
        vm.searchText = ""
        vm.selectedCategory = "Snacks & Bakery"
        let bakeryExpiring = vm.filteredProducts
        try assertEquals(bakeryExpiring.count, 1, "Only Gardenia Bread matches Snacks & Bakery + expiring soon")
        try assertEquals(bakeryExpiring.first?.id, 7, "Gardenia Bread id is 7")
    }
}
