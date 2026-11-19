import SwiftUI

public struct RecipeDetailView: View {
    @StateObject private var viewModel: RecipeDetailViewModel
    private let scope: HouseholdScope
    private let service: any CookWithPipService
    private let chatService: any PipChatService
    private let workflowService: any CookWithPipWorkflowService
    private let pendingStore: any PendingRecipeShoppingStore
    private let onShoppingConfirmed: () async -> Void
    private let onNavigateToShopping: () -> Void
    @State private var showingSubstitutionEditor = false

    public init(recipeID: Int, scope: HouseholdScope, service: any CookWithPipService = APIClient.shared,
                chatService: any PipChatService = APIClient.shared,
                workflowService: any CookWithPipWorkflowService = APIClient.shared,
                pendingStore: any PendingRecipeShoppingStore = KeychainStore.shared,
                onShoppingConfirmed: @escaping () async -> Void = {},
                onNavigateToShopping: @escaping () -> Void = {}) {
        self.scope = scope
        self.service = service
        self.chatService = chatService
        self.workflowService = workflowService
        self.pendingStore = pendingStore
        self.onShoppingConfirmed = onShoppingConfirmed
        self.onNavigateToShopping = onNavigateToShopping
        _viewModel = StateObject(wrappedValue: RecipeDetailViewModel(recipeID: recipeID, scope: scope, service: service))
    }

