import SwiftUI

public struct ShoppingListView: View {
    @ObservedObject var viewModel: ShoppingViewModel
    @State private var showingClearDoneConfirmation: Bool = false
    @State private var showingPurchasedReview: Bool = false
    @State private var itemToDelete: ShoppingItem? = nil
    
    public init(viewModel: ShoppingViewModel) {
        self.viewModel = viewModel
    }
    
    public var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Filter Picker
                Picker("Filter", selection: $viewModel.filter) {
                    Text("To Buy (\(viewModel.pendingCount))").tag(ShoppingFilter.pending)
                    Text("Purchased (\(viewModel.purchasedCount))").tag(ShoppingFilter.completed)
                    Text("All (\(viewModel.items.count))").tag(ShoppingFilter.all)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)

                if viewModel.pendingPurchasedGroceriesRecord != nil {
                    pendingPurchaseRecoveryBanner
                        .padding(.horizontal, 16)
                        .padding(.bottom, 8)
                } else if viewModel.pendingPurchasedGroceriesState == .corrupt
                            || viewModel.pendingPurchasedGroceriesState == .unavailable {
                    purchasedRecoveryBlockedBanner
                        .padding(.horizontal, 16)
                        .padding(.bottom, 8)
                } else if !viewModel.purchasedItemsNeedingReview.isEmpty {
                    purchasedReviewBanner
                        .padding(.horizontal, 16)
                        .padding(.bottom, 8)
                }
                
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
                ToolbarItemGroup(placement: .topBarTrailing) {
                    if viewModel.canReviewPurchasedItems {
                        Button("Add to Pantry") {
                            showingPurchasedReview = true
                        }
                        .font(.system(size: 13, weight: .semibold))
                        .accessibilityIdentifier("shopping-review-purchased")
                    }
                    if viewModel.reviewedPurchasedCount > 0 {
                        Button("Clear Reviewed") {
                            showingClearDoneConfirmation = true
                        }
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.redAlert)
                        .accessibilityIdentifier("shopping-clear-reviewed")
                    }
                }
            }
            .task {
                if viewModel.items.isEmpty {
                    await viewModel.loadItems()
                }
                viewModel.loadPendingPurchasedGroceries()
                if viewModel.isPreview {
                    viewModel.prepareDraftsForPendingPurchases()
                }
            }
            .sheet(isPresented: $showingPurchasedReview) {
                PurchasedGroceriesReviewSheet(viewModel: viewModel)
            }
            .alert("Clear Reviewed Purchases?", isPresented: $showingClearDoneConfirmation) {
                Button("Cancel", role: .cancel) {}
                Button("Clear Reviewed", role: .destructive) {
                    Task { await viewModel.clearCompleted() }
                }
            } message: {
                Text("This removes \(viewModel.reviewedPurchasedCount) purchases already added to the pantry or intentionally excluded. Purchases awaiting review stay on your list.")
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

    private var purchasedReviewBanner: some View {
        Button {
            showingPurchasedReview = true
        } label: {
            HStack(spacing: 10) {
                Image(systemName: "basket.fill")
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Review purchased groceries")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                    Text("\(viewModel.purchasedItemsNeedingReview.count) items need pantry review")
                        .font(.caption)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                Spacer(minLength: 4)
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }
            .frame(minHeight: 44)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(ProvisionTheme.provisionGreenLight)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("shopping-purchased-review-banner")
    }

    private var pendingPurchaseRecoveryBanner: some View {
        Button {
            Task { await viewModel.retryPendingPurchasedGroceries() }
        } label: {
            HStack(spacing: 10) {
                Image(systemName: "arrow.clockwise.circle.fill")
                    .foregroundStyle(ProvisionTheme.amberWarning)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Finish saved pantry update")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                    Text("Retry the exact saved request to check its result.")
                        .font(.caption)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                Spacer(minLength: 4)
                if viewModel.isReconcilingPurchasedGroceries { ProgressView() }
                else { Image(systemName: "arrow.right").foregroundStyle(ProvisionTheme.amberWarning) }
            }
            .frame(minHeight: 44)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(ProvisionTheme.amberWarning.opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .buttonStyle(.plain)
        .disabled(viewModel.isReconcilingPurchasedGroceries)
        .accessibilityIdentifier("shopping-retry-saved-reconciliation")
    }

    private var purchasedRecoveryBlockedBanner: some View {
        Label("A saved pantry update needs recovery before new purchases can be reviewed.",
              systemImage: "exclamationmark.triangle.fill")
            .font(.caption.weight(.medium))
            .foregroundStyle(ProvisionTheme.amberWarning)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(ProvisionTheme.amberWarning.opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .accessibilityIdentifier("shopping-reconciliation-recovery-blocked")
    }
    
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
                    .foregroundStyle(ProvisionTheme.onAccent)
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
                    if item.is_bought && item.reconciliationStatus != "pending" {
                        ZStack {
                            Circle().fill(ProvisionTheme.provisionGreen).frame(width: 24, height: 24)
                            Image(systemName: item.reconciliationStatus == "added_to_pantry" ? "checkmark" : "minus")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(ProvisionTheme.onAccent)
                        }
                        .accessibilityLabel(item.reconciliationStatus == "added_to_pantry" ? "Added to pantry" : "Excluded from pantry")
                    } else {
                        Button {
                            HapticFeedback.light()
                            Task { await viewModel.toggleItem(item) }
                        } label: {
                            ZStack {
                                Circle()
                                    .stroke(item.is_bought ? ProvisionTheme.provisionGreen : ProvisionTheme.border, lineWidth: 2)
                                    .frame(width: 24, height: 24)
                                if item.is_bought {
                                    Circle().fill(ProvisionTheme.provisionGreen).frame(width: 16, height: 16)
                                    Image(systemName: "checkmark")
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundStyle(ProvisionTheme.onAccent)
                                }
                            }
                            .accessibleTouchTarget()
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(item.is_bought ? "Mark \(item.name) as needed" : "Mark \(item.name) as purchased")
                        .accessibilityValue(item.is_bought ? "Purchased" : "To buy")
                    }
                    
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.name)
                            .font(.system(size: 16, weight: .medium))
                            .strikethrough(item.is_bought, color: ProvisionTheme.textTertiary)
                            .foregroundStyle(item.is_bought ? ProvisionTheme.textTertiary : ProvisionTheme.textPrimary)
                            .accessibilityIdentifier("shopping-list-item-name-\(item.id)")
                        
                        if let notes = item.notes, !notes.isEmpty {
                            Text(notes)
                                .font(.system(size: 12))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                        }
                        if item.is_bought {
                            Text(purchaseStatus(for: item))
                                .font(.caption.weight(.medium))
                                .foregroundStyle(item.reconciliationStatus == "pending"
                                    ? ProvisionTheme.amberWarning : ProvisionTheme.textSecondary)
                                .accessibilityIdentifier("shopping-purchase-status-\(item.id)")
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
                    if !(item.is_bought && item.reconciliationStatus == "pending") {
                        Button(role: .destructive) {
                            itemToDelete = item
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                        .tint(ProvisionTheme.redAlert)
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
            if viewModel.filter == .pending || viewModel.filter == .all {
                Image("pip_grocery")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 90, height: 90)
                    .accessibilityHidden(true)
            } else {
                Image(systemName: emptyStateIcon)
                    .font(.system(size: 44))
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
            return "Purchased items stay here until they are added to the pantry, excluded, or cleared after review."
        }
    }

    private func purchaseStatus(for item: ShoppingItem) -> String {
        switch item.reconciliationStatus {
        case "added_to_pantry": return "Added to pantry"
        case "excluded": return "Excluded from pantry"
        default: return "Needs pantry review"
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

private struct PurchasedGroceriesReviewSheet: View {
    @ObservedObject var viewModel: ShoppingViewModel
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focusedQuantityItemID: Int?
    @State private var isSubmitting = false

    private var pendingItems: [ShoppingItem] {
        Array(viewModel.purchasedItemsNeedingReview.prefix(50))
    }

    private var unreviewedCount: Int {
        max(0, viewModel.purchasedItemsNeedingReview.count - pendingItems.count)
    }

    private var canConfirm: Bool {
        !pendingItems.isEmpty
            && pendingItems.allSatisfy(isValidResolution)
            && viewModel.pendingPurchasedGroceriesState == .missing
            && !viewModel.isPreparingPurchasedReview
            && !viewModel.isReconcilingPurchasedGroceries
            && !isSubmitting
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Add only the amount you actually brought home. Planned shopping quantities are not copied into your pantry.")
                        .font(.subheadline)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                        .accessibilityIdentifier("shopping-reconciliation-guidance")
                }

                if unreviewedCount > 0 {
                    Section {
                        Text("Review these first. \(unreviewedCount) more purchased items will remain for the next review.")
                            .font(.caption)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                            .accessibilityIdentifier("shopping-reconciliation-batch-limit")
                    }
                }

                if viewModel.isPreparingPurchasedReview {
                    Section { ProgressView("Refreshing purchased items…") }
                } else if pendingItems.isEmpty {
                    Section {
                        ContentUnavailableView("Nothing to review", systemImage: "checkmark.circle",
                                               description: Text("Purchased groceries will appear here after you mark them as bought."))
                    }
                } else {
                    ForEach(pendingItems) { item in
                        resolutionSection(for: item)
                    }
                }

                if viewModel.pendingPurchasedGroceriesState == .corrupt
                    || viewModel.pendingPurchasedGroceriesState == .unavailable {
                    Section {
                        Label("A saved pantry update could not be read securely. Resolve that saved update before starting another one.",
                              systemImage: "exclamationmark.triangle.fill")
                            .foregroundStyle(ProvisionTheme.amberWarning)
                            .accessibilityIdentifier("shopping-reconciliation-recovery-warning")
                    }
                }

                if let message = viewModel.errorMessage {
                    Section {
                        Text(message)
                            .foregroundStyle(ProvisionTheme.redAlert)
                            .accessibilityIdentifier("shopping-reconciliation-error")
                    }
                }

                Section {
                    Text("No unit conversions are applied. Pick the product’s exact unit and enter the measured quantity. Excluded items are not added to inventory.")
                        .font(.caption)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
            }
            .accessibilityIdentifier("shopping-purchased-review-form")
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle("Review purchases")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .disabled(isSubmitting || viewModel.isReconcilingPurchasedGroceries)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        Task { await confirmReview() }
                    } label: {
                        if isSubmitting || viewModel.isReconcilingPurchasedGroceries {
                            ProgressView()
                        } else {
                            Text("Confirm pantry update")
                        }
                    }
                    .disabled(!canConfirm)
                    .accessibilityIdentifier("shopping-confirm-purchased-review")
                }
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") { focusedQuantityItemID = nil }
                        .accessibilityIdentifier("shopping-reconciliation-keyboard-done")
                }
            }
            .task { await viewModel.preparePurchasedReview() }
            .interactiveDismissDisabled(isSubmitting || viewModel.isReconcilingPurchasedGroceries)
            .presentationDetents([.large])
        }
    }

    @ViewBuilder
    private func resolutionSection(for item: ShoppingItem) -> some View {
        let draft = viewModel.purchasedGroceriesDrafts[item.id] ?? PurchasedGroceriesDraft(item: item, products: viewModel.products)
        Section {
            Text("Shopping list: \(item.displayQuantity) \(item.unit ?? "unit")")
                .font(.caption)
                .foregroundStyle(ProvisionTheme.textSecondary)

            HStack(spacing: 12) {
                Button {
                    updateDraft(item.id) { $0.choice = .addToPantry }
                } label: {
                    Label("Add to pantry", systemImage: draft.choice == .addToPantry ? "checkmark.circle.fill" : "plus.circle")
                        .frame(maxWidth: .infinity, minHeight: 44)
                }
                .buttonStyle(.borderedProminent)
                .tint(ProvisionTheme.provisionGreen)
                .accessibilityIdentifier("shopping-reconcile-add-\(item.id)")

                Button {
                    updateDraft(item.id) { $0.choice = .exclude }
                } label: {
                    Label("Exclude", systemImage: draft.choice == .exclude ? "checkmark.circle.fill" : "minus.circle")
                        .frame(maxWidth: .infinity, minHeight: 44)
                }
                .buttonStyle(.bordered)
                .accessibilityIdentifier("shopping-reconcile-exclude-\(item.id)")
            }

            if draft.choice == .addToPantry {
                Picker("Product", selection: stringBinding(item.id, keyPath: \.productSelection)) {
                    Text("Create new product").tag("")
                    ForEach(viewModel.products) { product in
                        Text(product.name).tag(String(product.id))
                    }
                }
                .pickerStyle(.menu)
                .accessibilityIdentifier("shopping-reconcile-product-\(item.id)")

                if let product = selectedProduct(for: draft) {
                    LabeledContent("Inventory unit", value: product.unit ?? "Unit missing")
                } else {
                    TextField("New product name", text: stringBinding(item.id, keyPath: \.newProductName))
                        .textInputAutocapitalization(.words)
                        .accessibilityIdentifier("shopping-reconcile-new-product-name-\(item.id)")

                    Picker("Product unit", selection: stringBinding(item.id, keyPath: \.newProductUnit)) {
                        Text("Choose exact unit").tag("")
                        ForEach(ProductUnits.allUnits, id: \.self) { unit in
                            Text(unit).tag(unit)
                        }
                    }
                    .pickerStyle(.menu)
                    .accessibilityIdentifier("shopping-reconcile-new-product-unit-\(item.id)")
                }

                let unit = selectedProduct(for: draft)?.unit ?? draft.newProductUnit
                TextField(unit.isEmpty ? "Actual amount" : "Actual amount in \(unit)",
                          text: stringBinding(item.id, keyPath: \.quantity))
                    .keyboardType(.decimalPad)
                    .focused($focusedQuantityItemID, equals: item.id)
                    .accessibilityIdentifier("shopping-reconcile-actual-quantity-\(item.id)")

                Picker("Storage location", selection: optionalIntBinding(item.id, keyPath: \.storageLocationID)) {
                    Text("Choose later").tag(nil as Int?)
                    ForEach(viewModel.locations) { location in
                        Text(location.name).tag(Optional(location.id))
                    }
                }
                .pickerStyle(.menu)
                .accessibilityIdentifier("shopping-reconcile-location-\(item.id)")

                Toggle("Set expiration date", isOn: boolBinding(item.id, keyPath: \.hasExpirationDate))
                    .accessibilityIdentifier("shopping-reconcile-expiration-toggle-\(item.id)")
                if draft.hasExpirationDate {
                    DatePicker("Expiration date", selection: dateBinding(item.id, keyPath: \.expirationDate),
                               in: Date()..., displayedComponents: .date)
                        .accessibilityIdentifier("shopping-reconcile-expiration-date-\(item.id)")
                }
            }
        } header: {
            Text(item.name)
                .accessibilityIdentifier("shopping-reconcile-item-\(item.id)")
        } footer: {
            if item.updated_at == nil {
                Text("This purchase is missing its revision timestamp. Refresh the list before reviewing it.")
                    .foregroundStyle(ProvisionTheme.redAlert)
            }
        }
    }

    private func selectedProduct(for draft: PurchasedGroceriesDraft) -> Product? {
        guard let id = Int(draft.productSelection) else { return nil }
        return viewModel.products.first(where: { $0.id == id })
    }

    private func isValidResolution(_ item: ShoppingItem) -> Bool {
        guard let draft = viewModel.purchasedGroceriesDrafts[item.id], item.updated_at != nil else { return false }
        switch draft.choice {
        case .unresolved:
            return false
        case .exclude:
            return true
        case .addToPantry:
            guard parsedQuantity(draft.quantity) != nil else { return false }
            if let product = selectedProduct(for: draft) {
                return ProductUnits.isValid(product.unit)
            }
            return !draft.newProductName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && ProductUnits.isValid(draft.newProductUnit)
        }
    }

    private func parsedQuantity(_ input: String) -> ExactQuantity? {
        let value = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard value.range(of: "^[0-9]{1,8}(\\.[0-9]{1,2})?$", options: .regularExpression) != nil,
              let decimal = Decimal(string: value, locale: Locale(identifier: "en_US_POSIX")), decimal > 0 else {
            return nil
        }
        return ExactQuantity(decimal)
    }

    private func request() -> ReconcilePurchasedItemsRequest? {
        var resolutions: [PurchasedItemResolutionRequest] = []
        for item in pendingItems {
            guard let draft = viewModel.purchasedGroceriesDrafts[item.id], let updatedAt = item.updated_at else { return nil }
            if draft.choice == .exclude {
                resolutions.append(PurchasedItemResolutionRequest(
                    shoppingItemID: item.id, expectedUpdatedAt: updatedAt, action: "exclude"
                ))
                continue
            }
            guard draft.choice == .addToPantry, let quantity = parsedQuantity(draft.quantity) else { return nil }
            let product = selectedProduct(for: draft)
            let newProduct: ProductCreate? = product == nil
                ? ProductCreate(name: draft.newProductName.trimmingCharacters(in: .whitespacesAndNewlines),
                                unit: draft.newProductUnit)
                : nil
            guard let unit = product?.unit ?? newProduct?.unit else { return nil }
            resolutions.append(PurchasedItemResolutionRequest(
                shoppingItemID: item.id,
                expectedUpdatedAt: updatedAt,
                action: "add",
                productID: product?.id,
                newProduct: newProduct,
                quantity: quantity,
                inventoryUnit: unit,
                storageLocationID: draft.storageLocationID,
                expirationDate: draft.hasExpirationDate ? expirationDateString(draft.expirationDate) : nil
            ))
        }
        guard !resolutions.isEmpty else { return nil }
        return ReconcilePurchasedItemsRequest(items: resolutions)
    }

    private func expirationDateString(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    private func updateDraft(_ itemID: Int, update: (inout PurchasedGroceriesDraft) -> Void) {
        guard let item = pendingItems.first(where: { $0.id == itemID }) else { return }
        var draft = viewModel.purchasedGroceriesDrafts[itemID]
            ?? PurchasedGroceriesDraft(item: item, products: viewModel.products)
        update(&draft)
        viewModel.purchasedGroceriesDrafts[itemID] = draft
    }

    private func stringBinding(_ itemID: Int, keyPath: WritableKeyPath<PurchasedGroceriesDraft, String>) -> Binding<String> {
        Binding(
            get: { viewModel.purchasedGroceriesDrafts[itemID]?[keyPath: keyPath] ?? "" },
            set: { value in updateDraft(itemID) { $0[keyPath: keyPath] = value } }
        )
    }

    private func boolBinding(_ itemID: Int, keyPath: WritableKeyPath<PurchasedGroceriesDraft, Bool>) -> Binding<Bool> {
        Binding(
            get: { viewModel.purchasedGroceriesDrafts[itemID]?[keyPath: keyPath] ?? false },
            set: { value in updateDraft(itemID) { $0[keyPath: keyPath] = value } }
        )
    }

    private func dateBinding(_ itemID: Int, keyPath: WritableKeyPath<PurchasedGroceriesDraft, Date>) -> Binding<Date> {
        Binding(
            get: { viewModel.purchasedGroceriesDrafts[itemID]?[keyPath: keyPath] ?? Date() },
            set: { value in updateDraft(itemID) { $0[keyPath: keyPath] = value } }
        )
    }

    private func optionalIntBinding(_ itemID: Int, keyPath: WritableKeyPath<PurchasedGroceriesDraft, Int?>) -> Binding<Int?> {
        Binding(
            get: { viewModel.purchasedGroceriesDrafts[itemID]?[keyPath: keyPath] ?? nil },
            set: { value in updateDraft(itemID) { $0[keyPath: keyPath] = value } }
        )
    }

    private func confirmReview() async {
        guard canConfirm, let payload = request() else { return }
        isSubmitting = true
        await viewModel.submitPurchasedGroceries(payload)
        isSubmitting = false
        if viewModel.errorMessage == nil && viewModel.pendingPurchasedGroceriesRecord == nil {
            dismiss()
        }
    }
}
