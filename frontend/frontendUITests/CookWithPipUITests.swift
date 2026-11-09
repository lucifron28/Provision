import XCTest

final class CookWithPipUITests: XCTestCase {
    func testHomeNavigationAndCaptureRecipeScreens() {
        let app = launch()
        let homeEntry = element("cook-with-pip-entry", in: app)
        XCTAssertTrue(homeEntry.waitForExistence(timeout: 10))
        XCTAssertTrue(element("ui-test-fixture-banner", in: app).exists)
        capture("Home_Cook_with_Pip", app: app)
        homeEntry.tap()

        XCTAssertTrue(element("cook-with-pip-introduction", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("recipe-card-301", in: app).waitForExistence(timeout: 10))
        capture("Cook_with_Pip", app: app)
        XCTAssertTrue(element("cook-mode-cookNow", in: app).exists)
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
        XCTAssertEqual(element("recipe-safety-status", in: app).label, "Review required")
        XCTAssertEqual(element("recipe-availability-status", in: app).label, "Unknown")
        capture("Recipe_Detail", app: app)
        let instructions = element("recipe-instructions", in: app)
        scrollTo(instructions, in: app)
        XCTAssertTrue(instructions.exists)
        capture("Recipe_Detail_Instructions", app: app)
    }

    func testCookWithPipLoadingEmptyAndOfflineRecovery() {
        let loadingApp = launch(scenario: "recipes-loading")
        openCookWithPip(loadingApp)
        XCTAssertTrue(element("cook-with-pip-loading-state", in: loadingApp).waitForExistence(timeout: 5))
        capture("Cook_with_Pip_Loading", app: loadingApp)
        XCTAssertTrue(element("recipe-card-301", in: loadingApp).waitForExistence(timeout: 10))

        loadingApp.terminate()
        let emptyApp = launch(scenario: "recipes-empty")
        openCookWithPip(emptyApp)
        XCTAssertTrue(element("cook-with-pip-empty-state", in: emptyApp).waitForExistence(timeout: 10))
        capture("Cook_with_Pip_Empty", app: emptyApp)

        emptyApp.terminate()
        let offlineApp = launch(scenario: "recipes-offline-once")
        openCookWithPip(offlineApp)
        let retry = element("cook-with-pip-retry", in: offlineApp)
        XCTAssertTrue(retry.waitForExistence(timeout: 10))
        capture("Cook_with_Pip_Offline", app: offlineApp)
        retry.tap()
        XCTAssertTrue(element("recipe-card-301", in: offlineApp).waitForExistence(timeout: 10))
        capture("Cook_with_Pip_Retry_Recovered", app: offlineApp)
    }

    func testSafetyAndAvailabilityStatesWithLongFilipinoNames() {
        let app = launch()
        openCookWithPip(app)
        element("cook-mode-myRecipes", in: app).tap()

        element("recipe-card-302", in: app).tap()
        XCTAssertTrue(element("recipe-safety-status", in: app).waitForExistence(timeout: 10))
        XCTAssertEqual(element("recipe-availability-status", in: app).label, "Partial")
        app.swipeUp()
        XCTAssertTrue(element("recipe-ingredient-1", in: app).exists)
        capture("Recipe_Detail_Partial_Missing", app: app)

        navigateBack(app)
        element("cook-mode-myRecipes", in: app).tap()
        element("recipe-card-303", in: app).tap()
        XCTAssertEqual(element("recipe-safety-status", in: app).label, "Review required")
        XCTAssertEqual(element("recipe-availability-status", in: app).label, "Unknown")
        app.swipeUp()
        capture("Recipe_Detail_Review_Unknown", app: app)

        navigateBack(app)
        element("cook-mode-myRecipes", in: app).tap()
        let longRecipe = element("recipe-card-304", in: app)
        scrollTo(longRecipe, in: app)
        longRecipe.tap()
        XCTAssertEqual(element("recipe-safety-status", in: app).label, "Blocked")
        XCTAssertEqual(element("recipe-availability-status", in: app).label, "Missing")
        app.swipeUp()
        capture("Recipe_Detail_Blocked_Long_Filipino", app: app)
        app.swipeUp()
        capture("Recipe_Detail_Scrolled", app: app)
    }

    func testPreferencesAndPackageLabelReviewScreens() {
        let app = launch()
        openCookWithPip(app)
        element("cook-with-pip-management", in: app).tap()
        element("cook-with-pip-preferences-link", in: app).tap()

        XCTAssertTrue(element("pip-preferences-save", in: app).waitForExistence(timeout: 10))
        let milkAllergen = element("pip-allergen-milk", in: app)
        scrollTo(milkAllergen, in: app)
        XCTAssertTrue(milkAllergen.waitForExistence(timeout: 5))
        XCTAssertTrue(element("pip-allergen-cross-contact-milk", in: app).exists)
        element("pip-preferences-save", in: app).tap()
        let savedMessage = element("pip-preferences-success", in: app)
        for _ in 0..<6 where !savedMessage.exists { app.swipeDown() }
        XCTAssertTrue(savedMessage.waitForExistence(timeout: 10))
        capture("Preferences_Allergy_Declared", app: app)

        navigateBack(app)
        element("cook-with-pip-product-labels-link", in: app).tap()
        XCTAssertTrue(element("pip-label-product-9903", in: app).waitForExistence(timeout: 10))
        capture("Product_Label_List", app: app)
        element("pip-label-product-9903", in: app).tap()
        XCTAssertTrue(element("pip-label-product-title", in: app).waitForExistence(timeout: 10))
        capture("Product_Label_Review", app: app)

        let source = element("pip-label-source-reference", in: app)
        scrollTo(source, in: app)
        source.tap()
        source.typeText("Synthetic package label")
        scrollTo(element("pip-label-save-review", in: app), in: app)
        element("pip-label-save-review", in: app).tap()
        let currentStatus = element("pip-label-current-status", in: app)
        scrollTowardTopUntilVisible(currentStatus, in: app)
        XCTAssertTrue(currentStatus.waitForExistence(timeout: 10))
        XCTAssertTrue(currentStatus.label.contains("Current label review"))
        capture("Product_Label_Review_Current", app: app)
    }

    func testStaleProductLabelReviewIsShownAsStale() {
        let app = launch(scenario: "product-label-stale")
        openCookWithPip(app)
        element("cook-with-pip-management", in: app).tap()
        element("cook-with-pip-product-labels-link", in: app).tap()
        element("pip-label-product-9903", in: app).tap()

        XCTAssertTrue(element("pip-label-product-title", in: app).waitForExistence(timeout: 10))
        let status = element("pip-label-current-status", in: app)
        scrollTo(status, in: app)
        XCTAssertTrue(status.waitForExistence(timeout: 10))
        XCTAssertTrue(status.label.contains("no longer current"))
        capture("Product_Label_Review_Stale", app: app)
    }

    func testSubstitutionChoicesUseStoredAmountsAndRefreshEvaluation() {
        let app = launch()
        openCookNowRecipe(app)
        let customize = element("recipe-review-substitutions", in: app)
        scrollTo(customize, in: app)
        customize.tap()

        let picker = element("recipe-substitution-choice-1", in: app)
        XCTAssertTrue(picker.waitForExistence(timeout: 10))
        capture("Recipe_Substitution_Options", app: app)
        picker.tap()
        let calamansi = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "calamansi")).firstMatch
        XCTAssertTrue(calamansi.waitForExistence(timeout: 5))
        calamansi.tap()
        element("recipe-substitution-recheck", in: app).tap()