    public var body: some View {
        ScrollView {
            Group {
                if viewModel.isLoading && !viewModel.hasLoadedOnce {
                    VStack(spacing: 12) {
                        ProgressView().tint(ProvisionTheme.provisionGreen)
                        Text("Loading current recipe evaluation")
                            .font(.subheadline)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(40)
                    .accessibilityIdentifier("recipe-detail-loading")
                } else if let error = viewModel.errorMessage, viewModel.recipe == nil {
                    VStack(alignment: .leading, spacing: 10) {
                        Label(viewModel.isOffline ? "You're offline" : "Unable to load recipe",
                              systemImage: viewModel.isOffline ? "wifi.slash" : "exclamationmark.triangle.fill")
                            .font(.headline)
                            .foregroundStyle(viewModel.isOffline ? ProvisionTheme.amberWarning : ProvisionTheme.redAlert)
                        Text(viewModel.isOffline ? "Connect to your server to load current recipe and safety information." : error)
                            .font(.subheadline)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                        Button("Try again") { Task { await viewModel.load() } }
                            .frame(minHeight: 44)
                            .accessibilityIdentifier("recipe-detail-retry")
                    }
                    .padding(18)
                    .provisionCard()
                } else if let recipe = viewModel.recipe, let evaluation = viewModel.evaluation {
                    RecipeDetailContents(
                        recipe: recipe,
                        scope: scope,
                        evaluation: evaluation,
                        appliedSubstitutions: viewModel.appliedSubstitutions,
                        appliedServings: viewModel.appliedServings,
                        appliedIncludeOptional: viewModel.appliedIncludeOptional,
                        sourceReference: viewModel.sourceReference,
                        sourceReferenceErrorMessage: viewModel.sourceReferenceErrorMessage,
                        isSourceOffline: viewModel.isSourceOffline,
                        isLoadingSourceReference: viewModel.isLoadingSourceReference,
                        retrySourceReference: { Task { await viewModel.retrySourceReference() } },
                        recipeService: service,
                        chatService: chatService,
                        workflowService: workflowService,
                        pendingStore: pendingStore,
                        onCustomizeSubstitutions: { showingSubstitutionEditor = true },
                        onShoppingConfirmed: onShoppingConfirmed,
                        onNavigateToShopping: onNavigateToShopping,
                        refreshEvaluation: { await viewModel.load() }
                    )
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 28)
        }
        .background(ProvisionTheme.background.ignoresSafeArea())
        .navigationTitle("Recipe")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(ProvisionTheme.background, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .scrollEdgeEffectStyle(.hard, for: .top)
        .refreshable { await viewModel.load() }
        .accessibilityIdentifier("recipe-detail-scroll")
        .task {
            if !viewModel.hasLoadedOnce { await viewModel.load() }
        }
        .sheet(isPresented: $showingSubstitutionEditor) {
            if let recipe = viewModel.recipe {
                RecipeSubstitutionEditorView(recipe: recipe, scope: scope, service: service) { evaluation, substitutions, servings, includeOptional in
                    viewModel.applyEvaluation(evaluation, substitutions: substitutions,
                                              servings: servings, includeOptional: includeOptional)
                    showingSubstitutionEditor = false
                }
            }
        }
    }
}

private struct RecipeDetailContents: View {
    @ScaledMetric(relativeTo: .subheadline) private var instructionNumberSize: CGFloat = 28
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    let recipe: HouseholdRecipe
    let scope: HouseholdScope
    let evaluation: RecipeEvaluation
    let appliedSubstitutions: [Int: IngredientRequirement]
    let appliedServings: ExactQuantity?
    let appliedIncludeOptional: Bool
    let sourceReference: RecipeSourceReference?
    let sourceReferenceErrorMessage: String?
    let isSourceOffline: Bool
    let isLoadingSourceReference: Bool
    let retrySourceReference: () -> Void
    let recipeService: any CookWithPipService
    let chatService: any PipChatService
    let workflowService: any CookWithPipWorkflowService
    let pendingStore: any PendingRecipeShoppingStore
    let onCustomizeSubstitutions: () -> Void
    let onShoppingConfirmed: () async -> Void
    let onNavigateToShopping: () -> Void
    let refreshEvaluation: () async -> Void

    private var availabilityByRecipeIndex: [Int: IngredientAvailabilitySnapshot] {
        var result: [Int: IngredientAvailabilitySnapshot] = [:]
        for (offset, recipeIndex) in evaluation.included_requirement_indexes.enumerated() {
            guard evaluation.result.availability.requirements.indices.contains(offset) else { continue }
            result[recipeIndex] = evaluation.result.availability.requirements[offset]
        }
        return result
    }

    private var safetyByRecipeIndex: [Int: IngredientSafetySnapshot] {
        var result: [Int: IngredientSafetySnapshot] = [:]
        for item in evaluation.result.ingredients {
            guard evaluation.included_requirement_indexes.indices.contains(item.requirement_index) else { continue }
            result[evaluation.included_requirement_indexes[item.requirement_index]] = item
        }
        return result
    }

    private var requiredIngredients: [Int] {
        recipe.ingredients.indices.filter { recipe.ingredients[$0].required }
    }

    private var optionalIngredients: [Int] {
        recipe.ingredients.indices.filter { !recipe.ingredients[$0].required }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            titleSection
            evaluationSection
            ingredientAvailabilityOverview
            workflowActions
            if dynamicTypeSize.isAccessibilitySize {
                summarySection
                metadataSection
            }
            if let sourceReference {
                sourceSection(sourceReference)
            } else if let sourceReferenceErrorMessage {
                sourceErrorSection(sourceReferenceErrorMessage)
            } else if isLoadingSourceReference {
                ProgressView("Loading source details")
                    .font(.footnote)
                    .tint(ProvisionTheme.provisionGreen)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(14)
                    .provisionCard(backgroundColor: ProvisionTheme.surfaceSecondary)
            }
            ingredientSection(title: "Required ingredients", indices: requiredIngredients)
            if !optionalIngredients.isEmpty {
                ingredientSection(title: "Optional ingredients", indices: optionalIngredients)
            }
            instructionsSection
        }
    }

    private var workflowActions: some View {
        VStack(alignment: .leading, spacing: 8) {
            if recipe.ingredients.contains(where: { !$0.substitution_options.isEmpty }) {
                Button(action: onCustomizeSubstitutions) {
                    Label("Review substitutions", systemImage: "arrow.triangle.swap")
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                }
                .accessibilityIdentifier("recipe-review-substitutions")
            }
            NavigationLink {
                PipChatView(
                    scope: scope,
                    context: PipChatContext(kind: .recipe, id: recipe.id),
                    contextTitle: recipe.title,
                    chatService: chatService,
                    recipeService: recipeService,
                    workflowService: workflowService,
                    pendingStore: pendingStore,
                    onShoppingConfirmed: onShoppingConfirmed,
                    onNavigateToShopping: onNavigateToShopping
                )
                .id("pip-chat-\(scope.storageKey)-recipe-\(recipe.id)")
            } label: {
                Label("Ask Pip about this recipe", systemImage: "bubble.left.and.bubble.right")
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            }
            .accessibilityIdentifier("recipe-ask-pip-link")
            NavigationLink {
                CookWithPipPreferencesView(scope: scope, service: workflowService,
                                           onProfileUpdated: refreshEvaluation)
            } label: {
                Label("Review my preferences and allergies", systemImage: "person.crop.circle.badge.checkmark")
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            }
            .accessibilityIdentifier("recipe-review-preferences")
            NavigationLink {
                ProductLabelReviewListView(scope: scope, service: workflowService,
                                           onLabelReviewUpdated: refreshEvaluation)
            } label: {
                Label("Review package labels", systemImage: "tag")
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            }
            .accessibilityIdentifier("recipe-review-product-labels")
            NavigationLink {
                RecipeShoppingReviewView(recipe: recipe, scope: scope, service: workflowService,
                                         pendingStore: pendingStore,
                                         substitutions: appliedSubstitutionSelections,
                                         initialServings: appliedServings,
                                         includeOptional: appliedIncludeOptional,
                                         onShoppingConfirmed: onShoppingConfirmed,
                                         onNavigateToShopping: onNavigateToShopping)
            } label: {
                Label("Review shopping list", systemImage: "cart.badge.plus")
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            }
            .accessibilityIdentifier("recipe-shopping-preview-link")
        }
        .font(.subheadline.weight(.semibold))
        .foregroundStyle(ProvisionTheme.provisionGreen)
        .padding(14)
        .provisionCard(backgroundColor: ProvisionTheme.surfaceSecondary)
    }

    private var titleSection: some View {
        VStack(alignment: .leading, spacing: dynamicTypeSize.isAccessibilitySize ? 5 : 10) {
            Text(recipe.title)
                .font(dynamicTypeSize.isAccessibilitySize
                    ? .system(.headline, design: .serif, weight: .bold)
                    : ProvisionTypography.titleSerif)
                .foregroundStyle(ProvisionTheme.provisionGreen)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("recipe-detail-title")
                .accessibilityAddTraits(.isHeader)
            if !dynamicTypeSize.isAccessibilitySize,
               let summary = recipe.summary, !summary.isEmpty {
                Text(summary)
                    .font(.body)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !dynamicTypeSize.isAccessibilitySize {
                Text(cuisineRegionLabel)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
            if !dynamicTypeSize.isAccessibilitySize {
                recipeMetadata
            }
        }
        .padding(dynamicTypeSize.isAccessibilitySize ? 12 : 18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard(backgroundColor: ProvisionTheme.heroCard)
    }

    private var recipeMetadata: some View {
        VStack(alignment: .leading, spacing: 8) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) {
                    metadataLabel("Prep \(recipe.prep_minutes) min", symbol: "clock")
                    metadataLabel("Cook \(recipe.cook_minutes) min", symbol: "flame")
                }
                VStack(alignment: .leading, spacing: 4) {
                    metadataLabel("Prep \(recipe.prep_minutes) min", symbol: "clock")
                    metadataLabel("Cook \(recipe.cook_minutes) min", symbol: "flame")
                }
            }
            .font(.footnote)
            .foregroundStyle(ProvisionTheme.textSecondary)
            Label("Servings: \(QuantityText.string(recipe.servings)) people", systemImage: "person.2")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(ProvisionTheme.textSecondary)
            Text("Stored household recipe")
                .font(.caption.weight(.semibold))
                .foregroundStyle(ProvisionTheme.provisionGreen)
        }
    }

    private var metadataSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            if dynamicTypeSize.isAccessibilitySize {
                Text(cuisineRegionLabel)
                    .font(.body.weight(.medium))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            recipeMetadata
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard(backgroundColor: ProvisionTheme.surfaceSecondary)
    }

    @ViewBuilder
    private var summarySection: some View {
        if let summary = recipe.summary, !summary.isEmpty {
            Text(summary)
                .font(.body)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("recipe-detail-summary")
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .provisionCard(backgroundColor: ProvisionTheme.surfaceSecondary)
        }
    }

    private var evaluationSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Recipe status")
                .font(ProvisionTypography.sectionSerif)
                .foregroundStyle(ProvisionTheme.textPrimary)
            recipeStatusSummary
            Text(evaluation.result.notice)
                .font(.subheadline)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("recipe-safety-notice")
            Text("Food-safety checks include all active household members unless you select specific diners.")
                .font(.footnote)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if !evaluation.result.reasons.isEmpty {
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(Array(evaluation.result.reasons.enumerated()), id: \.offset) { item in
                        Label(ReasonText.display(item.element), systemImage: "info.circle")
                            .font(.footnote)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                            .accessibilityIdentifier("recipe-safety-reason-\(item.offset)")
                    }
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard()
    }

    private var recipeStatusSummary: some View {
        VStack(alignment: .leading, spacing: 8) {
            recipeStatusItem(title: "Food safety") {
                StatusPill(presentation: .safety(evaluation.result.decision))
                    .accessibilityIdentifier("recipe-safety-status")
            }
            recipeStatusItem(title: "Pantry availability") {
                StatusPill(presentation: .availability(evaluation.result.availability.overall_status))
                    .accessibilityIdentifier("recipe-availability-status")
            }
        }
    }

    @ViewBuilder
    private var ingredientAvailabilityOverview: some View {
        if !requiredIngredients.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Ingredient check")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier("recipe-ingredient-availability-overview")
                ForEach(requiredIngredients, id: \.self) { index in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(recipe.ingredients[index].display_name)
                            .font(.footnote.weight(.medium))
                            .foregroundStyle(ProvisionTheme.textPrimary)
                        ingredientAvailabilitySummary(index)
                            .font(.footnote.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityIdentifier("recipe-ingredient-availability-summary-\(index)")
                    }
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .provisionCard(backgroundColor: ProvisionTheme.surfaceSecondary)
        }
    }

    @ViewBuilder
    private func ingredientAvailabilitySummary(_ index: Int) -> some View {
        if let line = availabilityByRecipeIndex[index] {
            let unit = line.unit ?? recipe.ingredients[index].unit
            let needed = line.required_amount.map { "Need \(QuantityText.string($0)) \(unit)" }
            if line.status == "unknown" || !line.unknown_reasons.isEmpty {
                Text(["Needs review", needed].compactMap { $0 }.joined(separator: " · "))
                    .foregroundStyle(ProvisionTheme.amberWarning)
            } else {
                let have = line.available_amount.map { "Have \(QuantityText.string($0)) \(unit)" }
                let missing = line.shortfall.flatMap {
                    $0.value > 0 ? "Missing \(QuantityText.string($0)) \(unit)" : nil
                }
                Text([have, needed, missing].compactMap { $0 }.joined(separator: " · "))
                    .foregroundStyle(line.status == "full" ? ProvisionTheme.provisionGreen : ProvisionTheme.amberWarning)
            }
        } else {
            Text("Needs review · Pantry amount is unavailable")
                .foregroundStyle(ProvisionTheme.amberWarning)
        }
    }

    private func recipeStatusItem<Content: View>(title: String, @ViewBuilder status: () -> Content) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .center, spacing: 8) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .layoutPriority(1)
                Spacer(minLength: 0)
                status()
            }
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                status()
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    private func sourceSection(_ source: RecipeSourceReference) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Text("Recipe source")
                .font(ProvisionTypography.sectionSerif)
                .foregroundStyle(ProvisionTheme.textPrimary)
            Text(source.publisher_name)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(ProvisionTheme.textPrimary)
            Text(source.currently_allowed ? source.source_label : "Source review is no longer current")
                .font(.footnote)
                .foregroundStyle(source.currently_allowed ? ProvisionTheme.textSecondary : ProvisionTheme.amberWarning)
            if let author = source.author, !author.isEmpty {
                Text("By \(author)")
                    .font(.footnote)
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
            if let url = URL(string: source.canonical_url) {
                Link("Open publisher page", destination: url)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                    .frame(minHeight: 44, alignment: .leading)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard()
        .accessibilityIdentifier("recipe-source-reference")
    }

    private func sourceErrorSection(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(isSourceOffline ? "Source details unavailable offline" : "Unable to load source details",
                  systemImage: isSourceOffline ? "wifi.slash" : "exclamationmark.triangle.fill")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(isSourceOffline ? ProvisionTheme.amberWarning : ProvisionTheme.redAlert)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(isSourceOffline ? "Source details unavailable offline" : "Unable to load source details")
                .accessibilityIdentifier("recipe-source-error")
            Text(isSourceOffline ? "The recipe and current safety evaluation are available. Reconnect to retry the source lookup." : message)
                .font(.footnote)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Button("Retry source lookup", action: retrySourceReference)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(ProvisionTheme.provisionGreen)
                .frame(minHeight: 44, alignment: .leading)
                .accessibilityIdentifier("recipe-source-retry")
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard(backgroundColor: ProvisionTheme.surfaceSecondary)
    }

    private func ingredientSection(title: String, indices: [Int]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(ProvisionTypography.sectionSerif)
                .foregroundStyle(ProvisionTheme.textPrimary)
            ForEach(indices, id: \.self) { index in
                RecipeIngredientRow(
                    index: index,
                    ingredient: recipe.ingredients[index],
                    substitution: appliedSubstitutions[index],
                    availability: availabilityByRecipeIndex[index],
                    safety: safetyByRecipeIndex[index]
                )
            }
        }
    }

