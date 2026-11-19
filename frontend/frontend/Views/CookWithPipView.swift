import SwiftUI

public struct CookWithPipView: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @StateObject private var viewModel: CookWithPipViewModel
    private let scope: HouseholdScope
    private let service: any CookWithPipService
    private let chatService: any PipChatService
    private let workflowService: any CookWithPipWorkflowService
    private let pendingStore: any PendingRecipeShoppingStore
    private let onShoppingConfirmed: () async -> Void
    private let onNavigateToShopping: () -> Void
    @State private var selectedRecipeID: Int?

    public init(scope: HouseholdScope, service: any CookWithPipService = APIClient.shared,
                chatService: any PipChatService = APIClient.shared,
                workflowService: any CookWithPipWorkflowService = APIClient.shared,
                pendingStore: any PendingRecipeShoppingStore = KeychainStore.shared,
                onShoppingConfirmed: @escaping () async -> Void = {},
                onNavigateToShopping: @escaping () -> Void = {},
                initialMode: CookWithPipMode = .cookNow, inventoryBatchID: Int? = nil,
                ingredientFilterLabel: String? = nil) {
        self.scope = scope
        self.service = service
        self.chatService = chatService
        self.workflowService = workflowService
        self.pendingStore = pendingStore
        self.onShoppingConfirmed = onShoppingConfirmed
        self.onNavigateToShopping = onNavigateToShopping
        _viewModel = StateObject(wrappedValue: CookWithPipViewModel(
            scope: scope, service: service, initialMode: initialMode,
            inventoryBatchID: inventoryBatchID, ingredientFilterLabel: ingredientFilterLabel))
    }

    @FocusState private var searchFieldFocused: Bool

    public var body: some View {
        VStack(spacing: 0) {
            if viewModel.mode == .myRecipes {
                HStack(spacing: 10) {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(ProvisionTheme.textSecondary)
                    TextField(
                        "Search household recipes",
                        text: $viewModel.searchQuery,
                        prompt: Text("Search household recipes").foregroundStyle(ProvisionTheme.textSecondary)
                    )
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .submitLabel(.search)
                        .onSubmit { searchFieldFocused = false }
                        .focused($searchFieldFocused)
                        .accessibilityIdentifier("cook-with-pip-search")
                    if !viewModel.searchQuery.isEmpty {
                        Button {
                            viewModel.searchQuery = ""
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(ProvisionTheme.textSecondary)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Clear search")
                    }
                }
                .font(.body)
                .padding(.horizontal, 12)
                .frame(minHeight: 46)
                .background(ProvisionTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(ProvisionTheme.border, lineWidth: 1))
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                if searchFieldFocused {
                    HStack {
                        Spacer()
                        Button("Done") { searchFieldFocused = false }
                            .font(.body.weight(.semibold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                            .frame(minWidth: 44, minHeight: 44)
                            .accessibilityIdentifier("cook-with-pip-search-keyboard-done")
                    }
                    .padding(.horizontal, 16)
                }
            }

            if searchFieldFocused {
                modePicker
                    .padding(.horizontal, 16)
                    .padding(.bottom, 8)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    introduction
                    if let ingredient = viewModel.ingredientFilterLabel {
                        Label("Stored recipes using \(ingredient)", systemImage: "leaf")
                            .font(.headline)
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityIdentifier("cook-with-pip-ingredient-filter")
                    }
                    if !searchFieldFocused {
                        modePicker
                    }
                    NavigationLink {
                        CookWithPipManagementView(scope: scope, service: workflowService)
                    } label: {
                        Label("Preferences and product labels", systemImage: "fork.knife.circle")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                            .frame(maxWidth: .infinity, minHeight: 46, alignment: .leading)
                    }
                    .accessibilityIdentifier("cook-with-pip-management")
                    NavigationLink {
                        PipChatView(
                            scope: scope,
                            chatService: chatService,
                            recipeService: service,
                            workflowService: workflowService,
                            pendingStore: pendingStore,
                            onShoppingConfirmed: onShoppingConfirmed,
                            onNavigateToShopping: onNavigateToShopping
                        )
                        .id("pip-chat-\(scope.storageKey)-household")
                    } label: {
                        Label("Chat with Pip", systemImage: "bubble.left.and.bubble.right")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                            .frame(maxWidth: .infinity, minHeight: 46, alignment: .leading)
                    }
                    .accessibilityIdentifier("cook-with-pip-chat-link")
                    if viewModel.mode != .myRecipes {
                        if !viewModel.needsReviewCandidates.isEmpty {
                            excludedCandidatesSection(
                                title: "Needs Review",
                                candidates: viewModel.needsReviewCandidates,
                                identifier: "cook-with-pip-needs-review"
                            )
                        }
                        if !viewModel.blockedCandidates.isEmpty {
                            excludedCandidatesSection(
                                title: "Blocked for Safety",
                                candidates: viewModel.blockedCandidates,
                                identifier: "cook-with-pip-blocked-recipes"
                            )
                        }
                        if viewModel.hasExcludedCandidates && viewModel.excludedCandidates.isEmpty {
                            excludedCandidatesNote
                        }
                    }

                    if viewModel.isLoading && !viewModel.hasLoadedOnce {
                        loadingState
                    } else if let error = viewModel.errorMessage,
                              viewModel.currentRecipes.isEmpty && viewModel.currentRecommendations.isEmpty {
                        errorState(error)
                    } else if viewModel.currentRecipes.isEmpty && viewModel.currentRecommendations.isEmpty {
                        if !viewModel.hasExcludedCandidates {
                            emptyState
                        }
                        if viewModel.hasMore {
                            loadMoreControl
                        }
                    } else {
                        if viewModel.mode != .myRecipes {
                            Text(viewModel.mode == .almostThere ? "Missing Ingredients" : "Ready to Cook")
                                .font(ProvisionTypography.sectionSerif)
                                .foregroundStyle(ProvisionTheme.textPrimary)
                                .accessibilityIdentifier("cook-with-pip-recommendation-heading")
                        }
                        recipeList
                        if let error = viewModel.errorMessage {
                            inlineErrorState(error)
                        }
                        if viewModel.isLoadingMore {
                            ProgressView("Loading more recipes")
                                .tint(ProvisionTheme.provisionGreen)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 12)
                        } else if viewModel.hasMore {
                            loadMoreControl
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 24)
            }
            .scrollDismissesKeyboard(.interactively)
            .refreshable { await viewModel.refresh() }
            .accessibilityIdentifier("cook-with-pip-recipe-list-scroll")
        }
        .background(ProvisionTheme.background.ignoresSafeArea())
        .navigationTitle("Cook with Pip")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(ProvisionTheme.background, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .navigationDestination(item: $selectedRecipeID) { recipeID in
            RecipeDetailView(recipeID: recipeID, scope: scope, service: service,
                             chatService: chatService, workflowService: workflowService,
                             pendingStore: pendingStore,
                             onShoppingConfirmed: onShoppingConfirmed,
                             onNavigateToShopping: onNavigateToShopping)
        }
        .task {
            if !viewModel.hasLoadedOnce {
                await viewModel.load(reset: true)
            }
        }
        .task(id: viewModel.searchQuery) {
            guard viewModel.hasLoadedOnce else { return }
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            await viewModel.load(reset: true)
        }
    }

    private var introduction: some View {
        HStack(alignment: .center, spacing: 14) {
            Image("pip_chef")
                .resizable()
                .scaledToFit()
                .frame(width: 54, height: 54)
                .padding(6)
                .background(ProvisionTheme.surface, in: Circle())
                .overlay(Circle().stroke(ProvisionTheme.border, lineWidth: 1))
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 5) {
                Text("Recipes from your household")
                    .font(ProvisionTypography.sectionSerif)
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Browse household recipes with current pantry and food-safety checks.")
                    .font(.subheadline)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(ProvisionTheme.heroCard)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(ProvisionTheme.border, lineWidth: 1))
        .accessibilityIdentifier("cook-with-pip-introduction")
    }

    private var modePicker: some View {
        Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(spacing: 8) {
                    modeButtons
                }
            } else {
                HStack(spacing: 8) {
                    modeButtons
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Recipe sections")
    }

    @ViewBuilder
    private var modeButtons: some View {
        ForEach(CookWithPipMode.allCases) { mode in
            Button {
                Task { await viewModel.select(mode) }
            } label: {
                Text(mode.title)
                    .font(.subheadline.weight(viewModel.mode == mode ? .semibold : .medium))
                    .foregroundStyle(viewModel.mode == mode ? ProvisionTheme.onAccent : ProvisionTheme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, minHeight: 46)
                    .background(viewModel.mode == mode ? ProvisionTheme.provisionGreen : ProvisionTheme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(ProvisionTheme.border, lineWidth: 1))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("cook-mode-\(mode.rawValue)")
            .accessibilityValue(viewModel.mode == mode ? "Selected" : "")
            .accessibilityAddTraits(viewModel.mode == mode ? .isSelected : [])
        }
    }

    private var excludedCandidatesNote: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Some household recipes are not shown")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(ProvisionTheme.textPrimary)
            Text(excludedCandidateSummary)
                .font(.footnote)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard(backgroundColor: ProvisionTheme.surfaceSecondary)
        .accessibilityIdentifier("cook-with-pip-excluded-candidates")
    }

    private func excludedCandidatesSection(title: String, candidates: [ExcludedRecipeCandidate],
                                            identifier: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(ProvisionTypography.sectionSerif)
                .foregroundStyle(ProvisionTheme.textPrimary)
                .accessibilityIdentifier(identifier)
            ForEach(candidates) { candidate in
                Button {
                    selectedRecipeID = candidate.recipe_id
                } label: {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(alignment: .top, spacing: 8) {
                            Text(candidate.title)
                                .font(.headline)
                                .foregroundStyle(ProvisionTheme.textPrimary)
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 4)
                            StatusPill(presentation: .excludedCandidate(candidate.status))
                        }
                        Text(excludedCandidateExplanation(candidate))
                            .font(.subheadline)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityIdentifier("cook-with-pip-review-explanation-\(candidate.recipe_id)")
                        Label("Open recipe review", systemImage: "arrow.right.circle")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(14)
                    .background(ProvisionTheme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(ProvisionTheme.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("cook-with-pip-review-recipe-\(candidate.recipe_id)")
            }
        }
    }

    private func excludedCandidateExplanation(_ candidate: ExcludedRecipeCandidate) -> String {
        if candidate.status == "blocked" {
            return "A household allergy or safety restriction conflicts with this recipe. Do not cook it unless the recorded information is corrected."
        }
        if candidate.status == "unknown_quantities" {
            let ingredients = candidate.unknown_ingredients.joined(separator: ", ")
            let subject = ingredients.isEmpty ? "One or more required ingredient quantities" : ingredients
            return "The server could not compare the quantity for \(subject). Review the ingredient and unit in the recipe."
        }
        var actions: [String] = []
        if candidate.reasons.contains("allergy_information_not_provided") {
            actions.append("Add allergy information for every household diner in Preferences.")
        }
        if candidate.reasons.contains("product_allergen_label_not_reviewed") {
            actions.append("Review the package label in Preferences and product labels.")
        }
        let ingredientMappingNeedsReview = candidate.reasons.contains(where: {
            ["ingredient_mapping_unknown", "ingredient_unresolved_or_ambiguous", "ambiguous_ingredient_name",
             "ingredient_name_not_found", "ingredient_reference_missing"].contains($0)
        })
        if ingredientMappingNeedsReview {
            let ingredients = candidate.unknown_ingredients.joined(separator: ", ")
            let subject = ingredients.isEmpty ? "the unresolved ingredient" : ingredients
            let explanation = "Provision cannot match \(subject) to an ingredient in its catalog, " +
                "so it cannot check pantry stock or ingredient-based safety. " +
                "This recipe stays under review until the match is corrected."
            actions.append(explanation)
        }
        if candidate.reasons.contains("recipe_content_permission_not_declared") ||
            candidate.reasons.contains("recipe_source_unavailable") {
            actions.append("Review the recipe's source and content permission.")
        }
        if !candidate.unknown_ingredients.isEmpty && !ingredientMappingNeedsReview {
            actions.append("Check quantities and units for \(candidate.unknown_ingredients.joined(separator: ", ")).")
        }
        if !actions.isEmpty {
            return actions.joined(separator: " ") + " Recheck this recipe before cooking."
        }
        return "Open the recipe to review its current safety details. It stays unavailable until the required checks pass."
    }

    private var excludedCandidateSummary: String {
        var counts: [String] = []
        if viewModel.excludedBlocked > 0 { counts.append("\(viewModel.excludedBlocked) blocked") }
        if viewModel.excludedReviewRequired > 0 { counts.append("\(viewModel.excludedReviewRequired) needing review") }
        if viewModel.excludedUnknownQuantities > 0 { counts.append("\(viewModel.excludedUnknownQuantities) with unknown quantities") }
        return "Not shown: " + counts.joined(separator: ", ") + " under the current food-safety and ingredient checks."
    }

    private var recipeList: some View {
        LazyVStack(spacing: 12) {
            if viewModel.mode == .myRecipes {
                ForEach(viewModel.recipes) { recipe in
                    Button {
                        selectedRecipeID = recipe.id
                    } label: {
                        HouseholdRecipeCard(recipe: recipe)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("recipe-card-\(recipe.id)")
                    .accessibilityValue("Household recipe")
                }
            } else {
                ForEach(viewModel.recommendations, id: \.recipe.id) { recommendation in
                    Button {
                        selectedRecipeID = recommendation.recipe.id
                    } label: {
                        RecommendationRecipeCard(recommendation: recommendation)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("recipe-card-\(recommendation.recipe.id)")
                    .accessibilityValue("Recommendation")
                }
            }
        }
        // A recipe ID can appear in both the household and recommendation collections.
        // Reset row identity when changing modes so SwiftUI cannot reuse a stale card.
        .id(viewModel.mode)
    }

    private var emptyState: some View {
        VStack(spacing: 10) {
            Image("pip_chef")
                .resizable()
                .scaledToFit()
                .frame(width: 56, height: 56)
                .accessibilityHidden(true)
            Text(emptyTitle)
                .font(ProvisionTypography.sectionSerif)
                .foregroundStyle(ProvisionTheme.textPrimary)
                .multilineTextAlignment(.center)
            Text(emptyMessage)
                .font(.subheadline)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .provisionCard()
        .accessibilityIdentifier("cook-with-pip-empty-state")
    }

    private var emptyTitle: String {
        if let ingredient = viewModel.ingredientFilterLabel {
            return "No stored recipes use \(ingredient) yet"
        }
        if !viewModel.normalizedQuery.isEmpty { return "No matching household recipes" }
        return switch viewModel.mode {
        case .cookNow: "No recipes are ready to cook"
        case .almostThere: "No recipes are almost ready"
        case .myRecipes: "No household recipes yet"
        }
    }

    private var emptyMessage: String {
        if viewModel.ingredientFilterLabel != nil {
            return "Recipes appear here when this ingredient is included in a saved recipe and matched to your pantry."
        }
        if !viewModel.normalizedQuery.isEmpty {
            return "Try another title. This search looks through recipes saved for your household."
        }
        switch viewModel.mode {
        case .cookNow:
            return "No saved recipe has all its required quantities in the pantry right now."
        case .almostThere:
            return "No saved recipe is close enough to cook with a small, known ingredient shortage."
        case .myRecipes:
            return "Recipes saved for your household will appear here."
        }
    }

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView().tint(ProvisionTheme.provisionGreen)
            Text("Checking household recipes")
                .font(.subheadline)
                .foregroundStyle(ProvisionTheme.textSecondary)
        }
        .frame(maxWidth: .infinity)
        .padding(36)
        .provisionCard()
        .accessibilityIdentifier("cook-with-pip-loading-state")
    }

    private var loadMoreControl: some View {
        Button {
            Task { await viewModel.loadMore() }
        } label: {
            Text("Load more")
                .font(.headline)
                .foregroundStyle(ProvisionTheme.provisionGreen)
                .frame(maxWidth: .infinity, minHeight: 48)
        }
        .accessibilityIdentifier("cook-with-pip-load-more")
    }

    private func errorState(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(viewModel.isOffline ? "You're offline" : "Unable to load recipes",
                  systemImage: viewModel.isOffline ? "wifi.slash" : "exclamationmark.triangle.fill")
                .font(.headline)
                .foregroundStyle(viewModel.isOffline ? ProvisionTheme.amberWarning : ProvisionTheme.redAlert)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(viewModel.isOffline ? "You're offline" : "Unable to load recipes")
                .accessibilityIdentifier("cook-with-pip-error-state")
            Text(viewModel.isOffline ? "Connect to your server and retry. No saved offline recipe evaluation is shown." : message)
                .font(.subheadline)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Button("Try again") { Task { await viewModel.load(reset: true) } }
                .font(.headline)
                .foregroundStyle(ProvisionTheme.provisionGreen)
                .frame(minHeight: 44)
                .accessibilityIdentifier("cook-with-pip-retry")
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard()
    }

    private func inlineErrorState(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(viewModel.isOffline ? "Offline. Showing the last loaded results." : message)
                .font(.footnote)
                .foregroundStyle(ProvisionTheme.textSecondary)
            Button("Retry") { Task { await viewModel.load(reset: true, preserveResults: true) } }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(ProvisionTheme.provisionGreen)
                .frame(minHeight: 44, alignment: .leading)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard(backgroundColor: ProvisionTheme.surfaceSecondary)
        .accessibilityIdentifier("cook-with-pip-inline-error")
    }
}

private struct RecommendationRecipeCard: View {
    let recommendation: RecipeRecommendation

    private var recipe: HouseholdRecipe { recommendation.recipe }
    private var safety: RecipeStatusPresentation { .safety(recommendation.evaluation.decision) }
    private var availability: RecipeStatusPresentation { .availability(recommendation.evaluation.availability.overall_status) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(recipe.title)
                        .font(ProvisionTypography.sectionSerif)
                        .foregroundStyle(ProvisionTheme.textPrimary)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(cuisineLine)
                        .font(.subheadline)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                        .multilineTextAlignment(.leading)
                }
                Spacer(minLength: 4)
                Image(systemName: "chevron.right")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(ProvisionTheme.textTertiary)
                    .padding(.top, 5)
                    .accessibilityHidden(true)
            }

            HStack(spacing: 8) {
                StatusPill(presentation: safety)
                StatusPill(presentation: availability)
            }

            HStack(spacing: 12) {
                Label("\(recipe.prep_minutes + recipe.cook_minutes) min", systemImage: "clock")
                Label("Serves \(QuantityText.string(recipe.servings))", systemImage: "person.2")
                if recommendation.missing_ingredient_count > 0 {
                    Label("\(recommendation.missing_ingredient_count) missing", systemImage: "basket")
                }
            }
            .font(.footnote)
            .foregroundStyle(ProvisionTheme.textSecondary)
            .lineLimit(1)
            .minimumScaleFactor(0.8)

            if let summary = recipe.summary, !summary.isEmpty {
                Text(summary)
                    .font(.subheadline)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .multilineTextAlignment(.leading)
                    .lineLimit(3)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard()
        .accessibilityElement(children: .combine)
    }

    private var cuisineLine: String {
        let regions = recipe.ph_regions.filter { $0 != "region_unknown" }
        let regionText = regions.isEmpty ? "Region not specified" : regions.joined(separator: ", ")
        return "\(recipe.cuisine) · \(regionText)"
    }
}

private struct HouseholdRecipeCard: View {
    let recipe: HouseholdRecipe

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(recipe.title)
                        .font(ProvisionTypography.sectionSerif)
                        .foregroundStyle(ProvisionTheme.textPrimary)
                        .multilineTextAlignment(.leading)
                    Text("\(recipe.cuisine) · \(regionText)")
                        .font(.subheadline)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                Spacer(minLength: 4)
                Image(systemName: "chevron.right")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(ProvisionTheme.textTertiary)
                    .accessibilityHidden(true)
            }
            Label("\(recipe.prep_minutes + recipe.cook_minutes) min · serves \(QuantityText.string(recipe.servings))",
                  systemImage: "clock")
                .font(.footnote)
                .foregroundStyle(ProvisionTheme.textSecondary)
            Text("Open to check current stock and food-safety results")
                .font(.footnote)
                .foregroundStyle(ProvisionTheme.textSecondary)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard()
        .accessibilityElement(children: .combine)
    }

    private var regionText: String {
        let regions = recipe.ph_regions.filter { $0 != "region_unknown" }
        return regions.isEmpty ? "region not specified" : regions.joined(separator: ", ")
    }
}

#if DEBUG
#Preview("Cook with Pip") {
    NavigationStack {
        CookWithPipView(scope: HouseholdScope(userID: 1, householdID: 1))
    }
}
#endif
