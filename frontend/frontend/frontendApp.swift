//
//  frontendApp.swift
//  frontend
//
//  Created by Mac-LAB on 9/8/26.
//

import SwiftUI

@main
struct ProvisionApp: App {
    init() {
        if ProcessInfo.processInfo.arguments.contains("-run-tests") ||
           ProcessInfo.processInfo.environment["PROVISION_RUN_TESTS"] == "1" {
            Task { @MainActor in
                do {
                    print("=== STARTING PROVISION AUTOMATED TEST SUITE ===")
                    try await ScanViewModelProductionTests.runAllTests()
                    print("=== PROVISION TEST SUITE COMPLETE: 18/18 TESTS PASSED ===")
                    fflush(stdout)
                    exit(0)
                } catch {
                    print("=== PROVISION TEST SUITE FAILED: \(error) ===")
                    fflush(stdout)
                    exit(1)
                }
            }
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
