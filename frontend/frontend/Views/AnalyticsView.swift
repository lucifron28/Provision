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
                    if viewModel.isLoading && !viewModel.hasLoadedOnce {
                        VStack(spacing: 12) {
                            ProgressView()
                                .tint(ProvisionTheme.provisionGreen)
                            Text("Loading household analytics...")
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
                            Text("Unable to load analytics")
                                .font(.system(size: 16, weight: .bold))
                                .foregroundStyle(ProvisionTheme.textPrimary)
                            Text(err)
                                .font(.system(size: 12))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                                .multilineTextAlignment(.center)
                            Button("Try Again") {
                                Task { await viewModel.loadAnalytics() }
                            }
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                            .padding(.top, 4)
                        }
                        .padding(24)
                        .frame(maxWidth: .infinity)
                        .provisionCard()
                    } else if viewModel.hasLoadedOnce && viewModel.isEmpty {
                        VStack(spacing: 12) {
                            Image(systemName: "chart.bar.xaxis")
                                .font(.system(size: 36))
                                .foregroundStyle(ProvisionTheme.textTertiary)
                            Text("No Household Analytics Recorded")
                                .font(.system(size: 16, weight: .bold, design: .serif))
                                .foregroundStyle(ProvisionTheme.textPrimary)
                            Text("Complete intake sessions or restock pantry items to begin tracking inventory valuation, cumulative spend, and waste reduction.")
                                .font(.system(size: 13))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                                .multilineTextAlignment(.center)
                        }
                        .padding(28)
                        .frame(maxWidth: .infinity)
                        .provisionCard()
                    } else {
                        // Inline refresh error banner if pull-to-refresh fails while data is already loaded
                        if let err = viewModel.errorMessage {
                            HStack(spacing: 8) {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .foregroundStyle(ProvisionTheme.redAlert)
                                Text("Refresh failed: \(err)")
                                    .font(.system(size: 13, weight: .medium))
                                    .foregroundStyle(ProvisionTheme.redAlert)
                                Spacer()
                                Button("Dismiss") {
                                    viewModel.errorMessage = nil
                                }
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(ProvisionTheme.redAlert)
                            }
                            .padding(12)
                            .background(ProvisionTheme.redLight)
                            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        }

                        // Key Metrics 2-Column Grid (Valuation & Cumulative Spend)
                        financialMetricsGrid

                        // Recorded Waste & Loss Prevention Card (Compact)
                        wastePreventionCard

                        // Pantry Intelligence & FEFO Card
                        decisionIntelligenceCard
                    }
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

    // MARK: - Consolidate Financial Metrics (2-Column Grid)

    private var financialMetricsGrid: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .top, spacing: 12) {
                valuationCard
                spendingCard
            }
            VStack(spacing: 12) {
                valuationCard
                spendingCard
            }
        }
    }

    private var valuationCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("VALUATION")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .tracking(0.5)
                Spacer()
                Image(systemName: "banknote.fill")
                    .font(.system(size: 13))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }

            Text("₱\(formatCurrency(viewModel.valuation.total_value))")
                .font(.system(size: 24, weight: .bold, design: .serif))
                .foregroundStyle(ProvisionTheme.textPrimary)
                .lineLimit(1)
                .minimumScaleFactor(0.75)

            Divider()
                .background(ProvisionTheme.border.opacity(0.6))

            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("BATCHES")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                    Text("\(viewModel.valuation.total_active_batches)")
                        .font(ProvisionTypography.headline)
                        .foregroundStyle(ProvisionTheme.textPrimary)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text("PRODUCTS")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                    Text("\(viewModel.valuation.total_active_products)")
                        .font(ProvisionTypography.headline)
                        .foregroundStyle(ProvisionTheme.textPrimary)
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity)
        .provisionCard()
    }

    private var spendingCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("TOTAL SPEND")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .tracking(0.5)
                Spacer()
                Image(systemName: "creditcard.fill")
                    .font(.system(size: 13))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }

            Text("₱\(formatCurrency(viewModel.spending.total_spent))")
                .font(.system(size: 24, weight: .bold, design: .serif))
                .foregroundStyle(ProvisionTheme.textPrimary)
                .lineLimit(1)
                .minimumScaleFactor(0.75)

            Divider()
                .background(ProvisionTheme.border.opacity(0.6))

            VStack(alignment: .leading, spacing: 2) {
                Text("INTAKE SESSIONS")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.textTertiary)
                Text("\(viewModel.spending.sessions_count) completed")
                    .font(ProvisionTypography.headline)
                    .foregroundStyle(ProvisionTheme.textPrimary)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity)
        .provisionCard()
    }

    // MARK: - Compact Waste Prevention Card

    private var wastePreventionCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                HStack(spacing: 6) {
                    Image(systemName: "arrow.triangle.2.circlepath.doc.on.clipboard")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(viewModel.waste.total_financial_loss > 0 ? ProvisionTheme.redAlert : ProvisionTheme.provisionGreen)
                    Text("RECORDED WASTE & SPOILAGE")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                        .tracking(0.5)
                }
                Spacer()
                if viewModel.waste.total_financial_loss == 0 {
                    Text("Zero Loss")
                        .font(.system(size: 11, weight: .bold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(ProvisionTheme.provisionGreenLight)
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                        .clipShape(Capsule())
                }
            }

            ViewThatFits(in: .horizontal) {
                HStack(alignment: .center) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("₱\(formatCurrency(viewModel.waste.total_financial_loss))")
                            .font(.system(size: 26, weight: .bold, design: .serif))
                            .foregroundStyle(viewModel.waste.total_financial_loss > 0 ? ProvisionTheme.redAlert : ProvisionTheme.provisionGreen)
                        Text("financial loss recorded")
                            .font(ProvisionTypography.caption)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }

                    Spacer()

                    HStack(spacing: 16) {
                        VStack(alignment: .trailing, spacing: 2) {
                            Text("WASTED UNITS")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(ProvisionTheme.textTertiary)
                            Text(String(format: "%.0f", viewModel.waste.total_quantity_wasted))
                                .font(ProvisionTypography.headline)
                                .foregroundStyle(ProvisionTheme.textPrimary)
                        }

                        VStack(alignment: .trailing, spacing: 2) {
                            Text("DISCARD EVENTS")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(ProvisionTheme.textTertiary)
                            Text("\(viewModel.waste.total_waste_events)")
                                .font(ProvisionTypography.headline)
                                .foregroundStyle(ProvisionTheme.textPrimary)
                        }
                    }
                }

                VStack(alignment: .leading, spacing: 10) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("₱\(formatCurrency(viewModel.waste.total_financial_loss))")
                            .font(.system(size: 26, weight: .bold, design: .serif))
                            .foregroundStyle(viewModel.waste.total_financial_loss > 0 ? ProvisionTheme.redAlert : ProvisionTheme.provisionGreen)
                        Text("financial loss recorded")
                            .font(ProvisionTypography.caption)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }

                    HStack(spacing: 20) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("WASTED UNITS")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(ProvisionTheme.textTertiary)
                            Text(String(format: "%.0f", viewModel.waste.total_quantity_wasted))
                                .font(ProvisionTypography.headline)
                                .foregroundStyle(ProvisionTheme.textPrimary)
                        }

                        VStack(alignment: .leading, spacing: 2) {
                            Text("DISCARD EVENTS")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(ProvisionTheme.textTertiary)
                            Text("\(viewModel.waste.total_waste_events)")
                                .font(ProvisionTypography.headline)
                                .foregroundStyle(ProvisionTheme.textPrimary)
                        }
                    }
                }
            }
        }
        .padding(14)
        .provisionCard(borderColor: viewModel.waste.total_financial_loss > 0 ? ProvisionTheme.amberWarning.opacity(0.3) : ProvisionTheme.border)
    }

    // MARK: - Decision Intelligence Card

    private var decisionIntelligenceCard: some View {
        HStack(spacing: 12) {
            Image("pip_guardian")
                .resizable()
                .scaledToFit()
                .frame(width: 48, height: 48)
                .background(
                    Circle()
                        .fill(ProvisionTheme.provisionGreenLight)
                        .frame(width: 54, height: 54)
                )

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 4) {
                    Text("FEFO Pantry Optimization")
                        .font(.system(size: 15, weight: .bold, design: .serif))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                    Spacer()
                    Text("Active")
                        .font(.system(size: 11, weight: .bold))
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(ProvisionTheme.provisionGreenLight)
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                        .clipShape(Capsule())
                }

                Text("First-Expiring, First-Out rule automatically prioritizes oldest stock during consumption to eliminate household food waste.")
                    .font(ProvisionTypography.footnote)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .provisionCard()
    }

    private func formatCurrency(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 0
        return formatter.string(from: NSNumber(value: value)) ?? "\(Int(value))"
    }
}

#Preview("Analytics & Insights") {
    AnalyticsView(viewModel: PreviewData.makeAnalyticsViewModel())
}
