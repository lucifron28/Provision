import SwiftUI

public struct PipChatView: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @StateObject private var viewModel: PipChatViewModel
    @FocusState private var composerFocused: Bool
    private let scope: HouseholdScope
    private let chatService: any PipChatService
    private let recipeService: any CookWithPipService
    private let workflowService: any CookWithPipWorkflowService
    private let pendingStore: any PendingRecipeShoppingStore
    private let onShoppingConfirmed: () async -> Void
    private let onNavigateToShopping: () -> Void

    public init(
        scope: HouseholdScope,
        chatService: any PipChatService = APIClient.shared,
        recipeService: any CookWithPipService = APIClient.shared,
        workflowService: any CookWithPipWorkflowService = APIClient.shared,
        pendingStore: any PendingRecipeShoppingStore = KeychainStore.shared,
        onShoppingConfirmed: @escaping () async -> Void = {},
        onNavigateToShopping: @escaping () -> Void = {}
    ) {
        self.scope = scope
        self.chatService = chatService
        self.recipeService = recipeService
        self.workflowService = workflowService
        self.pendingStore = pendingStore
        self.onShoppingConfirmed = onShoppingConfirmed
        self.onNavigateToShopping = onNavigateToShopping
        _viewModel = StateObject(wrappedValue: PipChatViewModel(scope: scope, service: chatService))
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
            }

            ForEach(message.actions) { action in
                if action.kind == "open_recipe" {
                    NavigationLink {
                        RecipeDetailView(
                            recipeID: action.recipe_id,
                            scope: scope,
                            service: recipeService,
                            workflowService: workflowService,
                            pendingStore: pendingStore,
                            onShoppingConfirmed: onShoppingConfirmed,
                            onNavigateToShopping: onNavigateToShopping
                        )
                    } label: {
                        Label("Open \(action.title)", systemImage: "book.closed")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                            .frame(minHeight: 44)
                    }
                    .accessibilityIdentifier("pip-chat-open-recipe-\(action.recipe_id)")
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

#if DEBUG
#Preview("Chat with Pip") {
    NavigationStack {
        PipChatView(scope: HouseholdScope(userID: 1, householdID: 1))
    }
}
#endif
