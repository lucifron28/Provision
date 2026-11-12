import XCTest

final class CookWithPipUITests: XCTestCase {
    func testHomeNavigationAndCaptureRecipeScreens() {
        let app = launch()
        let homeEntry = element("cook-with-pip-entry", in: app)
        XCTAssertTrue(homeEntry.waitForExistence(timeout: 10))
        XCTAssertTrue(element("ui-test-fixture-banner", in: app).exists)
        let emptyPantryTitle = element("home-empty-pantry-title", in: app)
        let emptyPantryGuidance = element("home-empty-pantry-guidance", in: app)
        XCTAssertTrue(emptyPantryTitle.waitForExistence(timeout: 5))
        XCTAssertTrue(emptyPantryGuidance.waitForExistence(timeout: 5))
        let homeViewport = visibleScrollFrame(of: app.scrollViews.firstMatch, in: app, inset: 8)
        XCTAssertTrue(emptyPantryGuidance.isHittable)
        XCTAssertGreaterThanOrEqual(emptyPantryGuidance.frame.minY, homeViewport.minY)
        XCTAssertLessThanOrEqual(emptyPantryGuidance.frame.maxY, homeViewport.maxY,
                                 "The home empty-pantry guidance stays fully visible on the first screen")
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
        nudgeContentDown(in: app, by: 0.055)
        XCTAssertTrue(instructions.isHittable)
        capture("Recipe_Detail_Instructions", app: app)
    }

    func testCookWithPipLoadingEmptyAndOfflineRecovery() {
        let loadingApp = launch(scenario: "recipes-loading")
        openCookWithPip(loadingApp)
        XCTAssertTrue(element("cook-with-pip-loading-state", in: loadingApp).waitForExistence(timeout: 5))
        capture("Cook_with_Pip_Loading", app: loadingApp)
        let releaseLoading = loadingApp.buttons["cook-with-pip-release-loading"]
        XCTAssertTrue(releaseLoading.waitForExistence(timeout: 5))
        releaseLoading.tap()
        XCTAssertTrue(element("cook-with-pip-loading-released", in: loadingApp).waitForExistence(timeout: 5))
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
        let partialIngredient = element("recipe-ingredient-1", in: app)
        scrollTargetIntoView(partialIngredient, inside: app.scrollViews["recipe-detail-scroll"], in: app)
        XCTAssertTrue(partialIngredient.isHittable)
        capture("Recipe_Detail_Partial_Missing", app: app)

        navigateBack(app)
        element("cook-mode-myRecipes", in: app).tap()
        element("recipe-card-303", in: app).tap()
        XCTAssertEqual(element("recipe-safety-status", in: app).label, "Review required")
        XCTAssertEqual(element("recipe-availability-status", in: app).label, "Unknown")
        let unknownIngredient = element("recipe-ingredient-name-0", in: app)
        scrollTargetIntoView(unknownIngredient, inside: app.scrollViews["recipe-detail-scroll"], in: app)
        XCTAssertTrue(unknownIngredient.isHittable)
        assertBelowNavigationBar(unknownIngredient, in: app)
        let reviewPreferences = element("recipe-review-preferences", in: app)
        let reviewLabels = element("recipe-review-product-labels", in: app)
        scrollTo(reviewPreferences, in: app)
        assertBelowNavigationBar(reviewPreferences, in: app)
        assertBelowNavigationBar(reviewLabels, in: app)
        let recipeTitle = element("recipe-detail-title", in: app)
        scrollTargetIntoView(recipeTitle, inside: app.scrollViews["recipe-detail-scroll"], in: app)
        assertBelowNavigationBar(recipeTitle, in: app)
        capture("Recipe_Detail_Review_Unknown", app: app)

        navigateBack(app)
        element("cook-mode-myRecipes", in: app).tap()
        let longRecipe = element("recipe-card-304", in: app)
        scrollTo(longRecipe, in: app)
        longRecipe.tap()
        XCTAssertEqual(element("recipe-safety-status", in: app).label, "Blocked")
        XCTAssertEqual(element("recipe-availability-status", in: app).label, "Missing")
        let longIngredient = element("recipe-ingredient-name-0", in: app)
        scrollTargetIntoView(longIngredient, inside: app.scrollViews["recipe-detail-scroll"], in: app)
        XCTAssertTrue(longIngredient.label.contains("talong na hiniwa nang pahaba"))
        capture("Recipe_Detail_Blocked_Long_Filipino", app: app)
        let instructions = element("recipe-instructions", in: app)
        scrollTargetIntoView(instructions, inside: app.scrollViews["recipe-detail-scroll"], in: app)
        nudgeContentDown(in: app, by: 0.09)
        XCTAssertTrue(instructions.isHittable)
        capture("Recipe_Detail_Scrolled", app: app)
    }

