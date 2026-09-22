import Foundation
import SwiftUI

// MARK: - Preview Data & Mock Fixtures
// Rich, realistic Philippine grocery pantry mock data matching backend seed.
// Used by SwiftUI #Preview macros to render the full Philippine pantry experience
// in Xcode canvas without requiring a running backend or active network connection.

public enum PreviewData {
    
    // MARK: - Date Calculation Helpers
    
    public static func dateString(daysFromNow: Int) -> String {
        let date = Calendar.current.date(byAdding: .day, value: daysFromNow, to: Date()) ?? Date()
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        return formatter.string(from: date)
    }
    
    public static func isoDateString(daysAgo: Int) -> String {
        let date = Calendar.current.date(byAdding: .day, value: -daysAgo, to: Date()) ?? Date()
        let formatter = ISO8601DateFormatter()
        return formatter.string(from: date)
    }

    // MARK: - Storage Locations
    
    public static let pantryShelfA = StorageLocation(
        id: 1,
        name: "Pantry - Shelf A",
        location_type: "pantry"
    )
    
    public static let pantryShelfB = StorageLocation(
        id: 2,
        name: "Pantry - Shelf B",
        location_type: "pantry"
    )
    
    public static let refrigeratorTopShelf = StorageLocation(
        id: 3,
        name: "Refrigerator - Top Shelf",
        location_type: "refrigerator"
    )
    
    public static let refrigeratorDoorRack = StorageLocation(
        id: 4,
        name: "Refrigerator - Door Rack",
        location_type: "refrigerator"
    )
    
    public static let refrigeratorCrisper = StorageLocation(
        id: 5,
        name: "Refrigerator - Crisper",
        location_type: "refrigerator"
    )
    
    public static let freezer = StorageLocation(
        id: 6,
        name: "Freezer",
        location_type: "freezer"
    )
    
    public static let spiceStation = StorageLocation(
        id: 7,
        name: "Spice & Seasoning Station",
        location_type: "pantry"
    )
    
    public static let locations: [StorageLocation] = [
        pantryShelfA,
        pantryShelfB,
        refrigeratorDoorRack,
        refrigeratorTopShelf,
        refrigeratorCrisper,
        freezer,
        spiceStation
    ]

    // MARK: - Sample Philippine Products
    
    public static let centuryTuna = Product(
        id: 1,
        name: "Century Tuna Flakes in Oil",
        brand: "Century Tuna",
        barcode: "4800016644818",
        category: "Canned Goods",
        package_size: 180.0,
        unit: "cans",
        total_remaining_quantity: 16.0,
        active_batches_count: 2
    )
    
    public static let pancitCanton = Product(
        id: 2,
        name: "Lucky Me! Pancit Canton Kalamansi",
        brand: "Lucky Me!",
        barcode: "4800361005210",
        category: "Noodles & Quick Meals",
        package_size: 80.0,
        unit: "packs",
        total_remaining_quantity: 1.0,
        active_batches_count: 1
    )
    
    public static let datuPutiSoySauce = Product(
        id: 3,
        name: "Datu Puti Soy Sauce",
        brand: "Datu Puti",
        barcode: "4801981110010",
        category: "Condiments & Sauces",
        package_size: 1.0,
        unit: "L",
        total_remaining_quantity: 0.3,
        active_batches_count: 1
    )
    
    public static let purefoodsCornedBeef = Product(
        id: 4,
        name: "Purefoods Corned Beef Classic",
        brand: "Purefoods",
        barcode: "4800361389440",
        category: "Canned Goods",
        package_size: 210.0,
        unit: "cans",
        total_remaining_quantity: 6.0,
        active_batches_count: 2
    )
    
    public static let magnoliaMilk = Product(
        id: 5,
        name: "Magnolia Fresh Milk",
        brand: "Magnolia",
        barcode: "4800110041117",
        category: "Dairy & Chilled",
        package_size: 1.0,
        unit: "L",
        total_remaining_quantity: 1.0,
        active_batches_count: 1
    )
    
    public static let tenderJuicyHotdog = Product(
        id: 6,
        name: "Purefoods Tender Juicy Hotdog Classic",
        brand: "Purefoods",
        barcode: "4800361301114",
        category: "Frozen & Meats",
        package_size: 1.0,
        unit: "kg",
        total_remaining_quantity: 1.0,
        active_batches_count: 1
    )
    
