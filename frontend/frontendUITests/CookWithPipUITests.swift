import XCTest
@testable import frontend

final class CookWithPipUITests: XCTestCase {
    func testPipChatConsentConversationAndValidatedRecipeAction() {
        let app = launch()
        openCookWithPip(app)
        let chatLink = element("cook-with-pip-chat-link", in: app)
        XCTAssertTrue(chatLink.waitForExistence(timeout: 10))
        chatLink.tap()

        XCTAssertTrue(element("pip-chat-privacy-card", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("pip-chat-empty-state", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("pip-chat-consent-chat", in: app).exists)
        XCTAssertTrue(element("pip-chat-consent-allergies", in: app).exists)
        capturePipChat("Pip_Chat_Empty", app: app)

        let input = element("pip-chat-input", in: app)
        XCTAssertTrue(input.waitForExistence(timeout: 5))
        input.tap()
        input.typeText("Anong lulutuin natin?")
        app.buttons["pip-chat-send"].tap()

        let reply = app.staticTexts[
            "Sige, puwede tayong tumingin sa household recipes. Check the verified recipe details in Cook with Pip."
        ]
        XCTAssertTrue(reply.waitForExistence(timeout: 10))
        capturePipChat("Pip_Chat_Conversation", app: app)
        XCTAssertTrue(element("pip-chat-recipe-card-301", in: app).exists,
                      "Recipe suggestions are rendered as validated household cards")

        let openRecipe = element("pip-chat-open-recipe-301", in: app)
        XCTAssertTrue(openRecipe.waitForExistence(timeout: 5))
        openRecipe.tap()
        XCTAssertTrue(element("recipe-detail-title", in: app).waitForExistence(timeout: 10))
    }

    func testPipChatShoppingActionOpensTheExistingReviewScreen() {
        let app = launch()
        openCookWithPip(app)
        element("cook-with-pip-chat-link", in: app).tap()

        let input = element("pip-chat-input", in: app)
        XCTAssertTrue(input.waitForExistence(timeout: 10))
        input.tap()
        input.typeText("What should I buy?")
        app.buttons["pip-chat-send"].tap()

        let previewAction = element("pip-chat-open-shopping-preview-301", in: app)
        XCTAssertTrue(previewAction.waitForExistence(timeout: 10))
        previewAction.tap()

        XCTAssertTrue(element("recipe-shopping-safety-status", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("recipe-shopping-confirm", in: app).exists,
                      "Chat opens the existing preview; the household must still review and confirm it")
    }

    func testPipChatPrivacyControlsAtAccessibilitySizeInDarkMode() {
        let app = launch(appearance: "dark", dynamicType: "accessibility")
        openCookWithPip(app)
        element("cook-with-pip-chat-link", in: app).tap()

        let chatConsent = app.switches["pip-chat-consent-chat"]
        let allergyConsent = app.switches["pip-chat-consent-allergies"]
        XCTAssertTrue(chatConsent.waitForExistence(timeout: 10))
        XCTAssertTrue(allergyConsent.waitForExistence(timeout: 10))
        let chatScroll = element("pip-chat-scroll", in: app)
        scrollTargetIntoView(chatConsent, inside: chatScroll, in: app)
        XCTAssertTrue(chatConsent.isHittable)
        scrollTargetIntoView(allergyConsent, inside: chatScroll, progressAnchor: chatConsent, in: app)
        XCTAssertTrue(allergyConsent.isHittable)
        capturePipChat("Pip_Chat_Dark_Large_Text", app: app)
    }

    func testHomeNavigationAndCaptureRecipeScreens() {
        let app = launch()
        let homeEntry = element("cook-with-pip-entry", in: app)
        XCTAssertTrue(homeEntry.waitForExistence(timeout: 10))
        XCTAssertTrue(element("ui-test-fixture-banner", in: app).exists)
        let emptyPantryTitle = element("home-empty-pantry-title", in: app)
        let emptyPantryGuidance = element("home-empty-pantry-guidance", in: app)
        XCTAssertTrue(emptyPantryTitle.waitForExistence(timeout: 5))
        XCTAssertTrue(emptyPantryGuidance.waitForExistence(timeout: 5))
        XCTAssertTrue(emptyPantryGuidance.isHittable,
                      "The home empty-pantry guidance remains accessible on the first screen")
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
        scrollTargetIntoView(instructions, inside: app.scrollViews["recipe-detail-scroll"], in: app)
        XCTAssertTrue(instructions.exists)
        XCTAssertTrue(instructions.isHittable,
                      "Recipe instructions remain visible after scrolling the recipe detail")
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
        assertReachable(unknownIngredient, in: app)
        let reviewPreferences = element("recipe-review-preferences", in: app)
        let reviewLabels = element("recipe-review-product-labels", in: app)
        scrollTargetIntoView(reviewPreferences, inside: app.scrollViews["recipe-detail-scroll"], in: app)
        assertReachable(reviewPreferences, in: app)
        scrollTargetIntoView(
            reviewLabels,
            inside: app.scrollViews["recipe-detail-scroll"],
            progressAnchor: reviewPreferences,
            in: app
        )
        assertReachable(reviewLabels, in: app)
        let recipeTitle = element("recipe-detail-title", in: app)
        scrollTargetIntoView(recipeTitle, inside: app.scrollViews["recipe-detail-scroll"], in: app)
        assertReachable(recipeTitle, in: app)
        capture("Recipe_Detail_Review_Unknown", app: app)

        navigateBack(app)
        element("cook-mode-myRecipes", in: app).tap()
        let longRecipe = element("recipe-card-304", in: app)
        scrollTargetIntoView(longRecipe, inside: app.scrollViews["cook-with-pip-recipe-list-scroll"], in: app)
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

    func testPreferencesAllergySettings() {
        let app = launch()
        openCookWithPip(app)
        element("cook-with-pip-management", in: app).tap()
        element("cook-with-pip-preferences-link", in: app).tap()

        let preferencesForm = app.collectionViews["pip-preferences-form"]
        XCTAssertTrue(element("pip-preferences-save", in: app).waitForExistence(timeout: 10))
        let cuisines = element("pip-preferred-cuisines", in: app)
        XCTAssertTrue(cuisines.isHittable, "The identified cuisine field is visible at the top of preferences")
        XCTAssertTrue(cuisines.isEnabled, "The identified cuisine field remains editable")
        let milkAllergen = app.switches["pip-allergen-milk"]
        let milkSeverity = element("pip-allergen-severity-milk", in: app)
        let milkCrossContact = app.switches["pip-allergen-cross-contact-milk"]
        scrollTargetIntoView(milkSeverity, inside: preferencesForm, progressAnchor: cuisines, in: app)
        XCTAssertTrue(milkAllergen.waitForExistence(timeout: 5))
        XCTAssertTrue(milkSeverity.isHittable)
        XCTAssertTrue(milkCrossContact.isHittable)
        XCTAssertEqual(milkAllergen.value as? String, "1")
        XCTAssertEqual(milkSeverity.value as? String, "Severe")
        XCTAssertEqual(milkCrossContact.value as? String, "1")
        element("pip-preferences-save", in: app).tap()
        let savedMessage = element("pip-preferences-success", in: app)
        scrollTargetIntoView(
            savedMessage,
            inside: preferencesForm,
            progressAnchor: milkSeverity,
            in: app,
            initialDirection: .towardStart
        )
        XCTAssertTrue(savedMessage.isHittable, "Saving preferences should show its confirmation at the top of the form")
        let allergyHeading = app.staticTexts["pip-preferences-allergies-heading"]
        scrollTargetIntoView(
            allergyHeading,
            inside: preferencesForm,
            progressAnchor: savedMessage,
            targetDescription: "pip-preferences-allergies-heading",
            in: app,
            initialDirection: .towardEnd
        )
        assertReachable(allergyHeading, in: app)
        assertReachable(milkAllergen, in: app)
        assertReachable(milkSeverity, in: app)
        assertReachable(milkCrossContact, in: app)
        XCTAssertEqual(milkAllergen.value as? String, "1")
        XCTAssertEqual(milkCrossContact.value as? String, "1")
        capture("Preferences_Allergy_Declared", app: app)
    }

    func testProductLabelReviewScreens() {
        let app = launch()
        openCookWithPip(app)
        element("cook-with-pip-management", in: app).tap()
        element("cook-with-pip-product-labels-link", in: app).tap()
        XCTAssertTrue(element("pip-label-product-9903", in: app).waitForExistence(timeout: 10))
        capture("Product_Label_List", app: app)
        element("pip-label-product-9903", in: app).tap()
        let productTitle = element("pip-label-product-title", in: app)
        XCTAssertTrue(productTitle.waitForExistence(timeout: 10))
        capture("Product_Label_Review", app: app)

        let labelForm = app.collectionViews["pip-label-review-form"]
        let milkDeclaration = element("pip-label-allergen-milk", in: app)
        scrollTargetIntoView(milkDeclaration, inside: labelForm, progressAnchor: productTitle, in: app)
        milkDeclaration.tap()
        let declaredOption = element("pip-label-disposition-declared", in: app)
        XCTAssertTrue(declaredOption.waitForExistence(timeout: 5))
        declaredOption.tap()
        XCTAssertEqual(milkDeclaration.value as? String, "Declared on label")

        let source = element("pip-label-source-reference", in: app)
        scrollTargetIntoView(source, inside: labelForm, progressAnchor: productTitle, in: app)
        source.tap()
        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        XCTAssertTrue(source.isHittable, "The focused label source stays available with the keyboard open")
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
        scrollTargetIntoView(saveReview, inside: labelForm, progressAnchor: productTitle, in: app)
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
        let packageDeclarationHeading = element("pip-label-package-declaration-heading", in: app)
        scrollTargetIntoView(
            packageDeclarationHeading,
            inside: labelForm,
            progressAnchor: source,
            in: app,
            initialDirection: .towardStart
        )
        assertReachable(currentStatus, in: app)
        assertReachable(packageDeclarationHeading, in: app)
        XCTAssertTrue(currentStatus.label.contains("Current label review"))
        XCTAssertEqual(milkDeclaration.value as? String, "Declared on label")
        XCTAssertFalse(app.keyboards.firstMatch.isHittable, "Saving a label review dismisses the keyboard")
        capture("Product_Label_Saved_Keyboard_Dismissed", app: app)
        capture("Product_Label_Review_Current", app: app)

        let technicalDetails = app.buttons["pip-label-technical-details"]
        scrollTargetIntoView(
            technicalDetails,
            inside: labelForm,
            progressAnchor: packageDeclarationHeading,
            targetDescription: "pip-label-technical-details",
            in: app,
            initialDirection: .towardStart
        )
        assertReachable(technicalDetails, in: app)
        let reviewRevision = app.staticTexts["pip-label-review-revision"]
        XCTAssertFalse(reviewRevision.exists, "Revision metadata starts collapsed")
        technicalDetails.tap()
        XCTAssertTrue(reviewRevision.waitForExistence(timeout: 5))
        scrollTargetIntoView(reviewRevision, inside: labelForm, progressAnchor: technicalDetails, in: app)
        XCTAssertTrue(reviewRevision.label.contains("v1"))
        assertReachable(reviewRevision, in: app)
        technicalDetails.tap()
        waitUntilGone(reviewRevision)
        let mappingVerified = element("pip-label-mapping-verified", in: app)
        let mappingType = element("pip-label-mapping-type", in: app)
        scrollTargetIntoView(mappingType, inside: labelForm, progressAnchor: productTitle, in: app)
        assertReachable(mappingType, in: app)
        scrollTargetIntoView(mappingVerified, inside: labelForm, progressAnchor: mappingType, in: app)
        assertReachable(mappingVerified, in: app)
    }

    func testFormsStayReadableInDarkModeAndLargeText() {
        let darkApp = launch(appearance: "dark")
        openCookWithPip(darkApp)
        element("cook-with-pip-management", in: darkApp).tap()
        element("cook-with-pip-preferences-link", in: darkApp).tap()
        let savePreferences = element("pip-preferences-save", in: darkApp)
        XCTAssertTrue(savePreferences.waitForExistence(timeout: 10))
        XCTAssertTrue(savePreferences.isHittable)
        let milkSeverity = element("pip-allergen-severity-milk", in: darkApp)
        let milkCrossContact = darkApp.switches["pip-allergen-cross-contact-milk"]
        let preferencesForm = darkApp.collectionViews["pip-preferences-form"]
        scrollTargetIntoView(
            milkCrossContact,
            inside: preferencesForm,
            progressAnchor: element("pip-preferred-cuisines", in: darkApp),
            in: darkApp
        )
        assertReachable(milkSeverity, in: darkApp)
        assertReachable(milkCrossContact, in: darkApp)
        XCTAssertTrue(milkCrossContact.label.contains("Milk"))
        capture("Preferences_Allergy_Dark_Mode", app: darkApp)

        navigateBack(darkApp, to: element("cook-with-pip-management", in: darkApp), screen: "Cook with Pip management")
        element("cook-with-pip-product-labels-link", in: darkApp).tap()
        element("pip-label-product-9903", in: darkApp).tap()
        let darkProductTitle = element("pip-label-product-title", in: darkApp)
        XCTAssertTrue(darkProductTitle.waitForExistence(timeout: 10))
        XCTAssertTrue(darkProductTitle.isHittable)
        capture("Product_Label_Review_Dark_Mode", app: darkApp)

        darkApp.terminate()
        let largeLabel = launch(dynamicType: "accessibility")
        openCookWithPip(largeLabel)
        element("cook-with-pip-management", in: largeLabel).tap()
        element("cook-with-pip-product-labels-link", in: largeLabel).tap()
        element("pip-label-product-9903", in: largeLabel).tap()
        let productTitle = element("pip-label-product-title", in: largeLabel)
        XCTAssertTrue(productTitle.waitForExistence(timeout: 10))
        XCTAssertTrue(productTitle.isHittable)
        assertReachable(productTitle, in: largeLabel)
        let labelForm = largeLabel.collectionViews["pip-label-review-form"]
        XCTAssertTrue(labelForm.waitForExistence(timeout: 5))
        let technicalDetails = largeLabel.buttons["pip-label-technical-details"]
        XCTAssertTrue(technicalDetails.waitForExistence(timeout: 5))
        scrollTargetIntoView(technicalDetails, inside: labelForm, progressAnchor: productTitle, in: largeLabel)
        let serverVersion = largeLabel.staticTexts["pip-label-server-version"]
        XCTAssertFalse(serverVersion.exists, "Technical metadata starts collapsed below the product details")
        capture("Product_Label_Review_Large_Text", app: largeLabel)
        technicalDetails.tap()
        XCTAssertTrue(serverVersion.waitForExistence(timeout: 5))
        scrollTargetIntoView(serverVersion, inside: labelForm, progressAnchor: technicalDetails, in: largeLabel)
        XCTAssertTrue(serverVersion.label.contains("2026-11-09T00:00:00Z"))
        assertReachable(serverVersion, in: largeLabel)
        scrollTargetIntoView(technicalDetails, inside: labelForm, progressAnchor: serverVersion, in: largeLabel)
        technicalDetails.tap()
        waitUntilGone(serverVersion)
        let mappingVerified = element("pip-label-mapping-verified", in: largeLabel)
        scrollTargetIntoView(mappingVerified, inside: labelForm, progressAnchor: technicalDetails, in: largeLabel)
        assertReachable(mappingVerified, in: largeLabel)
        capture("Product_Label_Review_Scrolled", app: largeLabel)

        let mappingNote = largeLabel.staticTexts[
            "A verified, complete mapping is required before a package label review can be recorded."
        ]
        scrollTargetIntoView(mappingNote, inside: labelForm, progressAnchor: mappingVerified, in: largeLabel)
        assertReachable(mappingNote, in: largeLabel)

        let milkDeclaration = element("pip-label-allergen-milk", in: largeLabel)
        scrollTargetIntoView(milkDeclaration, inside: labelForm, progressAnchor: mappingNote, in: largeLabel)
        XCTAssertTrue(milkDeclaration.label.hasSuffix("Milk label declaration"),
                      "The picker label preserves the allergen declaration description")
        assertReachable(milkDeclaration, in: largeLabel)

        let customAllergensHeading = element("pip-label-custom-allergens-heading", in: largeLabel)
        let customAllergensField = element("pip-label-custom-allergens", in: largeLabel)
        scrollTargetIntoView(customAllergensHeading, inside: labelForm, progressAnchor: milkDeclaration, in: largeLabel)
        assertReachable(customAllergensHeading, in: largeLabel)
        assertReachable(customAllergensField, in: largeLabel)

        let sourceField = element("pip-label-source-reference", in: largeLabel)
        scrollTargetIntoView(sourceField, inside: labelForm, progressAnchor: customAllergensHeading, in: largeLabel)
        XCTAssertEqual(sourceField.label, "Source reference")
        XCTAssertEqual(sourceField.placeholderValue, "Package label, URL, or label section")
        assertReachable(sourceField, in: largeLabel)
    }

    func testStaleProductLabelReviewIsShownAsStale() {
        let app = launch(scenario: "product-label-stale")
        openCookWithPip(app)
        element("cook-with-pip-management", in: app).tap()
        element("cook-with-pip-product-labels-link", in: app).tap()
        element("pip-label-product-9903", in: app).tap()

        let productTitle = element("pip-label-product-title", in: app)
        XCTAssertTrue(productTitle.waitForExistence(timeout: 10))
        let labelForm = app.collectionViews["pip-label-review-form"]
        let milkDeclaration = element("pip-label-allergen-milk", in: app)
        let ingredientSearchButton = element("pip-label-search-ingredients", in: app)
        scrollTargetIntoView(milkDeclaration, inside: labelForm, progressAnchor: productTitle, in: app)
        XCTAssertEqual(milkDeclaration.value as? String, "Declared on label")
        let status = element("pip-label-current-status", in: app)
        let packageDeclarationHeading = element("pip-label-package-declaration-heading", in: app)
        scrollTargetIntoView(status, inside: labelForm, progressAnchor: milkDeclaration, in: app)
        XCTAssertTrue(status.waitForExistence(timeout: 10))
        XCTAssertTrue(status.label.contains("no longer current"))
        let mappingVerified = element("pip-label-mapping-verified", in: app)
        let mappingType = element("pip-label-mapping-type", in: app)
        let ingredientSearchField = element("pip-label-ingredient-search", in: app)
        scrollTargetIntoView(mappingType, inside: labelForm, progressAnchor: productTitle, in: app)
        assertReachable(mappingType, in: app)
        scrollTargetIntoView(mappingVerified, inside: labelForm, progressAnchor: mappingType, in: app)
        assertReachable(mappingVerified, in: app)
        scrollTargetIntoView(status, inside: labelForm, progressAnchor: mappingVerified, in: app)
        nudgeContentDown(in: app, by: 0.32)
        assertReachable(mappingType, in: app)
        XCTAssertTrue(packageDeclarationHeading.waitForExistence(timeout: 5))
        assertReachable(packageDeclarationHeading, in: app)
        XCTAssertTrue(ingredientSearchField.waitForExistence(timeout: 5))
        assertReachable(ingredientSearchField, in: app)
        XCTAssertTrue(ingredientSearchButton.waitForExistence(timeout: 5))
        assertReachable(ingredientSearchButton, in: app)
        assertReachable(status, in: app)
        capture("Product_Label_Review_Stale", app: app)
    }

    func testSubstitutionChoicesUseStoredAmountsAndRefreshEvaluation() {
        let app = launch()
        openCookNowRecipe(app)
        let customize = element("recipe-review-substitutions", in: app)
        scrollTargetIntoView(customize, inside: app.scrollViews["recipe-detail-scroll"], in: app)
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
        scrollTargetIntoView(ingredient, inside: app.scrollViews["recipe-detail-scroll"], in: app)
        XCTAssertTrue(ingredient.waitForExistence(timeout: 10))
        let ingredientName = element("recipe-ingredient-name-1", in: app)
        XCTAssertTrue(ingredientName.label.contains("calamansi"))
        capture("Recipe_Detail_Substitution_Applied", app: app)
    }

    func testShoppingPreviewEditsConsolidationAndExplicitConfirmation() {
        let app = launch()
        openShoppingPreview(app)
        let shoppingForm = app.collectionViews["recipe-shopping-review-form"]
        XCTAssertEqual(element("recipe-shopping-safety-status", in: app).label, "Eligible")
        capture("Shopping_Preview_Ready", app: app)
        let unlinked = element("recipe-shopping-unlinked-9920", in: app)
        scrollTargetIntoView(unlinked, inside: shoppingForm, in: app)
        XCTAssertTrue(unlinked.exists)
        XCTAssertTrue(unlinked.isHittable)
        capture("Shopping_Unlinked_Manual_Items", app: app)

        let includeOptional = app.switches["recipe-shopping-include-optional"]
        scrollTargetIntoView(includeOptional, inside: shoppingForm, in: app)
        setSwitch(includeOptional, to: "1")
        let stalePreview = element("recipe-shopping-stale-preview", in: app)
        XCTAssertTrue(stalePreview.waitForExistence(timeout: 5))
        let refreshPreview = app.buttons["recipe-shopping-refresh-preview"]
        scrollTargetIntoView(refreshPreview, inside: shoppingForm, in: app)
        XCTAssertTrue(refreshPreview.exists)
        XCTAssertTrue(refreshPreview.isHittable)
        refreshPreview.tap()
        let optionalIngredient = element("recipe-shopping-row-913", in: app)
        scrollTargetIntoView(optionalIngredient, inside: shoppingForm, in: app)
        XCTAssertTrue(optionalIngredient.waitForExistence(timeout: 10))
        XCTAssertFalse(stalePreview.exists)
        XCTAssertTrue(optionalIngredient.isHittable)
        assertReachable(optionalIngredient, in: app)
        capture("Shopping_Optional_Ingredients", app: app)

        let target = element("recipe-shopping-target-901", in: app)
        scrollTargetIntoView(target, inside: shoppingForm, in: app)
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
        assertReachable(consolidate, in: app)
        capture("Shopping_Duplicate_Consolidation_Opt_In", app: app)

        element("recipe-shopping-confirm", in: app).tap()
        let confirmAction = app.buttons.matching(identifier: "recipe-shopping-confirm-action").firstMatch
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
        scrollTargetIntoView(servings, inside: largeApp.collectionViews["recipe-shopping-review-form"], in: largeApp)
        XCTAssertTrue(servings.isHittable)
        assertReachable(servings, in: largeApp)
        let confirm = largeApp.buttons["recipe-shopping-confirm"]
        XCTAssertTrue(confirm.isHittable, "The confirmation action stays reachable at accessibility text sizes")
        let refresh = element("recipe-shopping-refresh-preview", in: largeApp)
        XCTAssertTrue(refresh.isHittable, "Refresh remains visible at accessibility text sizes")
        let reviewForm = largeApp.collectionViews["recipe-shopping-review-form"]
        capture("Shopping_Preview_Large_Text", app: largeApp)

        let revisionDetails = element("recipe-shopping-revision-details", in: largeApp)
        scrollTargetIntoView(revisionDetails, inside: reviewForm, in: largeApp)
        XCTAssertTrue(revisionDetails.isHittable)
        let listRevision = element("recipe-shopping-list-revision", in: largeApp)
        XCTAssertFalse(listRevision.exists, "Revision rows remain hidden until the user opens them")
        revisionDetails.tap()
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
        let reviewConfirm = reviewApp.navigationBars.buttons["recipe-shopping-confirm"]
        XCTAssertFalse(reviewConfirm.isEnabled)
        capture("Shopping_Preview_Review_Required", app: reviewApp)
        let acknowledgement = reviewApp.switches["recipe-shopping-safety-acknowledgement"]
        let reviewForm = reviewApp.collectionViews["recipe-shopping-review-form"]
        scrollTargetIntoView(acknowledgement, inside: reviewForm, in: reviewApp)
        XCTAssertEqual(acknowledgement.value as? String, "0",
                       "Safety review stays Off until the user taps the switch")
        acknowledgement.coordinate(withNormalizedOffset: CGVector(dx: 0.90, dy: 0.5)).tap()
        let acknowledged = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "1"), object: acknowledgement
        )
        XCTAssertEqual(XCTWaiter.wait(for: [acknowledged], timeout: 5), .completed,
                       "The visible switch changes from Off to On after a direct tap")
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
        scrollTargetIntoView(offlineReady, inside: offlineApp.collectionViews["recipe-shopping-review-form"], in: offlineApp)

        offlineApp.terminate()
        let staleApp = launch(scenario: "shopping-stale")
        openShoppingPreview(staleApp)
        element("recipe-shopping-confirm", in: staleApp).tap()
        let staleConfirmAction = staleApp.buttons
            .matching(identifier: "recipe-shopping-confirm-action").firstMatch
        XCTAssertTrue(staleConfirmAction.waitForExistence(timeout: 5))
        staleConfirmAction.tap()
        let staleMessage = appText("Inventory or shopping data changed", in: staleApp)
        scrollTargetIntoView(
            staleMessage,
            inside: staleApp.collectionViews["recipe-shopping-review-form"],
            progressAnchor: element("recipe-shopping-safety-status", in: staleApp),
            in: staleApp,
            initialDirection: .towardStart
        )
        XCTAssertTrue(staleMessage.waitForExistence(timeout: 10))
        let refresh = element("recipe-shopping-load-preview", in: staleApp)
        scrollTargetIntoView(
            refresh,
            inside: staleApp.collectionViews["recipe-shopping-review-form"],
            progressAnchor: staleMessage,
            in: staleApp,
            initialDirection: .towardStart
        )
        XCTAssertTrue(refresh.exists)
        capture("Shopping_Stale_Preview_Refresh", app: staleApp)
        refresh.tap()
        let staleReady = element("recipe-shopping-safety-status", in: staleApp)
        XCTAssertTrue(element("recipe-shopping-servings", in: staleApp).waitForExistence(timeout: 10))
        scrollTargetIntoView(staleReady, inside: staleApp.collectionViews["recipe-shopping-review-form"], in: staleApp)
    }

    func testAmbiguousShoppingConfirmationSurvivesAppRelaunch() {
        let fixtureID = Int.random(in: 10_000...90_000)
        let app = launch(scenario: "shopping-restart", fixtureID: fixtureID, useKeychain: true)
        openShoppingPreview(app)
        let confirm = app.navigationBars.buttons["recipe-shopping-confirm"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 10))
        XCTAssertTrue(confirm.isEnabled,
                      "An eligible current preview with selected lines enables explicit confirmation")
        confirm.tap()
        let confirmAction = app.buttons.matching(identifier: "recipe-shopping-confirm-action").firstMatch
        XCTAssertTrue(confirmAction.waitForExistence(timeout: 10))
        XCTAssertTrue(confirmAction.isEnabled,
                      "The explicit confirmation choice stays enabled for the reviewed request")
        confirmAction.tap()

        let pendingStatus = element("recipe-shopping-pending-status", in: app)
        XCTAssertTrue(pendingStatus.waitForExistence(timeout: 10))
        let retryMessage = element("recipe-shopping-error", in: app)
        XCTAssertTrue(retryMessage.waitForExistence(timeout: 5))
        XCTAssertTrue(retryMessage.label.contains("request is saved"))
        let shoppingForm = app.collectionViews["recipe-shopping-review-form"]
        assertReachable(pendingStatus, in: app)
        XCTAssertEqual(pendingStatus.label, "Result not confirmed")
        let confirmWhilePending = app.navigationBars.buttons["recipe-shopping-confirm"]
        XCTAssertTrue(confirmWhilePending.waitForExistence(timeout: 5))
        XCTAssertFalse(confirmWhilePending.isEnabled,
                        "A pending request cannot be submitted as a new confirmation")
        XCTAssertFalse(element("recipe-shopping-servings", in: app).exists,
                        "A pending request cannot be edited before retry")
        let pendingRetryButton = app.buttons["recipe-shopping-retry-pending"]
        XCTAssertTrue(pendingRetryButton.waitForExistence(timeout: 5))
        scrollTargetIntoView(pendingRetryButton, inside: shoppingForm, in: app)
        XCTAssertTrue(pendingRetryButton.isEnabled)
        XCTAssertTrue(pendingRetryButton.isHittable)
        let pendingLine = element("recipe-shopping-pending-line-0", in: app)
        XCTAssertTrue(pendingLine.waitForExistence(timeout: 10))
        scrollTargetIntoView(pendingLine, inside: shoppingForm, in: app)
        capture("Shopping_Confirmation_Retry_Pending", app: app)
        app.terminate()

        let relaunched = launch(scenario: "shopping-restart", fixtureID: fixtureID, useKeychain: true)
        openShoppingPreview(relaunched, timeout: 30)
        let relaunchedStatus = element("recipe-shopping-pending-status", in: relaunched)
        XCTAssertTrue(relaunchedStatus.waitForExistence(timeout: 10))
        let relaunchedForm = relaunched.collectionViews["recipe-shopping-review-form"]
        assertReachable(relaunchedStatus, in: relaunched)
        XCTAssertEqual(relaunchedStatus.label, "Result not confirmed")
        let relaunchedConfirm = relaunched.navigationBars.buttons["recipe-shopping-confirm"]
        XCTAssertTrue(relaunchedConfirm.waitForExistence(timeout: 5))
        XCTAssertFalse(relaunchedConfirm.isEnabled,
                       "A saved pending request still blocks new confirmation after relaunch")
        let retryPending = relaunched.buttons["recipe-shopping-retry-pending"]
        scrollTargetIntoView(retryPending, inside: relaunchedForm, in: relaunched)
        XCTAssertEqual(retryPending.label, "Retry exact confirmation")
        XCTAssertTrue(retryPending.isEnabled)
        XCTAssertTrue(retryPending.isHittable)
        retryPending.tap()
        let resultCounts = element("recipe-shopping-result-counts", in: relaunched)
        XCTAssertTrue(resultCounts.waitForExistence(timeout: 10))

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
        scrollTargetIntoView(sourceError, inside: app.scrollViews["recipe-detail-scroll"], in: app)
        XCTAssertTrue(sourceError.waitForExistence(timeout: 10))
        nudgeContentDown(in: app, by: -0.04)
        assertReachable(sourceError, in: app)
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
        scrollTargetIntoView(firstRecipe, inside: largeApp.scrollViews["cook-with-pip-recipe-list-scroll"], in: largeApp)
        XCTAssertTrue(firstRecipe.exists)
        let myRecipesMode = element("cook-mode-myRecipes", in: largeApp)
        XCTAssertTrue(myRecipesMode.waitForExistence(timeout: 10))
        scrollTargetIntoView(myRecipesMode, inside: largeApp.scrollViews["cook-with-pip-recipe-list-scroll"], in: largeApp)
        myRecipesMode.tap()
        let selectedMode = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value CONTAINS %@", "Selected"), object: myRecipesMode
        )
        XCTAssertEqual(XCTWaiter.wait(for: [selectedMode], timeout: 5), .completed)
        let householdRecipe = element("recipe-card-303", in: largeApp)
        scrollTargetIntoView(householdRecipe, inside: largeApp.scrollViews["cook-with-pip-recipe-list-scroll"], in: largeApp)
        XCTAssertTrue(householdRecipe.exists)
        let longRecipe = element("recipe-card-304", in: largeApp)
        scrollTargetIntoView(longRecipe, inside: largeApp.scrollViews["cook-with-pip-recipe-list-scroll"], in: largeApp)
        longRecipe.tap()
        let largeTitle = element("recipe-detail-title", in: largeApp)
        XCTAssertTrue(largeTitle.waitForExistence(timeout: 10))
        XCTAssertTrue(largeTitle.isHittable)
        XCTAssertTrue(largeTitle.label.contains("mahahabang pangalan ng sangkap"))
        assertReachable(largeTitle, in: largeApp)
        let safetyStatus = element("recipe-safety-status", in: largeApp)
        XCTAssertTrue(safetyStatus.waitForExistence(timeout: 10))
        XCTAssertTrue(safetyStatus.isHittable, "The food-safety decision stays visible below the large recipe title")
        assertReachable(safetyStatus, in: largeApp)
        let availabilityStatus = element("recipe-availability-status", in: largeApp)
        XCTAssertTrue(availabilityStatus.waitForExistence(timeout: 10))
        XCTAssertTrue(availabilityStatus.isHittable, "Pantry availability remains visible alongside food safety")
        let recipeDetailScroll = largeApp.scrollViews["recipe-detail-scroll"]
        let largeSummary = element("recipe-detail-summary", in: largeApp)
        XCTAssertTrue(largeSummary.waitForExistence(timeout: 10))
        XCTAssertTrue(largeSummary.label.contains("long Filipino ingredient names"))
        let safetyNotice = element("recipe-safety-notice", in: largeApp)
        XCTAssertTrue(safetyNotice.waitForExistence(timeout: 5))
        capture("Recipe_Detail_Large_Text_Filipino", app: largeApp)
        scrollTargetIntoView(safetyNotice, inside: largeApp.scrollViews["recipe-detail-scroll"], in: largeApp)
        nudgeContentDown(in: largeApp, by: 0.14)
        XCTAssertTrue(safetyNotice.isHittable)
        assertReachable(safetyNotice, in: largeApp)
        capture("Recipe_Detail_Large_Text_Safety_Filipino", app: largeApp)
        scrollTargetIntoView(largeSummary, inside: recipeDetailScroll, in: largeApp)
        nudgeContentDown(in: largeApp, by: -0.23)
        XCTAssertTrue(largeSummary.isHittable)
        assertReachable(largeSummary, in: largeApp)
        capture("Recipe_Detail_Large_Text_Summary_Filipino", app: largeApp)
        let longIngredient = element("recipe-ingredient-name-0", in: largeApp)
        let requiredIngredientsHeading = largeApp.staticTexts["Required ingredients"].firstMatch
        scrollTargetIntoView(requiredIngredientsHeading, inside: recipeDetailScroll, in: largeApp)
        XCTAssertTrue(longIngredient.isHittable)
        XCTAssertTrue(longIngredient.label.contains("talong na hiniwa nang pahaba"))
        XCTAssertTrue(requiredIngredientsHeading.waitForExistence(timeout: 5))
        assertReachable(requiredIngredientsHeading, in: largeApp)
        assertReachable(longIngredient, in: largeApp)
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
        XCTAssertTrue(search.isHittable, "The search field remains available while the keyboard is open")
        let keyboardDone = element("cook-with-pip-search-keyboard-done", in: searchApp)
        XCTAssertTrue(keyboardDone.waitForExistence(timeout: 5))
        XCTAssertTrue(keyboardDone.isHittable)
        let searchMyRecipesMode = searchApp.buttons["cook-mode-myRecipes"]
        XCTAssertTrue(searchMyRecipesMode.waitForExistence(timeout: 5))
        XCTAssertTrue(searchMyRecipesMode.isHittable,
                      "The My Recipes filter remains usable while search is focused")
        let recipeModeButtons = [
            searchApp.buttons["cook-mode-cookNow"],
            searchApp.buttons["cook-mode-almostThere"],
            searchMyRecipesMode
        ]
        for button in recipeModeButtons {
            XCTAssertTrue(button.isHittable, "The recipe filter remains usable while search is focused")
        }
        capture("Cook_with_Pip_Search_Keyboard", app: searchApp)
        search.typeText("Laing")
        let matchingRecipe = element("recipe-card-302", in: searchApp)
        XCTAssertTrue(matchingRecipe.waitForExistence(timeout: 10))
        let recipeScrollView = searchApp.scrollViews["cook-with-pip-recipe-list-scroll"]
        XCTAssertTrue(recipeScrollView.exists)
        keyboardDone.tap()
        let keyboardDismissed = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "isHittable == false"),
            object: keyboard
        )
        XCTAssertEqual(XCTWaiter.wait(for: [keyboardDismissed], timeout: 5), .completed)
        scrollTargetIntoView(matchingRecipe, inside: recipeScrollView, in: searchApp)
        XCTAssertTrue(search.exists)
        XCTAssertTrue(matchingRecipe.isHittable)
        capture("My_Recipes_Search_Scrolled", app: searchApp)
    }

    func testShoppingPreviewExpiredIsNotConfirmable() {
        let app = launch(scenario: "shopping-expired")
        openShoppingPreview(app)
        let revisionDetails = element("recipe-shopping-revision-details", in: app)
        scrollTargetIntoView(revisionDetails, inside: app.collectionViews["recipe-shopping-review-form"], in: app)
        let expiration = element("recipe-shopping-expiration-value", in: app)
        XCTAssertFalse(expiration.exists, "Expiry details stay hidden while revision details are collapsed")
        XCTAssertTrue(revisionDetails.isHittable)
        revisionDetails.tap()
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

    private func openCookWithPip(_ app: XCUIApplication, timeout: TimeInterval = 10) {
        let entry = element("cook-with-pip-entry", in: app)
        XCTAssertTrue(entry.waitForExistence(timeout: timeout))
        entry.tap()
        XCTAssertTrue(element("cook-with-pip-introduction", in: app).waitForExistence(timeout: timeout))
    }

    private func openCookNowRecipe(_ app: XCUIApplication) {
        openCookWithPip(app)
        let recipe = element("recipe-card-301", in: app)
        XCTAssertTrue(recipe.waitForExistence(timeout: 10))
        recipe.tap()
        XCTAssertTrue(element("recipe-detail-title", in: app).waitForExistence(timeout: 10))
    }

    private func openShoppingPreview(_ app: XCUIApplication, timeout: TimeInterval = 10) {
        openCookWithPip(app, timeout: timeout)
        let myRecipes = app.buttons["cook-mode-myRecipes"]
        XCTAssertTrue(myRecipes.waitForExistence(timeout: 10))
        scrollTargetIntoView(myRecipes, inside: app.scrollViews["cook-with-pip-recipe-list-scroll"], in: app)
        XCTAssertTrue(myRecipes.isHittable)
        myRecipes.tap()
        let myRecipesSelected = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "Selected"), object: myRecipes
        )
        XCTAssertEqual(XCTWaiter.wait(for: [myRecipesSelected], timeout: 10), .completed)

        let recipe = app.buttons["recipe-card-305"]
        let recipeList = app.scrollViews["cook-with-pip-recipe-list-scroll"]
        XCTAssertTrue(recipeList.waitForExistence(timeout: 5))
        scrollTargetIntoView(recipe, inside: recipeList, progressAnchor: myRecipes, in: app)
        XCTAssertTrue(recipe.exists, "The selected My Recipes list contains the saved preview fixture")
        XCTAssertTrue(recipe.label.contains("Test Recipe: Ginataang Kangkong"))
        recipe.tap()
        let recipeTitle = app.staticTexts["recipe-detail-title"]
        XCTAssertTrue(recipeTitle.waitForExistence(timeout: 10),
                      "Tapping the visible saved recipe should open its detail screen")
        let previewLink = app.buttons["recipe-shopping-preview-link"]
        let recipeDetail = app.scrollViews["recipe-detail-scroll"]
        scrollTargetIntoView(previewLink, inside: recipeDetail, progressAnchor: recipeTitle, in: app)
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
            let reviewForm = app.collectionViews["recipe-shopping-review-form"]
            scrollTargetIntoView(ready, inside: reviewForm, in: app)
        }
    }

    private enum ScrollDirection {
        case towardEnd
        case towardStart
    }

    private func scrollTargetIntoView(
        _ target: XCUIElement,
        inside container: XCUIElement,
        progressAnchor: XCUIElement? = nil,
        targetDescription: String? = nil,
        in app: XCUIApplication,
        maximumSwipes: Int = 12,
        initialDirection: ScrollDirection = .towardEnd
    ) {
        let targetName = targetDescription ?? "target element"
        guard container.waitForExistence(timeout: 5) else {
            XCTFail("Expected scroll container '\(container.identifier)' while locating \(targetName)")
            return
        }
        var targetExists = target.exists
        if targetExists && target.isHittable { return }

        let anchor = progressAnchor ?? container.descendants(matching: .any).firstMatch
        var previousTargetFrame = targetExists ? measurableFrame(of: target) : nil
        var previousAnchorFrame = measurableFrame(of: anchor)

        for swipeNumber in 1...maximumSwipes {
            if targetExists && target.isHittable { return }

            let containerFrame = measurableFrame(of: container)
            let direction: ScrollDirection
            if let targetFrame = previousTargetFrame, let containerFrame {
                if targetFrame.minY < containerFrame.minY {
                    direction = .towardStart
                } else if targetFrame.maxY > containerFrame.maxY {
                    direction = .towardEnd
                } else {
                    direction = initialDirection
                }
            } else {
                direction = initialDirection
            }

            switch direction {
            case .towardEnd:
                container.swipeUp()
            case .towardStart:
                container.swipeDown()
            }

            targetExists = target.exists
            if targetExists && target.isHittable { return }

            let currentTargetFrame = targetExists ? measurableFrame(of: target) : nil
            let currentAnchorFrame = measurableFrame(of: anchor)
            let madeProgress = frameMoved(from: previousTargetFrame, to: currentTargetFrame)
                || frameMoved(from: previousAnchorFrame, to: currentAnchorFrame)
            guard madeProgress else {
                XCTFail(
                    "Scrolling stopped before \(targetName) became hittable. "
                    + "container='\(container.identifier)', targetFrame=\(describe(currentTargetFrame)), "
                    + "anchorFrame=\(describe(currentAnchorFrame)), "
                    + "completedSwipes=\(swipeNumber), targetExists=\(targetExists), "
                    + "appState=\(app.state)"
                )
                return
            }
            previousTargetFrame = currentTargetFrame
            previousAnchorFrame = currentAnchorFrame
        }

        XCTAssertTrue(
            target.waitForExistence(timeout: 10),
            "Expected \(targetName) after at most \(maximumSwipes) swipes in '\(container.identifier)'"
        )
        XCTAssertTrue(
            target.isHittable,
            "Expected \(targetName) to be visible and interactable after \(maximumSwipes) swipes; appState=\(app.state)"
        )
    }

    private func measurableFrame(of element: XCUIElement) -> CGRect? {
        guard element.exists else { return nil }
        let frame = element.frame
        guard !frame.isNull, !frame.isInfinite, !frame.isEmpty,
              frame.minX.isFinite, frame.minY.isFinite,
              frame.maxX.isFinite, frame.maxY.isFinite else {
            return nil
        }
        return frame
    }

    private func frameMoved(from previous: CGRect?, to current: CGRect?) -> Bool {
        guard let previous, let current else { return previous != current }
        return abs(previous.minX - current.minX) > 1
            || abs(previous.minY - current.minY) > 1
            || abs(previous.maxX - current.maxX) > 1
            || abs(previous.maxY - current.maxY) > 1
    }

    private func describe(_ frame: CGRect?) -> String {
        guard let frame else { return "unavailable" }
        return String(describing: frame)
    }

    private func navigateBack(_ app: XCUIApplication) {
        let back = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 5))
        back.tap()
    }

    private func navigateBack(_ app: XCUIApplication, to destination: XCUIElement, screen: String) {
        let back = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 5), "Expected a back button while leaving \(screen)")
        back.tap()

        let destinationIsVisible = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == true AND hittable == true"),
            object: destination
        )
        XCTAssertEqual(
            XCTWaiter.wait(for: [destinationIsVisible], timeout: 15),
            .completed,
            "Back navigation should return to \(screen)"
        )
    }

    private func assertReachable(_ target: XCUIElement, in app: XCUIApplication) {
        guard target.exists || target.waitForExistence(timeout: 5) else {
            XCTFail("Expected '\(target.identifier)' to exist before checking reachability")
            return
        }
        XCTAssertTrue(
            target.isHittable,
            "Expected \(target.identifier) to be visible and interactable; appState=\(app.state)"
        )
    }

    private func nudgeContentDown(in app: XCUIApplication, by fraction: CGFloat) {
        let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.3))
        let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.3 + fraction))
        start.press(forDuration: 0.2, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.1)
    }

    private func setSwitch(_ toggle: XCUIElement, to value: String) {
        XCTAssertTrue(toggle.waitForExistence(timeout: 5))
        if toggle.value as? String != value {
            XCTAssertTrue(toggle.isHittable)
            toggle.tap()
        }
        let expectedValue = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", value), object: toggle
        )
        XCTAssertEqual(XCTWaiter.wait(for: [expectedValue], timeout: 5), .completed,
                        "Expected \(toggle.identifier) to have value \(value); found \(String(describing: toggle.value))")
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
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func capturePipChat(_ name: String, app: XCUIApplication) {
        guard ProcessInfo.processInfo.environment["PROVISION_SKIP_CHAT_SCREENSHOTS"] != "1" else { return }
        capture(name, app: app)
    }
}
extension CookWithPipUITests {
    func testStagingPipChatContextAndShoppingPreviewRoutes() throws {
        let environment = ProcessInfo.processInfo.environment
        guard let baseURL = environment["PROVISION_API_BASE_URL"],
              let email = environment["PROVISION_STAGING_TEST_EMAIL"],
              let password = environment["PROVISION_STAGING_TEST_PASSWORD"],
              let recipeID = environment["PROVISION_STAGING_TEST_RECIPE_ID"].flatMap(Int.init),
              let productID = environment["PROVISION_STAGING_TEST_PRODUCT_ID"].flatMap(Int.init) else {
            throw XCTSkip("Staging API credentials and synthetic resource IDs are supplied only by the manual staging workflow")
        }

        let app = XCUIApplication()
        app.launchEnvironment["PROVISION_API_BASE_URL"] = baseURL
        app.launchEnvironment["PROVISION_STAGING_TEST_EMAIL"] = email
        app.launchEnvironment["PROVISION_STAGING_TEST_PASSWORD"] = password
        app.launchArguments = ["--provision-reset-staging-session"]
        app.launch()

        let emailField = app.textFields["login-email"]
        XCTAssertTrue(emailField.waitForExistence(timeout: 20))
        emailField.tap()
        emailField.typeText(email)
        let passwordField = app.secureTextFields["login-password"]
        passwordField.tap()
        passwordField.typeText(password)
        app.buttons["login-submit"].tap()
        XCTAssertTrue(app.buttons["Home"].waitForExistence(timeout: 40))
        dismissSavePasswordPromptIfPresent(in: app, readyElement: app.buttons["Home"])

        let homeEntry = element("cook-with-pip-entry", in: app)
        XCTAssertTrue(homeEntry.waitForExistence(timeout: 20))
        XCTAssertTrue(homeEntry.isHittable, "The Cook with Pip entry should be interactive after login")
        homeEntry.tap()
        let myRecipes = app.buttons["cook-mode-myRecipes"]
        XCTAssertTrue(myRecipes.waitForExistence(timeout: 15))
        myRecipes.tap()
        let recipe = element("recipe-card-\(recipeID)", in: app)
        XCTAssertTrue(recipe.waitForExistence(timeout: 20))
        recipe.tap()
        XCTAssertTrue(element("recipe-detail-title", in: app).waitForExistence(timeout: 20))

        let askAboutRecipe = element("recipe-ask-pip-link", in: app)
        scrollTargetIntoView(askAboutRecipe, inside: app.scrollViews["recipe-detail-scroll"], in: app)
        askAboutRecipe.tap()
        let chatInput = element("pip-chat-input", in: app)
        XCTAssertTrue(chatInput.waitForExistence(timeout: 15))
        chatInput.tap()
        chatInput.typeText("What should I buy?")
        app.buttons["pip-chat-send"].tap()
        let shoppingAction = element("pip-chat-open-shopping-preview-\(recipeID)", in: app)
        XCTAssertTrue(shoppingAction.waitForExistence(timeout: 20))
        shoppingAction.tap()
        XCTAssertTrue(element("recipe-shopping-safety-status", in: app).waitForExistence(timeout: 30))
        XCTAssertTrue(app.buttons["recipe-shopping-confirm"].exists,
                      "Chat opens the existing review screen without confirming changes")
        XCTAssertFalse(app.alerts.firstMatch.exists,
                       "No confirmation dialog appears until the user starts the existing confirmation flow")

        navigateBack(app, to: chatInput, screen: "Pip Chat")
        navigateBack(app, to: element("recipe-detail-title", in: app), screen: "Recipe Detail")
        navigateBack(app, to: recipe, screen: "My Recipes")
        navigateBack(app, to: homeEntry, screen: "Home")
        app.buttons["Inventory"].tap()
        let productRow = element("product-row-\(productID)", in: app)
        XCTAssertTrue(productRow.waitForExistence(timeout: 20))
        productRow.tap()
        let askAboutProduct = element("product-ask-pip-link", in: app)
        XCTAssertTrue(askAboutProduct.waitForExistence(timeout: 15))
        askAboutProduct.tap()
        let productChatInput = element("pip-chat-input", in: app)
        XCTAssertTrue(productChatInput.waitForExistence(timeout: 15))
        productChatInput.tap()
        productChatInput.typeText("How much is left?")
        app.buttons["pip-chat-send"].tap()
        XCTAssertTrue(element("pip-chat-fact-I1", in: app).waitForExistence(timeout: 15),
                      "Product context returns the backend's exact inventory fact")
    }

