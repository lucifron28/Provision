import SwiftUI

public struct HomeView: View {
    @ObservedObject var viewModel: HomeViewModel
    var onNavigateToInventory: () -> Void
    var onNavigateToShopping: () -> Void
    
    public init(
        viewModel: HomeViewModel,
        onNavigateToInventory: @escaping () -> Void = {},
        onNavigateToShopping: @escaping () -> Void = {}
    ) {
        self.viewModel = viewModel
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
                Text("Smart Pantry")
                    .font(.system(size: 22, weight: .bold, design: .serif))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }
            
            Spacer()
            
            Button {
                // Settings or notifications action
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
                
                let val = viewModel.valuation.total_value > 0 ? viewModel.valuation.total_value : 12850
                Text("₱\(formatCurrency(val))")
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
                    
                    let spend = viewModel.spending.total_spent > 0 ? viewModel.spending.total_spent : 8420
                    Text("₱\(formatCurrency(spend))")
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
                // Placeholder preview cards matching reference screen
                HStack(spacing: 12) {
                    expiringCardPreview(name: "Milk", detail: "Whole, 1L", days: 1, isUrgent: true, icon: "drop.fill")
                    expiringCardPreview(name: "Yogurt", detail: "Greek, Plain", days: 2, isUrgent: false, icon: "cup.and.saucer.fill")
                }
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
    
    private func expiringCardPreview(name: String, detail: String, days: Int, isUrgent: Bool, icon: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                ZStack {
                    Circle()
                        .fill(isUrgent ? ProvisionTheme.redLight : ProvisionTheme.amberLight)
                        .frame(width: 36, height: 36)
                    Image(systemName: icon)
                        .font(.system(size: 15))
                        .foregroundStyle(isUrgent ? ProvisionTheme.redAlert : ProvisionTheme.amberWarning)
                }
                
                Spacer()
                
                Text("\(days) \(days == 1 ? "day" : "days")")
                    .font(.system(size: 10, weight: .bold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(isUrgent ? ProvisionTheme.redLight : ProvisionTheme.amberLight)
                    .foregroundStyle(isUrgent ? ProvisionTheme.redAlert : ProvisionTheme.amberWarning)
                    .clipShape(Capsule())
            }
            
            VStack(alignment: .leading, spacing: 2) {
                Text(name)
                    .font(.system(size: 16, weight: .bold, design: .serif))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                Text(detail)
                    .font(.system(size: 12, weight: .regular))
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .provisionCard()
    }
    
    private var restockNeededSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Restock Needed")
                .font(.system(size: 18, weight: .bold, design: .serif))
                .foregroundStyle(ProvisionTheme.textPrimary)
            
            if viewModel.lowStockItems.isEmpty {
                // Static demo preview matching reference screens
                VStack(spacing: 10) {
                    restockRowPreview(name: "Eggs", detail: "Only 2 left", icon: "oval.fill")
                    restockRowPreview(name: "Jasmine Rice", detail: "In Stock (1 kg)", icon: "leaf.fill")
                }
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
    
    private func restockRowPreview(name: String, detail: String, icon: String) -> some View {
        HStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(ProvisionTheme.surfaceSecondary)
                    .frame(width: 40, height: 40)
                Image(systemName: icon)
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }
            
            VStack(alignment: .leading, spacing: 2) {
                Text(name)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                Text(detail)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(detail.contains("Only") ? ProvisionTheme.redAlert : ProvisionTheme.textSecondary)
            }
            
            Spacer()
            
            Button {
                onNavigateToShopping()
            } label: {
                Image(systemName: "cart")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                    .padding(8)
                    .background(ProvisionTheme.surfaceSecondary)
                    .clipShape(Circle())
            }
        }
        .padding(12)
        .provisionCard()
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
