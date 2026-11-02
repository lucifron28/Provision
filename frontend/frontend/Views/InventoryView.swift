import SwiftUI

public struct InventoryView: View {
    @ObservedObject var viewModel: InventoryViewModel

    @State private var showingFilterSheet: Bool = false
    @State private var showingAddSheet: Bool = false
    
    
    public init(viewModel: InventoryViewModel) {
        self.viewModel = viewModel
    }
    
    public var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if viewModel.isOffline {
                    offlineBanner
                }

                // Search Bar
                searchBar
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
                    .padding(.bottom, 6)

                // Filter & Sort Control Strip
                filterAndSortControlsBar
                    .padding(.bottom, 6)
                // Result Count Bar
                resultCountBar
                    .padding(.horizontal, 16)
                    .padding(.bottom, 6)
                
                // Products List
                if viewModel.isLoading && viewModel.products.isEmpty {
                    Spacer()
                    ProgressView("Loading inventory...")
                        .tint(ProvisionTheme.provisionGreen)
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
                    HStack(spacing: 16) {
                        Button {
                            showingAddSheet = true
                        } label: {
                            Image(systemName: "plus")
                                .font(.system(size: 17, weight: .semibold))
                                .foregroundStyle(ProvisionTheme.provisionGreen)
                                .accessibleTouchTarget()
                        }
                        .accessibilityLabel("Add Product to Inventory")
                        
                        Button {
                            Task { await viewModel.loadData() }
                        } label: {
                            Image(systemName: "arrow.clockwise")
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundStyle(ProvisionTheme.provisionGreen)
                                .accessibleTouchTarget()
                        }
                        .accessibilityLabel("Refresh Inventory")
                    }
                }
            }
            .task {
                if viewModel.products.isEmpty {
                    await viewModel.loadData()
                }
            }
            .sheet(isPresented: $showingAddSheet) {
                AddInventoryView(viewModel: viewModel)
            }
        }
    }