    public static let gardeniaBread = Product(
        id: 7,
        name: "Gardenia Classic White Bread",
        brand: "Gardenia",
        barcode: "4806500800018",
        category: "Snacks & Bakery",
        package_size: 600.0,
        unit: "loaves",
        total_remaining_quantity: 1.0,
        active_batches_count: 1
    )
    
    public static let bountyEggs = Product(
        id: 8,
        name: "Bounty Fresh Farm Eggs",
        brand: "Bounty Fresh",
        barcode: "4800999000042",
        category: "Dairy & Chilled",
        package_size: 12.0,
        unit: "pcs",
        total_remaining_quantity: 8.0,
        active_batches_count: 1
    )
    
    public static let sanMiguelBeer = Product(
        id: 9,
        name: "San Miguel Pale Pilsen",
        brand: "San Miguel",
        barcode: "4800010111118",
        category: "Beverages",
        package_size: 330.0,
        unit: "cans",
        total_remaining_quantity: 6.0,
        active_batches_count: 1
    )
    
    public static let argentinaCornedBeef = Product(
        id: 10,
        name: "Argentina Corned Beef",
        brand: "Argentina",
        barcode: "4800110014029",
        category: "Canned Goods",
        package_size: 150.0,
        unit: "cans",
        total_remaining_quantity: 0.0,
        active_batches_count: 0
    )
    
    public static let edenCheese = Product(
        id: 11,
        name: "Eden Original Cheese Melt",
        brand: "Eden",
        barcode: "4800016021114",
        category: "Dairy & Chilled",
        package_size: 165.0,
        unit: "blocks",
        total_remaining_quantity: 2.0,
        active_batches_count: 1
    )
    
    public static let skyFlakes = Product(
        id: 12,
        name: "SkyFlakes Crackers Tub",
        brand: "M.Y. San",
        barcode: "4800016001017",
        category: "Snacks & Bakery",
        package_size: 800.0,
        unit: "tubs",
        total_remaining_quantity: 0.8,
        active_batches_count: 1
    )
    
    public static let dinoradoRice = Product(
        id: 13,
        name: "Harvester's Dinorado Special Rice",
        brand: "Harvester's",
        barcode: "4806511110015",
        category: "Grains & Staples",
        package_size: 5.0,
        unit: "kg",
        total_remaining_quantity: 4.0,
        active_batches_count: 1
    )
    
    public static let c2GreenTea = Product(
        id: 14,
        name: "C2 Cool & Clean Green Tea Apple",
        brand: "C2",
        barcode: "4800016777110",
        category: "Beverages",
        package_size: 500.0,
        unit: "bottles",
        total_remaining_quantity: 3.0,
        active_batches_count: 1
    )
    
    public static let products: [Product] = [
        centuryTuna,
        pancitCanton,
        datuPutiSoySauce,
        purefoodsCornedBeef,
        magnoliaMilk,
        tenderJuicyHotdog,
        gardeniaBread,
        bountyEggs,
        sanMiguelBeer,
        argentinaCornedBeef,
        edenCheese,
        skyFlakes,
        dinoradoRice,
        c2GreenTea
    ]

    // MARK: - Sample Inventory Batches (FEFO & Expirations)
    
    // Magnolia Fresh Milk: Expiring Tomorrow ("EXPIRES TOMORROW")
    public static let magnoliaMilkBatch = InventoryBatch(
        id: 1,
        product_id: 5,
        storage_location_id: 4,
        grocery_session_id: 2,
        purchased_at: isoDateString(daysAgo: 6),
        expiration_date: dateString(daysFromNow: 1),
        original_quantity: 2.0,
        remaining_quantity: 1.0,
        unit_price: 108.00,
        product: magnoliaMilk,
        storage_location: refrigeratorDoorRack
    )
    
    // Gardenia Bread: Expiring in 2 Days ("EXPIRES IN 2D")
    public static let gardeniaBreadBatch = InventoryBatch(
        id: 2,
        product_id: 7,
        storage_location_id: 2,
        grocery_session_id: 3,
        purchased_at: isoDateString(daysAgo: 2),
        expiration_date: dateString(daysFromNow: 2),
        original_quantity: 2.0,
        remaining_quantity: 1.0,
        unit_price: 82.00,
        product: gardeniaBread,
        storage_location: pantryShelfB
    )
    
