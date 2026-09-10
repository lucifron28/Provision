import SwiftUI

public struct HomeView: View {
    @ObservedObject var viewModel: HomeViewModel
    @ObservedObject var authVM: AuthViewModel
    var onNavigateToInventory: () -> Void
    var onNavigateToShopping: () -> Void
    
    @State private var showingProfileSheet: Bool = false
    
    public init(
        viewModel: HomeViewModel,
        authVM: AuthViewModel,
        onNavigateToInventory: @escaping () -> Void = {},
        onNavigateToShopping: @escaping () -> Void = {}
    ) {
        self.viewModel = viewModel
        self.authVM = authVM
        self.onNavigateToInventory = onNavigateToInventory
        self.onNavigateToShopping = onNavigateToShopping
    }
    
    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Header Bar
                    headerBar
                    
                    // Pantry Health Hero Card
                    pantryHealthCard
                    
                    // Expiring Soon Section
                    expiringSoonSection
                    
                    // Restock Needed Section
                    restockNeededSection
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
                Text("Good Morning,")
                    .font(.system(size: 13, weight: .regular))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                Text("Provision")
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
            }
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
                    Text("Monthly Spend")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                    
                    Text("₱\(formatCurrency(viewModel.spending.total_spent))")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                }
                
                Spacer()
                
                HStack(spacing: 4) {
                    Image(systemName: "arrow.down.right")
                        .font(.system(size: 10, weight: .bold))
                    Text("Good")
                        .font(.system(size: 12, weight: .semibold))
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(ProvisionTheme.provisionGreen)
                .foregroundStyle(.white)
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
    
    private var expiringSoonSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Expiring Soon")
                    .font(.system(size: 18, weight: .bold, design: .serif))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                
                Spacer()
                
                Button("View All") {
                    onNavigateToInventory()
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
                        ForEach(viewModel.expiringSoonItems) { item in
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
                Task {
                    await viewModel.quickConsumeExpiringItem(item)
                }
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
            Text("Restock Needed")
                .font(.system(size: 18, weight: .bold, design: .serif))
                .foregroundStyle(ProvisionTheme.textPrimary)
            
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
                    ForEach(viewModel.lowStockItems) { item in
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
            VStack(spacing: 24) {
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
                .padding(.top, 24)
                
                VStack(alignment: .leading, spacing: 10) {
                    Text("HOUSEHOLD PANTRY")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                        .tracking(0.6)
                    
                    HStack {
                        Text("Pantry Access")
                            .font(.system(size: 15))
                        Spacer()
                        Text("Shared Household")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                    }
                    .padding(14)
                    .provisionCard()
                }
                
                Spacer()
                
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
                .padding(.bottom, 16)
            }
            .padding(.horizontal, 20)
            .background(ProvisionTheme.background.ignoresSafeArea())
            .navigationTitle("Provision")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { showingProfileSheet = false }
                }
            }
        }
        .presentationDetents([.medium])
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
