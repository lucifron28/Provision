import SwiftUI

public struct InventoryView: View {
    @ObservedObject var viewModel: InventoryViewModel
    @State private var showingFilterSheet: Bool = false
    
    public init(viewModel: InventoryViewModel) {
        self.viewModel = viewModel
    }
    
    public var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Search Bar & Filter Header
                searchAndFilterHeader
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                
                // Category Chips Scroll
                categoryChipsBar
                    .padding(.bottom, 8)
                
                // Products List
                if viewModel.isLoading && viewModel.products.isEmpty {
                    Spacer()
                    ProgressView("Loading inventory...")
                    Spacer()
                } else if viewModel.filteredProducts.isEmpty {
                    emptyInventoryState
                } else {
                    productsList
                }
            }
            .background(ProvisionTheme.background.ignoresSafeArea())
            .navigationTitle("Inventory")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await viewModel.loadData() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                    }
                }
            }
            .task {
                if viewModel.products.isEmpty {
                    await viewModel.loadData()
                }
            }
        }
    }
    
    // MARK: - Subviews
    
    private var searchAndFilterHeader: some View {
        HStack(spacing: 10) {
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(ProvisionTheme.textTertiary)
                
                TextField("Search inventory, barcode...", text: $viewModel.searchText)
                    .font(.system(size: 15))
                    .autocorrectionDisabled()
                
                if !viewModel.searchText.isEmpty {
                    Button {
                        viewModel.searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(ProvisionTheme.textTertiary)
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(ProvisionTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(ProvisionTheme.border, lineWidth: 1))
            
            if viewModel.selectedCategory != nil {
                Button {
                    viewModel.selectedCategory = nil
                } label: {
                    Text("Clear")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.redAlert)
                        .padding(.horizontal, 8)
                }
            }
        }
    }
    
    private var categoryChipsBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                // All Chip
                categoryChip(title: "All", isSelected: viewModel.selectedCategory == nil) {
                    viewModel.selectedCategory = nil
                }
                
                // Dynamic or Default Category Chips
                let cats = viewModel.categories.isEmpty ? ["Canned Goods", "Dairy", "Snacks", "Produce", "Pantry"] : viewModel.categories
                ForEach(cats, id: \.self) { cat in
                    categoryChip(title: cat, isSelected: viewModel.selectedCategory == cat) {
                        viewModel.selectedCategory = cat
                    }
                }
            }
            .padding(.horizontal, 16)
        }
    }
    
    private func categoryChip(title: String, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 13, weight: isSelected ? .bold : .medium))
                .padding(.horizontal, 14)
                .padding(.vertical, 7)
                .background(isSelected ? ProvisionTheme.provisionGreen : ProvisionTheme.surface)
                .foregroundStyle(isSelected ? .white : ProvisionTheme.textPrimary)
                .clipShape(Capsule())
                .overlay(
                    Capsule()
                        .stroke(isSelected ? ProvisionTheme.provisionGreen : ProvisionTheme.border, lineWidth: 1)
                )
        }
    }
    
    private var productsList: some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                ForEach(viewModel.filteredProducts) { product in
                    NavigationLink {
                        ProductDetailView(viewModel: viewModel, product: product)
                    } label: {
                        productRow(product: product)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
        .refreshable {
            await viewModel.loadData()
        }
    }
    
    private func productRow(product: Product) -> some View {
        HStack(spacing: 12) {
            // Health indicator dot
            Circle()
                .fill(statusColor(for: product))
                .frame(width: 10, height: 10)
            
            VStack(alignment: .leading, spacing: 3) {
                Text(product.name)
                    .font(.system(size: 16, weight: .bold, design: .serif))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                
                Text(product.subtitle)
                    .font(.system(size: 12))
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
            
            Spacer()
            
            VStack(alignment: .trailing, spacing: 2) {
                Text("\(product.displayStock) \(product.displayUnit)")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(product.isOutOfStock ? ProvisionTheme.redAlert : ProvisionTheme.textPrimary)
                
                if product.isOutOfStock {
                    Text("Out of stock")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.redAlert)
                } else if product.isLowStock {
                    Text("Low stock")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.amberWarning)
                } else {
                    Text("In stock")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                }
            }
            
            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(ProvisionTheme.textTertiary)
        }
        .padding(14)
        .provisionCard()
    }
    
    private var emptyInventoryState: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "tray.fill")
                .font(.system(size: 48))
                .foregroundStyle(ProvisionTheme.textTertiary)
            
            Text("No Products Found")
                .font(.system(size: 18, weight: .bold, design: .serif))
                .foregroundStyle(ProvisionTheme.textPrimary)
            
            Text("Try clearing your search or category filters, or scan new items into your pantry.")
                .font(.system(size: 14))
                .foregroundStyle(ProvisionTheme.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
            
            if !viewModel.searchText.isEmpty || viewModel.selectedCategory != nil {
                Button("Reset Filters") {
                    viewModel.searchText = ""
                    viewModel.selectedCategory = nil
                }
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(ProvisionTheme.provisionGreen)
                .padding(.top, 4)
            }
            Spacer()
        }
    }
    
    private func statusColor(for product: Product) -> Color {
        if product.isOutOfStock {
            return ProvisionTheme.redAlert
        } else if product.isLowStock {
            return ProvisionTheme.amberWarning
        } else {
            return ProvisionTheme.provisionGreen
        }
    }
}
