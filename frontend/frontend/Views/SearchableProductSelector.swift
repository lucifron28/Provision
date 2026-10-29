import SwiftUI

// MARK: - Reusable Searchable Product Selector Component
// Apple HIG compliant compact selector row presenting a native searchable sheet.

public struct SearchableProductSelector: View {
    public let products: [Product]
    @Binding public var selectedProductId: Int?
    public var onSelect: ((Product) -> Void)? = nil
    public var placeholder: String = "Select from catalog..."

    private var externalSheetBinding: Binding<Bool>?
    @State private var internalShowingSheet: Bool = false
    @State public var searchQuery: String = ""
    @State public var selectedCategory: String? = nil

    private var sheetBinding: Binding<Bool> {
        Binding(
            get: { externalSheetBinding?.wrappedValue ?? internalShowingSheet },
            set: { newValue in
                if let ext = externalSheetBinding {
                    ext.wrappedValue = newValue
                } else {
                    internalShowingSheet = newValue
                }
            }
        )
    }

    public var showingSheet: Bool {
        get { sheetBinding.wrappedValue }
        nonmutating set { sheetBinding.wrappedValue = newValue }
    }

    public init(
        products: [Product],
        selectedProductId: Binding<Int?>,
        placeholder: String = "Select from catalog...",
        isPresented: Binding<Bool>? = nil,
        onSelect: ((Product) -> Void)? = nil
    ) {
        self.products = products
        self._selectedProductId = selectedProductId
        self.placeholder = placeholder
        self.externalSheetBinding = isPresented
        self.onSelect = onSelect
    }

    public var selectedProduct: Product? {
        guard let id = selectedProductId else { return nil }
        return products.first(where: { $0.id == id })
    }

    public var categories: [String] {
        Set(products.compactMap { $0.category }).sorted()
    }

    public func filteredProducts(matching query: String, category: String? = nil) -> [Product] {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return products.filter { prod in
            let matchesQuery = q.isEmpty ||
                prod.name.lowercased().contains(q) ||
                (prod.brand?.lowercased().contains(q) == true) ||
                (prod.barcode?.contains(q) == true) ||
                (prod.category?.lowercased().contains(q) == true)

            let matchesCategory = category == nil || prod.category == category
            return matchesQuery && matchesCategory
        }
    }

    public var filteredProducts: [Product] {
        filteredProducts(matching: searchQuery, category: selectedCategory)
    }
    public func openSheet() {
        searchQuery = ""
        selectedCategory = nil
        showingSheet = true
    }

    public func cancelAndDismiss() {
        showingSheet = false
    }

    public func selectProduct(_ product: Product) {
        selectedProductId = product.id
        onSelect?(product)
        showingSheet = false
    }

    public var body: some View {
        Button {
            openSheet()
        } label: {
            if let selected = selectedProduct {
                compactSelectedProductRow(product: selected)
            } else {
                compactPlaceholderRow
            }
        }
        .buttonStyle(.plain)
        .accessibleTouchTarget()
        .sheet(isPresented: sheetBinding) {
            catalogSearchSheet
        }
    }
    // MARK: - Compact Row Displays

    private func compactSelectedProductRow(product: Product) -> some View {
        HStack(alignment: .center, spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(ProvisionTheme.provisionGreenLight)
                    .frame(width: 36, height: 36)
                Image(systemName: "checkmark.seal.fill")
                    .font(.system(size: 16))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(product.name)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .lineLimit(2)
                    .minimumScaleFactor(0.85)
                HStack(spacing: 4) {
                    if let brand = product.brand, !brand.isEmpty {
                        Text(brand)
                    }
                    if let cat = product.category, !cat.isEmpty {
                        Text("• \(cat)")
                    }
                }
                .font(.system(size: 11))
                .foregroundStyle(ProvisionTheme.textSecondary)
            }

            Spacer()

            HStack(spacing: 4) {
                Text("Change")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                Image(systemName: "chevron.right")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(ProvisionTheme.provisionGreenLight)
            .clipShape(Capsule())
        }
        .padding(10)
        .background(ProvisionTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(ProvisionTheme.provisionGreen.opacity(0.3), lineWidth: 1)
        )
    }

