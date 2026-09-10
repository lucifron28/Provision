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
            HomeView(
                viewModel: homeVM,
                onNavigateToInventory: {
                    selectedTab = 1
                },
                onNavigateToShopping: {
                    selectedTab = 3
                }
            )
            .tabItem {
                Label("Home", systemImage: "house.fill")
            }
            .tag(0)
            
            InventoryView(viewModel: inventoryVM)
                .tabItem {
                    Label("Inventory", systemImage: "shippingbox.fill")
                }
                .tag(1)
            
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
            .tabItem {
                Label("Scan", systemImage: "barcode.viewfinder")
            }
            .tag(2)
            
            ShoppingListView(viewModel: shoppingVM)
                .tabItem {
                    Label("Shopping", systemImage: "cart.fill")
                }
                .badge(shoppingVM.pendingCount > 0 ? "\(shoppingVM.pendingCount)" : nil)
                .tag(3)
            
            AnalyticsView(viewModel: analyticsVM)
                .tabItem {
                    Label("Analytics", systemImage: "chart.bar.fill")
                }
                .tag(4)
        }
        .tint(ProvisionTheme.provisionGreen)
    }
}

#Preview {
    ContentView()
}