    // Century Tuna Batch 1: Expiring in 90 days ("USE FIRST" under FEFO)
    public static let centuryTunaBatch1 = InventoryBatch(
        id: 3,
        product_id: 1,
        storage_location_id: 1,
        grocery_session_id: 1,
        purchased_at: isoDateString(daysAgo: 14),
        expiration_date: dateString(daysFromNow: 90),
        original_quantity: 6.0,
        remaining_quantity: 4.0,
        unit_price: 43.50,
        product: centuryTuna,
        storage_location: pantryShelfA
    )
    
    // Century Tuna Batch 2: Expiring in 365 days (Later FEFO batch)
    public static let centuryTunaBatch2 = InventoryBatch(
        id: 4,
        product_id: 1,
        storage_location_id: 1,
        grocery_session_id: 3,
        purchased_at: isoDateString(daysAgo: 2),
        expiration_date: dateString(daysFromNow: 365),
        original_quantity: 12.0,
        remaining_quantity: 12.0,
        unit_price: 45.00,
        product: centuryTuna,
        storage_location: pantryShelfA
    )
    
    // Purefoods Corned Beef Batch 1: Price history demo (₱98.50, expires in 300 days)
    public static let purefoodsCornedBeefBatch1 = InventoryBatch(
        id: 5,
        product_id: 4,
        storage_location_id: 1,
        grocery_session_id: 1,
        purchased_at: isoDateString(daysAgo: 14),
        expiration_date: dateString(daysFromNow: 300),
        original_quantity: 4.0,
        remaining_quantity: 2.0,
        unit_price: 98.50,
        product: purefoodsCornedBeef,
        storage_location: pantryShelfA
    )
    
    // Purefoods Corned Beef Batch 2: Price history demo (₱102.00, expires in 450 days)
    public static let purefoodsCornedBeefBatch2 = InventoryBatch(
        id: 6,
        product_id: 4,
        storage_location_id: 1,
        grocery_session_id: 3,
        purchased_at: isoDateString(daysAgo: 2),
        expiration_date: dateString(daysFromNow: 450),
        original_quantity: 4.0,
        remaining_quantity: 4.0,
        unit_price: 102.00,
        product: purefoodsCornedBeef,
        storage_location: pantryShelfA
    )
    
    // Purefoods Tender Juicy Hotdog Classic in Freezer
    public static let tenderJuicyHotdogBatch = InventoryBatch(
        id: 7,
        product_id: 6,
        storage_location_id: 6,
        grocery_session_id: 3,
        purchased_at: isoDateString(daysAgo: 2),
        expiration_date: dateString(daysFromNow: 90),
        original_quantity: 1.0,
        remaining_quantity: 1.0,
        unit_price: 215.00,
        product: tenderJuicyHotdog,
        storage_location: freezer
    )
    
    // Bounty Fresh Farm Eggs in Refrigerator Top Shelf
    public static let bountyEggsBatch = InventoryBatch(
        id: 8,
        product_id: 8,
        storage_location_id: 3,
        grocery_session_id: 2,
        purchased_at: isoDateString(daysAgo: 7),
        expiration_date: dateString(daysFromNow: 4),
        original_quantity: 12.0,
        remaining_quantity: 8.0,
        unit_price: 9.17,
        product: bountyEggs,
        storage_location: refrigeratorTopShelf
    )
    
    // Lucky Me! Pancit Canton Kalamansi (1 pack left)
    public static let pancitCantonBatch = InventoryBatch(
        id: 9,
        product_id: 2,
        storage_location_id: 2,
        grocery_session_id: 1,
        purchased_at: isoDateString(daysAgo: 14),
        expiration_date: dateString(daysFromNow: 120),
        original_quantity: 6.0,
        remaining_quantity: 1.0,
        unit_price: 15.50,
        product: pancitCanton,
        storage_location: pantryShelfB
    )
    
    // Datu Puti Soy Sauce (0.3 L left)
    public static let datuPutiSoySauceBatch = InventoryBatch(
        id: 10,
        product_id: 3,
        storage_location_id: 7,
        grocery_session_id: 1,
        purchased_at: isoDateString(daysAgo: 14),
        expiration_date: dateString(daysFromNow: 360),
        original_quantity: 1.0,
        remaining_quantity: 0.3,
        unit_price: 48.00,
        product: datuPutiSoySauce,
        storage_location: spiceStation
    )
    
