import Foundation
import SwiftUI
import Combine

public enum ShoppingFilter: String, CaseIterable, Identifiable {
    case all = "All"
    case pending = "To Buy"
    case completed = "Purchased"
    
    public var id: String { rawValue }
}

@MainActor
public class ShoppingViewModel: ObservableObject {
    @Published public var items: [ShoppingItem] = []
    @Published public var filter: ShoppingFilter = .all
    @Published public var newItemName: String = ""
    @Published public var newItemQuantity: Double = 1.0
    
    @Published public var isLoading: Bool = false
    @Published public var isGenerating: Bool = false
    @Published public var errorMessage: String? = nil
    @Published public var toastMessage: String? = nil
    
    private let client: APIClient
    public var isPreview: Bool
    
    public init(client: APIClient = .shared, isPreview: Bool = false) {
        self.client = client
        self.isPreview = isPreview
    }
    
    public var filteredItems: [ShoppingItem] {
        switch filter {
        case .all:
            return items
        case .pending:
            return items.filter { !$0.is_bought }
        case .completed:
            return items.filter { $0.is_bought }
        }
    }
    
    public var pendingCount: Int {
        items.filter { !$0.is_bought }.count
    }
    
    public func loadItems() async {
        if isPreview { return }
        isLoading = true
        errorMessage = nil
        do {
            self.items = try await client.fetchShoppingList()
        } catch {
            self.errorMessage = error.localizedDescription
        }
        
        self.isLoading = false
    }
    
    public func addItem() async {
        let name = newItemName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        
        if isPreview {
            let mockItem = ShoppingItem(
                id: (items.map { $0.id }.max() ?? 0) + 1,
                name: name,
                product_id: nil,
                quantity: newItemQuantity,
                unit: "pcs",
                is_bought: false,
                notes: nil
            )
            self.items.insert(mockItem, at: 0)
            self.newItemName = ""
            self.newItemQuantity = 1.0
            self.toastMessage = "Added \(name) to list"
            return
        }

        let createItem = ShoppingItemCreate(
            name: name,
            quantity: newItemQuantity,
            unit: "unit"
        )
        
        do {
            let item = try await client.createShoppingItem(createItem)
            self.items.insert(item, at: 0)
            self.newItemName = ""
            self.newItemQuantity = 1.0
            self.toastMessage = "Added \(item.name) to list"
        } catch {
            self.errorMessage = "Failed to add item: \(error.localizedDescription)"
        }
    }
    public func toggleItem(_ item: ShoppingItem) async {
        if isPreview {
            if let idx = items.firstIndex(where: { $0.id == item.id }) {
                items[idx].is_bought.toggle()
            }
            return
        }
        // Optimistic UI update
        if let idx = items.firstIndex(where: { $0.id == item.id }) {
            items[idx].is_bought.toggle()
        }
        
        do {
            let updated = try await client.toggleShoppingItem(id: item.id)
            if let idx = items.firstIndex(where: { $0.id == item.id }) {
                items[idx] = updated
            }
        } catch {
            // Revert optimistic update
            if let idx = items.firstIndex(where: { $0.id == item.id }) {
                items[idx].is_bought.toggle()
            }
            self.errorMessage = "Failed to update item: \(error.localizedDescription)"
        }
    }
    
    public func deleteItem(_ item: ShoppingItem) async {
        if isPreview {
            items.removeAll { $0.id == item.id }
            self.toastMessage = "Item deleted"
            return
        }
        let original = items
        items.removeAll { $0.id == item.id }
        do {
            try await client.deleteShoppingItem(id: item.id)
            self.toastMessage = "Item deleted"
        } catch {
            self.items = original
            self.errorMessage = "Failed to delete item: \(error.localizedDescription)"
        }
    }
    
    public func clearCompleted() async {
        if isPreview {
            items.removeAll { $0.is_bought }
            self.toastMessage = "Completed items cleared"
            return
        }
        do {
            try await client.clearCompletedShoppingItems()
            self.items.removeAll { $0.is_bought }
            self.toastMessage = "Completed items cleared"
        } catch {
            self.errorMessage = "Failed to clear completed items: \(error.localizedDescription)"
        }
    }
    
    public func autoGenerateSuggestions() async {
        if isPreview {
            self.toastMessage = "Generated 2 low-stock suggestions"
            return
        }
        isGenerating = true
        errorMessage = nil
        
        do {
            let suggestions = try await client.generateShoppingSuggestions(threshold: 2.0)
            self.toastMessage = "Generated \(suggestions.count) low-stock suggestions"
            await loadItems()
        } catch {
            self.errorMessage = "Failed to generate suggestions: \(error.localizedDescription)"
        }
        
        self.isGenerating = false
    }
}
