import XCTest
@testable import frontend

final class ScannerRecoveryTests: XCTestCase {
    @MainActor
    func testProductionScannerBehaviorSuite() async throws {
        try await ScanViewModelProductionTests.runAllTests()
    }
}
