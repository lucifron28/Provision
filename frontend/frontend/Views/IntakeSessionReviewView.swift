import SwiftUI

// MARK: - Dedicated Intake Session Review Workspace
// Full item management workspace with search, status filters, item editing, and commit action bar.

public struct IntakeSessionReviewView: View {
    @ObservedObject public var viewModel: ScanViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var searchQuery: String = ""
    @State private var selectedFilter: IntakeReviewFilter = .all
    @State private var reviewingItem: ScannedIntakeItem? = nil

    public enum IntakeReviewFilter: String, CaseIterable, Identifiable {
        case all = "All"
        case needsReview = "Needs Review"
        case needsDetails = "Needs Details"
        case ready = "Ready"
        case confirmed = "Confirmed"

        public var id: String { rawValue }

        public var icon: String {
            switch self {
            case .all: return "tray.full.fill"
            case .needsReview: return "exclamationmark.triangle.fill"
            case .needsDetails: return "exclamationmark.circle.fill"
            case .ready: return "circle"
            case .confirmed: return "checkmark.circle.fill"
            }
        }
    }

    public init(viewModel: ScanViewModel) {
        self.viewModel = viewModel
    }

    public var filteredItems: [ScannedIntakeItem] {
        let items = viewModel.scannedItems
        let query = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()

        return items.filter { item in
            // Search query filter
            if !query.isEmpty {
                let nameMatch = item.name.lowercased().contains(query)
                let brandMatch = item.brand?.lowercased().contains(query) == true
                let barcodeMatch = item.barcode.contains(query)
                if !nameMatch && !brandMatch && !barcodeMatch {
                    return false
                }
            }

            // Status filter
            let state = viewModel.validationState(for: item)
            switch selectedFilter {
            case .all:
                return true
            case .needsReview:
                return state == .needsReview
            case .needsDetails:
                return state == .needsDetails
            case .ready:
                return state == .ready
            case .confirmed:
                return state == .confirmed
            }
        }
    }

    public var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Search Bar
                searchBarSection
                    .padding(.horizontal, 16)
                    .padding(.top, 10)
                    .padding(.bottom, 8)

                // Status Filter Pills
                filterPillsBar
                    .padding(.bottom, 10)

                Divider()
                    .background(ProvisionTheme.border)

