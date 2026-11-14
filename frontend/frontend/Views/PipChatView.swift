import SwiftUI

public struct PipChatView: View {
    private struct Destination: Hashable, Identifiable {
        let recipeID: Int
        let opensShoppingPreview: Bool
        var id: String { "\(recipeID)-\(opensShoppingPreview)" }
    }

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @StateObject private var viewModel: PipChatViewModel
    @State private var selectedDestination: Destination?
    @FocusState private var composerFocused: Bool
    private let scope: HouseholdScope
    private let context: PipChatContext?
    private let chatService: any PipChatService
    private let recipeService: any CookWithPipService
    private let workflowService: any CookWithPipWorkflowService
    private let pendingStore: any PendingRecipeShoppingStore
    private let onShoppingConfirmed: () async -> Void
    private let onNavigateToShopping: () -> Void

    public init(
        scope: HouseholdScope,
        context: PipChatContext? = nil,
        chatService: any PipChatService = APIClient.shared,
        recipeService: any CookWithPipService = APIClient.shared,
        workflowService: any CookWithPipWorkflowService = APIClient.shared,
        pendingStore: any PendingRecipeShoppingStore = KeychainStore.shared,
        onShoppingConfirmed: @escaping () async -> Void = {},
        onNavigateToShopping: @escaping () -> Void = {}
    ) {
        self.scope = scope
        self.context = context
        self.chatService = chatService
        self.recipeService = recipeService
        self.workflowService = workflowService
        self.pendingStore = pendingStore
        self.onShoppingConfirmed = onShoppingConfirmed
        self.onNavigateToShopping = onNavigateToShopping
        _viewModel = StateObject(wrappedValue: PipChatViewModel(
            scope: scope, context: context, service: chatService
        ))
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                consentCard

                if viewModel.isLoadingConsent && !viewModel.hasLoadedConsent {
                    ProgressView("Loading privacy settings")
                        .tint(ProvisionTheme.provisionGreen)
                        .frame(maxWidth: .infinity)
                        .padding(24)
                        .accessibilityIdentifier("pip-chat-consent-loading")
                } else if let consent = viewModel.consent {
                    if !consent.chat_granted {
                        stateCard(
                            title: "Enable Pip Chat",
                            message: "Review the data notice above, then turn on chat sharing to continue.",
                            symbol: "lock.shield"
                        )
                        .accessibilityIdentifier("pip-chat-consent-required")
                    } else if !consent.all_active_members_chat_granted {
                        stateCard(
                            title: "Waiting for household consent",
                            message: "Every active household member needs to opt in before chat messages can be sent.",
                            symbol: "person.2"
                        )
                        .accessibilityIdentifier("pip-chat-household-consent-pending")
                    } else if !consent.provider_enabled {
                        stateCard(
                            title: "Pip Chat is unavailable",
                            message: "The chat service is not enabled right now. Your message has not been sent.",
                            symbol: "wifi.slash"
                        )
                        .accessibilityIdentifier("pip-chat-provider-disabled")
                    } else {
                        conversation
                    }
                } else if viewModel.hasLoadedConsent {
                    stateCard(
                        title: viewModel.isOffline ? "You're offline" : "Privacy settings unavailable",
                        message: viewModel.isOffline
                            ? "Reconnect to load household privacy settings. No chat message was sent."
                            : (viewModel.errorMessage ?? "Connect to Provision and try again."),
                        symbol: viewModel.isOffline ? "wifi.slash" : "exclamationmark.triangle"
                    )
                    Button("Try again") { Task { await viewModel.loadConsent() } }
                        .frame(minHeight: 44)
                        .accessibilityIdentifier("pip-chat-consent-retry")
                }

                if let error = viewModel.errorMessage, viewModel.consent != nil {
                    Label(
                        viewModel.isOffline ? "You're offline. Your unsent message remains in the composer." : error,
                        systemImage: viewModel.isOffline ? "wifi.slash" : "exclamationmark.triangle.fill"
                    )
                        .font(.footnote)
                        .foregroundStyle(ProvisionTheme.redAlert)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("pip-chat-error")
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 14)
            .padding(.bottom, 20)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if viewModel.isChatReady {
                composer
            }
        }
        .background(ProvisionTheme.background.ignoresSafeArea())
        .navigationTitle("Chat with Pip")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(ProvisionTheme.background, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbar {
            if !viewModel.messages.isEmpty {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Clear chat") { viewModel.clearConversation() }
                        .accessibilityIdentifier("pip-chat-clear")
                }
            }
        }
        .navigationDestination(item: $selectedDestination) { destination in
            if destination.opensShoppingPreview {
                shoppingPreview(for: destination.recipeID)
            } else {
                recipeDetail(for: destination.recipeID)
            }
        }
        .task {
            if !viewModel.hasLoadedConsent {
                await viewModel.loadConsent()
            }
        }
    }

    private var consentCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Your privacy controls", systemImage: "hand.raised.fill")
                .font(.headline)
                .foregroundStyle(ProvisionTheme.textPrimary)

            Toggle(isOn: Binding(
                get: { viewModel.consent?.chat_granted ?? false },
                set: { value in Task { await viewModel.setConsent(.chat, granted: value) } }
            )) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Allow Pip Chat")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                    Text("Shares your messages and limited relevant household context with DeepSeek.")
                        .font(.footnote)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .disabled(viewModel.isUpdatingConsent || viewModel.isLoadingConsent || viewModel.consent == nil)
            .accessibilityIdentifier("pip-chat-consent-chat")

            Toggle(isOn: Binding(
                get: { viewModel.consent?.allergy_sharing_granted ?? false },
                set: { value in Task { await viewModel.setConsent(.allergySharing, granted: value) } }
            )) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Share allergy labels separately")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                    Text("Only allergen labels are shared, and only after every active household member opts in.")
                        .font(.footnote)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .disabled(viewModel.isUpdatingConsent || viewModel.isLoadingConsent || viewModel.consent?.chat_granted != true)
            .accessibilityIdentifier("pip-chat-consent-allergies")

            if let consent = viewModel.consent {
                Text(consent.notice)
                    .font(.footnote)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("pip-chat-data-notice")
                if consent.allergy_sharing_granted && !consent.all_active_members_allergy_sharing_granted {
                    Text("Allergy labels stay out of chat until every active member separately opts in.")
                        .font(.footnote.weight(.medium))
                        .foregroundStyle(ProvisionTheme.amberWarning)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("pip-chat-allergy-consent-pending")
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard(backgroundColor: ProvisionTheme.surface)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("pip-chat-privacy-card")
    }

    private var conversation: some View {
        VStack(alignment: .leading, spacing: 12) {
            if viewModel.messages.isEmpty {
                stateCard(
                    title: "Ask Pip about cooking",
                    message: "Chat history stays on this screen and is not saved to your household account.",
                    symbol: "bubble.left.and.bubble.right"
                )
                .accessibilityIdentifier("pip-chat-empty-state")
            }

            ForEach(viewModel.messages) { message in
                messageBubble(message)
            }

            if viewModel.isSending {
                HStack(spacing: 10) {
                    ProgressView().tint(ProvisionTheme.provisionGreen)
                    Text("Pip is thinking")
                        .font(.subheadline)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityIdentifier("pip-chat-loading")
            }
        }
    }

    @ViewBuilder
    private func messageBubble(_ message: PipChatDisplayMessage) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(message.text)
                .font(.body)
                .foregroundStyle(ProvisionTheme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            ForEach(message.facts) { fact in
                VStack(alignment: .leading, spacing: 3) {
                    Text(fact.label)
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                    Text(fact.detail)
                        .font(.footnote)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(ProvisionTheme.surfaceSecondary, in: RoundedRectangle(cornerRadius: 10))
                .accessibilityIdentifier("pip-chat-fact-\(fact.reference)")
            }

            ForEach(message.recipeCards) { card in
                Button {
                    selectedDestination = Destination(recipeID: card.recipe_id, opensShoppingPreview: false)
                } label: {
                    recipeCardLabel(card)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("pip-chat-recipe-card-\(card.recipe_id)")
            }

            ForEach(message.actions) { action in
                if action.kind == "open_recipe" || action.kind == "open_shopping_preview" {
                    Button {
                        selectedDestination = Destination(
                            recipeID: action.recipe_id,
                            opensShoppingPreview: action.kind == "open_shopping_preview"
                        )
                    } label: {
                        Label(
                            action.kind == "open_shopping_preview"
                                ? "Review shopping for \(action.title)"
                                : "Open \(action.title)",
                            systemImage: action.kind == "open_shopping_preview" ? "cart" : "book.closed"
                        )
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                            .frame(minHeight: 44)
                    }
                    .accessibilityIdentifier(
                        "pip-chat-open-\(action.kind == "open_shopping_preview" ? "shopping-preview" : "recipe")-\(action.recipe_id)"
                    )
                    .buttonStyle(.plain)
                }
            }

            if let notice = message.safetyNotice {
                Text(notice)
                    .font(.caption)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(message.role == .assistant ? ProvisionTheme.surface : ProvisionTheme.provisionGreenLight)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(ProvisionTheme.border, lineWidth: 1))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(message.role == .assistant ? "pip-chat-message-assistant" : "pip-chat-message-user")
    }

    private func recipeDetail(for recipeID: Int) -> some View {
        RecipeDetailView(
            recipeID: recipeID,
            scope: scope,
            service: recipeService,
            chatService: chatService,
            workflowService: workflowService,
            pendingStore: pendingStore,
            onShoppingConfirmed: onShoppingConfirmed,
            onNavigateToShopping: onNavigateToShopping
        )
    }

    private func shoppingPreview(for recipeID: Int) -> some View {
        PipChatShoppingPreviewRoute(
            recipeID: recipeID,
            scope: scope,
            recipeService: recipeService,
            workflowService: workflowService,
            pendingStore: pendingStore,
            onShoppingConfirmed: onShoppingConfirmed,
            onNavigateToShopping: onNavigateToShopping
        )
    }

    private func recipeCardLabel(_ card: PipChatRecipeCard) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(card.title)
                        .font(.headline)
                        .foregroundStyle(ProvisionTheme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(card.cuisine)
                        .font(.caption)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                Spacer(minLength: 4)
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(ProvisionTheme.textTertiary)
                    .accessibilityHidden(true)
            }
            if let summary = card.summary {
                Text(summary)
                    .font(.subheadline)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Label(availabilityText(card), systemImage: availabilitySymbol(card.availability_status))
                .font(.footnote.weight(.medium))
                .foregroundStyle(ProvisionTheme.textSecondary)
            Label("Safety check: \(safetyText(card.safety_decision))", systemImage: "checkmark.shield")
                .font(.footnote.weight(.medium))
                .foregroundStyle(card.safety_decision == "blocked" ? ProvisionTheme.redAlert : ProvisionTheme.textSecondary)
            ForEach(Array(card.safety_reasons.enumerated()), id: \.offset) { item in
                Text(ReasonText.display(item.element))
                    .font(.caption)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(ProvisionTheme.surfaceSecondary, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(ProvisionTheme.border, lineWidth: 1))
        .contentShape(RoundedRectangle(cornerRadius: 12))
    }

    private func availabilityText(_ card: PipChatRecipeCard) -> String {
        switch card.availability_status {
        case "full": "Pantry has the required ingredients"
        case "partial": "Some ingredients are missing (\(card.missing_ingredient_count))"
        case "missing": "Missing ingredients: \(card.missing_ingredient_count)"
        default: "Ingredient availability needs review"
        }
    }

    private func availabilitySymbol(_ status: String) -> String {
        switch status {
        case "full": "checkmark.circle"
        case "partial": "minus.circle"
        case "missing": "cart"
        default: "questionmark.circle"
        }
    }

    private func safetyText(_ decision: String) -> String {
        switch decision {
        case "eligible": "eligible"
        case "blocked": "blocked"
        default: "review required"
        }
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Ask Pip…", text: $viewModel.draft, axis: .vertical)
                .lineLimit(dynamicTypeSize.isAccessibilitySize ? 1...6 : 1...4)
                .textInputAutocapitalization(.sentences)
                .autocorrectionDisabled(false)
                .submitLabel(.send)
                .focused($composerFocused)
                .onSubmit {
                    Task {
                        await viewModel.send()
                        composerFocused = false
                    }
                }
                .onChange(of: viewModel.draft) { _, value in
                    if value.count > 1200 {
                        viewModel.draft = String(value.prefix(1200))
                    }
                }
                .padding(.vertical, 10)
                .padding(.horizontal, 12)
                .background(ProvisionTheme.inputBackground)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(ProvisionTheme.border, lineWidth: 1))
                .accessibilityIdentifier("pip-chat-input")

            Button {
                Task {
                    await viewModel.send()
                    composerFocused = false
                }
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 30, weight: .semibold))
                    .foregroundStyle(viewModel.canSend ? ProvisionTheme.provisionGreen : ProvisionTheme.textTertiary)
                    .frame(minWidth: 44, minHeight: 44)
                    .contentShape(Rectangle())
            }
            .disabled(!viewModel.canSend)
            .accessibilityLabel("Send message")
            .accessibilityIdentifier("pip-chat-send")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(ProvisionTheme.background)
        .overlay(alignment: .top) { Rectangle().fill(ProvisionTheme.border).frame(height: 1) }
    }

    private func stateCard(title: String, message: String, symbol: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: symbol)
                .font(.headline)
                .foregroundStyle(ProvisionTheme.textPrimary)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(ProvisionTheme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard(backgroundColor: ProvisionTheme.surfaceSecondary)
    }
}

private struct PipChatShoppingPreviewRoute: View {
    let recipeID: Int
    let scope: HouseholdScope
    let recipeService: any CookWithPipService
    let workflowService: any CookWithPipWorkflowService
    let pendingStore: any PendingRecipeShoppingStore
    let onShoppingConfirmed: () async -> Void
    let onNavigateToShopping: () -> Void

    @State private var recipe: HouseholdRecipe?
    @State private var didFailToLoad = false

    var body: some View {
        Group {
            if let recipe {
                RecipeShoppingReviewView(
                    recipe: recipe,
                    scope: scope,
                    service: workflowService,
                    pendingStore: pendingStore,
                    onShoppingConfirmed: onShoppingConfirmed,
                    onNavigateToShopping: onNavigateToShopping
                )
            } else if didFailToLoad {
                VStack(alignment: .leading, spacing: 12) {
                    Label("Unable to load the selected recipe", systemImage: "exclamationmark.triangle.fill")
                        .font(.headline)
                        .foregroundStyle(ProvisionTheme.redAlert)
                    Text("Reconnect to Provision and try again. No shopping changes have been made.")
                        .font(.subheadline)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                    Button("Try again") { Task { await loadRecipe() } }
                        .frame(minHeight: 44)
                        .accessibilityIdentifier("pip-chat-shopping-preview-retry")
                }
                .padding(20)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            } else {
                ProgressView("Loading current recipe details")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .accessibilityIdentifier("pip-chat-shopping-preview-loading")
            }
        }
        .navigationTitle("Shopping Preview")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            guard recipe == nil, !didFailToLoad else { return }
            await loadRecipe()
        }
    }

    @MainActor
    private func loadRecipe() async {
        didFailToLoad = false
        do {
            recipe = try await recipeService.fetchRecipe(id: recipeID, scope: scope)
        } catch {
            didFailToLoad = true
        }
    }
}

#if DEBUG
#Preview("Chat with Pip") {
    NavigationStack {
        PipChatView(scope: HouseholdScope(userID: 1, householdID: 1))
    }
}
#endif
