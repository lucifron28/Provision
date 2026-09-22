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
    public var isPreview: Bool
    
    public init(client: APIClient = .shared, isPreview: Bool = false) {
        self.client = client
        self.isPreview = isPreview
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
        if isPreview { return }
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
        if isPreview { return }
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
        if isPreview {
            self.toastMessage = "Successfully consumed \(String(format: "%.1f", quantity)) units"
            return true
        }
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
        if isPreview {
            self.toastMessage = "Batch discarded"
            self.productBatches.removeAll { $0.id == batchId }
            return true
        }
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
        if isPreview {
            self.toastMessage = "Batch adjusted to \(newQuantity)"
            if let idx = self.productBatches.firstIndex(where: { $0.id == batchId }) {
                self.productBatches[idx].remaining_quantity = newQuantity
            }
            return true
        }
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
    
    public func updateProductMetadata(productId: Int, update: ProductUpdate) async -> Bool {
        if isPreview {
            if var sel = selectedProduct, sel.id == productId {
                if let n = update.name { sel.name = n }
                if let b = update.brand { sel.brand = b }
                if let c = update.category { sel.category = c }
                if let u = update.unit { sel.unit = u }
                self.selectedProduct = sel
            }
            if let idx = products.firstIndex(where: { $0.id == productId }) {
                if let n = update.name { products[idx].name = n }
                if let b = update.brand { products[idx].brand = b }
                if let c = update.category { products[idx].category = c }
                if let u = update.unit { products[idx].unit = u }
            }
            self.toastMessage = "Product updated successfully"
            return true
        }
        do {
            let updated = try await client.updateProduct(id: productId, update: update)
            self.toastMessage = "Product updated successfully"
            
            await loadData()
            await selectProduct(updated)
            return true
        } catch {
            self.errorMessage = error.localizedDescription
            return false
        }
    }
    
    public func createManualInventory(product: ProductCreate?, productId: Int?, batch: InventoryBatchCreate) async -> Bool {
        if isPreview {
            self.toastMessage = "Inventory added successfully"
            return true
        }
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
    
    public func updateBatchMetadata(batchId: Int, updates: [String: Any]) async -> Bool {
        if isPreview {
            self.toastMessage = "Batch updated successfully"
            return true
        }
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
