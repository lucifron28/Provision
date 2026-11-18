import SwiftUI

public struct RecipeShoppingReviewView: View {
    private enum QuantityField: Hashable {
        case servings
        case target(Int)
    }

    @StateObject private var viewModel: RecipeShoppingReviewViewModel
    private let recipe: HouseholdRecipe
    private let onShoppingConfirmed: () async -> Void
    private let onNavigateToShopping: () -> Void
    @State private var showingConfirmation = false
    @State private var showingRevisionDetails = false
    @FocusState private var focusedField: QuantityField?

    public init(recipe: HouseholdRecipe, scope: HouseholdScope,
                service: any CookWithPipWorkflowService = APIClient.shared,
                pendingStore: any PendingRecipeShoppingStore = KeychainStore.shared,
                substitutions: [RecipeSubstitution] = [],
                initialServings: ExactQuantity? = nil,
                includeOptional: Bool = false,
                onShoppingConfirmed: @escaping () async -> Void = {},
                onNavigateToShopping: @escaping () -> Void = {}) {
        _viewModel = StateObject(wrappedValue: RecipeShoppingReviewViewModel(
            recipe: recipe, scope: scope, service: service, pendingStore: pendingStore,
            substitutions: substitutions, initialServings: initialServings,
            includeOptional: includeOptional
        ))
        self.recipe = recipe
        self.onShoppingConfirmed = onShoppingConfirmed
        self.onNavigateToShopping = onNavigateToShopping
    }

