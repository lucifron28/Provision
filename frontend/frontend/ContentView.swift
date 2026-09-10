//
//  ContentView.swift
//  frontend
//
//  Created by Mac-LAB on 9/8/26.
//

import SwiftUI

public struct ContentView: View {
    @StateObject private var homeVM = HomeViewModel()
    @StateObject private var inventoryVM = InventoryViewModel()
    @StateObject private var shoppingVM = ShoppingViewModel()
    @StateObject private var scanVM = ScanViewModel()
    @StateObject private var analyticsVM = AnalyticsViewModel()
    
    @State private var selectedTab: Int = 0
    
    public init() {}
    
    public var body: some View {
        TabView(selection: $selectedTab) {
            Tab("Home", systemImage: "house.fill", value: 0) {
                HomeView(
                    viewModel: homeVM,
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
                ScanView(
                    viewModel: scanVM,
                    onSessionCommitted: {
                        Task {
                            await inventoryVM.loadData()
                            await homeVM.loadDashboard()
                        }
                        selectedTab = 1
                    }
                )
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
}

#Preview {
    ContentView()
}
