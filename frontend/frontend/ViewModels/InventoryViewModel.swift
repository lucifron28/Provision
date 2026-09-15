import Foundation
import SwiftUI
import Combine

@MainActor
public class InventoryViewModel: ObservableObject {
    @Published public var products: [Product] = []
    @Published public var locations: [StorageLocation] = []
    
    @Published public var searchText: String = ""
    @Published public var selectedCategory: String? = nil
    @Published public var selectedLocationId: Int? = nil
    
    // Detail view state
    @Published public var selectedProduct: Product? = nil
    @Published public var productBatches: [InventoryBatch] = []
    
    @Published public var isLoading: Bool = false
    @Published public var isDetailLoading: Bool = false
    @Published public var errorMessage: String? = nil
    @Published public var toastMessage: String? = nil
    
    private let client: APIClient
    
    public init(client: APIClient = .shared) {
        self.client = client
    }
    
    public var categories: [String] {
        let cats = Set(products.compactMap { $0.category }).sorted()
        return cats
    }
    
    public var filteredProducts: [Product] {
        products.filter { product in
            let matchesSearch = searchText.isEmpty ||
                product.name.localizedCaseInsensitiveContains(searchText) ||
                (product.brand?.localizedCaseInsensitiveContains(searchText) ?? false) ||
                (product.category?.localizedCaseInsensitiveContains(searchText) ?? false) ||
                (product.barcode?.contains(searchText) ?? false)
            
            let matchesCategory = selectedCategory == nil || product.category == selectedCategory
            return matchesSearch && matchesCategory
        }
    }
    
    public func loadData() async {
        isLoading = true
        errorMessage = nil
        
        do {
            async let prodsTask = client.fetchProducts()
            async let locsTask = client.fetchLocations()
            
            let (prods, locs) = try await (prodsTask, locsTask)
            self.products = prods
            self.locations = locs
        } catch {
            self.errorMessage = error.localizedDescription
        }
        
        self.isLoading = false
    }
    
    public func selectProduct(_ product: Product) async {
        let current = products.first(where: { $0.id == product.id }) ?? product
        self.selectedProduct = current
        self.isDetailLoading = true
        
        do {
            let batches = try await client.fetchBatches(productId: current.id, activeOnly: true)
            // Sort FEFO (Earliest expiration first)
            self.productBatches = batches.sorted {
                ($0.expiration_date ?? "9999-12-31") < ($1.expiration_date ?? "9999-12-31")
            }
        } catch {
            self.errorMessage = "Failed to load product batches: \(error.localizedDescription)"
        }
        
        self.isDetailLoading = false
    }
    
    public func consumeProduct(productId: Int, quantity: Double, reason: String? = "Household consumption") async -> Bool {
        do {
            let res = try await client.consumeProduct(productId: productId, quantity: quantity, reason: reason)
            self.toastMessage = "Successfully consumed \(String(format: "%.1f", res.total_consumed)) units"
            
            // Refresh product and batches
            await loadData()
            if let updated = products.first(where: { $0.id == productId }) {
                await selectProduct(updated)
            }
            return true
        } catch {
            self.errorMessage = error.localizedDescription
            return false
        }
    }
    
    public func discardBatch(batchId: Int, reason: String? = "Spoiled / Expired") async -> Bool {
        do {
            _ = try await client.discardBatch(batchId: batchId, reason: reason)
            self.toastMessage = "Batch discarded"
            
            await loadData()
            if let sel = selectedProduct, let updated = products.first(where: { $0.id == sel.id }) {
                await selectProduct(updated)
            }
            return true
        } catch {
            self.errorMessage = error.localizedDescription
            return false
        }
    }
    
    public func adjustBatch(batchId: Int, newQuantity: Double, reason: String = "Physical count adjustment") async -> Bool {
        do {
            _ = try await client.adjustBatch(batchId: batchId, newQuantity: newQuantity, reason: reason)
            self.toastMessage = "Batch adjusted to \(newQuantity)"
            
            await loadData()
            if let sel = selectedProduct, let updated = products.first(where: { $0.id == sel.id }) {
                await selectProduct(updated)
            }
            return true
        } catch {
            self.errorMessage = error.localizedDescription
            return false
        }
    }
    
    public func createManualInventory(product: ProductCreate?, productId: Int?, batch: InventoryBatchCreate) async -> Bool {
        do {
            var targetProductId = productId
            
            // 1. Create product if new
            if let p = product {
                let createdProduct = try await client.createProduct(p)
                targetProductId = createdProduct.id
            }
            
            guard let pid = targetProductId else {
                self.errorMessage = "Product ID is missing."
                return false
            }
            
            // 2. Create batch
            var finalBatch = batch
            finalBatch.product_id = pid
            
            _ = try await client.createBatch(finalBatch)
            self.toastMessage = "Inventory added successfully"
            
            await loadData()
            
            // If we are looking at this product, refresh it
            if let sel = selectedProduct, sel.id == pid {
                if let updated = products.first(where: { $0.id == pid }) {
                    await selectProduct(updated)
                }
            }
            return true
        } catch {
            self.errorMessage = error.localizedDescription
            return false
        }
    }
    
    public func restockProduct(productId: Int, batch: InventoryBatchCreate) async -> Bool {
        return await createManualInventory(product: nil, productId: productId, batch: batch)
    }
    
    public func updateBatchMetadata(batchId: Int, updates: [String: Any?]) async -> Bool {
        do {
            _ = try await client.updateBatchMetadata(batchId: batchId, updates: updates)
            self.toastMessage = "Batch updated successfully"
            
            await loadData()
            if let sel = selectedProduct, let updated = products.first(where: { $0.id == sel.id }) {
                await selectProduct(updated)
            }
            return true
        } catch {
            self.errorMessage = error.localizedDescription
            return false
        }
    }
}