    public static let batches: [InventoryBatch] = [
        magnoliaMilkBatch,
        gardeniaBreadBatch,
        centuryTunaBatch1,
        centuryTunaBatch2,
        purefoodsCornedBeefBatch1,
        purefoodsCornedBeefBatch2,
        tenderJuicyHotdogBatch,
        bountyEggsBatch,
        pancitCantonBatch,
        datuPutiSoySauceBatch
    ]
    
    public static let centuryTunaBatches: [InventoryBatch] = [
        centuryTunaBatch1,
        centuryTunaBatch2
    ]
    
    public static let purefoodsCornedBeefBatches: [InventoryBatch] = [
        purefoodsCornedBeefBatch1,
        purefoodsCornedBeefBatch2
    ]

    // MARK: - Analytics, Spending & Waste Summaries
    
    // Valuation: ₱12,450.00
    public static let valuation = InventoryValuation(
        total_value: 12450.00,
        total_active_batches: 32,
        total_active_products: 30
    )
    
    // Spending: ₱7,956.25 across intake sessions
    public static let spending = SpendingSummary(
        total_spent: 7956.25,
        sessions_count: 3
    )
    
    // Waste Summary: 2 logged waste events, 201 units, ₱100.00 loss
    public static let waste = WasteSummary(
        total_waste_events: 2,
        total_quantity_wasted: 201.0,
        total_financial_loss: 100.00
    )

    // MARK: - Expiring Soon Items (Home & Radar)
    
    public static let expiringSoonItems: [ExpiringSoonItem] = [
        ExpiringSoonItem(
            batch_id: 1,
            product_id: 5,
            product_name: "Magnolia Fresh Milk",
            brand: "Magnolia",
            remaining_quantity: 1.0,
            unit: "L",
            expiration_date: dateString(daysFromNow: 1),
            days_until_expiration: 1,
            storage_location: "Refrigerator - Door Rack"
        ),
        ExpiringSoonItem(
            batch_id: 2,
            product_id: 7,
            product_name: "Gardenia Classic White Bread",
            brand: "Gardenia",
            remaining_quantity: 1.0,
            unit: "loaves",
            expiration_date: dateString(daysFromNow: 2),
            days_until_expiration: 2,
            storage_location: "Pantry - Shelf B"
        ),
        ExpiringSoonItem(
            batch_id: 8,
            product_id: 8,
            product_name: "Bounty Fresh Farm Eggs",
            brand: "Bounty Fresh",
            remaining_quantity: 8.0,
            unit: "pcs",
            expiration_date: dateString(daysFromNow: 4),
            days_until_expiration: 4,
            storage_location: "Refrigerator - Top Shelf"
        )
    ]

    // MARK: - Restock Needed / Low Stock Items
    
    public static let lowStockItems: [LowStockItem] = [
        LowStockItem(
            product_id: 2,
            product_name: "Lucky Me! Pancit Canton Kalamansi",
            brand: "Lucky Me!",
            current_stock: 1.0,
            unit: "packs"
        ),
        LowStockItem(
            product_id: 3,
            product_name: "Datu Puti Soy Sauce",
            brand: "Datu Puti",
            current_stock: 0.3,
            unit: "L"
        ),
        LowStockItem(
            product_id: 10,
            product_name: "Argentina Corned Beef",
            brand: "Argentina",
            current_stock: 0.0,
            unit: "cans"
        )
    ]

    // MARK: - Shopping List Items (Active & Bought)
    
    public static let pancitCantonShoppingItem = ShoppingItem(
        id: 1,
        name: "Lucky Me! Pancit Canton Kalamansi",
        product_id: 2,
        quantity: 6.0,
        unit: "packs",
        is_bought: false,
        notes: "Urgent restock: only 1 pack left in pantry!",
        product: pancitCanton
    )
    
    public static let soySauceShoppingItem = ShoppingItem(
        id: 2,
        name: "Datu Puti Soy Sauce",
        product_id: 3,
        quantity: 1.0,
        unit: "L",
        is_bought: false,
        notes: "Low stock alert (0.3 L remaining)",
        product: datuPutiSoySauce
    )
    
    public static let tunaShoppingItem = ShoppingItem(
        id: 3,
        name: "Century Tuna Flakes in Oil",
        product_id: 1,
        quantity: 6.0,
        unit: "cans",
        is_bought: false,
        notes: "Stock up for rainy season emergency pantry",
        product: centuryTuna
    )
    
