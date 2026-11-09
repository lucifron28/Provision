import SwiftUI

public struct CookWithPipView: View {
    @StateObject private var viewModel: CookWithPipViewModel
    private let scope: HouseholdScope
    private let service: any CookWithPipService
    private let workflowService: any CookWithPipWorkflowService
    private let onShoppingConfirmed: () async -> Void
    private let onNavigateToShopping: () -> Void

    public init(scope: HouseholdScope, service: any CookWithPipService = APIClient.shared,
                workflowService: any CookWithPipWorkflowService = APIClient.shared,
                onShoppingConfirmed: @escaping () async -> Void = {},
                onNavigateToShopping: @escaping () -> Void = {}) {
        self.scope = scope
        self.service = service
        self.workflowService = workflowService
        self.onShoppingConfirmed = onShoppingConfirmed
        self.onNavigateToShopping = onNavigateToShopping
        _viewModel = StateObject(wrappedValue: CookWithPipViewModel(scope: scope, service: service))
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                introduction
                NavigationLink {
                    CookWithPipManagementView(scope: scope, service: workflowService)
                } label: {
                    Label("Preferences and product labels", systemImage: "fork.knife.circle")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                        .frame(maxWidth: .infinity, minHeight: 46, alignment: .leading)
                }
                .accessibilityIdentifier("cook-with-pip-management")
                modePicker

                if viewModel.hasExcludedCandidates && viewModel.mode != .myRecipes {
                    excludedCandidatesNote
                }

                if viewModel.isLoading && !viewModel.hasLoadedOnce {
                    loadingState
                } else if let error = viewModel.errorMessage,
                          viewModel.currentRecipes.isEmpty && viewModel.currentRecommendations.isEmpty {
                    errorState(error)
                } else if viewModel.currentRecipes.isEmpty && viewModel.currentRecommendations.isEmpty {
                    emptyState
                    if viewModel.hasMore {
                        loadMoreControl
                    }
                } else {
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
        .background(ProvisionTheme.background.ignoresSafeArea())
        .navigationTitle("Cook with Pip")
        .navigationBarTitleDisplayMode(.inline)
        .searchable(text: $viewModel.searchQuery, prompt: "Search household recipes")
        .refreshable { await viewModel.refresh() }
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
                .frame(width: 68, height: 68)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 5) {
                Text("Recipes from your household")
                    .font(ProvisionTypography.sectionSerif)
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Cook Now and Almost There use the server's current stock and safety evaluation. No live internet search.")
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
        HStack(spacing: 8) {
            ForEach(CookWithPipMode.allCases) { mode in
                Button {
                    Task { await viewModel.select(mode) }
                } label: {
                    Text(mode.title)
                        .font(.subheadline.weight(viewModel.mode == mode ? .semibold : .medium))
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .foregroundStyle(viewModel.mode == mode ? ProvisionTheme.onAccent : ProvisionTheme.textPrimary)
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
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Recipe sections")
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

    private var excludedCandidateSummary: String {
        var counts: [String] = []
        if viewModel.excludedBlocked > 0 { counts.append("\(viewModel.excludedBlocked) blocked") }
        if viewModel.excludedReviewRequired > 0 { counts.append("\(viewModel.excludedReviewRequired) needing review") }
        if viewModel.excludedUnknownQuantities > 0 { counts.append("\(viewModel.excludedUnknownQuantities) with unknown quantities") }
        return "The server excluded " + counts.joined(separator: ", ") + " under its current checks."
    }

    private var recipeList: some View {
        LazyVStack(spacing: 12) {
            if viewModel.mode == .myRecipes {
                ForEach(viewModel.recipes) { recipe in
                    NavigationLink {
                        RecipeDetailView(recipeID: recipe.id, scope: scope, service: service,
                                         workflowService: workflowService,
                                         onShoppingConfirmed: onShoppingConfirmed,
                                         onNavigateToShopping: onNavigateToShopping)
                    } label: {
                        HouseholdRecipeCard(recipe: recipe)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("recipe-card-\(recipe.id)")
                }
            } else {
                ForEach(viewModel.recommendations, id: \.recipe.id) { recommendation in
                    NavigationLink {
                        RecipeDetailView(recipeID: recommendation.recipe.id, scope: scope, service: service,
                                         workflowService: workflowService,
                                         onShoppingConfirmed: onShoppingConfirmed,
                                         onNavigateToShopping: onNavigateToShopping)
                    } label: {
                        RecommendationRecipeCard(recommendation: recommendation)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("recipe-card-\(recommendation.recipe.id)")
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 10) {
            Image(systemName: viewModel.mode == .cookNow ? "basket" : "book.closed")
                .font(.system(size: 30, weight: .regular))
                .foregroundStyle(ProvisionTheme.provisionGreen)
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
        if !viewModel.normalizedQuery.isEmpty { return "No matching household recipes" }
        return switch viewModel.mode {
        case .cookNow: "No recipes are ready to cook"
        case .almostThere: "No recipes are almost ready"
        case .myRecipes: "No household recipes yet"
        }
    }

    private var emptyMessage: String {
        if !viewModel.normalizedQuery.isEmpty {
            return "Try another title search. This screen only searches recipes stored in your household."
        }
        switch viewModel.mode {
        case .cookNow:
            return "The server found no stored recipe with all required quantities currently available."
        case .almostThere:
            return "The server found no eligible stored recipe with a small, known ingredient shortage."
        case .myRecipes:
            return "Recipes entered for this household will appear here. This is not an internet recipe search."
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
