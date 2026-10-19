import SwiftUI

public struct ShoppingListView: View {
    @ObservedObject var viewModel: ShoppingViewModel
    @State private var showingClearDoneConfirmation: Bool = false
    @State private var itemToDelete: ShoppingItem? = nil
    
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
            .scrollDismissesKeyboard(.interactively)
            .background(ProvisionTheme.background.ignoresSafeArea())
            .navigationTitle("Shopping List")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    if viewModel.items.contains(where: { $0.is_bought }) {
                        Button("Clear Done") {
                            showingClearDoneConfirmation = true
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
            .alert("Clear Completed Items?", isPresented: $showingClearDoneConfirmation) {
                Button("Cancel", role: .cancel) {}
                Button("Clear All", role: .destructive) {
                    Task { await viewModel.clearCompleted() }
                }
            } message: {
                let count = viewModel.items.filter { $0.is_bought }.count
                Text("Are you sure you want to remove \(count) completed item(s) from your shopping list?")
            }
            .alert("Delete Item?", isPresented: Binding(get: { itemToDelete != nil }, set: { if !$0 { itemToDelete = nil } })) {
                Button("Cancel", role: .cancel) { itemToDelete = nil }
                Button("Delete", role: .destructive) {
                    if let item = itemToDelete {
                        Task { await viewModel.deleteItem(item) }
                    }
                    itemToDelete = nil
                }
            } message: {
                if let item = itemToDelete {
                    Text("Are you sure you want to remove '\(item.name)' from your shopping list?")
                }
            }
            .overlay(alignment: .bottom) {
                if let msg = viewModel.toastMessage {
                    toastView(message: msg, isError: false)
                } else if let err = viewModel.errorMessage {
                    toastView(message: err, isError: true)
                }
            }
        }
    }
    
    // MARK: - Subviews
    
    private var autoGenerateBanner: some View {
        Button {
            Task { await viewModel.autoGenerateSuggestions() }
        } label: {
            HStack(spacing: 10) {
                if viewModel.isGenerating {
                    ProgressView()
                        .tint(ProvisionTheme.provisionGreen)
                } else {
                    Image(systemName: "sparkles")
                        .font(.system(size: 16))
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                }
                
                Text(viewModel.isGenerating ? "Analyzing inventory stock..." : "Auto-Generate from Low Stock")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                
                Spacer()
                
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(ProvisionTheme.provisionGreen.opacity(0.7))
            }
            .frame(minHeight: 44)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(ProvisionTheme.provisionGreenLight)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(ProvisionTheme.provisionGreen.opacity(0.25), lineWidth: 1)
            )
        }
        .disabled(viewModel.isGenerating)
        .accessibleTouchTarget()
    }
    
    private var addItemBar: some View {
        HStack(spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "plus.circle")
                    .font(.system(size: 15))
                    .foregroundStyle(ProvisionTheme.textTertiary)
                TextField("Add grocery item...", text: $viewModel.newItemName)
                    .font(.system(size: 15))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .tint(ProvisionTheme.provisionGreen)
                    .onSubmit {
                        Task { await viewModel.addItem() }
                    }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(ProvisionTheme.inputBackground)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(ProvisionTheme.border, lineWidth: 1)
            )
            
            Button {
                Task { await viewModel.addItem() }
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 44, height: 44)
                    .background(viewModel.newItemName.trimmingCharacters(in: .whitespaces).isEmpty ? ProvisionTheme.provisionGreen.opacity(0.4) : ProvisionTheme.provisionGreen)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .disabled(viewModel.newItemName.trimmingCharacters(in: .whitespaces).isEmpty)
            .accessibleTouchTarget()
        }
    }
    
    private var shoppingItemsList: some View {
        List {
            ForEach(viewModel.filteredItems) { item in
                HStack(spacing: 12) {
                    // Checkbox button with haptic feedback and accessible touch target
                    Button {
                        HapticFeedback.light()
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
                        .accessibleTouchTarget()
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(item.is_bought ? "Mark \(item.name) as needed" : "Mark \(item.name) as purchased")
                    .accessibilityValue(item.is_bought ? "Purchased" : "To buy")
                    
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
                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                    Button(role: .destructive) {
                        itemToDelete = item
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                    .tint(ProvisionTheme.redAlert)
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
            if viewModel.filter == .all {
                Image("pip_grocery")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 110, height: 110)
                    .accessibilityHidden(true)
            } else {
                Image(systemName: emptyStateIcon)
                    .font(.system(size: 48))
                    .foregroundStyle(ProvisionTheme.textTertiary)
            }
            
            Text(emptyStateTitle)
                .font(ProvisionTypography.sectionSerif)
                .foregroundStyle(ProvisionTheme.textPrimary)
            
            Text(emptyStateSubtitle)
                .font(ProvisionTypography.subheadline)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
            Spacer()
        }
    }

    private var emptyStateIcon: String {
        switch viewModel.filter {
        case .all: return "cart"
        case .pending: return "checklist"
        case .completed: return "checkmark.circle"
        }
    }

    private var emptyStateTitle: String {
        switch viewModel.filter {
        case .all: return "Shopping List is Empty"
        case .pending: return "No Items to Buy"
        case .completed: return "No Completed Items"
        }
    }

    private var emptyStateSubtitle: String {
        switch viewModel.filter {
        case .all:
            return "Add grocery items manually above or tap 'Auto-Generate' to restock low pantry supplies."
        case .pending:
            return "You're all caught up! Everything on your list has been purchased."
        case .completed:
            return "Items you check off as bought will appear here until cleared."
        }
    }

    private func toastView(message: String, isError: Bool) -> some View {
        HStack(spacing: 8) {
            Image(systemName: isError ? "exclamationmark.circle.fill" : "checkmark.circle.fill")
                .foregroundStyle(isError ? ProvisionTheme.redAlert : ProvisionTheme.provisionGreen)
            Text(message)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(ProvisionTheme.textPrimary)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(isError ? ProvisionTheme.redLight : ProvisionTheme.provisionGreenLight)
        .clipShape(Capsule())
        .shadow(color: .black.opacity(0.08), radius: 6, y: 3)
        .padding(.bottom, 16)
    }
}

#Preview("Shopping List - Philippine Household") {
    ShoppingListView(viewModel: PreviewData.makeShoppingViewModel())
}
