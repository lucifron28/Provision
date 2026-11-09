import SwiftUI

public struct ProductLabelReviewListView: View {
    @StateObject private var viewModel: ProductLabelListViewModel
    private let scope: HouseholdScope
    private let service: any CookWithPipWorkflowService
    private let onLabelReviewUpdated: () async -> Void
    @State private var searchText = ""

    public init(scope: HouseholdScope, service: any CookWithPipWorkflowService = APIClient.shared,
                onLabelReviewUpdated: @escaping () async -> Void = {}) {
        self.scope = scope
        self.service = service
        self.onLabelReviewUpdated = onLabelReviewUpdated
        _viewModel = StateObject(wrappedValue: ProductLabelListViewModel(scope: scope, service: service))
    }

    private var visibleProducts: [Product] {
        guard !searchText.isEmpty else { return viewModel.products }
        return viewModel.products.filter {
            $0.name.localizedCaseInsensitiveContains(searchText) || ($0.brand?.localizedCaseInsensitiveContains(searchText) == true)
        }
    }

    public var body: some View {
        Group {
            if viewModel.isLoading && viewModel.products.isEmpty {
                ProgressView("Loading household products")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .accessibilityIdentifier("pip-label-list-loading")
            } else if let error = viewModel.errorMessage, viewModel.products.isEmpty {
                ContentUnavailableView {
                    Label("Unable to load products", systemImage: "wifi.exclamationmark")
                } description: {
                    Text(error)
                } actions: {
                    Button("Try again") { Task { await viewModel.load() } }
                        .accessibilityIdentifier("pip-label-list-retry")
                }
            } else {
                List {
                    if let error = viewModel.errorMessage {
                        Section {
                            Label("Product list may be out of date: \(error)", systemImage: "wifi.exclamationmark")
                                .font(.footnote)
                                .foregroundStyle(ProvisionTheme.amberWarning)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    ForEach(visibleProducts) { product in
                    NavigationLink {
                        ProductLabelReviewView(productID: product.id, scope: scope, service: service,
                                               onReviewUpdated: onLabelReviewUpdated)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(product.name)
                                .font(.headline)
                                .foregroundStyle(ProvisionTheme.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                            Text([product.brand, product.category].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                                .font(.subheadline)
                                .foregroundStyle(ProvisionTheme.textSecondary)
                        }
                        .padding(.vertical, 5)
                    }
                    .accessibilityIdentifier("pip-label-product-\(product.id)")
                    }
                }
                .listStyle(.insetGrouped)
                .scrollContentBackground(.hidden)
                .background(ProvisionTheme.background)
                .overlay {
                    if visibleProducts.isEmpty {
                        ContentUnavailableView("No matching products", systemImage: "magnifyingglass")
                    }
                }
                .refreshable { await viewModel.load() }
            }
        }
        .background(ProvisionTheme.background)
        .navigationTitle("Product Label Reviews")
        .navigationBarTitleDisplayMode(.inline)
        .searchable(text: $searchText, prompt: "Search household products")
        .task { if viewModel.products.isEmpty { await viewModel.load() } }
    }
}

public struct ProductLabelReviewView: View {
    @StateObject private var viewModel: ProductLabelReviewViewModel
    private let onReviewUpdated: () async -> Void

    public init(productID: Int, scope: HouseholdScope, service: any CookWithPipWorkflowService = APIClient.shared,
                onReviewUpdated: @escaping () async -> Void = {}) {
        _viewModel = StateObject(wrappedValue: ProductLabelReviewViewModel(productID: productID, scope: scope, service: service))
        self.onReviewUpdated = onReviewUpdated
    }

    public var body: some View {
        Form {
            if let error = viewModel.errorMessage {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(ProvisionTheme.redAlert)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("pip-label-error")
                    Button("Reload product and review") { Task { await reload() } }
                        .accessibilityIdentifier("pip-label-retry")
                }
            }
            if let status = viewModel.statusMessage {
                Section {
                    Text(status)
                        .font(.subheadline)
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if let product = viewModel.product {
                Section("Product") {
                    Text(product.name).font(.headline).accessibilityIdentifier("pip-label-product-title")
                    if let brand = product.brand, !brand.isEmpty { LabeledContent("Brand", value: brand) }
                    if let category = product.category, !category.isEmpty { LabeledContent("Category", value: category) }
                    if let unit = product.unit, !unit.isEmpty { LabeledContent("Inventory unit", value: unit) }
                    if let updated = product.updated_at {
                        LabeledContent("Server version", value: updated)
                            .font(.caption.monospaced())
                    } else {
                        Label("Product is missing a server update timestamp", systemImage: "exclamationmark.triangle")
                            .foregroundStyle(ProvisionTheme.amberWarning)
                    }
                }
            }

            Section {
                if let mapping = viewModel.mapping {
                    Label("Mapping v\(mapping.version) · \(mapping.mode.rawValue)", systemImage: mapping.verification_status == "VERIFIED" ? "checkmark.seal" : "questionmark.circle")
                    Text(mapping.unknown_composition ? "Composition remains unknown." : "Mapping records a known ingredient composition.")
                        .font(.footnote)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                } else {
                    Text("No current product-to-ingredient mapping is recorded.")
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                Picker("Mapping type", selection: $viewModel.mappingMode) {
                    Text("Unknown").tag(IngredientMappingMode.unknown)
                    Text("One ingredient").tag(IngredientMappingMode.direct)
                    Text("Composite product").tag(IngredientMappingMode.composite)
                }
                .onChange(of: viewModel.mappingMode) { _, mode in
                    if mode == .unknown {
                        viewModel.selectedIngredientIDs = []
                        viewModel.mappingVerified = false
                        viewModel.mappingCompositionKnown = false
                    }
                }
                if viewModel.mappingMode != .unknown {
                    TextField("Search canonical ingredients", text: $viewModel.searchText)
                        .accessibilityIdentifier("pip-label-ingredient-search")
                    Button {
                        Task { await viewModel.searchIngredients() }
                    } label: {
                        if viewModel.isSearching { ProgressView() }
                        else { Label("Search ingredients", systemImage: "magnifyingglass") }
                    }
                    .disabled(viewModel.searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isSearching)
                    ForEach(viewModel.searchResults) { ingredient in
                        Toggle(isOn: ingredientBinding(ingredient.id)) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(ingredient.canonical_name)
                                    .fixedSize(horizontal: false, vertical: true)
                                if let filipinoName = ingredient.filipino_name, !filipinoName.isEmpty {
                                    Text(filipinoName).font(.caption).foregroundStyle(ProvisionTheme.textSecondary)
                                }
                            }
                        }
                        .accessibilityIdentifier("pip-label-ingredient-\(ingredient.id)")
                    }
                    Toggle("I checked this mapping against the package", isOn: $viewModel.mappingVerified)
                    Toggle("All ingredients are identified", isOn: $viewModel.mappingCompositionKnown)
                    Text("Unknown or incomplete composition must stay marked unknown. Package factors and unit conversions are not inferred here.")
                        .font(.footnote)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                Button("Save ingredient mapping") {
                    Task { if await viewModel.saveMapping() { await onReviewUpdated() } }
                }
                    .disabled(!viewModel.canSaveMapping || viewModel.isSaving || viewModel.isLoading)
                    .accessibilityIdentifier("pip-label-save-mapping")
            } header: {
                Text("Ingredient mapping")
            } footer: {
                Text("A verified, complete mapping is required before a package label review can be recorded.")
            }

            Section {
                if let label = viewModel.label {
                    Label(label.current_for_product ? "Current label review · v\(label.revision)" : "Review is no longer current · v\(label.revision)",
                          systemImage: label.current_for_product ? "checkmark.circle" : "exclamationmark.triangle")
                        .foregroundStyle(label.current_for_product ? ProvisionTheme.provisionGreen : ProvisionTheme.amberWarning)
                        .accessibilityIdentifier("pip-label-current-status")
                } else {
                    Text("No package label review is recorded.")
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                ForEach(FoodAllergenCode.allCases) { code in
                    Picker(code.title, selection: dispositionBinding(code)) {
                        Text("Not listed").tag("none")
                        Text("Declared on label").tag("declared")
                        Text("May contain").tag("possible")
                    }
                    .accessibilityIdentifier("pip-label-allergen-\(code.rawValue)")
                }
                TextField("Custom allergens, separated by commas", text: $viewModel.customAllergenText)
                    .accessibilityIdentifier("pip-label-custom-allergens")
                Toggle("Package composition is known", isOn: $viewModel.labelCompositionKnown)
                TextField("Source reference (package label, URL, or label section)", text: $viewModel.sourceReference, axis: .vertical)
                    .lineLimit(2...4)
                    .accessibilityIdentifier("pip-label-source-reference")
                Text("This records what a household member read. It is not a certification that a product or recipe is safe.")
                    .font(.footnote)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                Button("Record label review") {
                    Task { if await viewModel.saveLabel() { await onReviewUpdated() } }
                }
                    .disabled(!viewModel.canReviewLabel || viewModel.isSaving || viewModel.isLoading)
                    .accessibilityIdentifier("pip-label-save-review")
            } header: {
                Text("Package label declaration")
            } footer: {
                if !viewModel.canReviewLabel {
                    Text("Save a verified, complete ingredient mapping and refresh the product before recording this review.")
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(ProvisionTheme.background)
        .navigationTitle("Review Package Label")
        .navigationBarTitleDisplayMode(.inline)
        .task { if !viewModel.hasLoaded { await reload() } }
        .refreshable { await reload() }
    }

    private func ingredientBinding(_ ingredientID: Int) -> Binding<Bool> {
        Binding(
            get: { viewModel.selectedIngredientIDs.contains(ingredientID) },
            set: { selected in
                if selected { viewModel.selectedIngredientIDs.insert(ingredientID) }
                else { viewModel.selectedIngredientIDs.remove(ingredientID) }
            }
        )
    }

    private func dispositionBinding(_ code: FoodAllergenCode) -> Binding<String> {
        Binding(
            get: {
                if viewModel.declaredAllergens.contains(code.rawValue) { return "declared" }
                if viewModel.possibleAllergens.contains(code.rawValue) { return "possible" }
                return "none"
            },
            set: { viewModel.setAllergen(code, disposition: $0) }
        )
    }

    private func reload() async {
        await viewModel.load()
    }
}
