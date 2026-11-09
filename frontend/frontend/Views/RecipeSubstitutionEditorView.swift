import SwiftUI

public struct RecipeSubstitutionEditorView: View {
    @Environment(\.dismiss) private var dismiss
    let recipe: HouseholdRecipe
    let scope: HouseholdScope
    let service: any CookWithPipService
    let onApply: (RecipeEvaluation, [RecipeSubstitution]) -> Void
    @State private var selectedOptions: [Int: Int] = [:]
    @State private var includeOptional = true
    @State private var servingsText: String
    @State private var isEvaluating = false
    @State private var errorMessage: String?

    public init(recipe: HouseholdRecipe, scope: HouseholdScope,
                service: any CookWithPipService = APIClient.shared,
                onApply: @escaping (RecipeEvaluation, [RecipeSubstitution]) -> Void) {
        self.recipe = recipe
        self.scope = scope
        self.service = service
        self.onApply = onApply
        _servingsText = State(initialValue: NSDecimalNumber(decimal: recipe.servings.value).stringValue)
    }

    private var availableOptions: [(index: Int, ingredient: RecipeIngredient)] {
        recipe.ingredients.indices.compactMap { index in
            recipe.ingredients[index].substitution_options.isEmpty ? nil : (index, recipe.ingredients[index])
        }
    }

    private var substitutions: [RecipeSubstitution] {
        selectedOptions.keys.sorted().compactMap { requirementIndex in
            guard let optionIndex = selectedOptions[requirementIndex], optionIndex > 0,
                  recipe.ingredients.indices.contains(requirementIndex),
                  recipe.ingredients[requirementIndex].substitution_options.indices.contains(optionIndex - 1) else { return nil }
            return RecipeSubstitution(requirementIndex: requirementIndex,
                                      replacement: recipe.ingredients[requirementIndex].substitution_options[optionIndex - 1])
        }
    }

    public var body: some View {
        NavigationStack {
            Form {
                if let errorMessage {
                    Section {
                        Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                            .foregroundStyle(ProvisionTheme.redAlert)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityIdentifier("recipe-substitution-error")
                    }
                }
                Section("Evaluation settings") {
                    TextField("Servings", text: $servingsText)
                        .keyboardType(.decimalPad)
                        .accessibilityIdentifier("recipe-substitution-servings")
                    Toggle("Include optional ingredients", isOn: $includeOptional)
                }
                Section("Server-listed alternatives") {
                    if availableOptions.isEmpty {
                        Text("This recipe has no stored substitution options.")
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }
                    ForEach(availableOptions, id: \.index) { entry in
                        Picker(entry.ingredient.display_name, selection: selectionBinding(for: entry.index)) {
                            Text("Keep \(entry.ingredient.display_name) · \(quantity(entry.ingredient.amount)) \(entry.ingredient.unit)")
                                .tag(0)
                            ForEach(Array(entry.ingredient.substitution_options.enumerated()), id: \.offset) { option in
                                Text(optionLabel(option.element)).tag(option.offset + 1)
                            }
                        }
                        .accessibilityIdentifier("recipe-substitution-choice-\(entry.index)")
                    }
                    Text("Only alternatives and quantities stored for this recipe are available. No unit conversion is estimated.")
                        .font(.footnote)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
            }
            .scrollContentBackground(.hidden)
            .background(ProvisionTheme.background)
            .navigationTitle("Review Substitutions")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await reevaluate() }
                    } label: {
                        if isEvaluating { ProgressView() }
                        else { Text("Recheck") }
                    }
                    .disabled(isEvaluating || !isValidServings || substitutions.isEmpty)
                    .accessibilityIdentifier("recipe-substitution-recheck")
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func selectionBinding(for index: Int) -> Binding<Int> {
        Binding(
            get: { selectedOptions[index] ?? 0 },
            set: { selectedOptions[index] = $0 }
        )
    }

    private func optionLabel(_ requirement: IngredientRequirement) -> String {
        let name = requirement.display_name ?? "Ingredient \(requirement.ingredient_id ?? 0)"
        return "\(name) · \(quantity(requirement.amount)) \(requirement.unit)"
    }

    private func quantity(_ value: ExactQuantity) -> String {
        NSDecimalNumber(decimal: value.value).stringValue
    }

    private var isValidServings: Bool {
        guard let value = Decimal(string: servingsText, locale: Locale(identifier: "en_US_POSIX")),
              value > 0, value <= 10_000 else { return false }
        var source = value
        var rounded = Decimal()
        NSDecimalRound(&rounded, &source, 4, .plain)
        return rounded == value
    }

    private func reevaluate() async {
        guard let servings = Decimal(string: servingsText, locale: Locale(identifier: "en_US_POSIX")) else { return }
        isEvaluating = true
        errorMessage = nil
        do {
            let result = try await service.evaluateRecipe(
                id: recipe.id,
                payload: RecipeEvaluationRequest(
                    revision: recipe.revision,
                    servings: ExactQuantity(servings),
                    includeOptional: includeOptional,
                    substitutions: substitutions
                ),
                scope: scope
            )
            onApply(result, substitutions)
            dismiss()
        } catch {
            if let apiError = error as? APIError, apiError.serverErrorCode == "RECIPE_REVISION_CONFLICT" {
                errorMessage = "This recipe changed on the server. Close this editor and reload the recipe before trying again."
            } else {
                errorMessage = error.localizedDescription
            }
        }
        isEvaluating = false
    }
}
