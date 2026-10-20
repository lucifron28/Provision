import SwiftUI

// MARK: - Reusable Searchable Product Selector Component
// Apple HIG compliant product search and selection with progressive disclosure.

public struct SearchableProductSelector: View {
    public let products: [Product]
    @Binding public var selectedProductId: Int?
    public var onSelect: ((Product) -> Void)? = nil
    public var placeholder: String = "Search by product name, brand, or barcode..."

    @State private var searchQuery: String = ""
    @State private var isExpanded: Bool = false

    public init(
        products: [Product],
        selectedProductId: Binding<Int?>,
        placeholder: String = "Search by product name, brand, or barcode...",
        onSelect: ((Product) -> Void)? = nil
    ) {
        self.products = products
        self._selectedProductId = selectedProductId
        self.placeholder = placeholder
        self.onSelect = onSelect
    }

    public var selectedProduct: Product? {
        guard let id = selectedProductId else { return nil }
        return products.first(where: { $0.id == id })
    }

    public var filteredProducts: [Product] {
        let query = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !query.isEmpty else { return products }
        return products.filter { prod in
            let nameMatch = prod.name.lowercased().contains(query)
            let brandMatch = prod.brand?.lowercased().contains(query) == true
            let barcodeMatch = prod.barcode?.contains(query) == true
            let categoryMatch = prod.category?.lowercased().contains(query) == true
            return nameMatch || brandMatch || barcodeMatch || categoryMatch
        }
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Selected Product Card or Trigger
            if let selected = selectedProduct {
                selectedProductCard(product: selected)
            } else {
                selectorTrigger
            }

            // Expandable Search & Match List
            if isExpanded || selectedProduct == nil {
                searchField

                if filteredProducts.isEmpty {
                    emptySearchNotice
                } else {
                    matchingProductsList
                }
            }
        }
    }

    // MARK: - Selected Product Display

    private func selectedProductCard(product: Product) -> some View {
        HStack(alignment: .center, spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(ProvisionTheme.provisionGreenLight)
                    .frame(width: 40, height: 40)
                Image(systemName: "checkmark.seal.fill")
                    .font(.system(size: 18))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(product.name)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .lineLimit(1)

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

            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            } label: {
                Text(isExpanded ? "Done" : "Change")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(ProvisionTheme.provisionGreenLight)
                    .clipShape(Capsule())
            }
            .buttonStyle(.plain)
            .accessibleTouchTarget()
        }
        .padding(10)
        .background(ProvisionTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(ProvisionTheme.provisionGreen.opacity(0.3), lineWidth: 1)
        )
    }

    private var selectorTrigger: some View {
        HStack(spacing: 8) {
            Image(systemName: "shippingbox")
                .font(.system(size: 14))
                .foregroundStyle(ProvisionTheme.provisionGreen)
            Text("Select an existing catalog product...")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(ProvisionTheme.textSecondary)
            Spacer()
        }
        .padding(.vertical, 4)
    }

    // MARK: - Search Input Field

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 13))
                .foregroundStyle(ProvisionTheme.textTertiary)

            TextField(placeholder, text: $searchQuery)
                .font(.system(size: 13))
                .foregroundStyle(ProvisionTheme.textPrimary)
                .tint(ProvisionTheme.provisionGreen)

            if !searchQuery.isEmpty {
                Button {
                    searchQuery = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 13))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(ProvisionTheme.inputBackground)
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(ProvisionTheme.border, lineWidth: 1)
        )
    }

    // MARK: - Matching Products List

    private var matchingProductsList: some View {
        ScrollView(.vertical, showsIndicators: true) {
            LazyVStack(spacing: 6) {
                ForEach(Array(filteredProducts.prefix(8))) { prod in
                    let isCurrent = selectedProductId == prod.id

                    Button {
                        selectedProductId = prod.id
                        onSelect?(prod)
                        withAnimation(.easeInOut(duration: 0.2)) {
                            isExpanded = false
                        }
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(prod.name)
                                    .font(.system(size: 13, weight: isCurrent ? .bold : .medium))
                                    .foregroundStyle(ProvisionTheme.textPrimary)
                                    .lineLimit(1)

                                HStack(spacing: 4) {
                                    if let brand = prod.brand, !brand.isEmpty {
                                        Text(brand)
                                    }
                                    if let cat = prod.category, !cat.isEmpty {
                                        Text("• \(cat)")
                                    }
                                }
                                .font(.system(size: 11))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                            }

                            Spacer()

                            if isCurrent {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.system(size: 16))
                                    .foregroundStyle(ProvisionTheme.provisionGreen)
                            } else {
                                Text("Select")
                                    .font(.system(size: 11, weight: .bold))
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(ProvisionTheme.surfaceSecondary)
                                    .foregroundStyle(ProvisionTheme.textPrimary)
                                    .clipShape(Capsule())
                            }
                        }
                        .padding(8)
                        .background(isCurrent ? ProvisionTheme.provisionGreenLight.opacity(0.5) : ProvisionTheme.surface)
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .accessibleTouchTarget()
                }
            }
        }
        .frame(maxHeight: 180)
    }

    private var emptySearchNotice: some View {
        Text("No catalog products match '\(searchQuery)'.")
            .font(.system(size: 11))
            .foregroundStyle(ProvisionTheme.textSecondary)
            .padding(.vertical, 4)
    }
}
