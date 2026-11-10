import SwiftUI

public struct CookWithPipPreferencesView: View {
    @StateObject private var viewModel: CookWithPipPreferencesViewModel
    private let onProfileUpdated: () async -> Void
    @State private var servingsText = "2"
    @State private var cookMinutesText = ""
    @State private var budgetText = ""
    @State private var customAllergyText = ""

    public init(scope: HouseholdScope, service: any CookWithPipWorkflowService = APIClient.shared,
                onProfileUpdated: @escaping () async -> Void = {}) {
        _viewModel = StateObject(wrappedValue: CookWithPipPreferencesViewModel(scope: scope, service: service))
        self.onProfileUpdated = onProfileUpdated
    }

    public var body: some View {
        Form {
            if let error = viewModel.errorMessage {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(ProvisionTheme.redAlert)
                        .accessibilityIdentifier("pip-preferences-error")
                    Button("Reload profile") { Task { await reload() } }
                        .accessibilityIdentifier("pip-preferences-retry")
                }
            }
            if let success = viewModel.successMessage {
                Section {
                    Label(success, systemImage: "checkmark.circle.fill")
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(success)
                        .accessibilityIdentifier("pip-preferences-success")
                }
            }
            if let invalidNumberMessage {
                Section {
                    Label(invalidNumberMessage, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(ProvisionTheme.redAlert)
                }
            }

            Section("Cooking preferences") {
                TextField("Cuisines, separated by commas", text: listBinding(\.preferred_cuisines))
                    .accessibilityIdentifier("pip-preferred-cuisines")
                TextField("Filipino regions, separated by commas", text: listBinding(\.preferred_regions))
                    .accessibilityIdentifier("pip-preferred-regions")
                TextField("Dislikes, separated by commas", text: listBinding(\.dislikes))
                    .accessibilityIdentifier("pip-dislikes")
                TextField("Kitchen equipment, separated by commas", text: listBinding(\.equipment))
                    .accessibilityIdentifier("pip-equipment")
                ForEach(dietPatterns, id: \.value) { item in
                    Toggle(item.title, isOn: dietBinding(item.value))
                        .accessibilityIdentifier("pip-diet-\(item.value)")
                }
                Picker("Heat tolerance", selection: $viewModel.preferences.heat_tolerance) {
                    Text("No preference").tag("no_preference")
                    Text("Mild").tag("mild")
                    Text("Medium").tag("medium")
                    Text("Hot").tag("hot")
                }
                LabeledContent("Servings per meal (people)") {
                    TextField("Number of people", text: $servingsText)
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.trailing)
                        .accessibilityIdentifier("pip-preferred-servings")
                        .onChange(of: servingsText) { _, value in
                            if let amount = decimal(value), amount > 0 { viewModel.preferences.servings = amount }
                        }
                }
                TextField("Maximum cooking minutes", text: $cookMinutesText)
                    .keyboardType(.numberPad)
                    .accessibilityIdentifier("pip-max-cook-minutes")
                    .onChange(of: cookMinutesText) { _, value in
                        viewModel.preferences.max_cook_minutes = Int(value)
                    }
                TextField("Meal budget per person (PHP)", text: $budgetText)
                    .keyboardType(.decimalPad)
                    .accessibilityIdentifier("pip-meal-budget")
                    .onChange(of: budgetText) { _, value in
                        viewModel.preferences.meal_budget_php = value.isEmpty ? nil : decimal(value)
                    }
                Picker("Recipe language", selection: $viewModel.preferences.preferred_language) {
                    Text("English").tag("en")
                    Text("Filipino").tag("fil")
                }
            }

            Section {
                Picker("Allergy declaration", selection: $viewModel.allergyStatus) {
                    Text("Not provided").tag("NOT_PROVIDED")
                    Text("No allergies declared").tag("NONE_DECLARED")
                    Text("Allergies declared").tag("DECLARED")
                }
                .accessibilityIdentifier("pip-allergy-status")
                ForEach(FoodAllergenCode.allCases) { code in
                    VStack(alignment: .leading, spacing: 4) {
                        Toggle(code.title, isOn: allergyBinding(code))
                            .accessibilityIdentifier("pip-allergen-\(code.rawValue)")
                        if hasAllergy(code) {
                            Picker("\(code.title) severity", selection: allergySeverityBinding(code)) {
                                Text("Not specified").tag("")
                                Text("Mild").tag("mild")
                                Text("Moderate").tag("moderate")
                                Text("Severe").tag("severe")
                            }
                            .accessibilityIdentifier("pip-allergen-severity-\(code.rawValue)")
                            Toggle("Cross-contact concern for \(code.title)", isOn: allergyCrossContactBinding(code))
                                .accessibilityIdentifier("pip-allergen-cross-contact-\(code.rawValue)")
                        }
                    }
                }
                TextField("Custom allergens, separated by commas", text: $customAllergyText)
                    .accessibilityIdentifier("pip-custom-allergies")
                    .onChange(of: customAllergyText) { _, value in updateCustomAllergies(value) }
                ForEach(viewModel.allergies.compactMap(\.custom_text), id: \.self) { custom in
                    Picker("\(custom) severity", selection: customSeverityBinding(custom)) {
                        Text("Not specified").tag("")
                        Text("Mild").tag("mild")
                        Text("Moderate").tag("moderate")
                        Text("Severe").tag("severe")
                    }
                    .accessibilityIdentifier("pip-custom-allergen-severity")
                    Toggle("Cross-contact concern for \(custom)", isOn: customCrossContactBinding(custom))
                        .accessibilityIdentifier("pip-custom-allergen-cross-contact")
                }
            } header: {
                Text("Allergies")
            } footer: {
                Text("Choose an explicit declaration. A missing declaration is never treated as allergy-free.")
            }

            Section {
                Text("Cook with Pip sends only this member profile to the household-scoped server evaluation. It does not certify a recipe or package label as safe.")
                    .font(.footnote)
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
        }
        .scrollContentBackground(.hidden)
        .background(ProvisionTheme.background)
        .navigationTitle("My Cooking Preferences")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(ProvisionTheme.background, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task { await saveProfile() }
                } label: {
                    if viewModel.isSaving { ProgressView() }
                    else { Text("Save") }
                }
                .disabled(viewModel.isSaving || viewModel.isLoading || !viewModel.hasLoaded || !viewModel.canSave || !numericFieldsAreValid)
                .accessibilityIdentifier("pip-preferences-save")
            }
        }
        .task { await reload() }
        .refreshable { await reload() }
    }

    private var dietPatterns: [(value: String, title: String)] {
        [("vegetarian", "Vegetarian"), ("vegan", "Vegan"), ("pescatarian", "Pescatarian"),
         ("halal", "Halal"), ("no_pork", "No pork"), ("gluten_free", "Gluten-free"),
         ("dairy_free", "Dairy-free")]
    }

    private func listBinding(_ keyPath: WritableKeyPath<FoodPreferences, [String]>) -> Binding<String> {
        Binding(
            get: { viewModel.preferences[keyPath: keyPath].joined(separator: ", ") },
            set: { value in
                var preferences = viewModel.preferences
                preferences[keyPath: keyPath] = splitList(value)
                viewModel.preferences = preferences
            }
        )
    }

    private func dietBinding(_ value: String) -> Binding<Bool> {
        Binding(
            get: { viewModel.preferences.diet_patterns.contains(value) },
            set: { selected in
                var patterns = viewModel.preferences.diet_patterns.filter { $0 != value }
                if selected { patterns.append(value) }
                viewModel.preferences.diet_patterns = patterns
            }
        )
    }

    private func allergyBinding(_ code: FoodAllergenCode) -> Binding<Bool> {
        Binding(
            get: { viewModel.allergies.contains { $0.allergen_code == code.rawValue } },
            set: { selected in
                viewModel.allergies.removeAll { $0.allergen_code == code.rawValue }
                if selected {
                    viewModel.allergies.append(FoodAllergy(allergen_code: code.rawValue))
                    viewModel.allergyStatus = "DECLARED"
                }
            }
        )
    }

    private func hasAllergy(_ code: FoodAllergenCode) -> Bool {
        viewModel.allergies.contains { $0.allergen_code == code.rawValue }
    }

    private func allergySeverityBinding(_ code: FoodAllergenCode) -> Binding<String> {
        Binding(
            get: { viewModel.allergies.first(where: { $0.allergen_code == code.rawValue })?.severity ?? "" },
            set: { severity in
                guard let index = viewModel.allergies.firstIndex(where: { $0.allergen_code == code.rawValue }) else { return }
                viewModel.allergies[index].severity = severity.isEmpty ? nil : severity
            }
        )
    }

    private func allergyCrossContactBinding(_ code: FoodAllergenCode) -> Binding<Bool> {
        Binding(
            get: { viewModel.allergies.first(where: { $0.allergen_code == code.rawValue })?.cross_contact_concern ?? false },
            set: { value in
                guard let index = viewModel.allergies.firstIndex(where: { $0.allergen_code == code.rawValue }) else { return }
                viewModel.allergies[index].cross_contact_concern = value
            }
        )
    }

    private func customSeverityBinding(_ custom: String) -> Binding<String> {
        Binding(
            get: { viewModel.allergies.first(where: { $0.custom_text == custom })?.severity ?? "" },
            set: { severity in
                guard let index = viewModel.allergies.firstIndex(where: { $0.custom_text == custom }) else { return }
                viewModel.allergies[index].severity = severity.isEmpty ? nil : severity
            }
        )
    }

    private func customCrossContactBinding(_ custom: String) -> Binding<Bool> {
        Binding(
            get: { viewModel.allergies.first(where: { $0.custom_text == custom })?.cross_contact_concern ?? false },
            set: { value in
                guard let index = viewModel.allergies.firstIndex(where: { $0.custom_text == custom }) else { return }
                viewModel.allergies[index].cross_contact_concern = value
            }
        )
    }

    private func updateCustomAllergies(_ value: String) {
        let oldCustom = viewModel.allergies.filter { $0.custom_text != nil }
        viewModel.allergies.removeAll { $0.custom_text != nil }
        let custom = splitList(value).map { text in
            oldCustom.first(where: { $0.custom_text?.caseInsensitiveCompare(text) == .orderedSame })
                ?? FoodAllergy(custom_text: text)
        }
        viewModel.allergies.append(contentsOf: custom)
        if !custom.isEmpty { viewModel.allergyStatus = "DECLARED" }
    }

    private func reload() async {
        await viewModel.load()
        servingsText = decimalText(viewModel.preferences.servings)
        cookMinutesText = viewModel.preferences.max_cook_minutes.map { String($0) } ?? ""
        budgetText = viewModel.preferences.meal_budget_php.map(decimalText) ?? ""
        customAllergyText = viewModel.allergies.compactMap(\.custom_text).joined(separator: ", ")
    }

    private func saveProfile() async {
        let previousRevision = viewModel.profile?.revision
        await viewModel.save()
        if viewModel.successMessage != nil, viewModel.profile?.revision != previousRevision {
            await onProfileUpdated()
        }
    }

    private func splitList(_ value: String) -> [String] {
        var seen = Set<String>()
        return value.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty && seen.insert($0.lowercased()).inserted }
    }

    private func decimal(_ value: String) -> Decimal? {
        Decimal(string: value.trimmingCharacters(in: .whitespacesAndNewlines), locale: Locale(identifier: "en_US_POSIX"))
    }

    private func decimalText(_ value: Decimal) -> String {
        NSDecimalNumber(decimal: value).stringValue
    }

    private var numericFieldsAreValid: Bool {
        invalidNumberMessage == nil
    }

    private var invalidNumberMessage: String? {
        guard let servings = decimal(servingsText), servings > 0, servings <= 10_000,
              hasAtMostScale(servings, places: 4) else {
            return "Servings must be greater than 0 and at most 10,000, with at most four decimal places."
        }
        if !cookMinutesText.isEmpty && (Int(cookMinutesText).map { $0 > 0 && $0 <= 1440 } != true) {
            return "Maximum cooking time must be a whole number from 1 to 1440."
        }
        if !budgetText.isEmpty {
            guard let budget = decimal(budgetText), budget >= 0, budget <= 1_000_000,
                  hasAtMostScale(budget, places: 2) else {
                return "Meal budget must be from 0 to 1,000,000 PHP with at most two decimal places."
            }
        }
        return nil
    }

    private func hasAtMostScale(_ value: Decimal, places: Int) -> Bool {
        var source = value
        var rounded = Decimal()
        NSDecimalRound(&rounded, &source, places, .plain)
        return rounded == value
    }
}
