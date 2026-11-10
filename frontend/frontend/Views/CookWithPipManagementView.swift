import SwiftUI

public struct CookWithPipManagementView: View {
    private let scope: HouseholdScope
    private let service: any CookWithPipWorkflowService

    public init(scope: HouseholdScope, service: any CookWithPipWorkflowService = APIClient.shared) {
        self.scope = scope
        self.service = service
    }

    public var body: some View {
        List {
            Section {
                NavigationLink {
                    CookWithPipPreferencesView(scope: scope, service: service)
                } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        Label("Cooking preferences", systemImage: "person.crop.circle")
                            .font(.body)
                        Text("Set cuisine, diet, servings, and member allergy declarations.")
                            .font(.footnote)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .accessibilityIdentifier("cook-with-pip-preferences-link")

                NavigationLink {
                    ProductLabelReviewListView(scope: scope, service: service)
                } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        Label("Product label reviews", systemImage: "tag")
                            .font(.body)
                        Text("Review package labels and household product mappings.")
                            .font(.footnote)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .accessibilityIdentifier("cook-with-pip-product-labels-link")
            } footer: {
                Text("Food preferences and allergy declarations are member-specific. Product mappings and label reviews belong to this household.")
            }
        }
        .scrollContentBackground(.hidden)
        .background(ProvisionTheme.background)
        .navigationTitle("Cook with Pip")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(ProvisionTheme.background, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
    }
}
