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
        .toolbarBackground(ProvisionTheme.background, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .searchable(text: $searchText, prompt: "Search household products")
        .task { if viewModel.products.isEmpty { await viewModel.load() } }
    }
}

public struct ProductLabelReviewView: View {
    private enum InputField: Hashable {
        case ingredientSearch
        case customAllergens
        case sourceReference
    }

    @StateObject private var viewModel: ProductLabelReviewViewModel
    private let onReviewUpdated: () async -> Void
    @FocusState private var focusedField: InputField?

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
                    Text(product.name)
                        .font(.headline)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("pip-label-product-title")
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
                    LabeledContent("Search ingredients") {
                        TextField("Canonical or Filipino name", text: $viewModel.searchText)
                            .focused($focusedField, equals: .ingredientSearch)
                            .accessibilityIdentifier("pip-label-ingredient-search")
                    }
                    Button {
                        Task { await searchIngredients() }
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
                    Task { await saveIngredientMapping() }
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
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(label.current_for_product ? "Current label review · v\(label.revision)" : "Review is no longer current · v\(label.revision)")
                        .accessibilityIdentifier("pip-label-current-status")
                } else {
                    Text("No package label review is recorded.")
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                ForEach(FoodAllergenCode.allCases) { code in
                    allergenDeclarationMenu(code)
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("Custom allergens")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    TextField("Comma-separated", text: $viewModel.customAllergenText)
                        .focused($focusedField, equals: .customAllergens)
                        .accessibilityLabel("Custom allergens")
                        .accessibilityIdentifier("pip-label-custom-allergens")
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.vertical, 4)
                Toggle("Package composition is known", isOn: $viewModel.labelCompositionKnown)
                VStack(alignment: .leading, spacing: 6) {
                    Text("Source reference")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                    TextField("Package label, URL, or label section", text: $viewModel.sourceReference, axis: .vertical)
                        .lineLimit(2...4)
                        .focused($focusedField, equals: .sourceReference)
                        .accessibilityLabel("Source reference")
                        .accessibilityIdentifier("pip-label-source-reference")
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Text("This records what a household member read. It is not a certification that a product or recipe is safe.")
                    .font(.footnote)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                Button("Record label review") {
                    Task { await saveLabelReview() }
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
        .toolbarBackground(ProvisionTheme.background, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .scrollDismissesKeyboard(.interactively)
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                if focusedField != nil {
                    Spacer()
                    Button("Done") { focusedField = nil }
                        .accessibilityIdentifier("pip-label-keyboard-done")
                }
            }
        }
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

    private func currentDisposition(for code: FoodAllergenCode) -> String {
        if viewModel.declaredAllergens.contains(code.rawValue) { return "declared" }
        if viewModel.possibleAllergens.contains(code.rawValue) { return "possible" }
        return "none"
    }

    private func allergenDeclarationMenu(_ code: FoodAllergenCode) -> some View {
        let disposition = currentDisposition(for: code)
        let label = dispositionTitle(disposition)
        let color = disposition == "declared"
            ? ProvisionTheme.provisionGreen
            : (disposition == "possible" ? ProvisionTheme.amberWarning : ProvisionTheme.textSecondary)

        return Picker(selection: Binding(
            get: { currentDisposition(for: code) },
            set: { viewModel.setAllergen(code, disposition: $0) }
        )) {
            Text("Not listed")
                .tag("none")
                .accessibilityIdentifier("pip-label-disposition-none")
            Text("Declared on label")
                .tag("declared")
                .accessibilityIdentifier("pip-label-disposition-declared")
            Text("May contain")
                .tag("possible")
                .accessibilityIdentifier("pip-label-disposition-possible")
        } label: {
            Text(code.title)
                .foregroundStyle(ProvisionTheme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .pickerStyle(.menu)
        .tint(color)
        .accessibilityLabel("\(code.title) label declaration")
        .accessibilityValue(label)
        .accessibilityIdentifier("pip-label-allergen-\(code.rawValue)")
    }

    private func dispositionTitle(_ value: String) -> String {
        switch value {
        case "declared": "Declared on label"
        case "possible": "May contain"
        default: "Not listed"
        }
    }

    private func reload() async {
        await viewModel.load()
    }

    private func searchIngredients() async {
        await viewModel.searchIngredients()
        focusedField = nil
    }

    private func saveIngredientMapping() async {
        if await viewModel.saveMapping() {
            focusedField = nil
            await onReviewUpdated()
        }
    }

    private func saveLabelReview() async {
        if await viewModel.saveLabel() {
            focusedField = nil
            await onReviewUpdated()
        }
    }
}
