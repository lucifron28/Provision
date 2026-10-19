import SwiftUI

public struct HomeView: View {
    @ObservedObject var viewModel: HomeViewModel
    @ObservedObject var authVM: AuthViewModel
    var onNavigateToInventory: (InventoryQuickFilter?) -> Void
    var onNavigateToShopping: () -> Void

    @State private var showingProfileSheet: Bool = false
    @State private var notificationsEnabled: Bool = NotificationService.shared.isAlertsEnabled
    @State private var devBackendHost: String = APIEnvironment.localDeviceHost
    @State private var hostUpdateMessage: String? = nil
    @State private var itemToConsume: ExpiringSoonItem? = nil

    public init(
        viewModel: HomeViewModel,
        authVM: AuthViewModel,
        onNavigateToInventory: @escaping (InventoryQuickFilter?) -> Void = { _ in },
        onNavigateToShopping: @escaping () -> Void = {}
    ) {
        self.viewModel = viewModel
        self.authVM = authVM
        self.onNavigateToInventory = onNavigateToInventory
        self.onNavigateToShopping = onNavigateToShopping
    }

    public init(
        viewModel: HomeViewModel,
        authVM: AuthViewModel,
        onNavigateToInventory: @escaping () -> Void,
        onNavigateToShopping: @escaping () -> Void = {}
    ) {
        self.init(
            viewModel: viewModel,
            authVM: authVM,
            onNavigateToInventory: { _ in onNavigateToInventory() },
            onNavigateToShopping: onNavigateToShopping
        )
    }

    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Header Bar
                    headerBar
                    if viewModel.isLoading && !viewModel.hasLoadedOnce {
                        VStack(spacing: 12) {
                            ProgressView()
                                .tint(ProvisionTheme.provisionGreen)
                            Text("Loading household pantry...")
                                .font(.system(size: 13, weight: .medium))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(40)
                    } else if let err = viewModel.errorMessage, !viewModel.hasLoadedOnce {
                        VStack(spacing: 12) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .font(.system(size: 32))
                                .foregroundStyle(ProvisionTheme.redAlert)
                            Text("Unable to load pantry data")
                                .font(.system(size: 16, weight: .bold))
                                .foregroundStyle(ProvisionTheme.textPrimary)
                            Text(err)
                                .font(.system(size: 12))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                                .multilineTextAlignment(.center)
                            Button("Try Again") {
                                Task { await viewModel.loadDashboard() }
                            }
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                            .padding(.top, 4)
                        }
                        .padding(24)
                        .frame(maxWidth: .infinity)
                        .provisionCard()
                    } else {
                        // Pantry Health Hero Card
                        pantryHealthCard

                        // Pip Contextual Card
                        pipContextualCard

                        if viewModel.isPantryEmpty {
                            emptyPantryActionCard
                        } else {
                            // Chef Pip Kitchen Corner ("Use It First")
                            if viewModel.chefPipDateSafetyNotice != nil || !viewModel.approachingExpirationItems.isEmpty {
                                chefPipKitchenCorner
                            }

                            // Expiring Soon Section (Top 3)
                            if !viewModel.expiringSoonItems.isEmpty {
                                expiringSoonSection
                            }

                            // Restock Needed Section (Top 3)
                            if !viewModel.lowStockItems.isEmpty {
                                restockNeededSection
                            }
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 24)
            }
            .background(ProvisionTheme.background.ignoresSafeArea())
            .refreshable {
                await viewModel.loadDashboard()
            }
            .task {
                await viewModel.loadDashboard()
                if NotificationService.shared.isAlertsEnabled {
                    await NotificationService.shared.syncExpirationAlerts(expiringSoon: viewModel.expiringSoonItems)
                }
            }
            .overlay(alignment: .bottom) {
                if let msg = viewModel.alertMessage {
                    toastView(message: msg, isError: false)
                } else if let err = viewModel.errorMessage {
                    toastView(message: err, isError: true)
                }
            }
            .sheet(isPresented: $showingProfileSheet) {
                profileSheet
            }
            .alert("Log Consumption", isPresented: Binding(
                get: { itemToConsume != nil },
                set: { if !$0 { itemToConsume = nil } }
            )) {
                if let item = itemToConsume {
                    Button("Consume 1 \(item.unit ?? "unit")") {
                        let target = item
                        itemToConsume = nil
                        Task {
                            await viewModel.quickConsumeExpiringItem(target)
                            HapticFeedback.success()
                        }
                    }
                    Button("Cancel", role: .cancel) {
                        itemToConsume = nil
                    }
                }
            } message: {
                if let item = itemToConsume {
                    Text("Are you sure you want to log 1 \(item.unit ?? "unit") of \(item.product_name) as consumed?")
                }
            }
        }
    }

    // MARK: - Subviews

    private var headerBar: some View {
        HStack(spacing: 12) {
            // User Avatar
            ZStack {
                Circle()
                    .fill(ProvisionTheme.provisionGreenLight)
                    .frame(width: 44, height: 44)
                Image(systemName: "person.crop.circle.fill")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 38, height: 38)
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(timeGreeting)
                    .font(.system(size: 13, weight: .regular))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                Text(authVM.currentUser?.displayNameOrEmail ?? "Provision")
                    .font(.system(size: 22, weight: .bold, design: .serif))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }

            Spacer()

            Button {
                showingProfileSheet = true
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 18, weight: .medium))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .padding(10)
                    .background(ProvisionTheme.surface)
                    .clipShape(Circle())
                    .overlay(Circle().stroke(ProvisionTheme.border, lineWidth: 1))
                    .accessibleTouchTarget()
            }
            .accessibilityLabel("Settings and Account")
        }
        .padding(.top, 8)
    }

    private var pantryHealthCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Pantry Health")
                    .font(.system(size: 17, weight: .semibold, design: .serif))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                Spacer()
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 16))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("TOTAL VALUE")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .tracking(0.8)

                Text("₱\(formatCurrency(viewModel.valuation.total_value))")
                    .font(.system(size: 32, weight: .bold, design: .serif))
                    .foregroundStyle(ProvisionTheme.textPrimary)
            }

            Divider()
                .background(ProvisionTheme.border.opacity(0.8))

            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Recorded Spend")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(ProvisionTheme.textSecondary)

                    Text("₱\(formatCurrency(viewModel.spending.total_spent))")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                }

                Spacer()

                HStack(spacing: 4) {
                    Image(systemName: viewModel.pantryStatus.icon)
                        .font(.system(size: 10, weight: .bold))
                    Text(viewModel.pantryStatus.title)
                        .font(.system(size: 12, weight: .semibold))
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(viewModel.pantryStatus.color)
                .foregroundStyle(ProvisionTheme.onAccent)
                .clipShape(Capsule())
            }
        }
        .padding(18)
        .background(ProvisionTheme.heroCard)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(ProvisionTheme.border.opacity(0.6), lineWidth: 1)
        )
    }

    private var emptyPantryActionCard: some View {
        VStack(spacing: 12) {
            Image("pip_in_context")
                .resizable()
                .scaledToFit()
                .frame(maxHeight: 140)
                .clipShape(RoundedRectangle(cornerRadius: 12))

            Text("Your Pantry is Ready to Fill")
                .font(.system(size: 16, weight: .bold, design: .serif))
                .foregroundStyle(ProvisionTheme.textPrimary)

            Text("Start tracking freshness by scanning grocery receipt barcodes or adding pantry staples.")
                .font(.system(size: 13))
                .foregroundStyle(ProvisionTheme.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 16)
        }
        .padding(20)
        .frame(maxWidth: .infinity)
        .provisionCard()
    }

    private var pipContextualCard: some View {
        HStack(spacing: 14) {
            Image(viewModel.pipMascotAssetName)
                .resizable()
                .scaledToFit()
                .frame(width: 58, height: 58)
                .background(
                    Circle()
                        .fill(viewModel.pantryStatus.color.opacity(0.12))
                        .frame(width: 64, height: 64)
                )

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text("PIP'S PANTRY INSIGHT")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                        .tracking(0.6)

                    Spacer()

                    Text(viewModel.pipGuidanceTitle)
                        .font(.system(size: 10, weight: .bold))
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(viewModel.pantryStatus.color.opacity(0.15))
                        .foregroundStyle(viewModel.pantryStatus.color)
                        .clipShape(Capsule())
                }

                Text(viewModel.pipGuidanceMessage)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                if !viewModel.expiringSoonItems.isEmpty {
                    Button {
                        onNavigateToInventory(.expiringSoon)
                    } label: {
                        HStack(spacing: 4) {
                            Text("Review Expiring Items")
                                .font(.system(size: 12, weight: .semibold))
                            Image(systemName: "chevron.right")
                                .font(.system(size: 10, weight: .bold))
                        }
                        .foregroundStyle(ProvisionTheme.amberWarning)
                        .padding(.top, 2)
                    }
                } else if !viewModel.lowStockItems.isEmpty {
                    Button {
                        onNavigateToInventory(.lowStock)
                    } label: {
                        HStack(spacing: 4) {
                            Text("Check Low Stock")
                                .font(.system(size: 12, weight: .semibold))
                            Image(systemName: "chevron.right")
                                .font(.system(size: 10, weight: .bold))
                        }
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                        .padding(.top, 2)
                    }
                }
            }
        }
        .padding(14)
        .provisionCard(
            backgroundColor: ProvisionTheme.surface,
            cornerRadius: 16,
            borderColor: ProvisionTheme.border.opacity(0.7)
        )
    }

    private var chefPipKitchenCorner: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Image(viewModel.expiredItems.isEmpty ? "pip_cooking" : "pip_chef")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 48, height: 48)
                    .background(
                        Circle()
                            .fill(viewModel.expiredItems.isEmpty ? ProvisionTheme.provisionGreenLight : ProvisionTheme.amberLight)
                            .frame(width: 54, height: 54)
                    )

                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text("Chef Pip's Kitchen Corner")
                            .font(.system(size: 16, weight: .bold, design: .serif))
                            .foregroundStyle(ProvisionTheme.textPrimary)
                        Spacer()
                        HStack(spacing: 3) {
                            Image(systemName: viewModel.expiredItems.isEmpty ? "sparkles" : "exclamationmark.shield")
                                .font(.system(size: 10, weight: .bold))
                            Text(viewModel.expiredItems.isEmpty ? "Use It First" : "Date Check")
                                .font(.system(size: 10, weight: .heavy))
                        }
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(viewModel.expiredItems.isEmpty ? ProvisionTheme.amberLight : ProvisionTheme.redLight)
                        .foregroundStyle(viewModel.expiredItems.isEmpty ? ProvisionTheme.amberWarning : ProvisionTheme.redAlert)
                        .clipShape(Capsule())
                    }

                    Text(viewModel.expiredItems.isEmpty ? "Smart, zero-waste ideas for ingredients on hand" : "Safe kitchen guidance before cooking or meal prep")
                        .font(.system(size: 11))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
            }

            Divider()
                .background(ProvisionTheme.border.opacity(0.6))

            if let dateSafety = viewModel.chefPipDateSafetyNotice {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "exclamationmark.shield.fill")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.redAlert)
                        .padding(.top, 2)

                    Text(dateSafety)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(10)
                .background(ProvisionTheme.redLight.opacity(0.8))
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }

            if !viewModel.chefPipRecipeIdeas.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(viewModel.chefPipRecipeIdeas, id: \.self) { idea in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "fork.knife")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(ProvisionTheme.provisionGreen)
                                .padding(.top, 2)

                            Text(idea)
                                .font(.system(size: 13, weight: .regular))
                                .foregroundStyle(ProvisionTheme.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
        }
        .padding(16)
        .provisionCard(
            backgroundColor: ProvisionTheme.surfaceSecondary.opacity(0.6),
            cornerRadius: 16,
            borderColor: ProvisionTheme.border.opacity(0.8)
        )
    }

    private var timeGreeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        if hour >= 5 && hour < 12 {
            return "Good Morning,"
        } else if hour >= 12 && hour < 17 {
            return "Good Afternoon,"
        } else {
            return "Good Evening,"
        }
    }

    private var expiringSoonSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Expiring Soon")
                    .font(.system(size: 18, weight: .bold, design: .serif))
                    .foregroundStyle(ProvisionTheme.textPrimary)

                Spacer()

                Button("View All") {
                    onNavigateToInventory(.expiringSoon)
                }
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(ProvisionTheme.textSecondary)
            }

            if viewModel.expiringSoonItems.isEmpty {
                HStack(spacing: 12) {
                    ZStack {
                        Circle()
                            .fill(ProvisionTheme.provisionGreenLight)
                            .frame(width: 36, height: 36)
                        Image(systemName: "checkmark.seal.fill")
                            .font(.system(size: 16))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text("No Items Expiring Soon")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(ProvisionTheme.textPrimary)
                        Text("All inventory batches are within safe shelf life.")
                            .font(.system(size: 12))
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }
                    Spacer()
                }
                .padding(14)
                .provisionCard()
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(Array(viewModel.expiringSoonItems.prefix(3))) { item in
                            expiringItemCard(item: item)
                        }
                    }
                    .padding(.vertical, 2)
                }
            }
        }
    }

    private func expiringItemCard(item: ExpiringSoonItem) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                ZStack {
                    Circle()
                        .fill(item.days_until_expiration <= 1 ? ProvisionTheme.redLight : ProvisionTheme.amberLight)
                        .frame(width: 36, height: 36)
                    Image(systemName: item.days_until_expiration <= 1 ? "exclamationmark.triangle.fill" : "hourglass")
                        .font(.system(size: 15))
                        .foregroundStyle(item.days_until_expiration <= 1 ? ProvisionTheme.redAlert : ProvisionTheme.amberWarning)
                }

                Spacer()

                Text(item.urgencyBadgeText)
                    .font(.system(size: 10, weight: .bold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(item.days_until_expiration <= 1 ? ProvisionTheme.redLight : ProvisionTheme.amberLight)
                    .foregroundStyle(item.days_until_expiration <= 1 ? ProvisionTheme.redAlert : ProvisionTheme.amberWarning)
                    .clipShape(Capsule())
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(item.product_name)
                    .font(.system(size: 16, weight: .bold, design: .serif))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .lineLimit(1)

                Text(item.displayQuantity)
                    .font(.system(size: 12, weight: .regular))
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }

            Button {
                itemToConsume = item
            } label: {
                HStack {
                    Image(systemName: "checkmark")
                        .font(.system(size: 11, weight: .bold))
                    Text("Consume")
                        .font(.system(size: 12, weight: .semibold))
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 6)
                .background(ProvisionTheme.provisionGreenLight)
                .foregroundStyle(ProvisionTheme.provisionGreen)
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
        }
        .padding(14)
        .frame(width: 160)
        .provisionCard()
    }


    private var restockNeededSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Restock Needed")
                    .font(.system(size: 18, weight: .bold, design: .serif))
                    .foregroundStyle(ProvisionTheme.textPrimary)

                Spacer()

                if !viewModel.lowStockItems.isEmpty {
                    Button("View All") {
                        onNavigateToInventory(.lowStock)
                    }
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                }
            }

            if viewModel.lowStockItems.isEmpty {
                HStack(spacing: 12) {
                    ZStack {
                        Circle()
                            .fill(ProvisionTheme.provisionGreenLight)
                            .frame(width: 40, height: 40)
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Pantry Well Stocked")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(ProvisionTheme.textPrimary)
                        Text("No items are currently below low-stock threshold.")
                            .font(.system(size: 13))
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }
                    Spacer()
                }
                .padding(12)
                .provisionCard()
            } else {
                VStack(spacing: 10) {
                    ForEach(Array(viewModel.lowStockItems.prefix(3))) { item in
                        HStack(spacing: 12) {
                            ZStack {
                                Circle()
                                    .fill(ProvisionTheme.amberLight)
                                    .frame(width: 40, height: 40)
                                Image(systemName: "exclamationmark.circle.fill")
                                    .foregroundStyle(ProvisionTheme.amberWarning)
                            }

                            VStack(alignment: .leading, spacing: 2) {
                                Text(item.product_name)
                                    .font(.system(size: 15, weight: .semibold))
                                    .foregroundStyle(ProvisionTheme.textPrimary)
                                Text(item.displayStock)
                                    .font(.system(size: 13, weight: .medium))
                                    .foregroundStyle(ProvisionTheme.redAlert)
                            }

                            Spacer()

                            Button {
                                Task {
                                    await viewModel.addLowStockToShoppingList(item)
                                }
                            } label: {
                                Image(systemName: "cart.badge.plus")
                                    .font(.system(size: 16, weight: .semibold))
                                    .foregroundStyle(ProvisionTheme.provisionGreen)
                                    .padding(8)
                                    .background(ProvisionTheme.provisionGreenLight)
                                    .clipShape(Circle())
                            }
                        }
                        .padding(12)
                        .provisionCard()
                    }
                }
            }
        }
    }


    private var profileSheet: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Account Section
                    VStack(spacing: 12) {
                        ZStack {
                            Circle()
                                .fill(ProvisionTheme.provisionGreenLight)
                                .frame(width: 72, height: 72)
                            Image(systemName: "person.crop.circle.fill")
                                .resizable()
                                .scaledToFit()
                                .frame(width: 64, height: 64)
                                .foregroundStyle(ProvisionTheme.provisionGreen)
                        }

                        VStack(spacing: 4) {
                            Text(authVM.currentUser?.displayNameOrEmail ?? "Household Member")
                                .font(.system(size: 20, weight: .bold, design: .serif))
                                .foregroundStyle(ProvisionTheme.textPrimary)

                            Text(authVM.currentUser?.email ?? "user@provision.local")
                                .font(.system(size: 14))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                        }
                    }
                    .padding(.top, 16)

                    VStack(alignment: .leading, spacing: 10) {
                        Text("ACCOUNT")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(ProvisionTheme.textSecondary)
                            .tracking(0.6)

                        HStack {
                            Text("Pantry Access")
                                .font(.system(size: 15))
                                .foregroundStyle(ProvisionTheme.textPrimary)
                            Spacer()
                            Text("Shared Household")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(ProvisionTheme.provisionGreen)
                        }
                        .padding(14)
                        .provisionCard()
                    }

                    // Preferences Section
                    VStack(alignment: .leading, spacing: 10) {
                        Text("PREFERENCES & NOTIFICATIONS")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(ProvisionTheme.textSecondary)
                            .tracking(0.6)

                        Toggle(isOn: $notificationsEnabled) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Expiration Reminders")
                                    .font(.system(size: 15, weight: .medium))
                                    .foregroundStyle(ProvisionTheme.textPrimary)
                                Text("Daily 8:00 AM alert for items expiring in ≤ 2 days")
                                    .font(.system(size: 11))
                                    .foregroundStyle(ProvisionTheme.textSecondary)
                            }
                        }
                        .tint(ProvisionTheme.provisionGreen)
                        .onChange(of: notificationsEnabled) { _, newValue in
                            NotificationService.shared.isAlertsEnabled = newValue
                            if newValue {
                                Task {
                                    let granted = await NotificationService.shared.requestAuthorization()
                                    if granted {
                                        await NotificationService.shared.syncExpirationAlerts(expiringSoon: viewModel.expiringSoonItems)
                                    }
                                }
                            } else {
                                NotificationService.shared.cancelAllExpirationAlerts()
                            }
                        }
                        .padding(14)
                        .provisionCard()
                    }

                    // Development Server Host Section
                    VStack(alignment: .leading, spacing: 10) {
                        Text("DEVELOPMENT SERVER HOST")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(ProvisionTheme.textSecondary)
                            .tracking(0.6)

                        HStack {
                            Image(systemName: "network")
                                .foregroundStyle(ProvisionTheme.provisionGreen)
                            TextField("IP Address (e.g. 10.212.56.11)", text: $devBackendHost)
                                .font(.system(size: 14, design: .monospaced))
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .foregroundStyle(ProvisionTheme.textPrimary)
                            Button("Save") {
                                let trimmed = devBackendHost.trimmingCharacters(in: .whitespacesAndNewlines)
                                if let validURL = APIEnvironment.validateHost(trimmed) {
                                    APIEnvironment.localDeviceHost = trimmed
                                    Task {
                                        await APIClient.shared.setBaseURL(validURL)
                                    }
                                    hostUpdateMessage = "Host updated to \(trimmed)"
                                } else {
                                    hostUpdateMessage = "Invalid host format. Enter a valid IP or hostname."
                                }
                            }
                            .font(.system(size: 13, weight: .bold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                        }
                        .padding(14)
                        .provisionCard()

                        if let msg = hostUpdateMessage {
                            Text(msg)
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(msg.starts(with: "Host updated") ? ProvisionTheme.provisionGreen : ProvisionTheme.redAlert)
                                .padding(.leading, 4)
                        }
                    }

                    // Sign Out Section
                    Button(role: .destructive) {
                        showingProfileSheet = false
                        Task {
                            await authVM.logout()
                        }
                    } label: {
                        HStack {
                            Image(systemName: "rectangle.portrait.and.arrow.right")
                            Text("Log Out")
                                .font(.system(size: 16, weight: .semibold))
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(ProvisionTheme.redLight)
                        .foregroundStyle(ProvisionTheme.redAlert)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .padding(.top, 8)
                    .padding(.bottom, 16)
                }
                .padding(.horizontal, 20)
            }
            .background(ProvisionTheme.background.ignoresSafeArea())
            .navigationTitle("Settings & Account")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { showingProfileSheet = false }
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                }
            }
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }

    private func toastView(message: String, isError: Bool) -> some View {
        Text(message)
            .font(.system(size: 13, weight: .medium))
            .foregroundStyle(isError ? .white : ProvisionTheme.textPrimary)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(isError ? ProvisionTheme.redAlert : ProvisionTheme.surface)
            .clipShape(Capsule())
            .shadow(color: .black.opacity(0.12), radius: 8, y: 4)
            .padding(.bottom, 16)
            .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    private func formatCurrency(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 0
        return formatter.string(from: NSNumber(value: value)) ?? "\(Int(value))"
    }
}

#Preview("Home - Philippine Pantry") {
    HomeView(
        viewModel: PreviewData.makeHomeViewModel(),
        authVM: PreviewData.makeAuthViewModel()
    )
}
