//
//  ContentView.swift
//  frontend
//
//  Created by Mac-LAB on 9/8/26.
//

import SwiftUI

public struct ContentView: View {
    @StateObject private var authVM = AuthViewModel()

    @State private var showingRegister: Bool = false

    public init() {}

    public var body: some View {
        Group {
            switch authVM.authState {
            case .checkingSession:
                splashLoadingView
            case .sessionUnavailable:
                VStack(spacing: 16) {
                    Text("Unable to verify your session")
                        .font(.headline)
                    Text(authVM.errorMessage ?? "Check your connection and try again.")
                        .multilineTextAlignment(.center)
                    Button("Try again") {
                        Task { await authVM.checkExistingSession() }
                    }
                }
                .padding()
            case .signedOut:
                if showingRegister {
                    RegisterView(
                        authVM: authVM,
                        onNavigateToLogin: {
                            showingRegister = false
                        }
                    )
                } else {
                    LoginView(
                        authVM: authVM,
                        onNavigateToRegister: {
                            showingRegister = true
                        }
                    )
                }
            case .signedIn:
                if let scope = authVM.selectedScope {
                    HouseholdTabs(authVM: authVM, scope: scope)
                        .id(scope)
                        .onAppear { showingRegister = false }
                }
            }
        }
        .task {
            await authVM.checkExistingSession()
        }
        .onChange(of: authVM.authState) { _, _ in
            showingRegister = false
        }
    }

    private var splashLoadingView: some View {
        ZStack {
            ProvisionTheme.background.ignoresSafeArea()
            VStack(spacing: 16) {
                Text("Provision")
                    .font(.system(size: 36, weight: .bold, design: .serif))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                ProgressView()
                    .tint(ProvisionTheme.provisionGreen)
            }
        }
    }
}

private struct HouseholdTabs: View {
    @ObservedObject var authVM: AuthViewModel
    @StateObject private var homeVM: HomeViewModel
    @StateObject private var inventoryVM: InventoryViewModel
    @StateObject private var shoppingVM: ShoppingViewModel
    @StateObject private var scanVM: ScanViewModel
    @StateObject private var analyticsVM: AnalyticsViewModel
    @State private var selectedTab = 0

    init(authVM: AuthViewModel, scope: HouseholdScope) {
        self.authVM = authVM
        _homeVM = StateObject(wrappedValue: HomeViewModel(scope: scope))
        _inventoryVM = StateObject(wrappedValue: InventoryViewModel(scope: scope))
        _shoppingVM = StateObject(wrappedValue: ShoppingViewModel(scope: scope))
        _scanVM = StateObject(wrappedValue: ScanViewModel(scope: scope))
        _analyticsVM = StateObject(wrappedValue: AnalyticsViewModel(scope: scope))
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            Tab("Home", systemImage: "house.fill", value: 0) {
                HomeView(
                    viewModel: homeVM,
                    authVM: authVM,
                    onNavigateToInventory: { filter in
                        if let filter = filter {
                            inventoryVM.applyFilter(filter)
                        }
                        selectedTab = 1
                    },
                    onNavigateToShopping: {
                        selectedTab = 3
                    },
                    onShoppingConfirmed: {
                        await shoppingVM.refreshFromServer()
                    }
                )
            }

            Tab("Inventory", systemImage: "shippingbox.fill", value: 1) {
                InventoryView(viewModel: inventoryVM)
            }

            Tab("Scan", systemImage: "barcode.viewfinder", value: 2) {
                ScanView(viewModel: scanVM)
            }

            Tab("Shopping", systemImage: "cart.fill", value: 3) {
                ShoppingListView(viewModel: shoppingVM)
            }
            .badge(shoppingVM.pendingCount)

            Tab("Analytics", systemImage: "chart.bar.fill", value: 4) {
                AnalyticsView(viewModel: analyticsVM)
            }
        }
        .tint(ProvisionTheme.provisionGreen)
        .safeAreaInset(edge: .top) {
            if authVM.households.count > 1 {
                Menu {
                    ForEach(authVM.households) { household in
                        Button(household.name) { Task { await authVM.selectHousehold(household) } }
                    }
                } label: {
                    Label(authVM.households.first(where: { $0.id == authVM.selectedScope?.householdID })?.name ?? "Household", systemImage: "house")
                }
                .padding(.horizontal)
            }
        }
        .alert("Unable to switch household", isPresented: Binding(
            get: { authVM.errorMessage != nil },
            set: { if !$0 { authVM.errorMessage = nil } }
        )) {
            Button("OK", role: .cancel) { authVM.errorMessage = nil }
        } message: {
            Text(authVM.errorMessage ?? "Please try again.")
        }
    }

}

#Preview {
    ContentView()
}