                // Content List
                if filteredItems.isEmpty {
                    emptyFilterView
                } else {
                    ScrollView {
                        LazyVStack(spacing: 8) {
                            ForEach(filteredItems) { item in
                                workspaceItemRow(for: item)
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                    }
                }

                // Sticky Bottom Commit Bar
                workspaceCommitBar
            }
            .background(ProvisionTheme.background.ignoresSafeArea())
            .navigationTitle("Intake Workspace (\(viewModel.scannedItems.count))")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") {
                        dismiss()
                    }
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                }

                ToolbarItem(placement: .primaryAction) {
                    if viewModel.readyToConfirmCount > 0 {
                        Button {
                            viewModel.confirmAllReady()
                        } label: {
                            HStack(spacing: 4) {
                                Image(systemName: "checkmark.circle.fill")
                                Text("Confirm All")
                            }
                            .font(.system(size: 13, weight: .bold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                        }
                        .disabled(viewModel.isIntakeMutationLocked)
                    }
                }
            }
            .sheet(item: $reviewingItem) { item in
                IntakeItemReviewSheet(itemId: item.id, viewModel: viewModel)
            }
        }
    }

    // MARK: - Search Bar

    private var searchBarSection: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 14))
                .foregroundStyle(ProvisionTheme.textTertiary)

            TextField("Search items by name, brand, or barcode...", text: $searchQuery)
                .font(.system(size: 13))
                .foregroundStyle(ProvisionTheme.textPrimary)

            if !searchQuery.isEmpty {
                Button {
                    searchQuery = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 14))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(ProvisionTheme.inputBackground)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(ProvisionTheme.border, lineWidth: 1)
        )
    }

    // MARK: - Filter Pills

    private var filterPillsBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(IntakeReviewFilter.allCases) { filter in
                    let isSelected = selectedFilter == filter
                    let count = count(for: filter)

                    Button {
                        selectedFilter = filter
                    } label: {
                        HStack(spacing: 5) {
                            Image(systemName: filter.icon)
                                .font(.system(size: 10, weight: .semibold))
                            Text(filter.rawValue)
                                .font(.system(size: 12, weight: isSelected ? .bold : .medium))
                            Text("(\(count))")
                                .font(.system(size: 11, weight: .regular))
                                .opacity(0.8)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(isSelected ? ProvisionTheme.provisionGreen : ProvisionTheme.surface)
                        .foregroundStyle(isSelected ? ProvisionTheme.onAccent : ProvisionTheme.textPrimary)
                        .clipShape(Capsule())
                        .overlay(
                            Capsule()
                                .stroke(isSelected ? ProvisionTheme.provisionGreen : ProvisionTheme.border, lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .accessibleTouchTarget()
                }
            }
            .padding(.horizontal, 16)
        }
    }

    private func count(for filter: IntakeReviewFilter) -> Int {
        switch filter {
        case .all:
            return viewModel.scannedItems.count
        case .needsReview:
            return viewModel.scannedItems.filter { viewModel.validationState(for: $0) == .needsReview }.count
        case .needsDetails:
            return viewModel.scannedItems.filter { viewModel.validationState(for: $0) == .needsDetails }.count
        case .ready:
            return viewModel.scannedItems.filter { viewModel.validationState(for: $0) == .ready }.count
        case .confirmed:
            return viewModel.scannedItems.filter { viewModel.validationState(for: $0) == .confirmed }.count
        }
    }

    // MARK: - Item Row

    private func workspaceItemRow(for item: ScannedIntakeItem) -> some View {
        Button {
            reviewingItem = item
        } label: {
            let state = viewModel.validationState(for: item)
            let hasException = (state == .needsReview || state == .needsDetails)
            let hasConflict = item.conflictingReceiptQuantity != nil

            HStack(alignment: .center, spacing: 10) {
                if hasException {
                    Image(systemName: state == .needsReview ? "exclamationmark.triangle.fill" : "exclamationmark.circle.fill")
                        .font(.system(size: 15))
                        .foregroundStyle(state == .needsReview ? ProvisionTheme.redAlert : ProvisionTheme.amberWarning)
                }

                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(item.name)
                            .font(ProvisionTypography.headline)
                            .foregroundStyle(ProvisionTheme.textPrimary)
                            .lineLimit(2)
                            .fixedSize(horizontal: false, vertical: true)

                        if let brand = item.brand, !brand.isEmpty {
                            Text("(\(brand))")
                                .font(ProvisionTypography.caption)
                                .foregroundStyle(ProvisionTheme.textSecondary)
                                .lineLimit(1)
                        }
                    }

                    HStack(spacing: 6) {
                        Text("\(formattedQuantity(item.quantity)) \(item.unit)")
                            .font(ProvisionTypography.subheadline)
                            .foregroundStyle(ProvisionTheme.textSecondary)

                        Text("•")
                            .font(ProvisionTypography.caption)
                            .foregroundStyle(ProvisionTheme.textTertiary)

                        if let locId = item.storageLocationId,
                           let loc = viewModel.availableLocations.first(where: { $0.id == locId }) {
                            HStack(spacing: 3) {
                                Image(systemName: "archivebox")
                                    .font(.system(size: 10))
                                Text(loc.name)
                                    .font(ProvisionTypography.caption)
                            }
                            .foregroundStyle(ProvisionTheme.textSecondary)
                        } else {
                            HStack(spacing: 3) {
                                Image(systemName: "exclamationmark.circle.fill")
                                    .font(.system(size: 10))
                                Text("No location")
                                    .font(.system(size: 11, weight: .bold))
                            }
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(ProvisionTheme.amberLight)
                            .foregroundStyle(ProvisionTheme.amberWarning)
                            .clipShape(Capsule())
                        }

                        if hasConflict {
                            Text("•")
                                .font(ProvisionTypography.caption)
                                .foregroundStyle(ProvisionTheme.textTertiary)
                            Text("Conflict")
                                .font(.system(size: 10, weight: .bold))
                                .padding(.horizontal, 5)
                                .padding(.vertical, 1.5)
                                .background(ProvisionTheme.redLight)
                                .foregroundStyle(ProvisionTheme.redAlert)
                                .clipShape(Capsule())
                        }
                    }
                }

                Spacer(minLength: 6)

                HStack(spacing: 6) {
                    statusPill(for: state)

                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(ProvisionTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(hasException ? (state == .needsReview ? ProvisionTheme.redAlert.opacity(0.4) : ProvisionTheme.amberWarning.opacity(0.4)) : ProvisionTheme.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(item.name), \(formattedQuantity(item.quantity)) \(item.unit), \(item.storageLocationId != nil ? "location selected" : "no location selected"), status: \(viewModel.validationState(for: item).rawValue)")
        .accessibilityHint("Double tap to inspect and edit item details")
    }

    @ViewBuilder
    private func statusPill(for state: ScanViewModel.IntakeItemValidationState) -> some View {
        switch state {
        case .confirmed:
            HStack(spacing: 3) {
                Image(systemName: "checkmark")
                    .font(.system(size: 9, weight: .bold))
                Text("Confirmed")
                    .font(.system(size: 11, weight: .bold))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(ProvisionTheme.provisionGreenLight)
            .foregroundStyle(ProvisionTheme.provisionGreen)
            .clipShape(Capsule())

        case .needsReview:
            HStack(spacing: 3) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 9, weight: .bold))
                Text("Needs Review")
                    .font(.system(size: 11, weight: .bold))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(ProvisionTheme.redLight)
            .foregroundStyle(ProvisionTheme.redAlert)
            .clipShape(Capsule())

        case .needsDetails:
            HStack(spacing: 3) {
                Image(systemName: "exclamationmark.circle")
                    .font(.system(size: 9, weight: .bold))
                Text("Needs Details")
                    .font(.system(size: 11, weight: .bold))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(ProvisionTheme.amberLight)
            .foregroundStyle(ProvisionTheme.amberWarning)
            .clipShape(Capsule())

        case .ready:
            HStack(spacing: 3) {
                Image(systemName: "circle")
                    .font(.system(size: 9, weight: .bold))
                Text("Ready")
                    .font(.system(size: 11, weight: .bold))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(ProvisionTheme.provisionGreenLight.opacity(0.6))
            .foregroundStyle(ProvisionTheme.provisionGreen)
            .clipShape(Capsule())
        }
    }

    // MARK: - Empty State

    private var emptyFilterView: some View {
        VStack(spacing: 12) {
            Spacer()
            Image("pip_thinking")
                .resizable()
                .scaledToFit()
                .frame(width: 72, height: 72)
                .accessibilityHidden(true)

            Text("No Matching Items")
                .font(ProvisionTypography.headline)
                .foregroundStyle(ProvisionTheme.textPrimary)

            Text(searchQuery.isEmpty ? "No items in this filter tab." : "No intake items match '\(searchQuery)'.")
                .font(ProvisionTypography.footnote)
                .foregroundStyle(ProvisionTheme.textSecondary)

            if !searchQuery.isEmpty {
                Button("Clear Search") {
                    searchQuery = ""
                }
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(ProvisionTheme.provisionGreen)
                .padding(.top, 4)
            }
            Spacer()
        }
        .frame(maxWidth: .infinity)
        .padding(24)
    }

    // MARK: - Sticky Bottom Commit Bar

    private var workspaceCommitBar: some View {
        let totalCount = viewModel.scannedItems.count
        let confirmedCount = viewModel.confirmedItemsCount
        let allConfirmed = totalCount > 0 && confirmedCount == totalCount

        return VStack(spacing: 6) {
            Button {
                Task {
                    await viewModel.commitIntakeSession()
                    if viewModel.scannedItems.isEmpty {
                        dismiss()
                    }
                }
            } label: {
                HStack(spacing: 8) {
                    if viewModel.isCommitting {
                        ProgressView().tint(ProvisionTheme.onAccent)
                        Text("Committing Intake...")
                            .font(.system(size: 15, weight: .bold))
                    } else {
                        Image(systemName: allConfirmed ? "checkmark.circle.fill" : "lock.fill")
                        Text(allConfirmed ? "Commit \(totalCount) Items to Pantry" : "Commit Intake (\(confirmedCount)/\(totalCount) Confirmed)")
                            .font(.system(size: 15, weight: .bold))
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 13)
                .background((allConfirmed || viewModel.hasPendingCommitRecovery) ? ProvisionTheme.provisionGreen : ProvisionTheme.surfaceSecondary)
                .foregroundStyle((allConfirmed || viewModel.hasPendingCommitRecovery) ? ProvisionTheme.onAccent : ProvisionTheme.textTertiary)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .disabled(viewModel.isCommitting || (!viewModel.hasPendingCommitRecovery && !allConfirmed))
        }
        .padding(.horizontal, 16)
        .padding(.top, 8)
        .padding(.bottom, 6)
        .background(ProvisionTheme.surface)
        .overlay(alignment: .top) {
            Divider().background(ProvisionTheme.border.opacity(0.6))
        }
    }

    private func formattedQuantity(_ qty: Double) -> String {
        if qty.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(qty))"
        } else {
            return String(format: "%.1f", qty)
        }
    }
}
