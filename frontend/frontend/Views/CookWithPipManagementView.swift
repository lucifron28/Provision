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
                    Label("My cooking preferences", systemImage: "person.crop.circle")
                }
                .accessibilityIdentifier("cook-with-pip-preferences-link")

                NavigationLink {
                    ProductLabelReviewListView(scope: scope, service: service)
                } label: {
                    Label("Product label reviews", systemImage: "tag")
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
    }
}