    func testPreferencesAndPackageLabelReviewScreens() {
        let app = launch()
        openCookWithPip(app)
        element("cook-with-pip-management", in: app).tap()
        element("cook-with-pip-preferences-link", in: app).tap()

        XCTAssertTrue(element("pip-preferences-save", in: app).waitForExistence(timeout: 10))
        let cuisines = element("pip-preferred-cuisines", in: app)
        XCTAssertEqual(cuisines.label, "Preferred cuisines")
        let milkAllergen = app.switches["pip-allergen-milk"]
        let milkSeverity = element("pip-allergen-severity-milk", in: app)
        let milkCrossContact = app.switches["pip-allergen-cross-contact-milk"]
        scrollTo(milkSeverity, in: app)
        XCTAssertTrue(milkAllergen.waitForExistence(timeout: 5))
        XCTAssertTrue(milkSeverity.isHittable)
        XCTAssertTrue(milkCrossContact.isHittable)
        XCTAssertEqual(milkAllergen.value as? String, "1")
        XCTAssertEqual(milkSeverity.value as? String, "Severe")
        XCTAssertEqual(milkCrossContact.value as? String, "1")
        element("pip-preferences-save", in: app).tap()
        let savedMessage = element("pip-preferences-success", in: app)
        for _ in 0..<6 where !savedMessage.exists { app.swipeDown() }
        XCTAssertTrue(savedMessage.waitForExistence(timeout: 10))
        scrollTo(milkAllergen, in: app)
        nudgeContentDown(in: app, by: -0.08)
        let allergyHeading = element("pip-preferences-allergies-heading", in: app)
        assertBelowNavigationBar(allergyHeading, in: app)
        XCTAssertTrue(milkAllergen.isHittable)
        XCTAssertTrue(milkSeverity.isHittable)
        XCTAssertTrue(milkCrossContact.isHittable)
        let preferencesViewport = visibleApplicationFrame(of: app, inset: 8)
        XCTAssertLessThanOrEqual(milkCrossContact.frame.maxY, preferencesViewport.maxY,
                                 "The declared-allergy controls stay inside the visible form area")
        XCTAssertEqual(milkAllergen.value as? String, "1")
        XCTAssertEqual(milkCrossContact.value as? String, "1")
        capture("Preferences_Allergy_Declared", app: app)

        navigateBack(app)
        element("cook-with-pip-product-labels-link", in: app).tap()
        XCTAssertTrue(element("pip-label-product-9903", in: app).waitForExistence(timeout: 10))
        capture("Product_Label_List", app: app)
        element("pip-label-product-9903", in: app).tap()
        XCTAssertTrue(element("pip-label-product-title", in: app).waitForExistence(timeout: 10))
        capture("Product_Label_Review", app: app)

        let milkDeclaration = element("pip-label-allergen-milk", in: app)
        scrollTo(milkDeclaration, in: app)
        milkDeclaration.tap()
        let declaredOption = element("pip-label-disposition-declared", in: app)
        XCTAssertTrue(declaredOption.waitForExistence(timeout: 5))
        declaredOption.tap()
        XCTAssertEqual(milkDeclaration.value as? String, "Declared on label")

        let source = element("pip-label-source-reference", in: app)
        scrollTo(source, in: app)
        source.tap()
        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        XCTAssertLessThan(source.frame.maxY, keyboard.frame.minY)
        typeTextAndWait("Synthetic", in: source)
        XCTAssertEqual(source.value as? String, "Synthetic")
        typeTextAndWait(" package", in: source)
        XCTAssertEqual(source.value as? String, "Synthetic package")
        typeTextAndWait(" label", in: source)
        XCTAssertEqual(source.value as? String, "Synthetic package label")
        let keyboardDone = element("pip-label-keyboard-done", in: app)
        XCTAssertTrue(keyboardDone.waitForExistence(timeout: 5))
        keyboardDone.tap()
        let keyboardDismissed = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "isHittable == false"), object: keyboard
        )
        XCTAssertEqual(XCTWaiter.wait(for: [keyboardDismissed], timeout: 5), .completed)
        let saveReview = element("pip-label-save-review", in: app)
        scrollTo(saveReview, in: app)
        XCTAssertTrue(saveReview.isEnabled, "A verified mapping and source reference enable saving the label review")
        XCTAssertTrue(saveReview.isHittable)
        saveReview.tap()
        let savedLabelMessage = element("pip-label-status-message", in: app)
        let saveError = element("pip-label-error", in: app)
        let didSave = savedLabelMessage.waitForExistence(timeout: 15)
        let saveFailure = saveError.exists ? saveError.label : "No save status appeared"
        XCTAssertTrue(didSave, "Expected the save result before checking the updated label: \(saveFailure)")
        XCTAssertTrue(savedLabelMessage.label.contains("Package label review recorded"))
        let currentStatus = element("pip-label-current-status", in: app)
        let packageDeclarationHeading = app.staticTexts["Package label declaration"].firstMatch
        let technicalDetails = element("pip-label-technical-details", in: app)
        scrollTo(technicalDetails, in: app)
        XCTAssertTrue(technicalDetails.isHittable)
        technicalDetails.tap()
        let reviewRevision = element("pip-label-review-revision", in: app)
        XCTAssertTrue(reviewRevision.waitForExistence(timeout: 5))
        scrollTo(reviewRevision, in: app)
        XCTAssertTrue(reviewRevision.label.contains("v1"))
        assertBelowNavigationBar(reviewRevision, in: app)
        scrollTo(technicalDetails, in: app)
        technicalDetails.tap()
        waitUntilGone(reviewRevision)
        scrollTo(currentStatus, in: app)
        XCTAssertTrue(currentStatus.waitForExistence(timeout: 10))
        XCTAssertTrue(currentStatus.label.contains("Current label review"))
        XCTAssertEqual(milkDeclaration.value as? String, "Declared on label")
        XCTAssertFalse(app.keyboards.firstMatch.isHittable, "Saving a label review dismisses the keyboard")
        let mappingVerified = element("pip-label-mapping-verified", in: app)
        let mappingType = element("pip-label-mapping-type", in: app)
        scrollTo(mappingType, in: app)
        assertBelowNavigationBar(mappingType, in: app)
        scrollTo(mappingVerified, in: app)
        assertBelowNavigationBar(mappingVerified, in: app)
        scrollTo(currentStatus, in: app)
        nudgeContentDown(in: app, by: -0.05)
        XCTAssertTrue(packageDeclarationHeading.waitForExistence(timeout: 5))
        assertBelowNavigationBar(packageDeclarationHeading, in: app)
        assertBelowNavigationBar(currentStatus, in: app)
        let currentLabelViewport = visibleApplicationFrame(of: app, inset: 8)
        XCTAssertLessThanOrEqual(currentStatus.frame.maxY, currentLabelViewport.maxY,
                                 "The saved declaration stays above the bottom safe area")
        capture("Product_Label_Saved_Keyboard_Dismissed", app: app)
        capture("Product_Label_Review_Current", app: app)
    }

    func testFormsStayReadableInDarkModeAndLargeText() {
        let darkPreferences = launch(appearance: "dark")
        openCookWithPip(darkPreferences)
        element("cook-with-pip-management", in: darkPreferences).tap()
        element("cook-with-pip-preferences-link", in: darkPreferences).tap()
        let savePreferences = element("pip-preferences-save", in: darkPreferences)
        XCTAssertTrue(savePreferences.waitForExistence(timeout: 10))
        XCTAssertTrue(savePreferences.isHittable)
        let milkSeverity = element("pip-allergen-severity-milk", in: darkPreferences)
        let milkCrossContact = darkPreferences.switches["pip-allergen-cross-contact-milk"]
        scrollTo(milkCrossContact, in: darkPreferences)
        nudgeContentDown(in: darkPreferences, by: -0.10)
        XCTAssertTrue(milkSeverity.isHittable)
        XCTAssertTrue(milkCrossContact.isHittable)
        XCTAssertTrue(milkCrossContact.label.contains("Milk"))
        let preferencesViewport = visibleApplicationFrame(of: darkPreferences, inset: 8)
        XCTAssertGreaterThanOrEqual(milkSeverity.frame.minY, preferencesViewport.minY)
        XCTAssertLessThanOrEqual(milkCrossContact.frame.maxY, preferencesViewport.maxY,
                                 "The allergy controls stay inside the dark-mode viewport")
        capture("Preferences_Allergy_Dark_Mode", app: darkPreferences)

        darkPreferences.terminate()
        let darkLabel = launch(appearance: "dark")
        openCookWithPip(darkLabel)
        element("cook-with-pip-management", in: darkLabel).tap()
        element("cook-with-pip-product-labels-link", in: darkLabel).tap()
        element("pip-label-product-9903", in: darkLabel).tap()
        let darkProductTitle = element("pip-label-product-title", in: darkLabel)
        XCTAssertTrue(darkProductTitle.waitForExistence(timeout: 10))
        XCTAssertTrue(darkProductTitle.isHittable)
        capture("Product_Label_Review_Dark_Mode", app: darkLabel)

        darkLabel.terminate()
        let largeLabel = launch(dynamicType: "accessibility")
        openCookWithPip(largeLabel)
        element("cook-with-pip-management", in: largeLabel).tap()
        element("cook-with-pip-product-labels-link", in: largeLabel).tap()
        element("pip-label-product-9903", in: largeLabel).tap()
        let productTitle = element("pip-label-product-title", in: largeLabel)
        XCTAssertTrue(productTitle.waitForExistence(timeout: 10))
        XCTAssertTrue(productTitle.isHittable)
        assertBelowNavigationBar(productTitle, in: largeLabel)
        let technicalDetails = element("pip-label-technical-details", in: largeLabel)
        XCTAssertTrue(technicalDetails.waitForExistence(timeout: 5))
        XCTAssertTrue(technicalDetails.isHittable)
        let serverVersion = element("pip-label-server-version", in: largeLabel)
        XCTAssertFalse(serverVersion.exists, "Technical metadata starts collapsed below the product details")
        capture("Product_Label_Review_Large_Text", app: largeLabel)
        technicalDetails.tap()
        XCTAssertTrue(serverVersion.waitForExistence(timeout: 5))
        scrollTo(serverVersion, in: largeLabel)
        XCTAssertTrue(serverVersion.label.contains("2026-11-09T00:00:00Z"))
        assertBelowNavigationBar(serverVersion, in: largeLabel)
        scrollTo(technicalDetails, in: largeLabel)
        technicalDetails.tap()
        waitUntilGone(serverVersion)
        let sourceField = element("pip-label-source-reference", in: largeLabel)
        let customAllergensHeading = element("pip-label-custom-allergens-heading", in: largeLabel)
        scrollTo(sourceField, in: largeLabel)
        XCTAssertEqual(sourceField.label, "Source reference")
        XCTAssertEqual(sourceField.placeholderValue, "Package label, URL, or label section")
        assertBelowNavigationBar(sourceField, in: largeLabel)
        let customAllergensField = element("pip-label-custom-allergens", in: largeLabel)
        scrollTo(customAllergensHeading, in: largeLabel)
        assertBelowNavigationBar(customAllergensHeading, in: largeLabel)
        assertBelowNavigationBar(customAllergensField, in: largeLabel)

        let milkDeclaration = element("pip-label-allergen-milk", in: largeLabel)
        let mappingNote = largeLabel.staticTexts[
            "A verified, complete mapping is required before a package label review can be recorded."
        ]
        scrollTo(milkDeclaration, in: largeLabel)
        nudgeContentDown(in: largeLabel, by: 0.16)
        XCTAssertTrue(mappingNote.waitForExistence(timeout: 5))
        assertBelowNavigationBar(mappingNote, in: largeLabel)
        XCTAssertTrue(milkDeclaration.isHittable)
        assertBelowNavigationBar(milkDeclaration, in: largeLabel)

        let mappingVerified = element("pip-label-mapping-verified", in: largeLabel)
        scrollTo(mappingVerified, in: largeLabel)
        nudgeContentDown(in: largeLabel, by: -0.16)
        assertBelowNavigationBar(mappingVerified, in: largeLabel)
        let labelViewport = visibleApplicationFrame(of: largeLabel, inset: 8)
        XCTAssertGreaterThanOrEqual(mappingVerified.frame.minY, labelViewport.minY,
                                     "The mapping confirmation control clears the navigation bar")
        XCTAssertLessThanOrEqual(mappingVerified.frame.maxY, labelViewport.maxY,
                                 "The mapping confirmation control stays fully inside the large-text viewport")
        capture("Product_Label_Review_Scrolled", app: largeLabel)
    }

    func testStaleProductLabelReviewIsShownAsStale() {
        let app = launch(scenario: "product-label-stale")
        openCookWithPip(app)
        element("cook-with-pip-management", in: app).tap()
        element("cook-with-pip-product-labels-link", in: app).tap()
        element("pip-label-product-9903", in: app).tap()

        XCTAssertTrue(element("pip-label-product-title", in: app).waitForExistence(timeout: 10))
        let milkDeclaration = element("pip-label-allergen-milk", in: app)
        let ingredientSearchButton = element("pip-label-search-ingredients", in: app)
        scrollTo(milkDeclaration, in: app)
        XCTAssertEqual(milkDeclaration.value as? String, "Declared on label")
        let status = element("pip-label-current-status", in: app)
        let packageDeclarationHeading = app.staticTexts["Package label declaration"].firstMatch
        scrollTo(status, in: app)
        XCTAssertTrue(status.waitForExistence(timeout: 10))
        XCTAssertTrue(status.label.contains("no longer current"))
        let mappingVerified = element("pip-label-mapping-verified", in: app)
        let mappingType = element("pip-label-mapping-type", in: app)
        let ingredientSearchField = element("pip-label-ingredient-search", in: app)
        scrollTo(mappingType, in: app)
        assertBelowNavigationBar(mappingType, in: app)
        scrollTo(mappingVerified, in: app)
        assertBelowNavigationBar(mappingVerified, in: app)
        scrollTo(status, in: app)
        nudgeContentDown(in: app, by: 0.32)
        assertBelowNavigationBar(mappingType, in: app)
        XCTAssertTrue(packageDeclarationHeading.waitForExistence(timeout: 5))
        assertBelowNavigationBar(packageDeclarationHeading, in: app)
        XCTAssertTrue(ingredientSearchField.waitForExistence(timeout: 5))
        assertBelowNavigationBar(ingredientSearchField, in: app)
        XCTAssertTrue(ingredientSearchButton.waitForExistence(timeout: 5))
        assertBelowNavigationBar(ingredientSearchButton, in: app)
        assertBelowNavigationBar(status, in: app)
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
        let ingredientName = element("recipe-ingredient-name-1", in: app)
        XCTAssertTrue(ingredientName.label.contains("calamansi"))
        capture("Recipe_Detail_Substitution_Applied", app: app)
    }

    func testShoppingPreviewEditsConsolidationAndExplicitConfirmation() {
        let app = launch()
        openShoppingPreview(app)
        let shoppingForm = app.descendants(matching: .any)
            .matching(identifier: "recipe-shopping-review-form").firstMatch
        XCTAssertEqual(element("recipe-shopping-safety-status", in: app).label, "Eligible")
        capture("Shopping_Preview_Ready", app: app)
        let unlinked = element("recipe-shopping-unlinked-9920", in: app)
        scrollTargetIntoView(unlinked, inside: shoppingForm, in: app)
        XCTAssertTrue(unlinked.exists)
        XCTAssertTrue(unlinked.isHittable)
        let unlinkedViewport = visibleScrollFrame(of: shoppingForm, in: app, inset: 8)
        XCTAssertGreaterThanOrEqual(unlinked.frame.minY, unlinkedViewport.minY)
        XCTAssertLessThanOrEqual(unlinked.frame.maxY, unlinkedViewport.maxY)
        capture("Shopping_Unlinked_Manual_Items", app: app)

        let includeOptional = app.switches["recipe-shopping-include-optional"]
        scrollTo(includeOptional, in: app)
        setSwitch(includeOptional, to: "1")
        let stalePreview = element("recipe-shopping-stale-preview", in: app)
        XCTAssertTrue(stalePreview.waitForExistence(timeout: 5))
        let refreshPreview = app.buttons["recipe-shopping-refresh-preview"]
        scrollTo(refreshPreview, in: app)
        XCTAssertTrue(refreshPreview.exists)
        XCTAssertTrue(refreshPreview.isHittable)
        refreshPreview.tap()
        let optionalIngredient = element("recipe-shopping-row-913", in: app)
        scrollTargetIntoView(optionalIngredient, inside: shoppingForm, in: app)
        XCTAssertTrue(optionalIngredient.waitForExistence(timeout: 10))
        XCTAssertFalse(stalePreview.exists)
        XCTAssertTrue(optionalIngredient.isHittable)
        assertBelowNavigationBar(optionalIngredient, in: app)
        let optionalViewport = visibleScrollFrame(of: shoppingForm, in: app, inset: 8)
        XCTAssertGreaterThanOrEqual(optionalIngredient.frame.minY, optionalViewport.minY)
        XCTAssertLessThanOrEqual(optionalIngredient.frame.maxY, optionalViewport.maxY,
                                 "The optional ingredient row stays fully inside the shopping viewport")
        capture("Shopping_Optional_Ingredients", app: app)

        let target = element("recipe-shopping-target-901", in: app)
        scrollTo(target, in: app)
        replaceText(target, with: "125")
        XCTAssertEqual(target.value as? String, "125")
        let done = element("recipe-shopping-keyboard-done", in: app)
        XCTAssertTrue(done.waitForExistence(timeout: 5))
        done.tap()
        capture("Shopping_Line_Exact_Quantity_Edited", app: app)

        let consolidate = app.switches["recipe-shopping-consolidate-914"]
        scrollTargetIntoView(consolidate, inside: shoppingForm, in: app)
        setSwitch(consolidate, to: "1")
        scrollTargetIntoView(consolidate, inside: shoppingForm, in: app)
        XCTAssertTrue(consolidate.isHittable)
        assertBelowNavigationBar(consolidate, in: app)
        let consolidationViewport = visibleApplicationFrame(of: app, inset: 8)
        XCTAssertGreaterThanOrEqual(consolidate.frame.minY, consolidationViewport.minY)
        XCTAssertLessThanOrEqual(consolidate.frame.maxY, consolidationViewport.maxY,
                                 "The consolidation control stays inside the shopping viewport")
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

    func testShoppingPreviewDarkAndLargeTextStates() {
        let darkApp = launch(appearance: "dark")
        openShoppingPreview(darkApp)
        let darkStatus = element("recipe-shopping-safety-status", in: darkApp)
        let darkConfirm = darkApp.buttons["recipe-shopping-confirm"]
        XCTAssertTrue(darkStatus.isHittable)
        XCTAssertTrue(darkConfirm.isHittable)
        capture("Shopping_Preview_Dark_Mode", app: darkApp)

        darkApp.terminate()
        let largeApp = launch(dynamicType: "accessibility")
        openShoppingPreview(largeApp)
        let servings = element("recipe-shopping-servings", in: largeApp)
        scrollTo(servings, in: largeApp)
        XCTAssertTrue(servings.isHittable)
        assertBelowNavigationBar(servings, in: largeApp)
        let confirm = largeApp.buttons["recipe-shopping-confirm"]
        XCTAssertTrue(confirm.isHittable, "The confirmation action stays reachable at accessibility text sizes")
        let refresh = element("recipe-shopping-refresh-preview", in: largeApp)
        XCTAssertTrue(refresh.isHittable, "Refresh remains visible at accessibility text sizes")
        let reviewForm = largeApp.descendants(matching: .any)
            .matching(identifier: "recipe-shopping-review-form").firstMatch
        let largeTextViewport = visibleScrollFrame(of: reviewForm, in: largeApp, inset: 8)
        XCTAssertGreaterThanOrEqual(refresh.frame.minY, largeTextViewport.minY)
        XCTAssertLessThanOrEqual(refresh.frame.maxY, largeTextViewport.maxY,
                                 "The Refresh action stays above the bottom safe area")
        capture("Shopping_Preview_Large_Text", app: largeApp)

        let revisionDetails = element("recipe-shopping-revision-details", in: largeApp)
        scrollTo(revisionDetails, in: largeApp)
        XCTAssertTrue(revisionDetails.isHittable)
        XCTAssertEqual(revisionDetails.value as? String, "Collapsed")
        revisionDetails.coordinate(withNormalizedOffset: CGVector(dx: 0.92, dy: 0.5)).tap()
        let expanded = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "Expanded"), object: revisionDetails
        )
        XCTAssertEqual(XCTWaiter.wait(for: [expanded], timeout: 5), .completed)
        let listRevision = element("recipe-shopping-list-revision", in: largeApp)
        scrollTargetIntoView(listRevision, inside: reviewForm, in: largeApp)
        XCTAssertTrue(listRevision.isHittable)
        XCTAssertTrue(listRevision.label.contains("Shopping list"))
        let pantryRevision = element("recipe-shopping-pantry-revision", in: largeApp)
        XCTAssertTrue(pantryRevision.waitForExistence(timeout: 5))
        XCTAssertTrue(pantryRevision.label.contains("Pantry"))
        let expiration = element("recipe-shopping-expiration-value", in: largeApp)
        XCTAssertTrue(expiration.waitForExistence(timeout: 5))
        XCTAssertFalse(expiration.label.isEmpty)
        nudgeContentDown(in: largeApp, by: 0.04)
        capture("Shopping_Preview_Revision_Details_Large_Text", app: largeApp)
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
        setSwitch(acknowledgement, to: "1")
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
        let offlineError = element("recipe-shopping-error", in: offlineApp)
        XCTAssertTrue(offlineError.waitForExistence(timeout: 10))
        XCTAssertEqual(offlineError.label, "You're offline. Reconnect and load a fresh preview.")
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

    func testAmbiguousShoppingConfirmationSurvivesAppRelaunch() {
        let fixtureID = Int.random(in: 10_000...90_000)
        let app = launch(scenario: "shopping-restart", fixtureID: fixtureID, useKeychain: true)
        openShoppingPreview(app)
        let confirm = app.buttons["recipe-shopping-confirm"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 10))
        XCTAssertTrue(confirm.isHittable, "The shopping confirmation action stays in the navigation toolbar")
        confirm.tap()
        let confirmAction = element("recipe-shopping-confirm-action", in: app)
        XCTAssertTrue(confirmAction.waitForExistence(timeout: 10))
        confirmAction.tap()

        let pendingStatus = element("recipe-shopping-pending-status", in: app)
        XCTAssertTrue(pendingStatus.waitForExistence(timeout: 10))
        let retryMessage = element("recipe-shopping-error", in: app)
        XCTAssertTrue(retryMessage.waitForExistence(timeout: 5))
        let retryCopyVisible = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label CONTAINS %@", "Retry it without editing"),
            object: retryMessage
        )
        XCTAssertEqual(XCTWaiter.wait(for: [retryCopyVisible], timeout: 10), .completed)
        XCTAssertFalse(retryMessage.label.contains("Network connection failed"))
        let pendingLine = element("recipe-shopping-pending-line-0", in: app)
        XCTAssertTrue(pendingLine.waitForExistence(timeout: 10))
        XCTAssertTrue(pendingLine.label.contains("kangkong"))
        scrollTo(pendingLine, in: app)
        capture("Shopping_Confirmation_Retry_Pending", app: app)
        app.terminate()

        let relaunched = launch(scenario: "shopping-restart", fixtureID: fixtureID, useKeychain: true)
        openShoppingPreview(relaunched, timeout: 30)
        let relaunchedPending = element("recipe-shopping-pending-line-0", in: relaunched)
        XCTAssertTrue(relaunchedPending.waitForExistence(timeout: 10))
        XCTAssertTrue(relaunchedPending.label.contains("kangkong"))
        let retryPending = relaunched.buttons["recipe-shopping-retry-pending"]
        scrollTo(retryPending, in: relaunched)
        retryPending.tap()
        let resultCounts = relaunched.staticTexts["recipe-shopping-result-counts"]
        XCTAssertTrue(resultCounts.waitForExistence(timeout: 10))
        XCTAssertEqual(resultCounts.label, "Created 2 · Updated 0 · Unchanged 0 · Consolidated 0")

        let viewShoppingList = relaunched.buttons["recipe-shopping-view-list"]
        XCTAssertTrue(viewShoppingList.waitForExistence(timeout: 10))
        viewShoppingList.tap()
        XCTAssertTrue(relaunched.navigationBars["Shopping List"].waitForExistence(timeout: 10))
        let shoppingItemNames = relaunched.staticTexts.matching(
            NSPredicate(format: "identifier BEGINSWITH %@", "shopping-list-item-name-")
        )
        let twoPersistedRows = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "count == 2"), object: shoppingItemNames
        )
        XCTAssertEqual(XCTWaiter.wait(for: [twoPersistedRows], timeout: 10), .completed,
                       "An exact retry must leave only the two server-confirmed shopping rows")
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
        nudgeContentDown(in: app, by: -0.04)
        assertBelowNavigationBar(sourceError, in: app)
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
        let largeTitle = element("recipe-detail-title", in: largeApp)
        XCTAssertTrue(largeTitle.waitForExistence(timeout: 10))
        XCTAssertTrue(largeTitle.isHittable)
        XCTAssertTrue(largeTitle.label.contains("mahahabang pangalan ng sangkap"))
        assertBelowNavigationBar(largeTitle, in: largeApp)
        let safetyStatus = element("recipe-safety-status", in: largeApp)
        XCTAssertTrue(safetyStatus.waitForExistence(timeout: 10))
        XCTAssertTrue(safetyStatus.isHittable, "The food-safety decision stays visible below the large recipe title")
        assertBelowNavigationBar(safetyStatus, in: largeApp)
        let availabilityStatus = element("recipe-availability-status", in: largeApp)
        XCTAssertTrue(availabilityStatus.waitForExistence(timeout: 10))
        XCTAssertTrue(availabilityStatus.isHittable, "Pantry availability remains visible alongside food safety")
        let recipeDetailScroll = largeApp.scrollViews["recipe-detail-scroll"]
        let recipeViewport = visibleScrollFrame(of: recipeDetailScroll, in: largeApp, inset: 8)
        XCTAssertLessThanOrEqual(availabilityStatus.frame.maxY, recipeViewport.maxY,
                                 "The pantry status badge stays fully above the bottom safe area")
        let largeSummary = element("recipe-detail-summary", in: largeApp)
        XCTAssertTrue(largeSummary.waitForExistence(timeout: 10))
        XCTAssertTrue(largeSummary.label.contains("long Filipino ingredient names"))
        let safetyNotice = element("recipe-safety-notice", in: largeApp)
        XCTAssertTrue(safetyNotice.waitForExistence(timeout: 5))
        capture("Recipe_Detail_Large_Text_Filipino", app: largeApp)
        scrollTo(safetyNotice, in: largeApp)
        nudgeContentDown(in: largeApp, by: 0.10)
        XCTAssertTrue(safetyNotice.isHittable)
        assertBelowNavigationBar(safetyNotice, in: largeApp)
        let safetyViewport = visibleScrollFrame(of: recipeDetailScroll, in: largeApp, inset: 8)
        XCTAssertGreaterThanOrEqual(safetyNotice.frame.minY, safetyViewport.minY)
        XCTAssertLessThanOrEqual(safetyNotice.frame.maxY, safetyViewport.maxY,
                                 "The full safety notice stays visible after scrolling at large text sizes")
        capture("Recipe_Detail_Large_Text_Safety_Filipino", app: largeApp)
        scrollTargetIntoView(largeSummary, inside: recipeDetailScroll, in: largeApp)
        nudgeContentDown(in: largeApp, by: -0.23)
        XCTAssertTrue(largeSummary.isHittable)
        assertBelowNavigationBar(largeSummary, in: largeApp)
        let summaryViewport = visibleScrollFrame(of: recipeDetailScroll, in: largeApp, inset: 8)
        XCTAssertGreaterThanOrEqual(largeSummary.frame.minY, summaryViewport.minY)
        XCTAssertLessThanOrEqual(largeSummary.frame.maxY, summaryViewport.maxY,
                                 "The long recipe summary stays fully visible at large text sizes")
        capture("Recipe_Detail_Large_Text_Summary_Filipino", app: largeApp)
        let longIngredient = element("recipe-ingredient-name-0", in: largeApp)
        let requiredIngredientsHeading = largeApp.staticTexts["Required ingredients"].firstMatch
        scrollTargetIntoView(requiredIngredientsHeading, inside: recipeDetailScroll, in: largeApp)
        XCTAssertTrue(longIngredient.isHittable)
        XCTAssertTrue(longIngredient.label.contains("talong na hiniwa nang pahaba"))
        XCTAssertTrue(requiredIngredientsHeading.waitForExistence(timeout: 5))
        assertBelowNavigationBar(requiredIngredientsHeading, in: largeApp)
        assertBelowNavigationBar(longIngredient, in: largeApp)
        let ingredientViewport = visibleScrollFrame(
            of: largeApp.scrollViews["recipe-detail-scroll"], in: largeApp, inset: 8
        )
        XCTAssertLessThanOrEqual(longIngredient.frame.maxY, ingredientViewport.maxY,
                                 "The long ingredient name stays fully above the bottom safe area")
        capture("Recipe_Ingredient_Long_Filipino", app: largeApp)

        largeApp.terminate()
        let searchApp = launch()
        openCookWithPip(searchApp)
        element("cook-mode-myRecipes", in: searchApp).tap()
        let search = element("cook-with-pip-search", in: searchApp)
        XCTAssertTrue(search.waitForExistence(timeout: 10))
        search.tap()
        let keyboard = searchApp.keyboards.firstMatch
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        XCTAssertLessThan(search.frame.maxY, keyboard.frame.minY)
        let keyboardDone = element("cook-with-pip-search-keyboard-done", in: searchApp)
        XCTAssertTrue(keyboardDone.waitForExistence(timeout: 5))
        XCTAssertTrue(keyboardDone.isHittable)
        let searchMyRecipesMode = searchApp.buttons["cook-mode-myRecipes"]
        XCTAssertTrue(searchMyRecipesMode.waitForExistence(timeout: 5))
        XCTAssertFalse(keyboardDone.frame.intersects(searchMyRecipesMode.frame),
                       "The search Done action must not cover the My Recipes filter")
        let recipeModeButtons = [
            searchApp.buttons["cook-mode-cookNow"],
            searchApp.buttons["cook-mode-almostThere"],
            searchMyRecipesMode
        ]
        for button in recipeModeButtons {
            XCTAssertTrue(button.isHittable, "The recipe filter remains usable while search is focused")
            XCTAssertGreaterThanOrEqual(button.frame.minY, keyboardDone.frame.maxY,
                                        "The pinned recipe filters stay below the search Done action")
            XCTAssertLessThanOrEqual(button.frame.maxY, keyboard.frame.minY - 8,
                                     "The recipe filter stays above the software keyboard")
        }
        capture("Cook_with_Pip_Search_Keyboard", app: searchApp)
        search.typeText("Laing")
        let matchingRecipe = element("recipe-card-302", in: searchApp)
        XCTAssertTrue(matchingRecipe.waitForExistence(timeout: 10))
        XCTAssertGreaterThanOrEqual(matchingRecipe.frame.minY, search.frame.maxY)
        let recipeScrollView = searchApp.scrollViews["cook-with-pip-recipe-list-scroll"]
        XCTAssertTrue(recipeScrollView.exists)
        keyboardDone.tap()
        let keyboardDismissed = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "isHittable == false"),
            object: keyboard
        )
        XCTAssertEqual(XCTWaiter.wait(for: [keyboardDismissed], timeout: 5), .completed)
        for _ in 0..<5 where !matchingRecipe.isHittable {
            recipeScrollView.swipeUp()
        }
        XCTAssertTrue(search.exists)
        XCTAssertGreaterThanOrEqual(matchingRecipe.frame.minY, search.frame.maxY)
        XCTAssertTrue(matchingRecipe.isHittable)
        capture("My_Recipes_Search_Scrolled", app: searchApp)
    }

    func testShoppingPreviewExpiredIsNotConfirmable() {
        let app = launch(scenario: "shopping-expired")
        openShoppingPreview(app)
        let revisionDetails = element("recipe-shopping-revision-details", in: app)
        scrollTo(revisionDetails, in: app)
        XCTAssertEqual(revisionDetails.value as? String, "Collapsed")
        revisionDetails.coordinate(withNormalizedOffset: CGVector(dx: 0.92, dy: 0.5)).tap()
        let expandedDetails = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "Expanded"), object: revisionDetails
        )
        XCTAssertEqual(XCTWaiter.wait(for: [expandedDetails], timeout: 5), .completed)
        let expiration = element("recipe-shopping-expiration-value", in: app)
        XCTAssertTrue(expiration.waitForExistence(timeout: 10))
        XCTAssertFalse(expiration.label.isEmpty)
        XCTAssertTrue(element("recipe-shopping-expired", in: app).exists)
        let confirm = app.buttons["recipe-shopping-confirm"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 5))
        XCTAssertFalse(confirm.isEnabled)
        capture("Shopping_Preview_Expired", app: app)
    }

    private func launch(scenario: String = "default", appearance: String? = nil,
                        dynamicType: String? = nil, fixtureID: Int? = nil,
                        useKeychain: Bool = false) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments.append(contentsOf: [
            "-cook-with-pip-ui-tests",
            "-pip-ui-scenario", scenario,
            "-pip-ui-fixture-id", String(fixtureID ?? Int.random(in: 10_000...90_000))
        ])
        if useKeychain { app.launchArguments.append(contentsOf: ["-pip-ui-use-keychain", "1"]) }
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

    private func openShoppingPreview(_ app: XCUIApplication, timeout: TimeInterval = 10) {
        openCookWithPip(app)
        let myRecipes = app.buttons["cook-mode-myRecipes"]
        XCTAssertTrue(myRecipes.waitForExistence(timeout: 10))
        scrollTo(myRecipes, in: app)
        XCTAssertTrue(myRecipes.isHittable)
        myRecipes.tap()
        let myRecipesSelected = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "Selected"), object: myRecipes
        )
        XCTAssertEqual(XCTWaiter.wait(for: [myRecipesSelected], timeout: 10), .completed)

        let recipe = app.buttons["recipe-card-305"]
        let recipeList = app.scrollViews["cook-with-pip-recipe-list-scroll"]
        XCTAssertTrue(recipeList.waitForExistence(timeout: 5))
        for _ in 0..<12 where !recipe.exists { recipeList.swipeUp() }
        XCTAssertTrue(recipe.waitForExistence(timeout: 10))
        XCTAssertTrue(recipe.label.contains("Test Recipe: Ginataang Kangkong"))
        scrollTargetIntoView(recipe, inside: recipeList, in: app)
        recipe.tap()
        let recipeTitle = app.staticTexts["recipe-detail-title"]
        XCTAssertTrue(recipeTitle.waitForExistence(timeout: 10),
                      "Tapping the visible saved recipe should open its detail screen")
        let previewLink = app.buttons["recipe-shopping-preview-link"]
        let recipeDetail = app.scrollViews["recipe-detail-scroll"]
        for _ in 0..<12 where !previewLink.isHittable { recipeDetail.swipeUp() }
        XCTAssertTrue(previewLink.isHittable, "The shopping preview link stays available from recipe details")
        previewLink.tap()
        let ready = element("recipe-shopping-safety-status", in: app)
        let retry = element("recipe-shopping-load-preview", in: app)
        let pending = element("recipe-shopping-pending-status", in: app)
        let recovery = element("recipe-shopping-recovery-retry", in: app)
        let settings = element("recipe-shopping-servings", in: app)
        let previewLoaded = NSPredicate { _, _ in settings.exists || retry.exists || pending.exists || recovery.exists }
        let loadExpectation = XCTNSPredicateExpectation(predicate: previewLoaded, object: app)
        XCTAssertEqual(XCTWaiter.wait(for: [loadExpectation], timeout: timeout), .completed)
        if settings.exists {
            XCTAssertTrue(ready.waitForExistence(timeout: 10))
            scrollTo(ready, in: app)
        }
    }

    private func scrollTargetIntoView(_ target: XCUIElement, inside container: XCUIElement, in app: XCUIApplication) {
        XCTAssertTrue(container.waitForExistence(timeout: 5), "Expected the identified scroll container")
        for _ in 0..<16 where !target.exists { container.swipeUp() }
        XCTAssertTrue(target.waitForExistence(timeout: 10), "Expected \(target.identifier) before scrolling")

        let inset: CGFloat = 20
        for _ in 0..<12 {
            let targetFrame = target.frame
            guard !targetFrame.isNull, !targetFrame.isEmpty else {
                container.swipeUp()
                continue
            }

            let viewport = visibleScrollFrame(of: container, in: app, inset: inset)
            guard !viewport.isNull, !viewport.isEmpty else {
                container.swipeUp()
                continue
            }
            let fullyVisible = targetFrame.minY >= viewport.minY && targetFrame.maxY <= viewport.maxY
            if target.isHittable && fullyVisible { return }

            if targetFrame.minY < viewport.minY {
                container.swipeDown()
            } else {
                container.swipeUp()
            }
        }

        let targetFrame = target.frame
        let viewport = visibleScrollFrame(of: container, in: app, inset: inset)
        XCTAssertTrue(target.isHittable, "Expected \(target.identifier) to be hittable after scrolling")
        XCTAssertTrue(targetFrame.minY >= viewport.minY && targetFrame.maxY <= viewport.maxY,
                      "Expected \(target.identifier) to clear navigation and system overlays inside the scroll viewport")
    }

    private func visibleScrollFrame(of container: XCUIElement, in app: XCUIApplication, inset: CGFloat) -> CGRect {
        let frame = container.frame
        let navigationBar = app.navigationBars.firstMatch
        let top = max(frame.minY + inset,
                      navigationBar.exists ? navigationBar.frame.maxY + inset : frame.minY + inset)
        let keyboard = app.keyboards.firstMatch
        let tabBar = app.tabBars.firstMatch
        let bottom = min(frame.maxY - inset,
                         keyboard.exists ? keyboard.frame.minY - inset
                            : (tabBar.exists ? tabBar.frame.minY - inset : app.frame.maxY - inset))
        return CGRect(x: frame.minX, y: top, width: frame.width, height: max(0, bottom - top))
    }

    private func visibleApplicationFrame(of app: XCUIApplication, inset: CGFloat) -> CGRect {
        let frame = app.frame
        let navigationBar = app.navigationBars.firstMatch
        let top = max(frame.minY + inset,
                      navigationBar.exists ? navigationBar.frame.maxY + inset : frame.minY + inset)
        let keyboard = app.keyboards.firstMatch
        let tabBar = app.tabBars.firstMatch
        let bottom = min(frame.maxY - inset,
                         keyboard.exists ? keyboard.frame.minY - inset
                            : (tabBar.exists ? tabBar.frame.minY - inset : frame.maxY - inset))
        return CGRect(x: frame.minX, y: top, width: frame.width, height: max(0, bottom - top))
    }

    private func navigateBack(_ app: XCUIApplication) {
        let back = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 5))
        back.tap()
    }

    private func assertBelowNavigationBar(_ target: XCUIElement, in app: XCUIApplication) {
        let navigationBar = app.navigationBars.firstMatch
        XCTAssertTrue(navigationBar.waitForExistence(timeout: 5))
        XCTAssertTrue(target.isHittable, "Expected \(target.identifier) to be visible and interactable")
        XCTAssertGreaterThanOrEqual(target.frame.minY, navigationBar.frame.maxY - 1,
                                    "Expected \(target.identifier) to clear the navigation bar")
    }

    private func nudgeContentDown(in app: XCUIApplication, by fraction: CGFloat) {
        let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.3))
        let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.3 + fraction))
        start.press(forDuration: 0.2, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.1)
    }

    private func scrollTo(_ target: XCUIElement, in app: XCUIApplication) {
        let scrollView = app.scrollViews.firstMatch
        for _ in 0..<16 where !target.exists {
            if scrollView.exists { scrollView.swipeUp() } else { app.swipeUp() }
        }
        for _ in 0..<16 where !target.exists {
            if scrollView.exists { scrollView.swipeDown() } else { app.swipeDown() }
        }
        for _ in 0..<24 {
            guard target.exists else { break }
            let frame = target.frame
            guard !frame.isNull, !frame.isInfinite, !frame.isEmpty,
                  frame.minY.isFinite, frame.maxY.isFinite else { break }
            let navigationBar = app.navigationBars.firstMatch
            let safeTop = navigationBar.exists ? navigationBar.frame.maxY + 44 : app.frame.minY + 120
            let keyboard = app.keyboards.firstMatch
            let tabBar = app.tabBars.firstMatch
            let safeBottom = keyboard.exists ? keyboard.frame.minY - 8
                : (tabBar.exists ? tabBar.frame.minY - 8 : app.frame.maxY - 40)
            if frame.midY >= safeTop && frame.midY <= safeBottom && target.isHittable { return }
            if frame.midY < safeTop {
                if scrollView.exists { scrollView.swipeDown() } else { app.swipeDown() }
            } else {
                if scrollView.exists { scrollView.swipeUp() } else { app.swipeUp() }
            }
        }
        XCTAssertTrue(target.exists, "Expected \(target.identifier) to appear after scrolling")
        let frame = target.frame
        let navigationBar = app.navigationBars.firstMatch
        let safeTop = navigationBar.exists ? navigationBar.frame.maxY + 44 : app.frame.minY + 120
        let keyboard = app.keyboards.firstMatch
        let tabBar = app.tabBars.firstMatch
        let safeBottom = keyboard.exists ? keyboard.frame.minY - 8
            : (tabBar.exists ? tabBar.frame.minY - 8 : app.frame.maxY - 40)
        XCTAssertTrue(target.isHittable && frame.midY >= safeTop && frame.midY <= safeBottom,
                      "Expected \(target.identifier) to be visible after scrolling")
    }

    private func setSwitch(_ toggle: XCUIElement, to value: String) {
        XCTAssertTrue(toggle.waitForExistence(timeout: 5))
        if toggle.value as? String != value {
            XCTAssertTrue(toggle.isHittable)
            toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.92, dy: 0.5)).tap()
        }
        let expectedValue = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", value), object: toggle
        )
        XCTAssertEqual(XCTWaiter.wait(for: [expectedValue], timeout: 5), .completed,
                        "Expected \(toggle.identifier) to have value \(value); found \(String(describing: toggle.value))")
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

    private func typeTextAndWait(_ text: String, in field: XCUIElement) {
        let expectedValue = (field.value as? String ?? "") + text
        field.typeText(text)
        let typedText = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", expectedValue),
            object: field
        )
        XCTAssertEqual(XCTWaiter.wait(for: [typedText], timeout: 10), .completed,
                        "Expected \(field.identifier) to receive the complete keyboard input")
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
        guard ProcessInfo.processInfo.environment["PROVISION_SKIP_UI_SCREENSHOTS"] != "1" else { return }
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