// MARK: - Subviews

    private var offlineBanner: some View {
        HStack(spacing: 6) {
            Image(systemName: "wifi.slash")
                .font(.system(size: 13, weight: .semibold))
            Text("Offline Mode • Viewing Cached Pantry")
                .font(.system(size: 13, weight: .medium))
        }
        .foregroundStyle(ProvisionTheme.amberWarning)
        .padding(.horizontal, 14)
        .padding(.vertical, 6)
        .background(ProvisionTheme.amberLight)
        .clipShape(Capsule())
        .overlay(
            Capsule()
                .stroke(ProvisionTheme.amberWarning.opacity(0.3), lineWidth: 1)
        )
        .padding(.top, 4)
        .padding(.bottom, 4)
    }
    
    private var searchBar: some View {
        HStack(spacing: 10) {
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(ProvisionTheme.textTertiary)
                
                TextField("Search inventory, barcode...", text: $viewModel.searchText)
                    .font(.system(size: 15))
                    .autocorrectionDisabled()
                    .foregroundStyle(ProvisionTheme.textPrimary)
                
                if !viewModel.searchText.isEmpty {
                    Button {
                        viewModel.searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(ProvisionTheme.textTertiary)
                    }
                    .accessibleTouchTarget()
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(ProvisionTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(ProvisionTheme.border, lineWidth: 1))
        }
    }

    private var filterAndSortControlsBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                // Category Filter Menu
                Menu {
                    Button("All Categories") {
                        viewModel.selectedCategory = nil
                    }
                    Divider()
                    let cats = viewModel.categories.isEmpty ? ["Canned Goods", "Dairy", "Snacks", "Produce", "Pantry"] : viewModel.categories
                    ForEach(cats, id: \.self) { cat in
                        Button(cat) {
                            viewModel.selectedCategory = cat
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "line.3.horizontal.decrease.circle")
                            .font(.system(size: 11, weight: .semibold))
                        Text(viewModel.selectedCategory ?? "All Categories")
                            .font(.system(size: 12, weight: viewModel.selectedCategory != nil ? .bold : .medium))
                            .lineLimit(1)
                        Image(systemName: "chevron.down")
                            .font(.system(size: 8, weight: .bold))
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .background(viewModel.selectedCategory != nil ? ProvisionTheme.provisionGreen : ProvisionTheme.surface)
                    .foregroundStyle(viewModel.selectedCategory != nil ? ProvisionTheme.onAccent : ProvisionTheme.textPrimary)
                    .clipShape(Capsule())
                    .overlay(
                        Capsule().stroke(viewModel.selectedCategory != nil ? ProvisionTheme.provisionGreen : ProvisionTheme.border, lineWidth: 1)
                    )
                }

                // Sort Menu
                Menu {
                    ForEach(InventorySortOption.allCases) { opt in
                        Button {
                            viewModel.sortOption = opt
                        } label: {
                            HStack {
                                Text(opt.rawValue)
                                if viewModel.sortOption == opt {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.up.arrow.down")
                            .font(.system(size: 10, weight: .semibold))
                        Text(viewModel.sortOption.rawValue)
                            .font(.system(size: 12, weight: .medium))
                            .lineLimit(1)
                        Image(systemName: "chevron.down")
                            .font(.system(size: 8, weight: .bold))
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .background(ProvisionTheme.surface)
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .clipShape(Capsule())
                    .overlay(
                        Capsule().stroke(ProvisionTheme.border, lineWidth: 1)
                    )
                }

                // Quick Status Filter Chips
                ForEach(InventoryQuickFilter.allCases) { filter in
                    let isSelected = viewModel.activeQuickFilter == filter
                    Button {
                        viewModel.applyFilter(filter)
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: filter.icon)
                                .font(.system(size: 10, weight: .semibold))
                            Text(filter.title)
                                .font(.system(size: 12, weight: isSelected ? .bold : .medium))
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 7)
                        .background(isSelected ? ProvisionTheme.provisionGreen : ProvisionTheme.surface)
                        .foregroundStyle(isSelected ? ProvisionTheme.onAccent : ProvisionTheme.textPrimary)
                        .clipShape(Capsule())
                        .overlay(
                            Capsule().stroke(isSelected ? ProvisionTheme.provisionGreen : ProvisionTheme.border, lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .accessibleTouchTarget()
                }
            }
            .padding(.horizontal, 16)
        }
    }

    private var resultCountBar: some View {
        HStack {
            Text("Showing \(viewModel.filteredProducts.count) \(viewModel.filteredProducts.count == 1 ? "item" : "items")")
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(ProvisionTheme.textSecondary)

            Spacer()

            if isAnyFilterActive {
                Button("Reset Filters") {
                    viewModel.searchText = ""
                    viewModel.selectedCategory = nil
                    viewModel.activeQuickFilter = .all
                    viewModel.sortOption = .nameAsc
                }
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(ProvisionTheme.redAlert)
                .accessibleTouchTarget()
            }
        }
    }

    private var isAnyFilterActive: Bool {
        !viewModel.searchText.isEmpty ||
        viewModel.selectedCategory != nil ||
        viewModel.activeQuickFilter != .all ||
        viewModel.sortOption != .nameAsc
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
            VStack(alignment: .leading, spacing: 4) {
                Text(product.name)
                    .font(.system(size: 16, weight: .bold, design: .serif))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .lineLimit(1)
                
                Text(product.subtitle)
                    .font(.system(size: 12))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .lineLimit(1)

                // Status indicator (text + icon + color)
                productStatusBadge(for: product)
                    .padding(.top, 2)
            }
            
            Spacer()
            
            VStack(alignment: .trailing, spacing: 4) {
                Text("\(product.displayStock) \(product.displayUnit)")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(product.isOutOfStock ? ProvisionTheme.redAlert : ProvisionTheme.textPrimary)
                
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.textTertiary)
                    .padding(.top, 4)
            }
        }
        .padding(14)
        .provisionCard()
    }

    private func productStatusBadge(for product: Product) -> some View {
        let daysUntilExp = product.daysUntilExpiration ?? viewModel.productExpirations[product.id]
        
        if product.isOutOfStock || (product.total_remaining_quantity ?? 0) <= 0 {
            return HStack(spacing: 4) {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 10, weight: .bold))
                Text("Out of stock")
                    .font(.system(size: 11, weight: .semibold))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(ProvisionTheme.redLight)
            .foregroundStyle(ProvisionTheme.redAlert)
            .clipShape(Capsule())
        } else if let days = daysUntilExp, days <= 7 {
            let isUrgent = days <= 1
            let text: String = {
                if days < 0 { return "Expired (\(abs(days))d ago)" }
                if days == 0 { return "Expires today" }
                if days == 1 { return "Expires tomorrow" }
                return "Expires in \(days)d"
            }()
            return HStack(spacing: 4) {
                Image(systemName: isUrgent ? "exclamationmark.triangle.fill" : "clock.fill")
                    .font(.system(size: 10, weight: .bold))
                Text(text)
                    .font(.system(size: 11, weight: .semibold))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(isUrgent ? ProvisionTheme.redLight : ProvisionTheme.amberLight)
            .foregroundStyle(isUrgent ? ProvisionTheme.redAlert : ProvisionTheme.amberWarning)
            .clipShape(Capsule())
        } else if product.isLowStock || ((product.total_remaining_quantity ?? 0) > 0 && (product.total_remaining_quantity ?? 0) <= 2) {
            return HStack(spacing: 4) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 10, weight: .bold))
                Text("Low stock")
                    .font(.system(size: 11, weight: .semibold))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(ProvisionTheme.amberLight)
            .foregroundStyle(ProvisionTheme.amberWarning)
            .clipShape(Capsule())
        } else {
            return HStack(spacing: 4) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 10, weight: .bold))
                Text("In stock")
                    .font(.system(size: 11, weight: .semibold))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(ProvisionTheme.provisionGreenLight)
            .foregroundStyle(ProvisionTheme.provisionGreen)
            .clipShape(Capsule())
        }
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
                Button("Reset All Filters") {
                    viewModel.searchText = ""
                    viewModel.selectedCategory = nil
                    viewModel.applyFilter(.all)
                }
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

#Preview("Inventory - Philippine Catalog") {
    InventoryView(viewModel: PreviewData.makeInventoryViewModel())
}
