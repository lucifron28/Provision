//
//  ContentView.swift
//  frontend
//
//  Created by Mac-LAB on 9/8/26.
//

import SwiftUI

public struct ContentView: View {
    @StateObject private var authVM = AuthViewModel()
    @StateObject private var homeVM = HomeViewModel()
    @StateObject private var inventoryVM = InventoryViewModel()
    @StateObject private var shoppingVM = ShoppingViewModel()
    @StateObject private var scanVM = ScanViewModel()
    @StateObject private var analyticsVM = AnalyticsViewModel()
    
    @State private var selectedTab: Int = 0
    @State private var showingRegister: Bool = false
    
    public init() {}
    
    public var body: some View {
        Group {
            switch authVM.authState {
            case .checkingSession:
                splashLoadingView
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
                mainAppTabView
                    .onAppear {
                        showingRegister = false
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
    
    private var mainAppTabView: some View {
        TabView(selection: $selectedTab) {
            Tab("Home", systemImage: "house.fill", value: 0) {
                HomeView(
                    viewModel: homeVM,
                    authVM: authVM,
                    onNavigateToInventory: {
                        selectedTab = 1
                    },
                    onNavigateToShopping: {
                        selectedTab = 3
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

#Preview {
    ContentView()
}
