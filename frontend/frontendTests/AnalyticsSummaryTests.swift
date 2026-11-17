import XCTest
@testable import frontend

final class AnalyticsSummaryTests: XCTestCase {
    func testInventoryValueDisclosesThatUnpricedStockIsExcluded() {
        let valuation = InventoryValuation(total_value: 0, total_active_batches: 2, total_active_products: 2)

        XCTAssertTrue(valuation.valueDisclosure.contains("Unpriced stock is excluded"))
    }

    func testWasteWithNoPricedLossDoesNotClaimZeroWaste() {
        let summary = WasteSummary(total_waste_events: 1, total_quantity_wasted: 2, total_financial_loss: 0)

        XCTAssertEqual(summary.costStatusLabel, "Cost estimate")
        XCTAssertTrue(summary.costDisclosure.contains("others are unpriced"))
    }

    func testNoWasteEventsHasAnAccurateStatus() {
        let summary = WasteSummary(total_waste_events: 0, total_quantity_wasted: 0, total_financial_loss: 0)

        XCTAssertEqual(summary.costStatusLabel, "No waste recorded")
    }
}
