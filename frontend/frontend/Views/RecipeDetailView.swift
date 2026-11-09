import SwiftUI

public struct RecipeDetailView: View {
    @StateObject private var viewModel: RecipeDetailViewModel

    public init(recipeID: Int, scope: HouseholdScope, service: any CookWithPipService = APIClient.shared) {
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
                    RecipeDetailContents(recipe: recipe, evaluation: evaluation, sourceReference: viewModel.sourceReference)
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 28)
        }
        .background(ProvisionTheme.background.ignoresSafeArea())
        .navigationTitle(viewModel.recipe?.title ?? "Recipe")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await viewModel.load() }
        .task {
            if !viewModel.hasLoadedOnce { await viewModel.load() }
        }
    }
}

private struct RecipeDetailContents: View {
    let recipe: HouseholdRecipe
    let evaluation: RecipeEvaluation
    let sourceReference: RecipeSourceReference?

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
            if let sourceReference {
                sourceSection(sourceReference)
            }
            ingredientSection(title: "Required ingredients", indices: requiredIngredients)
            if !optionalIngredients.isEmpty {
                ingredientSection(title: "Optional ingredients", indices: optionalIngredients)
            }
            instructionsSection
        }
    }

    private var titleSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(recipe.title)
                .font(ProvisionTypography.heroSerif)
                .foregroundStyle(ProvisionTheme.provisionGreen)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("recipe-detail-title")
            if let summary = recipe.summary, !summary.isEmpty {
                Text(summary)
                    .font(.body)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text("\(recipe.cuisine) · \(regionText)")
                .font(.subheadline.weight(.medium))
                .foregroundStyle(ProvisionTheme.textSecondary)
            HStack(spacing: 12) {
                metadataLabel("Prep \(recipe.prep_minutes) min", symbol: "clock")
                metadataLabel("Cook \(recipe.cook_minutes) min", symbol: "flame")
                metadataLabel("Serves \(QuantityText.string(recipe.servings))", symbol: "person.2")
            }
            .font(.footnote)
            .foregroundStyle(ProvisionTheme.textSecondary)
            Text("Stored household recipe")
                .font(.caption.weight(.semibold))
                .foregroundStyle(ProvisionTheme.provisionGreen)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard(backgroundColor: ProvisionTheme.heroCard)
    }

    private var evaluationSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Current server evaluation")
                .font(ProvisionTypography.sectionSerif)
                .foregroundStyle(ProvisionTheme.textPrimary)
            HStack(spacing: 10) {
                StatusPill(presentation: .safety(evaluation.result.decision))
                    .accessibilityIdentifier("recipe-safety-status")
                StatusPill(presentation: .availability(evaluation.result.availability.overall_status))
                    .accessibilityIdentifier("recipe-availability-status")
            }
            Text(evaluation.result.notice)
                .font(.subheadline)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Text("Evaluation uses all active household members unless the server request names diners.")
                .font(.footnote)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if !evaluation.result.reasons.isEmpty {
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(Array(evaluation.result.reasons.enumerated()), id: \.offset) { item in
                        Label(ReasonText.display(item.element), systemImage: "info.circle")
                            .font(.footnote)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard()
        .accessibilityIdentifier("recipe-safety-evaluation")
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

    private func ingredientSection(title: String, indices: [Int]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(ProvisionTypography.sectionSerif)
                .foregroundStyle(ProvisionTheme.textPrimary)
            ForEach(indices, id: \.self) { index in
                RecipeIngredientRow(
                    index: index,
                    ingredient: recipe.ingredients[index],
                    availability: availabilityByRecipeIndex[index],
                    safety: safetyByRecipeIndex[index]
                )
            }
        }
    }

    private var instructionsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Instructions")
                .font(ProvisionTypography.sectionSerif)
                .foregroundStyle(ProvisionTheme.textPrimary)
            ForEach(Array(recipe.instructions.enumerated()), id: \.offset) { step in
                HStack(alignment: .top, spacing: 12) {
                    Text("\(step.offset + 1)")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(ProvisionTheme.onAccent)
                        .frame(width: 28, height: 28)
                        .background(ProvisionTheme.provisionGreen)
                        .clipShape(Circle())
                        .accessibilityHidden(true)
                    Text(step.element)
                        .font(.body)
                        .foregroundStyle(ProvisionTheme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard()
        .accessibilityIdentifier("recipe-instructions")
    }

    private var regionText: String {
        let regions = recipe.ph_regions.filter { $0 != "region_unknown" }
        return regions.isEmpty ? "Region not specified" : regions.joined(separator: ", ")
    }

    private func metadataLabel(_ title: String, symbol: String) -> some View {
        Label(title, systemImage: symbol)
            .lineLimit(1)
            .minimumScaleFactor(0.8)
    }
}

private struct RecipeIngredientRow: View {
    let index: Int
    let ingredient: RecipeIngredient
    let availability: IngredientAvailabilitySnapshot?
    let safety: IngredientSafetySnapshot?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(ingredient.display_name)
                .font(.headline)
                .foregroundStyle(ProvisionTheme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            Text("Recipe amount: \(QuantityText.string(ingredient.amount)) \(ingredient.unit)")
                .font(.subheadline)
                .foregroundStyle(ProvisionTheme.textSecondary)
            if let preparation = ingredient.preparation, !preparation.isEmpty {
                Text(preparation)
                    .font(.footnote)
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
            if let availability {
                StatusPill(presentation: .availability(availability.status))
                availabilityQuantities(availability)
                if !availability.unknown_reasons.isEmpty {
                    reasonList(availability.unknown_reasons, title: "Quantity uncertainty")
                }
            } else {
                StatusPill(presentation: .availability("unknown"))
                Text("The server did not return an availability line for this ingredient.")
                    .font(.footnote)
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
            if let safety {
                StatusPill(presentation: .safety(safety.decision))
                if !safety.reasons.isEmpty {
                    reasonList(safety.reasons, title: "Safety review")
                }
            } else {
                StatusPill(presentation: .safety("unknown"))
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard(backgroundColor: ProvisionTheme.surfaceSecondary)
        .accessibilityIdentifier("recipe-ingredient-\(index)")
    }

    @ViewBuilder
    private func availabilityQuantities(_ line: IngredientAvailabilitySnapshot) -> some View {
        let unit = line.unit ?? ingredient.unit
        VStack(alignment: .leading, spacing: 3) {
            if let required = line.required_amount {
                Text("Needed: \(QuantityText.string(required)) \(unit)")
            }
            if let available = line.available_amount {
                Text("Counted on hand: \(QuantityText.string(available)) \(unit)")
            }
            if let shortfall = line.shortfall, shortfall.value > 0 {
                Text("Short: \(QuantityText.string(shortfall)) \(unit)")
                    .foregroundStyle(ProvisionTheme.amberWarning)
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
