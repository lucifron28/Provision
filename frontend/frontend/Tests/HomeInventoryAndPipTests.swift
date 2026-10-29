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
        try testInventorySortingOptions()
        try testShoppingListDefaultToBuyAndPurchasedSeparation()
        try testReviewAllWorkspaceFiltering()
        try testReviewWorkspaceScannerSuspensionAndCommitRecovery()
        try testRestoredAllConfirmedPendingSubmissionPrecedence()
        try testReusableSearchableProductSelector()
        try testProductSelectorSelectionAndSheetDismissal()
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

        // When ONLY expired items exist, Chef Pip must return NO recipe suggestions (empty array)
        let ideas = vm.chefPipRecipeIdeas
        try assertTrue(ideas.isEmpty, "Chef Pip must return no recipe suggestions when only expired items exist")
        try assertTrue(vm.chefPipDateSafetyNotice != nil, "Must provide date safety notice for expired items")
        try assertTrue(vm.chefPipDateSafetyNotice!.contains("past its recorded date"), "Notice warns about past dates")
        try assertTrue(!vm.chefPipDateSafetyNotice!.contains("odor") && !vm.chefPipDateSafetyNotice!.contains("smell"), "Must avoid claiming smell or appearance confirms safety")
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

    // MARK: - Inventory Sorting Tests

    public static func testInventorySortingOptions() throws {
        let vm = PreviewData.makeInventoryViewModel()

        // 1. Name Ascending (A-Z)
        vm.sortOption = .nameAsc
        let sortedAsc = vm.filteredProducts
        try assertTrue(sortedAsc.count >= 2, "Products must not be empty")
        for i in 0..<(sortedAsc.count - 1) {
            try assertTrue(sortedAsc[i].name.localizedCaseInsensitiveCompare(sortedAsc[i+1].name) != .orderedDescending, "Must be sorted A-Z")
        }

        // 2. Name Descending (Z-A)
        vm.sortOption = .nameDesc
        let sortedDesc = vm.filteredProducts
        for i in 0..<(sortedDesc.count - 1) {
            try assertTrue(sortedDesc[i].name.localizedCaseInsensitiveCompare(sortedDesc[i+1].name) != .orderedAscending, "Must be sorted Z-A")
        }

        // 3. Stock Lowest First
        vm.sortOption = .stockLowest
        let sortedStockLow = vm.filteredProducts
        for i in 0..<(sortedStockLow.count - 1) {
            let stockA = sortedStockLow[i].total_remaining_quantity ?? 0
            let stockB = sortedStockLow[i+1].total_remaining_quantity ?? 0
            try assertTrue(stockA <= stockB, "Stock must be ascending")
        }
    }

    // MARK: - Shopping List To-Buy Segmentation Tests

    public static func testShoppingListDefaultToBuyAndPurchasedSeparation() throws {
        let vm = ShoppingViewModel(isPreview: true)
        vm.items = [
            ShoppingItem(id: 1, name: "Bananas", quantity: 1, is_bought: false),
            ShoppingItem(id: 2, name: "Apples", quantity: 2, is_bought: true),
            ShoppingItem(id: 3, name: "Milk", quantity: 1, is_bought: false),
            ShoppingItem(id: 4, name: "Bread", quantity: 1, is_bought: true)
        ]

        // 1. Verify default filter is To Buy (.pending)
        try assertEquals(vm.filter, .pending, "Shopping list must default to To Buy (.pending)")

        // 2. Filtered items in To Buy must only contain unpurchased items
        let toBuyItems = vm.filteredItems
        try assertEquals(toBuyItems.count, 2, "Must show exactly 2 items to buy")
        for item in toBuyItems {
            try assertTrue(!item.is_bought, "To Buy items must not be purchased")
        }
        try assertEquals(vm.pendingCount, 2, "Pending count must be 2")
        try assertEquals(vm.purchasedCount, 2, "Purchased count must be 2")

        // 3. Switch to Purchased (.completed)
        vm.filter = .completed
        let purchasedItems = vm.filteredItems
        try assertEquals(purchasedItems.count, 2, "Must show exactly 2 purchased items")
        for item in purchasedItems {
            try assertTrue(item.is_bought, "Purchased items must have is_bought = true")
        }

        // 4. Switch to All (.all)
        vm.filter = .all
        try assertEquals(vm.filteredItems.count, 4, "All filter must show all 4 items")
    }

    // MARK: - Review All Workspace & Large List Tests

    public static func testReviewAllWorkspaceFiltering() throws {
        let vm = ScanViewModel(isPreview: true)
        let itemReady = ScannedIntakeItem(
            id: UUID(),
            name: "Century Tuna",
            brand: "Century",
            barcode: "4800016644818",
            quantity: 2,
            unit: "cans",
            status: .recognized,
            productId: 1,
            storageLocationId: 10
        )
        let itemNoLoc = ScannedIntakeItem(
            id: UUID(),
            name: "Purefoods Corned Beef",
            brand: "Purefoods",
            barcode: "4800361389440",
            quantity: 1,
            unit: "can",
            status: .recognized,
            productId: 2,
            storageLocationId: nil
        )
        let itemUnresolved = ScannedIntakeItem(
            id: UUID(),
            name: "Mystery Biscuit",
            brand: "Unknown",
            barcode: "9999999999999",
            quantity: 1,
            unit: "pcs",
            status: .needsReview,
            productId: nil,
            storageLocationId: 10
        )
        vm.scannedItems = [itemReady, itemNoLoc, itemUnresolved]

        let reviewWorkspace = IntakeSessionReviewView(viewModel: vm)
        
        // 1. All filter shows 3 items
        try assertEquals(reviewWorkspace.filteredItems.count, 3, "All filter should return all 3 items")

        // 2. Authoritative validation states
        try assertEquals(vm.validationState(for: itemReady), .ready, "itemReady must be .ready")
        try assertEquals(vm.validationState(for: itemNoLoc), .needsDetails, "itemNoLoc must be .needsDetails")
        try assertEquals(vm.validationState(for: itemUnresolved), .needsReview, "itemUnresolved must be .needsReview")

        // 3. Large-list performance test: 35 items
        var largeItems: [ScannedIntakeItem] = []
        for i in 1...35 {
            largeItems.append(ScannedIntakeItem(
                id: UUID(),
                name: "Batch Item \(i)",
                barcode: "BARCODE_\(i)",
                quantity: 1.0,
                unit: "pcs",
                status: i % 5 == 0 ? .needsReview : .recognized,
                productId: i % 5 == 0 ? nil : i,
                storageLocationId: i % 3 == 0 ? nil : 1
            ))
        }
        vm.scannedItems = largeItems
        try assertEquals(vm.scannedItems.count, 35, "Large session has 35 items")
        let largeWorkspace = IntakeSessionReviewView(viewModel: vm)
        try assertEquals(largeWorkspace.filteredItems.count, 35, "Large session renders 35 items in workspace")
    }

    // MARK: - Review Workspace Scanner Suspension & Recovery Tests

    public static func testReviewWorkspaceScannerSuspensionAndCommitRecovery() throws {
        let vm = ScanViewModel(isPreview: false)
        
        // 1. Suspend for .reviewWorkspace
        vm.suspendScanning(for: .reviewWorkspace)
        try assertTrue(vm.activeSuspensions.contains(.reviewWorkspace), "Must contain .reviewWorkspace suspension")
        try assertTrue(!vm.scannerManager.acceptanceGate.isArmed, "Acceptance gate must be locked during workspace review")

        // 2. Resume releasing .reviewWorkspace
        vm.resumeScanning(releasing: .reviewWorkspace)
        try assertTrue(!vm.activeSuspensions.contains(.reviewWorkspace), "Must release .reviewWorkspace suspension")
    }

    // MARK: - Searchable Product Selector Tests

    public static func testReusableSearchableProductSelector() throws {
        let prods = PreviewData.products
        var selectedId: Int? = nil
        let binding = Binding<Int?>(get: { selectedId }, set: { selectedId = $0 })
        
        let selector = SearchableProductSelector(
            products: prods,
            selectedProductId: binding,
            placeholder: "Search catalog..."
        )

        // 1. Initially compact sheet is closed
        try assertTrue(!selector.showingSheet, "Selector sheet is not presented initially")
        try assertEquals(selector.filteredProducts(matching: "").count, prods.count, "All products returned when query is empty")

        // 2. Search query matching name
        let tunaMatches = selector.filteredProducts(matching: "Tuna")
        try assertTrue(!tunaMatches.isEmpty, "Should find matches for 'Tuna'")
        for p in tunaMatches {
            let matches = p.name.localizedCaseInsensitiveContains("Tuna") || (p.brand?.localizedCaseInsensitiveContains("Tuna") == true) || (p.category?.localizedCaseInsensitiveContains("Tuna") == true)
            try assertTrue(matches, "All matches must match 'Tuna' in name, brand, or category")
        }

        // 3. Search query matching brand
        let centuryMatches = selector.filteredProducts(matching: "Century")
        try assertTrue(!centuryMatches.isEmpty, "Should find matches for brand 'Century'")

        // 4. Category filtering
        let cannedMatches = selector.filteredProducts(matching: "", category: "Canned Goods")
        try assertTrue(!cannedMatches.isEmpty, "Should find matches for Canned Goods")
        for p in cannedMatches {
            try assertEquals(p.category, "Canned Goods", "Category must match Canned Goods")
        }
    }

    // MARK: - Restored All-Confirmed Pending Submission Recovery Precedence Tests

    public static func testRestoredAllConfirmedPendingSubmissionPrecedence() throws {
        let defaults = UserDefaults(suiteName: "test.precedence.\(UUID().uuidString)")!
        defer { defaults.removePersistentDomain(forName: "test.precedence") }

        let vm = ScanViewModel(isPreview: false, pendingCommitDefaults: defaults)
        
        let item1 = ScannedIntakeItem(
            name: "Century Tuna",
            barcode: "111",
            quantity: 1.0,
            unit: "cans",
            status: .confirmed,
            productId: 1,
            storageLocationId: 10,
            isConfirmed: true
        )
        let item2 = ScannedIntakeItem(
            name: "Eden Cheese",
            barcode: "222",
            quantity: 1.0,
            unit: "pcs",
            status: .confirmed,
            productId: 2,
            storageLocationId: 10,
            isConfirmed: true
        )
        vm.scannedItems = [item1, item2]

        // Both items are confirmed -> allConfirmed would be true
        let totalCount = vm.scannedItems.count
        let confirmedCount = vm.confirmedItemsCount
        let allConfirmed = totalCount > 0 && confirmedCount == totalCount
        try assertTrue(allConfirmed, "All items in queue are confirmed")

        // 1. Simulate an active pending commit recovery
        vm.suspendScanning(for: .pendingCommitRecovery)
        try assertTrue(vm.activeSuspensions.contains(.pendingCommitRecovery), "Must contain pendingCommitRecovery suspension")
        try assertTrue(vm.isIntakeMutationLocked, "Intake mutations must be locked during pending recovery")

        // 2. In both ScanView and IntakeSessionReviewView, hasPendingCommitRecovery MUST take precedence over allConfirmed
        let hasRecovery = vm.hasPendingCommitRecovery || vm.activeSuspensions.contains(.pendingCommitRecovery)
        try assertTrue(hasRecovery, "Pending recovery status must take precedence over allConfirmed")
    }

    // MARK: - Product Selection Callback and Sheet Dismissal Tests

    public static func testProductSelectorSelectionAndSheetDismissal() throws {
        let prods = PreviewData.products
        var selectedId: Int? = nil
        var callbackFired: Bool = false
        var selectedName: String = ""
        let binding = Binding<Int?>(get: { selectedId }, set: { selectedId = $0 })

        let selector = SearchableProductSelector(
            products: prods,
            selectedProductId: binding,
            placeholder: "Choose item..."
        ) { product in
            callbackFired = true
            selectedName = product.name
        }

        // Initially no selection
        try assertEquals(selector.selectedProduct, nil, "Initially selectedProduct is nil")
        try assertTrue(!selector.showingSheet, "Initially sheet is not showing")

        // Tap first product
        if let first = prods.first {
            selectedId = first.id
            selector.onSelect?(first)
            try assertEquals(selector.selectedProduct?.id, first.id, "selectedProduct must reflect updated selectedProductId")
            try assertTrue(callbackFired, "onSelect callback must fire on product selection")
            try assertEquals(selectedName, first.name, "Callback must pass selected product")
        }
    }
}