    func testStagingLoginAndRelaunch() throws {
        let environment = ProcessInfo.processInfo.environment
        guard let baseURL = environment["PROVISION_API_BASE_URL"],
              let email = environment["PROVISION_STAGING_TEST_EMAIL"],
              let password = environment["PROVISION_STAGING_TEST_PASSWORD"] else {
            throw XCTSkip("Staging API credentials are supplied only by the manual staging workflow")
        }
        let app = XCUIApplication()
        app.launchEnvironment["PROVISION_API_BASE_URL"] = baseURL
        app.launchEnvironment["PROVISION_STAGING_TEST_EMAIL"] = email
        app.launchEnvironment["PROVISION_STAGING_TEST_PASSWORD"] = password
        app.launchArguments = ["--provision-reset-staging-session"]
        app.launch()

        let emailField = app.textFields["login-email"]
        let passwordField = app.secureTextFields["login-password"]
        let signIn = app.buttons["login-submit"]
        XCTAssertTrue(emailField.waitForExistence(timeout: 20))
        emailField.tap()
        emailField.typeText(email)
        passwordField.tap()
        passwordField.typeText(password)
        signIn.tap()

        let inventoryTab = app.buttons["Inventory"]
        XCTAssertTrue(inventoryTab.waitForExistence(timeout: 40), "Staging login did not establish an authorized household session")
        dismissSavePasswordPromptIfPresent(in: app, readyElement: inventoryTab)
        capture("Staging_Authenticated_Home", app: app)

        app.terminate()
        app.launchArguments = []
        app.launch()
        XCTAssertTrue(inventoryTab.waitForExistence(timeout: 40), "The verified staging session did not recover after relaunch")
        capture("Staging_Relaunch_Recovery", app: app)

        let accountSettings = app.buttons["settings-account-button"]
        XCTAssertTrue(accountSettings.waitForExistence(timeout: 20))
        accountSettings.tap()
        let logOut = app.buttons["account-logout"]
        if !logOut.isHittable {
            scrollTargetIntoView(logOut, inside: app.scrollViews.firstMatch, in: app)
        }
        XCTAssertTrue(logOut.waitForExistence(timeout: 10), "Account settings did not expose Log Out")
        logOut.tap()
        XCTAssertTrue(emailField.waitForExistence(timeout: 20), "Log Out did not return the app to login")
        app.terminate()
        app.launchArguments = []
        app.launch()
        XCTAssertTrue(emailField.waitForExistence(timeout: 20), "The logged-out state did not survive relaunch")
        capture("Staging_Logged_Out", app: app)

        emailField.tap()
        emailField.typeText(email)
        passwordField.tap()
        passwordField.typeText(password)
        signIn.tap()
        XCTAssertTrue(inventoryTab.waitForExistence(timeout: 40), "The synthetic staging account could not log in again")
        dismissSavePasswordPromptIfPresent(in: app, readyElement: inventoryTab)
        app.terminate()
        app.launchArguments = []
        app.launch()
        XCTAssertTrue(inventoryTab.waitForExistence(timeout: 40), "The new staging session did not survive relaunch")
        capture("Staging_Relogin_Relaunch_Recovery", app: app)
    }

    private func dismissSavePasswordPromptIfPresent(
        in app: XCUIApplication,
        readyElement: XCUIElement
    ) {
        // The AutoFill sheet and its button are exposed in the target app's
        // accessibility tree, and the prompt can arrive after login completes.
        let notNowButton = app.buttons["Not Now"]
        if notNowButton.waitForExistence(timeout: 15) {
            notNowButton.tap()
        }
        let signedInScreenIsInteractive = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == true AND hittable == true"),
            object: readyElement
        )
        XCTAssertEqual(
            XCTWaiter.wait(for: [signedInScreenIsInteractive], timeout: 10),
            .completed,
            "The signed-in screen should be interactive after handling the password-save prompt"
        )
    }
}