    private var compactPlaceholderRow: some View {
        HStack(spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(ProvisionTheme.surfaceSecondary)
                    .frame(width: 36, height: 36)
                Image(systemName: "shippingbox")
                    .font(.system(size: 15))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }

            Text(placeholder)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(ProvisionTheme.textSecondary)

            Spacer()

            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(ProvisionTheme.textTertiary)
        }
        .padding(10)
        .background(ProvisionTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(ProvisionTheme.border, lineWidth: 1)
        )
    }

    // MARK: - Native Searchable Sheet

    private var catalogSearchSheet: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Search Input Field
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 14))
                        .foregroundStyle(ProvisionTheme.textTertiary)

                    TextField("Search catalog by name, brand, barcode...", text: $searchQuery)
                        .font(.system(size: 14))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                        .tint(ProvisionTheme.provisionGreen)

                    if !searchQuery.isEmpty {
                        Button {
                            searchQuery = ""
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 14))
                                .foregroundStyle(ProvisionTheme.textTertiary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 9)
                .background(ProvisionTheme.inputBackground)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .stroke(ProvisionTheme.border, lineWidth: 1)
                )
                .padding(.horizontal, 16)
                .padding(.top, 10)
                .padding(.bottom, 8)

                // Category Filter Chips
                if !categories.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            categoryPill(title: "All", isSelected: selectedCategory == nil) {
                                selectedCategory = nil
                            }

                            ForEach(categories, id: \.self) { cat in
                                categoryPill(title: cat, isSelected: selectedCategory == cat) {
                                    selectedCategory = cat
                                }
                            }
                        }
                        .padding(.horizontal, 16)
                    }
                    .padding(.bottom, 8)
                }

                Divider()
                    .background(ProvisionTheme.border)

                // Results Count Bar
                HStack {
                    Text("Showing \(filteredProducts.count) product\(filteredProducts.count == 1 ? "" : "s")")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                    Spacer()
                    if selectedCategory != nil || !searchQuery.isEmpty {
                        Button("Reset") {
                            searchQuery = ""
                            selectedCategory = nil
                        }
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.redAlert)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 8)
                .padding(.bottom, 4)

                // Matching Products List
                if filteredProducts.isEmpty {
                    VStack(spacing: 12) {
                        Spacer()
                        Image("pip_thinking")
                            .resizable()
                            .scaledToFit()
                            .frame(width: 64, height: 64)
                            .accessibilityHidden(true)

                        Text("No Products Found")
                            .font(ProvisionTypography.headline)
                            .foregroundStyle(ProvisionTheme.textPrimary)

                        Text(searchQuery.isEmpty ? "No products in this category." : "No catalog products match '\(searchQuery)'.")
                            .font(ProvisionTypography.footnote)
                            .foregroundStyle(ProvisionTheme.textSecondary)

                        Spacer()
                    }
                    .frame(maxWidth: .infinity)
                    .padding(24)
                } else {
                    ScrollView {
                        LazyVStack(spacing: 8) {
                            ForEach(filteredProducts) { prod in
                                let isCurrent = selectedProductId == prod.id

                                Button {
                                    selectProduct(prod)
                                } label: {
                                    catalogRow(product: prod, isSelected: isCurrent)
                                }
                                .buttonStyle(.plain)
                                .accessibleTouchTarget()
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                    }
                }
            }
            .background(ProvisionTheme.background.ignoresSafeArea())
            .navigationTitle("Select Catalog Product")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        cancelAndDismiss()
                    }
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                }
            }
        }
    }

    private func categoryPill(title: String, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 12, weight: isSelected ? .bold : .medium))
                .padding(.horizontal, 11)
                .padding(.vertical, 6)
                .background(isSelected ? ProvisionTheme.provisionGreen : ProvisionTheme.surface)
                .foregroundStyle(isSelected ? ProvisionTheme.onAccent : ProvisionTheme.textPrimary)
                .clipShape(Capsule())
                .overlay(
                    Capsule().stroke(isSelected ? ProvisionTheme.provisionGreen : ProvisionTheme.border, lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }

    private func catalogRow(product: Product, isSelected: Bool) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(product.name)
                    .font(.system(size: 15, weight: isSelected ? .bold : .semibold))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .lineLimit(2)
                    .minimumScaleFactor(0.85)
                HStack(spacing: 6) {
                    if let brand = product.brand, !brand.isEmpty {
                        Text(brand)
                            .font(.system(size: 12))
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }
                    if let cat = product.category, !cat.isEmpty {
                        Text("• \(cat)")
                            .font(.system(size: 12))
                            .foregroundStyle(ProvisionTheme.textTertiary)
                    }
                    if let barcode = product.barcode, !barcode.isEmpty {
                        Text("• \(barcode)")
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(ProvisionTheme.textTertiary)
                    }
                }
            }

            Spacer()

            if isSelected {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 18))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            } else {
                Text("Select")
                    .font(.system(size: 12, weight: .bold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(ProvisionTheme.surfaceSecondary)
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .clipShape(Capsule())
            }
        }
        .padding(12)
        .background(isSelected ? ProvisionTheme.provisionGreenLight.opacity(0.4) : ProvisionTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(isSelected ? ProvisionTheme.provisionGreen.opacity(0.5) : ProvisionTheme.border, lineWidth: 1)
        )
    }
}