    public var body: some View {
        Form {
            if let error = viewModel.errorMessage {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(ProvisionTheme.redAlert)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(error)
                        .accessibilityIdentifier("recipe-shopping-error")
                }
            }
            if let message = viewModel.statusMessage {
                Section {
                    Text(message)
                        .font(.subheadline)
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("recipe-shopping-status-message")
                }
            }

            if let result = viewModel.confirmationResult {
                confirmationResultSection(result)
            } else if let pending = viewModel.pendingRecord {
                pendingConfirmationSection(pending)
            } else if viewModel.pendingStorageState != .missing {
                pendingStorageRecoverySection
            } else if let preview = viewModel.preview {
                previewControls(preview)
                if !preview.substitutions.isEmpty {
                    appliedSubstitutionsSection(preview)
                }
                safetySection(preview)
                ingredientLines(preview)
                if !preview.unlinked_manual_items.isEmpty {
                    unlinkedItems(preview)
                }
                if preview.safety.decision == "review_required" {
                    Section {
                        Toggle("I reviewed the safety reasons above", isOn: $viewModel.safetyReviewAcknowledged)
                            .accessibilityIdentifier("recipe-shopping-safety-acknowledgement")
                        Text("This acknowledgement does not certify the recipe or product labels as safe.")
                            .font(.footnote)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }
                }
            } else if viewModel.isLoading {
                Section {
                    ProgressView("Checking current inventory and shopping list")
                        .tint(ProvisionTheme.provisionGreen)
                        .accessibilityIdentifier("recipe-shopping-loading")
                }
            } else {
                Section {
                    Text("No current preview is available. Load one before confirming any changes.")
                        .foregroundStyle(ProvisionTheme.textSecondary)
                    Button("Load fresh preview") { Task { await viewModel.refreshPreview() } }
                        .accessibilityIdentifier("recipe-shopping-load-preview")
                }
            }

        }
        .scrollContentBackground(.hidden)
        .accessibilityIdentifier("recipe-shopping-review-form")
        .background(ProvisionTheme.background)
        .navigationTitle("Shopping Preview")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(ProvisionTheme.background, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Confirm") { showingConfirmation = true }
                    .disabled(!viewModel.canConfirm || viewModel.isConfirming)
                    .accessibilityIdentifier("recipe-shopping-confirm")
            }
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { focusedField = nil }
                    .accessibilityIdentifier("recipe-shopping-keyboard-done")
            }
        }
        .alert("Add the selected recipe ingredients to the household shopping list?", isPresented: $showingConfirmation) {
            Button("Confirm shopping changes") { Task { await confirmSelectedLines() } }
                .accessibilityIdentifier("recipe-shopping-confirm-action")
            Button("Keep reviewing", role: .cancel) {}
        } message: {
            Text("Only the selected lines will change. Inventory quantities stay the same.")
        }
        .task { await viewModel.load() }
    }

    @ViewBuilder
    private func previewControls(_ preview: RecipeShoppingPreview) -> some View {
        Section {
            VStack(alignment: .leading, spacing: 6) {
                Text("Servings (people)")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                TextField("Number of people", text: $viewModel.servingsText,
                          prompt: Text("Number of people").foregroundStyle(ProvisionTheme.textSecondary))
                    .keyboardType(.decimalPad)
                    .focused($focusedField, equals: .servings)
                    .accessibilityLabel("Servings (people)")
                    .accessibilityIdentifier("recipe-shopping-servings")
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 4)
            Toggle("Include optional ingredients", isOn: $viewModel.includeOptional)
                .accessibilityIdentifier("recipe-shopping-include-optional")
            if !viewModel.isPreviewCurrent {
                Label("Settings changed. Refresh the preview before confirming.", systemImage: "arrow.clockwise")
                    .font(.footnote)
                    .foregroundStyle(ProvisionTheme.amberWarning)
                    .accessibilityIdentifier("recipe-shopping-stale-preview")
            }
            DisclosureGroup(isExpanded: $showingRevisionDetails) {
                revisionDetailRow("Shopping list", value: String(preview.shopping_revision),
                                  identifier: "recipe-shopping-list-revision")
                revisionDetailRow("Pantry", value: String(preview.inventory_revision),
                                  identifier: "recipe-shopping-pantry-revision")
                if let expirationDate = viewModel.expirationDate {
                    LabeledContent("Preview expires", value: expirationDate.formatted(date: .abbreviated, time: .shortened))
                        .accessibilityIdentifier("recipe-shopping-expiration-value")
                } else {
                    LabeledContent("Preview expires", value: "Unavailable")
                        .accessibilityIdentifier("recipe-shopping-expiration-value")
                }
            } label: {
                Text("Revision details")
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("recipe-shopping-revision-details")
            .accessibilityValue(showingRevisionDetails ? "Expanded" : "Collapsed")
            .accessibilityHint(showingRevisionDetails ? "Hide revision details" : "Show revision details")
            if viewModel.isExpired {
                Label("This preview has expired. Refresh it before confirming.", systemImage: "clock.badge.exclamationmark")
                    .foregroundStyle(ProvisionTheme.amberWarning)
                    .accessibilityIdentifier("recipe-shopping-expired")
            }
            Button {
                Task { await viewModel.refreshPreview() }
            } label: {
                if viewModel.isLoading { ProgressView() }
                else { Label("Refresh preview", systemImage: "arrow.clockwise") }
            }
            .disabled(viewModel.isLoading || viewModel.isConfirming || viewModel.pendingRecord != nil)
            .accessibilityIdentifier("recipe-shopping-refresh-preview")
        } header: {
            Text("Preview settings")
                .accessibilityIdentifier("recipe-shopping-preview-settings-heading")
        }
    }

    private func appliedSubstitutionsSection(_ preview: RecipeShoppingPreview) -> some View {
        Section {
            ForEach(Array(preview.substitutions.enumerated()), id: \.offset) { entry in
                let substitution = entry.element
                let original = recipe.ingredients.indices.contains(substitution.requirement_index)
                    ? recipe.ingredients[substitution.requirement_index].display_name
                    : "recipe ingredient"
                let replacement = substitution.replacement.display_name
                    ?? "ingredient \(substitution.replacement.ingredient_id ?? 0)"
                Label("Use \(replacement) instead of \(original)", systemImage: "arrow.triangle.swap")
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("Use \(replacement) instead of \(original)")
                    .accessibilityIdentifier("recipe-shopping-applied-substitution-\(entry.offset)")
            }
        } header: {
            Text("Applied substitutions")
                .accessibilityIdentifier("recipe-shopping-applied-substitutions")
        }
    }

    @ViewBuilder
    private func revisionDetailRow(_ title: String, value: String, identifier: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.subheadline)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Text(value)
                .font(.body.weight(.semibold))
                .foregroundStyle(ProvisionTheme.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(title), revision \(value)")
        .accessibilityIdentifier(identifier)
    }

    private func safetySection(_ preview: RecipeShoppingPreview) -> some View {
        Section("Food safety and pantry availability") {
            VStack(alignment: .leading, spacing: 6) {
                Text("Food safety")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                StatusPill(presentation: .safety(preview.safety.decision))
                    .accessibilityIdentifier("recipe-shopping-safety-status")
            }
            VStack(alignment: .leading, spacing: 6) {
                Text("Ingredient availability")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                StatusPill(presentation: .availability(preview.safety.availability.overall_status))
                    .accessibilityIdentifier("recipe-shopping-availability-status")
            }
            Text(preview.safety.notice)
                .font(.footnote)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(Array(preview.safety.reasons.enumerated()), id: \.offset) { reason in
                Label(ReasonText.display(reason.element), systemImage: "info.circle")
                    .font(.footnote)
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
            if preview.safety.decision == "blocked" {
                Text("The server blocked shopping confirmation for this preview.")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(ProvisionTheme.redAlert)
            }
        }
    }

    private func ingredientLines(_ preview: RecipeShoppingPreview) -> some View {
        Section("Ingredient lines") {
            ForEach(Array(preview.lines.enumerated()), id: \.offset) { entry in
                let line = entry.element
                VStack(alignment: .leading, spacing: 10) {
                    HStack(alignment: .top, spacing: 10) {
                        if let id = line.ingredient_id, line.status == "ready",
                           (line.additional_quantity?.value ?? 0) > 0 {
                            Toggle(isOn: lineSelectionBinding(id)) {
                                Text(line.display_name)
                                    .font(.headline)
                                    .foregroundStyle(ProvisionTheme.textPrimary)
                                    .fixedSize(horizontal: false, vertical: true)
                                    .accessibilityIdentifier("recipe-shopping-name-\(line.ingredient_id ?? -1)")
                            }
                            .accessibilityIdentifier("recipe-shopping-line-\(id)")
                        } else {
                            Text(line.display_name)
                                .font(.headline)
                                .foregroundStyle(ProvisionTheme.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                                .accessibilityIdentifier("recipe-shopping-name-\(line.ingredient_id ?? -1)")
                        }
                    }
                    let isCovered = line.status == "ready" && (line.additional_quantity?.value ?? 0) == 0
                    Label(isCovered ? "Already covered" : (line.status == "ready" ? "Ready to add" : "Review required"),
                          systemImage: isCovered ? "checkmark.circle" : (line.status == "ready" ? "plus.circle" : "exclamationmark.triangle"))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(isCovered || line.status == "ready" ? ProvisionTheme.provisionGreen : ProvisionTheme.amberWarning)
                    quantitySummary(line, safetyDecision: preview.safety.decision)
                    if let id = line.ingredient_id,
                       viewModel.selectedIngredientIDs.contains(id), line.target_quantity != nil {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Target quantity (\(line.unit ?? "server unit"))")
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(ProvisionTheme.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                            TextField("Quantity", text: targetBinding(id),
                                      prompt: Text("Quantity").foregroundStyle(ProvisionTheme.textSecondary))
                                .keyboardType(.decimalPad)
                                .focused($focusedField, equals: .target(id))
                                .accessibilityLabel("Target quantity (\(line.unit ?? "server unit"))")
                                .accessibilityIdentifier("recipe-shopping-target-\(id)")
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 4)
                        if line.pending_item_ids.count > 1 {
                            Toggle("Consolidate \(line.pending_item_ids.count) linked pending items", isOn: consolidationBinding(id))
                                .accessibilityIdentifier("recipe-shopping-consolidate-\(id)")
                        } else if !line.pending_item_ids.isEmpty {
                            Text("Existing pending quantity is preserved.")
                                .font(.footnote)
                                .foregroundStyle(ProvisionTheme.textSecondary)
                        }
                    }
                    ForEach(Array(line.review_reasons.enumerated()), id: \.offset) { reason in
                        Text(ReasonText.display(reason.element))
                            .font(.footnote)
                            .foregroundStyle(ProvisionTheme.amberWarning)
                    }
                }
                .padding(.vertical, 5)
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("recipe-shopping-row-\(line.ingredient_id ?? -1)")
            }
        }
    }

    @ViewBuilder
    private func quantitySummary(_ line: RecipeShoppingLine, safetyDecision: String) -> some View {
        RecipeShoppingQuantitySummary(line: line, safetyDecision: safetyDecision)
    }

    private func unlinkedItems(_ preview: RecipeShoppingPreview) -> some View {
        Section("Unlinked manual shopping items") {
            Text("These rows stay separate because the server has no ingredient link. They will not be merged by name.")
                .font(.footnote)
                .foregroundStyle(ProvisionTheme.textSecondary)
            ForEach(preview.unlinked_manual_items, id: \.item_id) { item in
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.name).font(.subheadline.weight(.medium))
                    Text("\(NSDecimalNumber(decimal: item.quantity.value).stringValue) \(item.unit ?? "unit not specified") · \(ReasonText.display(item.reason))")
                        .font(.footnote)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                .accessibilityIdentifier("recipe-shopping-unlinked-\(item.item_id)")
            }
        }
    }

    private func pendingConfirmationSection(_ record: PendingRecipeShoppingRecord) -> some View {
        Section("Saved confirmation") {
            Label("Result not confirmed", systemImage: "arrow.trianglehead.2.clockwise.rotate.90")
                .font(.headline)
                .foregroundStyle(ProvisionTheme.amberWarning)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("Result not confirmed")
                .accessibilityIdentifier("recipe-shopping-pending-status")
            Text(record.recipeTitle)
                .font(.subheadline.weight(.semibold))
            ForEach(Array(record.lines.enumerated()), id: \.offset) { entry in
                Text("\(entry.element.name): \(NSDecimalNumber(decimal: entry.element.targetQuantity.value).stringValue) \(entry.element.unit ?? "unit not specified")")
                    .accessibilityIdentifier("recipe-shopping-pending-line-\(entry.offset)")
            }
            Text("Retry reuses this exact request and key. Keep it unchanged while the result is unknown.")
                .font(.footnote)
                .foregroundStyle(ProvisionTheme.textSecondary)
            Button {
                Task { await retryPendingConfirmation() }
            } label: {
                if viewModel.isConfirming { ProgressView() }
                else { Text("Retry exact confirmation") }
            }
            .disabled(viewModel.isConfirming)
            .accessibilityIdentifier("recipe-shopping-retry-pending")
        }
    }

    private var pendingStorageRecoverySection: some View {
        Section("Saved confirmation check") {
            Text("Provision cannot safely tell whether an earlier shopping confirmation is still pending. Check the saved request again before asking for a preview or sending another change.")
                .font(.footnote)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Button("Check saved confirmation again") {
                Task { await viewModel.reloadPendingState() }
            }
            .accessibilityIdentifier("recipe-shopping-recovery-retry")
        }
    }

    private func confirmationResultSection(_ result: RecipeShoppingConfirmationResult) -> some View {
        Section("Shopping-list result") {
            Text("Created \(result.created.count) · Updated \(result.updated.count) · Unchanged \(result.unchanged.count) · Consolidated \(result.consolidated.count)")
                .font(.subheadline.weight(.semibold))
                .accessibilityIdentifier("recipe-shopping-result-counts")
            Button("View Shopping List", action: onNavigateToShopping)
                .accessibilityIdentifier("recipe-shopping-view-list")
        }
    }

    private func lineSelectionBinding(_ id: Int) -> Binding<Bool> {
        Binding(
            get: { viewModel.selectedIngredientIDs.contains(id) },
            set: { selected in
                if selected { viewModel.selectedIngredientIDs.insert(id) }
                else { viewModel.selectedIngredientIDs.remove(id) }
            }
        )
    }

    private func targetBinding(_ id: Int) -> Binding<String> {
        Binding(
            get: { viewModel.targetQuantityTexts[id] ?? "" },
            set: { viewModel.targetQuantityTexts[id] = $0 }
        )
    }

    private func consolidationBinding(_ id: Int) -> Binding<Bool> {
        Binding(
            get: { viewModel.consolidateIngredientIDs.contains(id) },
            set: { selected in
                if selected { viewModel.consolidateIngredientIDs.insert(id) }
                else { viewModel.consolidateIngredientIDs.remove(id) }
            }
        )
    }

    private func confirmSelectedLines() async {
        await viewModel.confirmSelectedLines()
        if viewModel.confirmationResult != nil { await onShoppingConfirmed() }
    }

    private func retryPendingConfirmation() async {
        await viewModel.retryPendingConfirmation()
        if viewModel.confirmationResult != nil { await onShoppingConfirmed() }
    }
}

private struct RecipeShoppingQuantitySummary: View {
    let line: RecipeShoppingLine
    let safetyDecision: String
    @State private var showingDetails = false

    private var identifierSuffix: String { String(line.ingredient_id ?? -1) }
    private var unit: String { line.unit ?? "unit not specified" }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(actionSummary)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(safetyDecision == "eligible" && line.status == "ready"
                    ? ProvisionTheme.textPrimary : ProvisionTheme.amberWarning)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("recipe-shopping-action-summary-\(identifierSuffix)")
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    showingDetails.toggle()
                }
            } label: {
                HStack(spacing: 8) {
                    Text("Quantity details")
                        .font(.footnote.weight(.medium))
                    Spacer(minLength: 8)
                    Image(systemName: showingDetails ? "chevron.up" : "chevron.down")
                        .font(.caption.weight(.semibold))
                        .accessibilityHidden(true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("recipe-shopping-quantity-details-\(identifierSuffix)")
            .accessibilityValue(showingDetails ? "Expanded" : "Collapsed")
            .accessibilityHint(showingDetails ? "Hide quantity details" : "Show quantity details")
            if showingDetails {
                VStack(alignment: .leading, spacing: 2) {
                    quantityLine("Required", line.required_quantity, id: "required")
                    quantityLine("Counted on hand", line.pantry_quantity, id: "pantry")
                    quantityLine("Short", line.shortage, id: "shortage")
                    quantityLine("Already on shopping list", line.pending_quantity, id: "pending")
                    quantityLine("Additional needed", line.additional_quantity, id: "additional")
                }
                .accessibilityElement(children: .contain)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(ProvisionTheme.surfaceSecondary, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private var actionSummary: String {
        if safetyDecision == "blocked" {
            return "Food-safety review blocks adding \(line.display_name)."
        }
        if safetyDecision == "review_required" {
            return "Review the food-safety status before adding \(line.display_name)."
        }
        guard line.status == "ready" else {
            return "Review required before adding \(line.display_name)."
        }
        guard let amount = line.additional_quantity else {
            return "The amount to add is unavailable. Review the quantity details."
        }
        if amount.value == 0 {
            return "\(line.display_name) is already covered by pantry stock or the shopping list."
        }
        return "Add \(NSDecimalNumber(decimal: amount.value).stringValue) \(unit) \(line.display_name) to shopping list"
    }

    @ViewBuilder
    private func quantityLine(_ title: String, _ quantity: ExactQuantity?, id: String) -> some View {
        if let quantity {
            let value = "\(NSDecimalNumber(decimal: quantity.value).stringValue) \(unit)"
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text(title)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Text(value)
                        .fontWeight(.semibold)
                        .foregroundStyle(ProvisionTheme.textPrimary)
                        .multilineTextAlignment(.trailing)
                        .fixedSize(horizontal: false, vertical: true)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.subheadline)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                    Text(value)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .font(.subheadline)
            .padding(.vertical, 3)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("recipe-shopping-quantity-\(id)-\(identifierSuffix)")
        }
    }
}
