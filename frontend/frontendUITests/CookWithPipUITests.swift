import XCTest

final class CookWithPipUITests: XCTestCase {
    func testHomeNavigationAndCaptureRecipeScreens() throws {
        let app = XCUIApplication()
        app.launchArguments.append("-cook-with-pip-ui-tests")
        app.launch()

        let homeEntry = element("cook-with-pip-entry", in: app)
        XCTAssertTrue(homeEntry.waitForExistence(timeout: 10))
        XCTAssertTrue(element("ui-test-fixture-banner", in: app).exists)
        capture("Home_Cook_with_Pip", app: app)
        homeEntry.tap()

        XCTAssertTrue(element("cook-with-pip-introduction", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("recipe-card-301", in: app).waitForExistence(timeout: 10))
        capture("Cook_with_Pip", app: app)

        let cookNow = element("cook-mode-cookNow", in: app)
        XCTAssertTrue(cookNow.exists)
        cookNow.tap()
        XCTAssertTrue(element("recipe-card-301", in: app).waitForExistence(timeout: 10))
        capture("Cook_Now", app: app)

        element("cook-mode-almostThere", in: app).tap()
        let almostThereRecipe = element("recipe-card-302", in: app)
        XCTAssertTrue(almostThereRecipe.waitForExistence(timeout: 10))
        XCTAssertTrue(almostThereRecipe.label.contains("2 missing"))
        capture("Almost_There", app: app)

        element("cook-mode-myRecipes", in: app).tap()
        let householdRecipe = element("recipe-card-303", in: app)
        XCTAssertTrue(householdRecipe.waitForExistence(timeout: 10))
        capture("My_Recipes", app: app)
        householdRecipe.tap()

        XCTAssertTrue(element("recipe-detail-title", in: app).waitForExistence(timeout: 10))
        let safetyStatus = element("recipe-safety-status", in: app)
        let availabilityStatus = element("recipe-availability-status", in: app)
        XCTAssertTrue(safetyStatus.waitForExistence(timeout: 10))
        XCTAssertTrue(availabilityStatus.waitForExistence(timeout: 10))
        XCTAssertEqual(safetyStatus.label, "Review required")
        XCTAssertEqual(availabilityStatus.label, "Unknown")
        capture("Recipe_Detail", app: app)
    }

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: identifier).firstMatch
    }

    private func capture(_ name: String, app: XCUIApplication) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
