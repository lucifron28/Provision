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
        try testChefPipNeverRecommendsExpiredItems()
        try testChefPipEmptyPantryDoesNotClaimWellStocked()
        try testChefPipMixedExpiredAndExpiringScenario()
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

        // 1. Empty pantry -> pip_guardian, Welcome to Provision
        vm.valuation = InventoryValuation(total_value: 0, total_active_batches: 0, total_active_products: 0)
        vm.expiringSoonItems = []
        vm.lowStockItems = []
        try assertEquals(vm.pipMascotAssetName, "pip_guardian", "Empty pantry should use pip_guardian")
        try assertEquals(vm.pipGuidanceTitle, "Welcome to Provision", "Empty pantry guidance title")
        try assertEquals(vm.pantryStatus, .empty, "Pantry status should be .empty")

        // 2. Expired items exist -> pip_concerned, Check Expired Items
        let expiredItem = ExpiringSoonItem(
            batch_id: 101,
            product_id: 10,
            product_name: "Expired Yoghurt",
            brand: "Pantry",
            remaining_quantity: 1,
            unit: "cups",
            expiration_date: "2026-10-10",
            days_until_expiration: -5,
            storage_location: "Fridge"
        )
        vm.valuation = InventoryValuation(total_value: 5000, total_active_batches: 10, total_active_products: 8)
        vm.expiringSoonItems = [expiredItem]
        try assertEquals(vm.pipMascotAssetName, "pip_concerned", "Expired items should use pip_concerned")
        try assertEquals(vm.pipGuidanceTitle, "Check Expired Items", "Expired items guidance title")
        try assertEquals(vm.pantryStatus, .expired, "Pantry status should be .expired")

        // 3. Expiring soon items exist (approaching expiration) -> pip_concerned
        vm.expiringSoonItems = PreviewData.expiringSoonItems
        try assertEquals(vm.pipMascotAssetName, "pip_concerned", "Expiring soon should use pip_concerned")
        try assertEquals(vm.pipGuidanceTitle, "Expiring Soon", "Expiring soon guidance title")

        // 4. No expiring items, but low stock items exist -> pip_grocery
        vm.expiringSoonItems = []
        vm.lowStockItems = PreviewData.lowStockItems
        try assertEquals(vm.pipMascotAssetName, "pip_grocery", "Low stock should use pip_grocery")
        try assertEquals(vm.pipGuidanceTitle, "Restock Needed", "Restock needed guidance title")

        // 5. Fully stocked and fresh -> pip_proud
        vm.lowStockItems = []
        try assertEquals(vm.pipMascotAssetName, "pip_proud", "Healthy pantry should use pip_proud")
        try assertEquals(vm.pipGuidanceTitle, "Pantry Healthy", "Healthy pantry guidance title")
        try assertEquals(vm.pantryStatus, .healthy, "Pantry status should be .healthy")
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
        try assertTrue(vm.pipGuidanceMessage.contains("well within their dates"), "Fresh pantry message")
    }

    public static func testChefPipRecipeIdeasWithRealExpiringProducts() throws {
        let vm = HomeViewModel(isPreview: true)
        vm.valuation = InventoryValuation(total_value: 5000, total_active_batches: 6, total_active_products: 4)
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

    public static func testChefPipNeverRecommendsExpiredItems() throws {
        let vm = HomeViewModel(isPreview: true)
        vm.valuation = InventoryValuation(total_value: 3000, total_active_batches: 5, total_active_products: 4)

        let expiredMilk = ExpiringSoonItem(
            batch_id: 201,
            product_id: 1,
            product_name: "Expired Whole Milk",
            brand: "CowBrand",
            remaining_quantity: 1,
            unit: "cartons",
            expiration_date: "2026-10-01",
            days_until_expiration: -10,
            storage_location: "Fridge"
        )
        vm.expiringSoonItems = [expiredMilk]

        // Chef Pip must NOT suggest recipes with Expired Whole Milk!
        let ideas = vm.chefPipRecipeIdeas
        try assertTrue(ideas.count == 1, "Should fall back to general pantry guidance when only expired items exist")
        try assertTrue(!ideas[0].contains("Expired Whole Milk"), "Must NEVER recommend expired items in recipe suggestions")
        try assertTrue(vm.chefPipDateSafetyNotice != nil, "Must provide date safety notice for expired items")
        try assertTrue(vm.chefPipDateSafetyNotice!.contains("past its recorded date"), "Notice warns about past dates")
    }

    public static func testChefPipEmptyPantryDoesNotClaimWellStocked() throws {
        let vm = HomeViewModel(isPreview: true)
        vm.valuation = InventoryValuation(total_value: 0, total_active_batches: 0, total_active_products: 0)
        vm.expiringSoonItems = []
        vm.lowStockItems = []

        // When pantry is empty, chefPipRecipeIdeas must be empty (card hidden), never claim 'well-stocked'
        let ideas = vm.chefPipRecipeIdeas
        try assertTrue(ideas.isEmpty, "Empty pantry should produce zero recipe ideas")
        try assertTrue(vm.isPantryEmpty, "isPantryEmpty must be true")
        try assertTrue(!vm.pipGuidanceMessage.contains("All pantry stock is fresh!"), "Empty pantry must not claim all stock is fresh")
        try assertTrue(vm.pipGuidanceMessage.contains("Your pantry has no active stock"), "Guidance directs user to scan items")
    }

    public static func testChefPipMixedExpiredAndExpiringScenario() throws {
        let vm = HomeViewModel(isPreview: true)
        vm.valuation = InventoryValuation(total_value: 5000, total_active_batches: 6, total_active_products: 5)

        let expiredBread = ExpiringSoonItem(
            batch_id: 301,
            product_id: 2,
            product_name: "Expired Loaf",
            brand: "BakeShop",
            remaining_quantity: 1,
            unit: "loaf",
            expiration_date: "2026-10-15",
            days_until_expiration: -4,
            storage_location: "Pantry"
        )
        let validTuna = ExpiringSoonItem(
            batch_id: 302,
            product_id: 3,
            product_name: "Century Tuna Flakes",
            brand: "Century",
            remaining_quantity: 2,
            unit: "cans",
            expiration_date: "2026-10-22",
            days_until_expiration: 3,
            storage_location: "Pantry"
        )
        vm.expiringSoonItems = [expiredBread, validTuna]

        let ideas = vm.chefPipRecipeIdeas
        try assertTrue(!ideas.isEmpty, "Should generate an idea for valid item")
        for idea in ideas {
            try assertTrue(!idea.contains("Expired Loaf"), "Must NOT recommend Expired Loaf")
            try assertTrue(idea.contains("Century Tuna Flakes"), "Must recommend valid unexpired Tuna")
        }
        try assertTrue(vm.chefPipDateSafetyNotice != nil, "Must include date safety notice for the expired item")
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
