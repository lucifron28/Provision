import SwiftUI

public struct AnalyticsView: View {
    @ObservedObject var viewModel: AnalyticsViewModel
    
    public init(viewModel: AnalyticsViewModel) {
        self.viewModel = viewModel
    }
    
    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    // Valuation Summary Card
                    valuationCard
                    
                    // Monthly Spending Card
                    spendingCard
                    
                    // Waste & Loss Prevention Card
                    wastePreventionCard
                    
                    // Expiration Risk Radar
                    riskRadarCard
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
            }
            .background(ProvisionTheme.background.ignoresSafeArea())
            .navigationTitle("Analytics & Insights")
            .navigationBarTitleDisplayMode(.inline)
            .refreshable {
                await viewModel.loadAnalytics()
            }
            .task {
                await viewModel.loadAnalytics()
            }
        }
    }
    
    // MARK: - Subviews
    
    private var valuationCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("INVENTORY VALUATION")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .tracking(0.6)
                Spacer()
                Image(systemName: "banknote.fill")
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }
            
            Text("₱\(formatCurrency(viewModel.valuation.total_value))")
                .font(.system(size: 32, weight: .bold, design: .serif))
                .foregroundStyle(ProvisionTheme.textPrimary)
            
            Divider()
            
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("ACTIVE BATCHES")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                    Text("\(viewModel.valuation.total_active_batches)")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                }
                
                Spacer()
                
                VStack(alignment: .trailing, spacing: 2) {
                    Text("CATALOG PRODUCTS")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                    Text("\(viewModel.valuation.total_active_products)")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                }
            }
        }
        .padding(18)
        .provisionCard()
    }
    
    private var spendingCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("GROCERY SPENDING")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .tracking(0.6)
                Spacer()
                Image(systemName: "creditcard.fill")
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }
            
            Text("₱\(formatCurrency(viewModel.spending.total_spent))")
                .font(.system(size: 28, weight: .bold, design: .serif))
                .foregroundStyle(ProvisionTheme.textPrimary)
            
            HStack(spacing: 6) {
                Image(systemName: "checkmark.seal.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                Text("Across \(viewModel.spending.sessions_count) intake grocery sessions")
                    .font(.system(size: 13))
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
        }
        .padding(18)
        .provisionCard()
    }
    
    private var wastePreventionCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("WASTE & LOSS INTELLIGENCE")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .tracking(0.6)
                Spacer()
                Image(systemName: "arrow.triangle.2.circlepath.doc.on.clipboard")
                    .foregroundStyle(ProvisionTheme.amberWarning)
            }
            
            HStack(alignment: .firstTextBaseline) {
                Text("₱\(formatCurrency(viewModel.waste.total_financial_loss))")
                    .font(.system(size: 28, weight: .bold, design: .serif))
                    .foregroundStyle(ProvisionTheme.redAlert)
                
                Text("financial loss")
                    .font(.system(size: 13))
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
            
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("ITEMS WASTED")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                    Text(String(format: "%.0f units", viewModel.waste.total_quantity_wasted))
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                }
                
                Spacer()
                
                VStack(alignment: .trailing, spacing: 2) {
                    Text("WASTE LOGS")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                    Text("\(viewModel.waste.total_waste_events) logged")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                }
            }
        }
        .padding(18)
        .provisionCard(borderColor: ProvisionTheme.amberWarning.opacity(0.4))
    }
    
    private var riskRadarCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("DECISION INTELLIGENCE")
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(ProvisionTheme.textSecondary)
                .tracking(0.6)
            
            HStack(spacing: 12) {
                ZStack {
                    Circle()
                        .fill(ProvisionTheme.provisionGreenLight)
                        .frame(width: 42, height: 42)
                    Image(systemName: "leaf.circle.fill")
                        .font(.system(size: 22))
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                }
                
                VStack(alignment: .leading, spacing: 2) {
                    Text("FEFO Consumption Active")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                    Text("Oldest batches are prioritized automatically during consumption to minimize spoilage.")
                        .font(.system(size: 12))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
            }
            .padding(14)
            .provisionCard()
        }
    }
    
    private func formatCurrency(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 0
        return formatter.string(from: NSNumber(value: value)) ?? "\(Int(value))"
    }
}