    public static let sugarShoppingItem = ShoppingItem(
        id: 4,
        name: "Refined White Sugar",
        product_id: nil,
        quantity: 1.0,
        unit: "kg",
        is_bought: false,
        notes: "Victoria or Robinsons brand for baking and morning coffee",
        product: nil
    )
    
    public static let hotdogShoppingItem = ShoppingItem(
        id: 5,
        name: "Purefoods Tender Juicy Hotdog Classic",
        product_id: 6,
        quantity: 1.0,
        unit: "kg",
        is_bought: true,
        notes: "Purchased at Puregold on 2026-09-13",
        product: tenderJuicyHotdog
    )
    
    public static let breadShoppingItem = ShoppingItem(
        id: 6,
        name: "Gardenia Classic White Bread",
        product_id: 7,
        quantity: 2.0,
        unit: "loaves",
        is_bought: true,
        notes: "Purchased at Puregold on 2026-09-13",
        product: gardeniaBread
    )
    
    public static let beerShoppingItem = ShoppingItem(
        id: 7,
        name: "San Miguel Pale Pilsen",
        product_id: 9,
        quantity: 6.0,
        unit: "cans",
        is_bought: true,
        notes: "Purchased at Puregold on 2026-09-13",
        product: sanMiguelBeer
    )
    
    public static let shoppingItems: [ShoppingItem] = [
        pancitCantonShoppingItem,
        soySauceShoppingItem,
        tunaShoppingItem,
        sugarShoppingItem,
        hotdogShoppingItem,
        breadShoppingItem,
        beerShoppingItem
    ]

    // MARK: - User Accounts
    
    public static let user = User(
        id: 1,
        email: "user@provision.local",
        display_name: "Maria Santos",
        is_active: true,
        created_at: "2026-09-01T08:00:00Z"
    )
    
    public static let demoUser = User(
        id: 2,
        email: "demo@provision.local",
        display_name: "Juan Dela Cruz",
        is_active: true,
        created_at: "2026-09-01T08:00:00Z"
    )

    // MARK: - Mock ViewModel Factory Methods
    
    @MainActor
    public static func makeHomeViewModel() -> HomeViewModel {
        let vm = HomeViewModel(isPreview: true)
        vm.valuation = valuation
        vm.spending = spending
        vm.expiringSoonItems = expiringSoonItems
        vm.lowStockItems = lowStockItems
        return vm
    }
    
    @MainActor
    public static func makeAuthViewModel(user: User? = nil) -> AuthViewModel {
        let vm = AuthViewModel(isPreview: true)
        let resolvedUser = user ?? PreviewData.user
        vm.currentUser = resolvedUser
        vm.authState = .signedIn(resolvedUser)
        return vm
    }
    
    @MainActor
    public static func makeInventoryViewModel(
        selectedProduct: Product? = nil,
        batches: [InventoryBatch]? = nil
    ) -> InventoryViewModel {
        let vm = InventoryViewModel(isPreview: true)
        vm.products = products
        vm.locations = locations
        
        let targetProduct = selectedProduct ?? centuryTuna
        vm.selectedProduct = targetProduct
        
        if let batches = batches {
            vm.productBatches = batches
        } else if targetProduct.id == centuryTuna.id {
            vm.productBatches = centuryTunaBatches
        } else if targetProduct.id == purefoodsCornedBeef.id {
            vm.productBatches = purefoodsCornedBeefBatches
        } else if let foundBatch = PreviewData.batches.first(where: { $0.product_id == targetProduct.id }) {
            vm.productBatches = [foundBatch]
        } else {
            vm.productBatches = []
        }
        
        return vm
    }
    
    @MainActor
    public static func makeAnalyticsViewModel() -> AnalyticsViewModel {
        let vm = AnalyticsViewModel(isPreview: true)
        vm.valuation = valuation
        vm.spending = spending
        vm.waste = waste
        vm.expiringSoonItems = expiringSoonItems
        vm.lowStockItems = lowStockItems
        return vm
    }
    
    @MainActor
    public static func makeShoppingViewModel() -> ShoppingViewModel {
        let vm = ShoppingViewModel(isPreview: true)
        vm.items = shoppingItems
        return vm
    }

    @MainActor
    public static func makeScanViewModel() -> ScanViewModel {
        ScanViewModel(isPreview: true)
    }
}
