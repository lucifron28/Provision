import XCTest
@testable import frontend

final class ProductUnitsTests: XCTestCase {
    func testKnownCountUnitsUseSingularForOneItem() {
        XCTAssertEqual(ProductUnits.displayUnit(for: 1, unit: "pcs"), "piece")
        XCTAssertEqual(ProductUnits.displayUnit(for: 1, unit: "cans"), "can")
        XCTAssertEqual(ProductUnits.displayUnit(for: 1, unit: "bottles"), "bottle")
        XCTAssertEqual(ProductUnits.displayUnit(for: 1, unit: "packs"), "pack")
        XCTAssertEqual(ProductUnits.displayUnit(for: 1, unit: "boxes"), "box")
        XCTAssertEqual(ProductUnits.displayUnit(for: 1, unit: "bags"), "bag")
    }

    func testPluralAndUnknownUnitsRemainUnchanged() {
        XCTAssertEqual(ProductUnits.displayUnit(for: 0, unit: "cans"), "cans")
        XCTAssertEqual(ProductUnits.displayUnit(for: 2, unit: "cans"), "cans")
        XCTAssertEqual(ProductUnits.displayUnit(for: 1, unit: "kg"), "kg")
        XCTAssertEqual(ProductUnits.displayUnit(for: 1, unit: "sachets"), "sachets")
        XCTAssertEqual(ProductUnits.displayUnit(for: 1, unit: nil), "unit")
        XCTAssertEqual(ProductUnits.displayUnit(for: 2, unit: nil), "units")
    }
}
