import SwiftUI

public struct CookWithPipPreferencesView: View {
    private enum InputField: Hashable {
        case cuisines
        case regions
        case dislikes
        case equipment
        case servings
        case cookMinutes
        case budget
        case customAllergies
    }

    @StateObject private var viewModel: CookWithPipPreferencesViewModel
    private let onProfileUpdated: () async -> Void
    @State private var servingsText = "2"
    @State private var cookMinutesText = ""
    @State private var budgetText = ""
    @State private var customAllergyText = ""
    @State private var cuisineDraft = ""
    @State private var regionDraft = ""
    @State private var equipmentDraft = ""
    @FocusState private var focusedField: InputField?

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
                preferenceChoices(
                    title: "Preferred cuisines",
                    suggestions: cuisineSuggestions,
                    keyPath: \.preferred_cuisines,
                    identifierPrefix: "pip-cuisine",
                    inputIdentifier: "pip-preferred-cuisines",
                    inputLabel: "Add a cuisine",
                    focus: .cuisines,
                    draft: $cuisineDraft
                )
                preferenceChoices(
                    title: "Filipino regions",
                    suggestions: regionSuggestions,
                    keyPath: \.preferred_regions,
                    identifierPrefix: "pip-region",
                    inputIdentifier: "pip-preferred-regions",
                    inputLabel: "Add a region or style",
                    focus: .regions,
                    draft: $regionDraft
                )
                labeledField("Dislikes") {
                    TextField("Comma-separated", text: listBinding(\.dislikes),
                              prompt: Text("Comma-separated").foregroundStyle(ProvisionTheme.textSecondary))
                        .focused($focusedField, equals: .dislikes)
                        .accessibilityLabel("Dislikes")
                        .accessibilityIdentifier("pip-dislikes")
                }
                preferenceChoices(
                    title: "Kitchen equipment",
                    suggestions: equipmentSuggestions,
                    keyPath: \.equipment,
                    identifierPrefix: "pip-equipment",
                    inputIdentifier: "pip-equipment",
                    inputLabel: "Add equipment",
                    focus: .equipment,
                    draft: $equipmentDraft
                )
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
                labeledField("Servings per meal (people)") {
                    TextField("People", text: $servingsText,
                              prompt: Text("People").foregroundStyle(ProvisionTheme.textSecondary))
                        .keyboardType(.decimalPad)
                        .focused($focusedField, equals: .servings)
                        .accessibilityLabel("Servings per meal (people)")
                        .accessibilityIdentifier("pip-preferred-servings")
                        .onChange(of: servingsText) { _, value in
                            if let amount = decimal(value), amount > 0 { viewModel.preferences.servings = amount }
                        }
                }
                labeledField("Maximum cooking time (minutes)") {
                    TextField("Minutes", text: $cookMinutesText,
                              prompt: Text("Minutes").foregroundStyle(ProvisionTheme.textSecondary))
                        .keyboardType(.numberPad)
                        .focused($focusedField, equals: .cookMinutes)
                        .accessibilityLabel("Maximum cooking time (minutes)")
                        .accessibilityIdentifier("pip-max-cook-minutes")
                        .onChange(of: cookMinutesText) { _, value in
                            viewModel.preferences.max_cook_minutes = Int(value)
                        }
                }
                labeledField("Meal budget per person (PHP)") {
                    TextField("PHP", text: $budgetText,
                              prompt: Text("PHP").foregroundStyle(ProvisionTheme.textSecondary))
                        .keyboardType(.decimalPad)
                        .focused($focusedField, equals: .budget)
                        .accessibilityLabel("Meal budget per person (PHP)")
                        .accessibilityIdentifier("pip-meal-budget")
                        .onChange(of: budgetText) { _, value in
                            viewModel.preferences.meal_budget_php = value.isEmpty ? nil : decimal(value)
                        }
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
                    VStack(alignment: .leading, spacing: 12) {
                        Toggle(code.title, isOn: allergyBinding(code))
                            .accessibilityIdentifier("pip-allergen-\(code.rawValue)")
                        if hasAllergy(code) {
                            severityMenu(
                                title: "\(code.title) severity",
                                selection: allergySeverityBinding(code),
                                identifier: "pip-allergen-severity-\(code.rawValue)"
                            )
                            Toggle("Cross-contact concern", isOn: allergyCrossContactBinding(code))
                                .accessibilityLabel("Cross-contact concern for \(code.title)")
                                .accessibilityIdentifier("pip-allergen-cross-contact-\(code.rawValue)")
                        }
                    }
                }
                labeledField("Custom allergies") {
                    TextField("Comma-separated", text: $customAllergyText,
                              prompt: Text("Comma-separated").foregroundStyle(ProvisionTheme.textSecondary))
                        .focused($focusedField, equals: .customAllergies)
                        .accessibilityLabel("Custom allergies")
                        .accessibilityIdentifier("pip-custom-allergies")
                        .onChange(of: customAllergyText) { _, value in updateCustomAllergies(value) }
                }
                ForEach(viewModel.allergies.compactMap(\.custom_text), id: \.self) { custom in
                    VStack(alignment: .leading, spacing: 12) {
                        severityMenu(
                            title: "\(custom) severity",
                            selection: customSeverityBinding(custom),
                            identifier: "pip-custom-allergen-severity"
                        )
                        Toggle("Cross-contact concern", isOn: customCrossContactBinding(custom))
                            .accessibilityLabel("Cross-contact concern for \(custom)")
                            .accessibilityIdentifier("pip-custom-allergen-cross-contact")
                    }
                }
            } header: {
                Text("Allergies")
                    .accessibilityElement(children: .ignore)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier("pip-preferences-allergies-heading")
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
        .accessibilityIdentifier("pip-preferences-form")
        .background(ProvisionTheme.background)
        .navigationTitle("My Cooking Preferences")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(ProvisionTheme.background, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .scrollDismissesKeyboard(.interactively)
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
            ToolbarItemGroup(placement: .keyboard) {
                if focusedField != nil {
                    Spacer()
                    Button("Done") { focusedField = nil }
                        .accessibilityIdentifier("pip-preferences-keyboard-done")
                }
            }
        }
        .task { await reload() }
        .refreshable { await reload() }
    }

    private func labeledField<Field: View>(
        _ title: String,
        @ViewBuilder field: () -> Field
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(ProvisionTheme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            field()
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 4)
    }

    private var dietPatterns: [(value: String, title: String)] {
        [("vegetarian", "Vegetarian"), ("vegan", "Vegan"), ("pescatarian", "Pescatarian"),
         ("halal", "Halal"), ("no_pork", "No pork"), ("gluten_free", "Gluten-free"),
         ("dairy_free", "Dairy-free")]
    }

    private var cuisineSuggestions: [String] {
        ["Filipino", "Ilocano", "Kapampangan", "Bicolano", "Visayan", "Japanese", "Korean",
         "Chinese", "Thai", "Vietnamese", "Italian", "Mexican"]
    }

    private var regionSuggestions: [String] {
        ["Ilocos", "Cordillera", "Central Luzon", "Bicol", "Visayas", "Mindanao", "Tagalog"]
    }

    private var equipmentSuggestions: [String] {
        ["Stovetop", "Rice cooker", "Oven", "Microwave", "Air fryer", "Pressure cooker",
         "Blender", "Grill"]
    }

    private func preferenceChoices(
        title: String,
        suggestions: [String],
        keyPath: WritableKeyPath<FoodPreferences, [String]>,
        identifierPrefix: String,
        inputIdentifier: String,
        inputLabel: String,
        focus: InputField,
        draft: Binding<String>
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(ProvisionTheme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 96), spacing: 8)],
                      alignment: .leading, spacing: 8) {
                ForEach(choiceValues(suggestions, keyPath: keyPath), id: \.self) { value in
                    let selected = viewModel.preferences[keyPath: keyPath].contains {
                        $0.caseInsensitiveCompare(value) == .orderedSame
                    }
                    Button {
                        toggleChoice(value, keyPath: keyPath)
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                            Text(value)
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(selected ? ProvisionTheme.provisionGreen : ProvisionTheme.textPrimary)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .padding(.horizontal, 10)
                        .background(selected ? ProvisionTheme.provisionGreenLight : ProvisionTheme.surfaceSecondary)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(value)
                    .accessibilityValue(selected ? "Selected" : "Not selected")
                    .accessibilityIdentifier("\(identifierPrefix)-\(accessibilitySlug(value))")
                }
            }
            HStack(spacing: 8) {
                TextField(inputLabel, text: draft,
                          prompt: Text(inputLabel).foregroundStyle(ProvisionTheme.textSecondary))
                    .focused($focusedField, equals: focus)
                    .accessibilityLabel(inputLabel)
                    .accessibilityIdentifier(inputIdentifier)
                    .onSubmit { addCustomChoice(draft, keyPath: keyPath) }
                Button("Add") { addCustomChoice(draft, keyPath: keyPath) }
                    .disabled(draft.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .accessibilityIdentifier("\(identifierPrefix)-add-custom")
            }
            .padding(.vertical, 4)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 4)
    }

    private func choiceValues(_ suggestions: [String], keyPath: WritableKeyPath<FoodPreferences, [String]>) -> [String] {
        var values = suggestions
        for custom in viewModel.preferences[keyPath: keyPath]
        where !values.contains(where: { $0.caseInsensitiveCompare(custom) == .orderedSame }) {
            values.append(custom)
        }
        return values
    }

    private func toggleChoice(_ value: String, keyPath: WritableKeyPath<FoodPreferences, [String]>) {
        var preferences = viewModel.preferences
        if let index = preferences[keyPath: keyPath].firstIndex(where: {
            $0.caseInsensitiveCompare(value) == .orderedSame
        }) {
            preferences[keyPath: keyPath].remove(at: index)
        } else {
            preferences[keyPath: keyPath].append(value)
        }
        viewModel.preferences = preferences
    }

    private func addCustomChoice(_ draft: Binding<String>, keyPath: WritableKeyPath<FoodPreferences, [String]>) {
        let value = draft.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return }
        var preferences = viewModel.preferences
        if !preferences[keyPath: keyPath].contains(where: { $0.caseInsensitiveCompare(value) == .orderedSame }) {
            preferences[keyPath: keyPath].append(value)
            viewModel.preferences = preferences
        }
        draft.wrappedValue = ""
    }

    private func accessibilitySlug(_ value: String) -> String {
        value.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber }).joined(separator: "-")
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

    private func severityMenu(title: String, selection: Binding<String>, identifier: String) -> some View {
        Picker(title, selection: selection) {
            ForEach(severityOptions, id: \.value) { option in
                Text(option.title).tag(option.value)
            }
        }
        .pickerStyle(.menu)
        .accessibilityLabel(title)
        .accessibilityValue(severityTitle(selection.wrappedValue))
        .accessibilityIdentifier(identifier)
    }

    private var severityOptions: [(title: String, value: String)] {
        [("Not specified", ""), ("Mild", "mild"), ("Moderate", "moderate"), ("Severe", "severe")]
    }

    private func severityTitle(_ value: String) -> String {
        severityOptions.first(where: { $0.value == value })?.title ?? "Not specified"
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
        if viewModel.successMessage != nil {
            focusedField = nil
            if viewModel.profile?.revision != previousRevision {
                await onProfileUpdated()
            }
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
