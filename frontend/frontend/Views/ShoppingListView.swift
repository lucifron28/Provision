import SwiftUI

public struct ShoppingListView: View {
    @ObservedObject var viewModel: ShoppingViewModel
    
    public init(viewModel: ShoppingViewModel) {
        self.viewModel = viewModel
    }
    
    public var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Filter Picker
                Picker("Filter", selection: $viewModel.filter) {
                    ForEach(ShoppingFilter.allCases) { filter in
                        Text(filter.rawValue).tag(filter)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                
                // Low-Stock Auto Suggestion Bar
                autoGenerateBanner
                    .padding(.horizontal, 16)
                    .padding(.bottom, 8)
                
                // Add Item Row
                addItemBar
                    .padding(.horizontal, 16)
                    .padding(.bottom, 12)
                
                // Items List
                if viewModel.isLoading && viewModel.items.isEmpty {
                    Spacer()
                    ProgressView("Loading shopping list...")
                    Spacer()
                } else if viewModel.filteredItems.isEmpty {
                    emptyShoppingList
                } else {
                    shoppingItemsList
                }
            }
            .background(ProvisionTheme.background.ignoresSafeArea())
            .navigationTitle("Shopping List")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    if viewModel.items.contains(where: { $0.is_bought }) {
                        Button("Clear Done") {
                            Task { await viewModel.clearCompleted() }
                        }
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.redAlert)
                    }
                }
            }
            .task {
                if viewModel.items.isEmpty {
                    await viewModel.loadItems()
                }
            }
        }
    }
    
    // MARK: - Subviews
    
    private var autoGenerateBanner: some View {
        Button {
            Task { await viewModel.autoGenerateSuggestions() }
        } label: {
            HStack(spacing: 8) {
                if viewModel.isGenerating {
                    ProgressView()
                        .tint(ProvisionTheme.provisionGreen)
                } else {
                    Image(systemName: "sparkles")
                        .font(.system(size: 15))
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                }
                
                Text(viewModel.isGenerating ? "Analyzing inventory stock..." : "Auto-Generate from Low Stock")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                
                Spacer()
                
                Image(systemName: "chevron.right")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(ProvisionTheme.provisionGreen.opacity(0.6))
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(ProvisionTheme.provisionGreenLight)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .disabled(viewModel.isGenerating)
    }
    
    private var addItemBar: some View {
        HStack(spacing: 8) {
            TextField("Add grocery item...", text: $viewModel.newItemName)
                .font(.system(size: 14))
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(ProvisionTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(ProvisionTheme.border, lineWidth: 1))
                .onSubmit {
                    Task { await viewModel.addItem() }
                }
            
            Button {
                Task { await viewModel.addItem() }
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 40, height: 40)
                    .background(ProvisionTheme.provisionGreen)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
            }
            .disabled(viewModel.newItemName.trimmingCharacters(in: .whitespaces).isEmpty)
        }
    }
    
    private var shoppingItemsList: some View {
        List {
            ForEach(viewModel.filteredItems) { item in
                HStack(spacing: 12) {
                    // Checkbox button
                    Button {
                        Task { await viewModel.toggleItem(item) }
                    } label: {
                        ZStack {
                            Circle()
                                .stroke(item.is_bought ? ProvisionTheme.provisionGreen : ProvisionTheme.border, lineWidth: 2)
                                .frame(width: 24, height: 24)
                            
                            if item.is_bought {
                                Circle()
                                    .fill(ProvisionTheme.provisionGreen)
                                    .frame(width: 16, height: 16)
                                Image(systemName: "checkmark")
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundStyle(.white)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.name)
                            .font(.system(size: 16, weight: .medium))
                            .strikethrough(item.is_bought, color: ProvisionTheme.textTertiary)
                            .foregroundStyle(item.is_bought ? ProvisionTheme.textTertiary : ProvisionTheme.textPrimary)
                        
                        if let notes = item.notes, !notes.isEmpty {
                            Text(notes)
                                .font(.system(size: 12))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                        }
                    }
                    
                    Spacer()
                    
                    Text("\(item.displayQuantity) \(item.unit ?? "unit")")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(item.is_bought ? ProvisionTheme.textTertiary : ProvisionTheme.textSecondary)
                }
                .padding(.vertical, 6)
                .listRowBackground(ProvisionTheme.surface)
                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                    Button(role: .destructive) {
                        Task { await viewModel.deleteItem(item) }
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .refreshable {
            await viewModel.loadItems()
        }
    }
    
    private var emptyShoppingList: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "cart")
                .font(.system(size: 48))
                .foregroundStyle(ProvisionTheme.textTertiary)
            
            Text("No Items in Shopping List")
                .font(.system(size: 18, weight: .bold, design: .serif))
                .foregroundStyle(ProvisionTheme.textPrimary)
            
            Text("Add pantry items you need to restock or tap 'Auto-Generate' to populate based on low inventory.")
                .font(.system(size: 14))
                .foregroundStyle(ProvisionTheme.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
            Spacer()
        }
    }
}

#Preview("Shopping List - Philippine Household") {
    ShoppingListView(viewModel: PreviewData.makeShoppingViewModel())
}