    private var appliedSubstitutionSelections: [RecipeSubstitution] {
        appliedSubstitutions.keys.sorted().compactMap { index in
            guard let replacement = appliedSubstitutions[index] else { return nil }
            return RecipeSubstitution(requirementIndex: index, replacement: replacement)
        }
    }

    private var instructionsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image("pip_cooking")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 36, height: 36)
                    .accessibilityHidden(true)
                Text("Instructions")
                    .font(ProvisionTypography.sectionSerif)
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .accessibilityIdentifier("recipe-instructions")
            }
            ForEach(Array(recipe.instructions.enumerated()), id: \.offset) { step in
                HStack(alignment: .top, spacing: 12) {
                    Text("\(step.offset + 1)")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(ProvisionTheme.onAccent)
                        .frame(width: instructionNumberSize, height: instructionNumberSize)
                        .background(ProvisionTheme.provisionGreen)
                        .clipShape(Circle())
                        .accessibilityHidden(true)
                    Text(step.element)
                        .font(.body)
                        .foregroundStyle(ProvisionTheme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("recipe-instruction-step-\(step.offset + 1)")
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard()
    }

    private var cuisineRegionLabel: String {
        let regions = recipe.ph_regions.filter { $0 != "region_unknown" }
        guard !regions.isEmpty else { return "\(recipe.cuisine) · Region not specified" }
        let distinctRegions = regions.filter { $0.localizedCaseInsensitiveCompare(recipe.cuisine) != .orderedSame }
        guard !distinctRegions.isEmpty else { return recipe.cuisine }
        return "\(recipe.cuisine) · \(distinctRegions.joined(separator: ", "))"
    }

    private func metadataLabel(_ title: String, symbol: String) -> some View {
        Label(title, systemImage: symbol)
            .fixedSize(horizontal: false, vertical: true)
    }
}

private struct RecipeIngredientRow: View {
    let index: Int
    let ingredient: RecipeIngredient
    let substitution: IngredientRequirement?
    let availability: IngredientAvailabilitySnapshot?
    let safety: IngredientSafetySnapshot?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(substitution.map { "\(ingredient.display_name) → \($0.display_name ?? "Selected ingredient")" } ?? ingredient.display_name)
                .font(.headline)
                .foregroundStyle(ProvisionTheme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("recipe-ingredient-name-\(index)")
            Text(substitution.map { "Selected amount: \(QuantityText.string($0.amount)) \($0.unit)" }
                 ?? "Recipe amount: \(QuantityText.string(ingredient.amount)) \(ingredient.unit)")
                .font(.subheadline)
                .foregroundStyle(ProvisionTheme.textSecondary)
            if let preparation = ingredient.preparation, !preparation.isEmpty {
                Text(preparation)
                    .font(.footnote)
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("Pantry availability")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .accessibilityIdentifier("recipe-ingredient-availability-heading-\(index)")
                if let availability {
                    StatusPill(presentation: .availability(availability.status))
                        .accessibilityIdentifier("recipe-ingredient-availability-\(index)")
                    availabilityQuantities(availability, index: index)
                    if !availability.unknown_reasons.isEmpty {
                        reasonList(availability.unknown_reasons, title: "Quantity uncertainty")
                    }
                } else {
                    StatusPill(presentation: .availability("unknown"))
                    Text("The server did not return an availability line for this ingredient.")
                        .font(.footnote)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("Food safety")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                if let safety {
                    StatusPill(presentation: .safety(safety.decision))
                    if !safety.reasons.isEmpty {
                        reasonList(safety.reasons, title: "Safety review")
                    }
                } else {
                    StatusPill(presentation: .safety("unknown"))
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard(backgroundColor: ProvisionTheme.surfaceSecondary)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("recipe-ingredient-\(index)")
    }

    @ViewBuilder
    private func availabilityQuantities(_ line: IngredientAvailabilitySnapshot, index: Int) -> some View {
        let unit = line.unit ?? substitution?.unit ?? ingredient.unit
        VStack(alignment: .leading, spacing: 3) {
            if let required = line.required_amount {
                Text("Need: \(QuantityText.string(required)) \(unit)")
                    .accessibilityIdentifier("recipe-ingredient-needed-\(index)")
            }
            if let available = line.available_amount {
                Text("Have: \(QuantityText.string(available)) \(unit)")
                    .accessibilityIdentifier("recipe-ingredient-on-hand-\(index)")
            }
            if let shortfall = line.shortfall, shortfall.value > 0 {
                Text("Missing: \(QuantityText.string(shortfall)) \(unit)")
                    .foregroundStyle(ProvisionTheme.amberWarning)
                    .accessibilityIdentifier("recipe-ingredient-short-\(index)")
            }
        }
        .font(.footnote)
        .foregroundStyle(ProvisionTheme.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
    }

    private func reasonList(_ reasons: [String], title: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(ProvisionTheme.textSecondary)
            ForEach(Array(reasons.enumerated()), id: \.offset) { item in
                Text(ReasonText.display(item.element))
                    .font(.footnote)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}