        let ingredient = element("recipe-ingredient-1", in: app)
        scrollTo(ingredient, in: app)
        XCTAssertTrue(ingredient.waitForExistence(timeout: 10))
        XCTAssertTrue(ingredient.label.contains("calamansi"))
        capture("Recipe_Detail_Substitution_Applied", app: app)
    }

    func testShoppingPreviewEditsConsolidationAndExplicitConfirmation() {
        let app = launch()
        openShoppingPreview(app)
        XCTAssertEqual(element("recipe-shopping-safety-status", in: app).label, "Eligible")
        capture("Shopping_Preview_Ready", app: app)
        let unlinked = element("recipe-shopping-unlinked-9906", in: app)
        scrollTo(unlinked, in: app)
        XCTAssertTrue(unlinked.exists)
        capture("Shopping_Unlinked_Manual_Items", app: app)

        let includeOptional = app.switches["recipe-shopping-include-optional"]
        scrollTo(includeOptional, in: app)
        includeOptional.tap()
        XCTAssertEqual(includeOptional.value as? String, "1")
        app.buttons["recipe-shopping-refresh-preview"].tap()
        let optionalIngredient = app.staticTexts["kangkong (optional)"]
        scrollTo(optionalIngredient, in: app)
        XCTAssertTrue(optionalIngredient.waitForExistence(timeout: 10))
        capture("Shopping_Optional_Ingredients", app: app)
        scrollTo(includeOptional, in: app)
        includeOptional.tap()
        XCTAssertEqual(includeOptional.value as? String, "0")
        app.buttons["recipe-shopping-refresh-preview"].tap()

        let target = element("recipe-shopping-target-901", in: app)
        scrollTo(target, in: app)
        replaceText(target, with: "125")
        XCTAssertEqual(target.value as? String, "125")
        let done = element("recipe-shopping-keyboard-done", in: app)
        XCTAssertTrue(done.waitForExistence(timeout: 5))
        done.tap()
        capture("Shopping_Line_Exact_Quantity_Edited", app: app)

        let consolidate = app.switches["recipe-shopping-consolidate-914"]
        scrollTo(consolidate, in: app)
        consolidate.tap()
        XCTAssertEqual(consolidate.value as? String, "1")
        capture("Shopping_Duplicate_Consolidation_Opt_In", app: app)

        element("recipe-shopping-confirm", in: app).tap()
        let confirmAction = element("recipe-shopping-confirm-action", in: app)
        XCTAssertTrue(confirmAction.waitForExistence(timeout: 5))
        confirmAction.tap()
        XCTAssertTrue(element("recipe-shopping-result-counts", in: app).waitForExistence(timeout: 10))
        capture("Shopping_Confirmation_Result", app: app)
        element("recipe-shopping-view-list", in: app).tap()
        XCTAssertTrue(app.navigationBars["Shopping List"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["kangkong"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["gata"].exists)
        capture("Shopping_List_Updated", app: app)
    }

    func testShoppingReviewRequiredAndBlockedStates() {
        let reviewApp = launch(scenario: "shopping-review-required")
        openShoppingPreview(reviewApp)
        XCTAssertEqual(element("recipe-shopping-safety-status", in: reviewApp).label, "Review required")
        let reviewConfirm = reviewApp.buttons["recipe-shopping-confirm"]
        XCTAssertFalse(reviewConfirm.isEnabled)
        capture("Shopping_Preview_Review_Required", app: reviewApp)
        let acknowledgement = reviewApp.switches["recipe-shopping-safety-acknowledgement"]
        scrollTo(acknowledgement, in: reviewApp)
        acknowledgement.tap()
        XCTAssertEqual(acknowledgement.value as? String, "1")
        XCTAssertTrue(reviewConfirm.isEnabled)

        reviewApp.terminate()
        let blockedApp = launch(scenario: "shopping-blocked")
        openShoppingPreview(blockedApp)
        XCTAssertEqual(element("recipe-shopping-safety-status", in: blockedApp).label, "Blocked")
        XCTAssertFalse(blockedApp.buttons["recipe-shopping-confirm"].isEnabled)
        capture("Shopping_Preview_Blocked", app: blockedApp)
    }

    func testShoppingOfflineRetryAndStalePreviewRecovery() {
        let offlineApp = launch(scenario: "shopping-offline-once")
        openShoppingPreview(offlineApp)
        XCTAssertTrue(element("recipe-shopping-error", in: offlineApp).waitForExistence(timeout: 10))
        capture("Shopping_Offline_Error_Retry", app: offlineApp)
        element("recipe-shopping-load-preview", in: offlineApp).tap()
        let offlineReady = element("recipe-shopping-safety-status", in: offlineApp)
        XCTAssertTrue(element("recipe-shopping-servings", in: offlineApp).waitForExistence(timeout: 10))
        scrollTo(offlineReady, in: offlineApp)

        offlineApp.terminate()
        let staleApp = launch(scenario: "shopping-stale")
        openShoppingPreview(staleApp)
        element("recipe-shopping-confirm", in: staleApp).tap()
        element("recipe-shopping-confirm-action", in: staleApp).tap()
        let staleMessage = appText("Inventory or shopping data changed", in: staleApp)
        scrollTowardTopUntilVisible(staleMessage, in: staleApp)
        XCTAssertTrue(staleMessage.waitForExistence(timeout: 10))
        let refresh = element("recipe-shopping-load-preview", in: staleApp)
        scrollTowardTopUntilVisible(refresh, in: staleApp)
        XCTAssertTrue(refresh.exists)
        capture("Shopping_Stale_Preview_Refresh", app: staleApp)
        refresh.tap()
        let staleReady = element("recipe-shopping-safety-status", in: staleApp)
        XCTAssertTrue(element("recipe-shopping-servings", in: staleApp).waitForExistence(timeout: 10))
        scrollTo(staleReady, in: staleApp)
    }

    func testAmbiguousShoppingConfirmationRetainsExactRetry() {
        let app = launch(scenario: "shopping-retry")
        openShoppingPreview(app)
        element("recipe-shopping-confirm", in: app).tap()
        element("recipe-shopping-confirm-action", in: app).tap()

        let pendingStatus = element("recipe-shopping-pending-status", in: app)
        XCTAssertTrue(pendingStatus.waitForExistence(timeout: 10))
        let pendingLine = element("recipe-shopping-pending-line-0", in: app)
        XCTAssertTrue(pendingLine.waitForExistence(timeout: 5))
        XCTAssertTrue(pendingLine.label.contains("kangkong"))
        capture("Shopping_Confirmation_Retry_Pending", app: app)
        app.buttons["recipe-shopping-retry-pending"].tap()
        XCTAssertTrue(element("recipe-shopping-result-counts", in: app).waitForExistence(timeout: 10))
    }

    func testSourceLookupErrorKeepsRecipeAndCanRetry() {
        let app = launch(scenario: "source-error-once")
        openCookWithPip(app)
        element("cook-mode-myRecipes", in: app).tap()
        element("recipe-card-303", in: app).tap()

        XCTAssertTrue(element("recipe-detail-title", in: app).waitForExistence(timeout: 10))
        let sourceError = element("recipe-source-error", in: app)
        scrollTo(sourceError, in: app)
        XCTAssertTrue(sourceError.waitForExistence(timeout: 10))
        XCTAssertTrue(element("recipe-safety-status", in: app).exists)
        capture("Source_Error_Retry", app: app)
        element("recipe-source-retry", in: app).tap()
        waitUntilGone(sourceError)
    }

    func testDarkModeLargeTextAndSearchKeyboard() {
        let darkApp = launch(appearance: "dark")
        openCookWithPip(darkApp)
        capture("Cook_with_Pip_Dark_Mode", app: darkApp)

        darkApp.terminate()
        let largeApp = launch(dynamicType: "accessibility")
        openCookWithPip(largeApp)
        let firstRecipe = element("recipe-card-301", in: largeApp)
        scrollTo(firstRecipe, in: largeApp)
        XCTAssertTrue(firstRecipe.exists)
        let myRecipesMode = element("cook-mode-myRecipes", in: largeApp)
        XCTAssertTrue(myRecipesMode.waitForExistence(timeout: 10))
        scrollTo(myRecipesMode, in: largeApp)
        myRecipesMode.tap()
        let selectedMode = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value CONTAINS %@", "Selected"), object: myRecipesMode
        )
        XCTAssertEqual(XCTWaiter.wait(for: [selectedMode], timeout: 5), .completed)
        let householdRecipe = element("recipe-card-303", in: largeApp)
        scrollTo(householdRecipe, in: largeApp)
        XCTAssertTrue(householdRecipe.exists)
        let longRecipe = element("recipe-card-304", in: largeApp)
        scrollTo(longRecipe, in: largeApp)
        longRecipe.tap()
        XCTAssertTrue(element("recipe-detail-title", in: largeApp).exists)
        capture("Recipe_Detail_Large_Text_Filipino", app: largeApp)

        largeApp.terminate()
        let searchApp = launch()
        openCookWithPip(searchApp)
        let search = searchApp.searchFields.firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 10))
        search.tap()
        search.typeText("Laing")
        XCTAssertTrue(element("recipe-card-302", in: searchApp).waitForExistence(timeout: 10))
        capture("Cook_with_Pip_Search_Keyboard", app: searchApp)
    }

    private func launch(scenario: String = "default", appearance: String? = nil,
                        dynamicType: String? = nil) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments.append(contentsOf: [
            "-cook-with-pip-ui-tests",
            "-pip-ui-scenario", scenario,
            "-pip-ui-fixture-id", String(Int.random(in: 10_000...90_000))
        ])
        if let appearance {
            app.launchArguments.append(contentsOf: ["-pip-ui-appearance", appearance])
        }
        if let dynamicType {
            app.launchArguments.append(contentsOf: ["-pip-ui-type", dynamicType])
        }
        app.launch()
        return app
    }

    private func openCookWithPip(_ app: XCUIApplication) {
        let entry = element("cook-with-pip-entry", in: app)
        XCTAssertTrue(entry.waitForExistence(timeout: 10))
        entry.tap()
        XCTAssertTrue(element("cook-with-pip-introduction", in: app).waitForExistence(timeout: 10))
    }

    private func openCookNowRecipe(_ app: XCUIApplication) {
        openCookWithPip(app)
        let recipe = element("recipe-card-301", in: app)
        XCTAssertTrue(recipe.waitForExistence(timeout: 10))
        recipe.tap()
        XCTAssertTrue(element("recipe-detail-title", in: app).waitForExistence(timeout: 10))
    }

    private func openShoppingPreview(_ app: XCUIApplication) {
        openCookNowRecipe(app)
        let previewLink = element("recipe-shopping-preview-link", in: app)
        scrollTo(previewLink, in: app)
        previewLink.tap()
        let ready = element("recipe-shopping-safety-status", in: app)
        let retry = element("recipe-shopping-load-preview", in: app)
        let settings = element("recipe-shopping-servings", in: app)
        let previewLoaded = NSPredicate { _, _ in settings.exists || retry.exists }
        let loadExpectation = XCTNSPredicateExpectation(predicate: previewLoaded, object: app)
        XCTAssertEqual(XCTWaiter.wait(for: [loadExpectation], timeout: 10), .completed)
        if settings.exists {
            scrollTo(ready, in: app)
        }
    }

    private func navigateBack(_ app: XCUIApplication) {
        let back = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 5))
        back.tap()
    }

    private func scrollTo(_ target: XCUIElement, in app: XCUIApplication) {
        let scrollView = app.scrollViews.firstMatch
        for _ in 0..<12 where !target.exists {
            if scrollView.exists { scrollView.swipeUp() } else { app.swipeUp() }
        }
        for _ in 0..<12 where !target.exists {
            if scrollView.exists { scrollView.swipeDown() } else { app.swipeDown() }
        }
        XCTAssertTrue(target.exists, "Expected \(target.identifier) to appear after scrolling")
        let safeTop = app.frame.minY + 170
        let safeBottom = app.frame.maxY - 130
        for _ in 0..<8 {
            let frame = target.frame
            guard !frame.isNull, !frame.isInfinite, !frame.isEmpty,
                  frame.minY.isFinite, frame.maxY.isFinite else { break }
            if frame.minY >= safeTop && frame.maxY <= safeBottom { return }
            if frame.midY < safeTop {
                if scrollView.exists { scrollView.swipeDown() } else { app.swipeDown() }
            } else {
                if scrollView.exists { scrollView.swipeUp() } else { app.swipeUp() }
            }
        }
        let frame = target.frame
        XCTAssertTrue(frame.minY < safeBottom && frame.maxY > safeTop,
                      "Expected \(target.identifier) to be visible after scrolling")
    }

    private func scrollTowardTopUntilVisible(_ target: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<12 where !target.exists || !target.isHittable {
            app.swipeDown()
        }
        XCTAssertTrue(target.exists, "Expected \(target.identifier) to appear while scrolling toward the top")
        XCTAssertTrue(target.isHittable, "Expected \(target.identifier) to be visible while scrolling toward the top")
    }

    private func replaceText(_ field: XCUIElement, with value: String) {
        field.tap()
        let oldValue = field.value as? String ?? ""
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: oldValue.count) + value)
    }

    private func waitUntilGone(_ element: XCUIElement) {
        let expectation = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: element)
        XCTAssertEqual(XCTWaiter.wait(for: [expectation], timeout: 5), .completed)
    }

    private func appText(_ text: String, in app: XCUIApplication) -> XCUIElement {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch
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
