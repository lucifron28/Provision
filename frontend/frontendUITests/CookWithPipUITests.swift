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
        XCTAssertTrue(element("pip-chat-suggested-prompt-cook-tonight", in: app).isHittable)
        XCTAssertTrue(element("pip-chat-suggested-prompt-expiring-food", in: app).isHittable)
        capturePipChat("Pip_Chat_Empty", app: app)

        let input = element("pip-chat-input", in: app)
        XCTAssertTrue(input.waitForExistence(timeout: 5))
        input.tap()
        input.typeText("Anong lulutuin natin?")
        app.buttons["pip-chat-send"].tap()

        let reply = app.staticTexts[
            "May Sinigang na Baboy sa recipes natin. Kailangan nito ng 120 g kangkong, at 120 g ang nasa pantry ngayon. Pasok ang kasalukuyang recipe check; buksan ang recipe para tingnan ang iba pang sangkap at safety details."
        ]
        XCTAssertTrue(reply.waitForExistence(timeout: 10))
        let recipeCard = element("pip-chat-recipe-card-301", in: app)
        XCTAssertTrue(recipeCard.waitForExistence(timeout: 5),
                      "Recipe suggestions are rendered as validated household cards")
        scrollTargetIntoView(recipeCard, inside: app.scrollViews["pip-chat-scroll"], in: app)
        assertReachable(recipeCard, in: app)
        capturePipChat("Pip_Chat_Conversation", app: app)

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
        let prompt = element("pip-chat-suggested-prompt-missing-ingredients", in: app)
        scrollTargetIntoView(prompt, inside: app.scrollViews["pip-chat-scroll"], in: app)
        XCTAssertTrue(prompt.isHittable)
        prompt.tap()
        XCTAssertEqual(input.value as? String, "What ingredients am I missing?")
        app.buttons["pip-chat-send"].tap()
        let shoppingReply = app.staticTexts.containing(
            NSPredicate(format: "label CONTAINS %@", "kulang ang 100 g kangkong")
        ).firstMatch
        XCTAssertTrue(shoppingReply.waitForExistence(timeout: 10),
                      "The scripted reply uses the recipe check's exact kangkong shortfall")

        let previewAction = element("pip-chat-open-shopping-preview-305", in: app)
        XCTAssertTrue(previewAction.waitForExistence(timeout: 10))
        let chatScroll = app.scrollViews["pip-chat-scroll"]
        scrollTargetIntoView(previewAction, inside: chatScroll, in: app)
        let composer = element("pip-chat-input", in: app)
        XCTAssertTrue(composer.exists)
        XCTAssertLessThan(previewAction.frame.maxY, composer.frame.minY,
                          "The shopping action must remain above the fixed message composer")
        assertReachable(previewAction, in: app)
        capturePipChat("Pip_Chat_Shopping_Preview_Action", app: app)
        previewAction.tap()

        XCTAssertTrue(app.navigationBars["Shopping Preview"].waitForExistence(timeout: 10),
                      "Pip's shopping action opens the existing shopping review screen")
        XCTAssertTrue(element("recipe-shopping-safety-status", in: app).waitForExistence(timeout: 10))
        let confirmShopping = element("recipe-shopping-confirm", in: app)
        XCTAssertTrue(confirmShopping.exists,
                      "Chat opens the existing preview; the household must still review and confirm it")
        XCTAssertFalse(element("recipe-shopping-confirm-action", in: app).exists,
                         "Opening the preview never submits shopping changes")
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
        let privacyDetails = element("pip-chat-privacy-details", in: app)
        XCTAssertTrue(privacyDetails.waitForExistence(timeout: 10))
        scrollTargetIntoView(privacyDetails, inside: chatScroll, progressAnchor: allergyConsent, in: app)
        XCTAssertTrue(privacyDetails.isHittable)
        privacyDetails.tap()
        let privacyNotice = element("pip-chat-data-notice", in: app)
        XCTAssertTrue(privacyNotice.waitForExistence(timeout: 5))
        scrollTargetIntoView(privacyNotice, inside: chatScroll, progressAnchor: privacyDetails, in: app)
        XCTAssertTrue(privacyNotice.isHittable)
        capturePipChat("Pip_Chat_Dark_Large_Text", app: app)
    }

    func testPipChatConsentControlsGallery() {
        let app = launch()
        openCookWithPip(app)
        app.buttons["cook-with-pip-chat-link"].tap()

        let chatConsent = app.switches["pip-chat-consent-chat"]
        let allergyConsent = app.switches["pip-chat-consent-allergies"]
        XCTAssertTrue(chatConsent.waitForExistence(timeout: 10))
        XCTAssertTrue(allergyConsent.waitForExistence(timeout: 10))
        let consentLoaded = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "1"), object: chatConsent
        )
        let separateAllergyConsentOff = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "0"), object: allergyConsent
        )
        XCTAssertEqual(XCTWaiter.wait(for: [consentLoaded, separateAllergyConsentOff], timeout: 10), .completed)
        XCTAssertEqual(chatConsent.value as? String, "1", "The fixture starts with Pip Chat consent enabled")
        XCTAssertEqual(allergyConsent.value as? String, "0", "Allergy sharing remains a separate consent")
        XCTAssertTrue(chatConsent.isHittable)
        XCTAssertTrue(allergyConsent.isHittable)
        let allergyConsentReady = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "isEnabled == true AND isHittable == true"),
            object: allergyConsent
        )
        XCTAssertEqual(XCTWaiter.wait(for: [allergyConsentReady], timeout: 10), .completed,
                       "Separate allergy consent becomes available after chat consent finishes loading")

        tapSwitchControl(allergyConsent)
        let allergyConsentEnabled = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "1"), object: allergyConsent
        )
        XCTAssertEqual(XCTWaiter.wait(for: [allergyConsentEnabled], timeout: 10), .completed)
        XCTAssertTrue(allergyConsent.isEnabled)
        XCTAssertTrue(allergyConsent.isHittable)
        XCTAssertTrue(element("pip-chat-privacy-details", in: app).waitForExistence(timeout: 5),
                      "Full privacy details remain available after chat consent")
        capturePipChat("Pip_Chat_Consent_Controls", app: app)
    }

    func testPipChatRecipeContextGallery() {
        let app = launch()
        openCookNowRecipe(app)
        let askPip = app.buttons["recipe-ask-pip-link"]
        scrollTargetIntoView(
            askPip,
            inside: app.scrollViews["recipe-detail-scroll"],
            progressAnchor: element("recipe-detail-title", in: app),
            in: app
        )
        assertReachable(askPip, in: app)
        askPip.tap()

        let contextCard = element("pip-chat-context-card", in: app)
        let contextTitle = app.staticTexts["pip-chat-context-title"]
        XCTAssertTrue(contextCard.waitForExistence(timeout: 10))
        XCTAssertTrue(contextTitle.waitForExistence(timeout: 5))
        XCTAssertTrue(element("pip-chat-empty-state", in: app).waitForExistence(timeout: 10))
        XCTAssertEqual(contextTitle.label, "Sinigang na Baboy")
        XCTAssertTrue(element("pip-chat-suggested-prompt-substitute", in: app).exists)
        assertReachable(contextCard, in: app)
        capturePipChat("Pip_Chat_Recipe_Context", app: app)
    }

    func testPipChatProductContextGallery() {
        let app = launch(screen: "product-chat-context")
        let askPip = app.buttons["product-ask-pip-link"]
        XCTAssertTrue(askPip.waitForExistence(timeout: 10))
        XCTAssertTrue(askPip.isHittable)
        askPip.tap()

        let contextCard = element("pip-chat-context-card", in: app)
        let contextTitle = app.staticTexts["pip-chat-context-title"]
        XCTAssertTrue(contextCard.waitForExistence(timeout: 10))
        XCTAssertTrue(contextTitle.waitForExistence(timeout: 5))
        XCTAssertTrue(element("pip-chat-empty-state", in: app).waitForExistence(timeout: 10))
        XCTAssertEqual(contextTitle.label, "Century Tuna Flakes in Oil")
        XCTAssertTrue(element("pip-chat-suggested-prompt-use-product", in: app).exists)
        assertReachable(contextCard, in: app)
        capturePipChat("Pip_Chat_Product_Context", app: app)
    }

    func testExpiringKangkongFindsSinigangWithCurrentIngredientAvailability() {
        let app = launch(screen: "expiring-recipe-flow")
        XCTAssertTrue(element("home-dashboard-loaded", in: app).waitForExistence(timeout: 10))

        let dashboardScroll = app.scrollViews["home-dashboard-scroll"]
        let expiringHeading = element("home-expiring-soon-heading", in: app)
        scrollTargetIntoView(expiringHeading, inside: dashboardScroll, in: app)
        let expiringItemsScroll = app.scrollViews["home-expiring-items-scroll"]
        scrollTargetIntoView(expiringItemsScroll, inside: dashboardScroll,
                             progressAnchor: expiringHeading, in: app)
        let findKangkongRecipes = element("expiring-find-recipes-15", in: app)
        XCTAssertTrue(findKangkongRecipes.waitForExistence(timeout: 5),
                      "The expiring Kangkong card offers a recipe route")
        scrollTargetIntoView(findKangkongRecipes, inside: expiringItemsScroll,
                             targetDescription: "the expiring Kangkong Find Recipes action",
                             in: app, axis: .horizontal)
        XCTAssertTrue(findKangkongRecipes.isHittable,
                      "Find Recipes is visible and usable from the expiring Kangkong card")
        findKangkongRecipes.tap()

        let ingredientFilter = element("cook-with-pip-ingredient-filter", in: app)
        XCTAssertTrue(ingredientFilter.waitForExistence(timeout: 10))
        XCTAssertTrue(ingredientFilter.label.contains("Fresh Kangkong"))
        let recipeList = app.scrollViews["cook-with-pip-recipe-list-scroll"]
        let matchingSinigang = element("recipe-card-301", in: app)
        XCTAssertTrue(matchingSinigang.waitForExistence(timeout: 10),
                      "The filtered household recipe list includes Sinigang na Baboy")
        XCTAssertTrue(matchingSinigang.label.contains("Sinigang na Baboy"))
        scrollTargetIntoView(matchingSinigang, inside: recipeList, in: app)
        matchingSinigang.tap()

        XCTAssertTrue(element("recipe-detail-title", in: app).waitForExistence(timeout: 10))
        XCTAssertEqual(element("recipe-safety-status", in: app).label, "Eligible")
        XCTAssertEqual(element("recipe-availability-status", in: app).label, "Partial")
        XCTAssertTrue(element("recipe-ingredient-availability-overview", in: app).exists)
        XCTAssertTrue(element("recipe-ingredient-availability-summary-0", in: app).label.contains("Have 0.25 kg"))
        XCTAssertTrue(element("recipe-ingredient-availability-summary-0", in: app).label.contains("Missing 0.25 kg"))
        XCTAssertTrue(element("recipe-ingredient-availability-summary-1", in: app).label.contains("Missing 45.25 g"))
        let recipeDetailScroll = app.scrollViews["recipe-detail-scroll"]
        let porkNeeded = element("recipe-ingredient-needed-0", in: app)
        scrollTargetIntoView(porkNeeded, inside: recipeDetailScroll, in: app)
        XCTAssertEqual(element("recipe-ingredient-name-0", in: app).label, "baboy")
        XCTAssertEqual(element("recipe-ingredient-availability-0", in: app).label, "Partial")
        XCTAssertEqual(porkNeeded.label, "Need: 0.5 kg")
        XCTAssertEqual(element("recipe-ingredient-on-hand-0", in: app).label, "Have: 0.25 kg")
        XCTAssertEqual(element("recipe-ingredient-short-0", in: app).label, "Missing: 0.25 kg")

        let sampalokMissing = element("recipe-ingredient-availability-1", in: app)
        scrollTargetIntoView(sampalokMissing, inside: recipeDetailScroll,
                             progressAnchor: porkNeeded, in: app)
        XCTAssertEqual(sampalokMissing.label, "Missing")
        XCTAssertEqual(element("recipe-ingredient-needed-1", in: app).label, "Need: 45.25 g")
        XCTAssertEqual(element("recipe-ingredient-short-1", in: app).label, "Missing: 45.25 g")

        let kangkongAvailable = element("recipe-ingredient-availability-2", in: app)
        scrollTargetIntoView(kangkongAvailable, inside: recipeDetailScroll,
                             progressAnchor: sampalokMissing, in: app)
        XCTAssertEqual(kangkongAvailable.label, "Available")
        XCTAssertEqual(element("recipe-ingredient-on-hand-2", in: app).label, "Have: 500 g")
        let instructions = element("recipe-instructions", in: app)
        scrollTargetIntoView(instructions, inside: recipeDetailScroll,
                             progressAnchor: kangkongAvailable, in: app)
        XCTAssertTrue(instructions.isHittable,
                      "The recipe route opens the existing cooking instructions")

        let shoppingPreviewLink = element("recipe-shopping-preview-link", in: app)
        scrollTargetIntoView(shoppingPreviewLink, inside: recipeDetailScroll,
                             progressAnchor: instructions, in: app)
        XCTAssertTrue(shoppingPreviewLink.isHittable)
        XCTAssertTrue(shoppingPreviewLink.label.contains("Review shopping list"))
        shoppingPreviewLink.tap()
        XCTAssertTrue(element("recipe-shopping-safety-status", in: app).waitForExistence(timeout: 10))
        XCTAssertEqual(element("recipe-shopping-availability-status", in: app).label, "Partial")
        let shoppingReviewForm = scrollContainer("recipe-shopping-review-form", in: app)
        let porkShoppingLine = element("recipe-shopping-name-911", in: app)
        scrollTargetIntoView(porkShoppingLine, inside: shoppingReviewForm, in: app)
        XCTAssertEqual(porkShoppingLine.label, "baboy")
        let sampalokShoppingLine = element("recipe-shopping-name-912", in: app)
        scrollTargetIntoView(sampalokShoppingLine, inside: shoppingReviewForm,
                             progressAnchor: porkShoppingLine, in: app)
        XCTAssertEqual(sampalokShoppingLine.label, "sampalok")
        let confirmShopping = element("recipe-shopping-confirm", in: app)
        XCTAssertTrue(confirmShopping.waitForExistence(timeout: 5))
        XCTAssertTrue(confirmShopping.isEnabled,
                      "Only the reviewed, eligible shortage lines are selected for confirmation")
        confirmShopping.tap()
        let confirmAction = app.buttons.matching(identifier: "recipe-shopping-confirm-action").firstMatch
        XCTAssertTrue(confirmAction.waitForExistence(timeout: 5))
        confirmAction.tap()
        let resultCounts = element("recipe-shopping-result-counts", in: app)
        XCTAssertTrue(resultCounts.waitForExistence(timeout: 10))
        XCTAssertEqual(resultCounts.label, "Created 2 · Updated 0 · Unchanged 0 · Consolidated 0")
        element("recipe-shopping-view-list", in: app).tap()
        XCTAssertTrue(app.navigationBars["Shopping List"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["baboy"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["sampalok"].exists,
                      "The confirmed missing ingredients appear in the existing Shopping List")
    }

    func testHomeNavigationAndCaptureRecipeScreens() {
        let app = launch()
        let homeEntry = element("cook-with-pip-entry", in: app)
        XCTAssertTrue(homeEntry.waitForExistence(timeout: 10))
        let quickAdd = element("home-quick-add-groceries", in: app)
        let shoppingShortcut = element("home-quick-shopping", in: app)
        XCTAssertTrue(quickAdd.waitForExistence(timeout: 5))
        XCTAssertTrue(quickAdd.isHittable)
        XCTAssertTrue(shoppingShortcut.isHittable)
        quickAdd.tap()
        XCTAssertTrue(element("inventory-add-mode-picker", in: app).waitForExistence(timeout: 10),
                      "The Home Add Groceries shortcut opens the existing inventory intake form")
        XCTAssertTrue(element("inventory-add-submit", in: app).exists)
        let cancelQuickAdd = app.navigationBars.buttons["Cancel"]
        XCTAssertTrue(cancelQuickAdd.waitForExistence(timeout: 5))
        cancelQuickAdd.tap()
        XCTAssertTrue(homeEntry.waitForExistence(timeout: 5))
        XCTAssertFalse(element("ui-test-fixture-banner", in: app).exists,
                        "The demo must not show a developer fixture banner")
        let dashboardLoaded = element("home-dashboard-loaded", in: app)
        XCTAssertTrue(dashboardLoaded.waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Fresh Kangkong"].exists,
                      "The home demo shows believable household inventory")
        capture("Home_Cook_with_Pip", app: app)
        homeEntry.tap()

        XCTAssertTrue(element("cook-with-pip-introduction", in: app).waitForExistence(timeout: 10))
        let myRecipes = app.buttons["cook-mode-myRecipes"]
        XCTAssertTrue(myRecipes.waitForExistence(timeout: 10))
        myRecipes.tap()
        let search = app.textFields["cook-with-pip-search"]
        XCTAssertTrue(search.waitForExistence(timeout: 10),
                      "Choosing My Recipes opens household recipe search")
        XCTAssertTrue(search.isHittable,
                      "Household recipe search remains available after selecting My Recipes")
        search.tap()
        search.typeText("Ginisang Kangkong")
        let searchDone = app.buttons["cook-with-pip-search-keyboard-done"]
        XCTAssertTrue(searchDone.waitForExistence(timeout: 5))
        searchDone.tap()
        let searchedRecipe = app.buttons["recipe-card-303"]
        XCTAssertTrue(searchedRecipe.waitForExistence(timeout: 10))
        XCTAssertTrue(searchedRecipe.label.contains("Ginisang Kangkong"))
        XCTAssertFalse(searchedRecipe.label.contains("Filipino · Filipino"),
                       "Recipe cards should not repeat the same cuisine and region")
        XCTAssertTrue(searchedRecipe.isHittable,
                      "The filtered household recipe is visible in the Cook with Pip search state")
        XCTAssertFalse(app.keyboards.firstMatch.isHittable,
                       "The Cook with Pip search capture is taken after dismissing the keyboard")
        capture("Cook_with_Pip", app: app)

        let clearSearch = app.buttons["Clear search"]
        XCTAssertTrue(clearSearch.waitForExistence(timeout: 5))
        clearSearch.tap()
        let cookNow = app.buttons["cook-mode-cookNow"]
        XCTAssertTrue(cookNow.waitForExistence(timeout: 5))
        XCTAssertTrue(cookNow.isHittable)
        cookNow.tap()
        let cookNowSelected = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "Selected"), object: cookNow
        )
        XCTAssertEqual(XCTWaiter.wait(for: [cookNowSelected], timeout: 10), .completed)
        let cookNowRecipe = app.buttons["recipe-card-301"]
        XCTAssertTrue(cookNowRecipe.waitForExistence(timeout: 10))
        XCTAssertTrue(cookNowRecipe.isHittable)
        XCTAssertEqual(cookNowRecipe.value as? String, "Recommendation")
        capture("Cook_Now", app: app)

        let almostThereMode = element("cook-mode-almostThere", in: app)
        almostThereMode.tap()
        let almostThereSelected = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "Selected"), object: almostThereMode
        )
        XCTAssertEqual(XCTWaiter.wait(for: [almostThereSelected], timeout: 10), .completed,
                       "Almost There becomes selected before its results are captured")
        let almostThereRecipe = app.buttons["recipe-card-302"]
        XCTAssertTrue(almostThereRecipe.waitForExistence(timeout: 10))
        let recommendationType = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "Recommendation"), object: almostThereRecipe
        )
        XCTAssertEqual(XCTWaiter.wait(for: [recommendationType], timeout: 10), .completed,
                       "The card is a server recommendation, not a household recipe")
        let recommendationLoaded = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label CONTAINS %@", "2 missing"), object: almostThereRecipe
        )
        XCTAssertEqual(XCTWaiter.wait(for: [recommendationLoaded], timeout: 10), .completed,
                       "Almost There shows the recommendation and its server-reported missing count")
        XCTAssertTrue(almostThereRecipe.isHittable,
                      "The captured Almost There card is the visible recommendation, not a stale household card")
        capture("Almost_There", app: app)

        let myRecipesMode = element("cook-mode-myRecipes", in: app)
        myRecipesMode.tap()
        let householdModeSelected = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "Selected"), object: myRecipesMode
        )
        XCTAssertEqual(XCTWaiter.wait(for: [householdModeSelected], timeout: 10), .completed,
                       "My Recipes becomes selected before household recipes are captured")
        let householdRecipe = element("recipe-card-303", in: app)
        XCTAssertTrue(householdRecipe.waitForExistence(timeout: 10))
        XCTAssertEqual(householdRecipe.value as? String, "Household recipe")
        capture("My_Recipes", app: app)
        householdRecipe.tap()

        XCTAssertTrue(element("recipe-detail-title", in: app).waitForExistence(timeout: 10))
        XCTAssertEqual(element("recipe-safety-status", in: app).label, "Review required")
        XCTAssertEqual(element("recipe-availability-status", in: app).label, "Unknown")
        XCTAssertFalse(app.staticTexts["Filipino · Filipino"].exists,
                       "Recipe details should not repeat the same cuisine and region")
        let toyoAvailability = element("recipe-ingredient-availability-summary-1", in: app)
        XCTAssertTrue(toyoAvailability.waitForExistence(timeout: 5))
        XCTAssertTrue(toyoAvailability.label.contains("Have 300 mL"))
        XCTAssertTrue(toyoAvailability.label.contains("Need 15 mL"),
                      "Ginisang Kangkong uses the household toyo line at its recipe quantity")
        capture("Recipe_Detail", app: app)
        let instructions = element("recipe-instructions", in: app)
        let recipeScroll = app.scrollViews["recipe-detail-scroll"]
        scrollTargetIntoView(instructions, inside: recipeScroll, in: app)
        XCTAssertTrue(instructions.exists)
        XCTAssertTrue(instructions.isHittable,
                      "Recipe instructions remain visible after scrolling the recipe detail")
        let firstInstruction = app.staticTexts["recipe-instruction-step-1"]
        scrollTargetIntoView(
            firstInstruction,
            inside: recipeScroll,
            progressAnchor: instructions,
            targetDescription: "first instruction for Ginisang Kangkong",
            in: app
        )
        XCTAssertEqual(firstInstruction.label, "Prepare the measured ingredients.",
                       "The screenshot must show an actual instruction from the selected recipe")
        assertReachable(firstInstruction, in: app)
        capture("Recipe_Detail_Instructions", app: app)

        let shoppingPreviewLink = element("recipe-shopping-preview-link", in: app)
        scrollTargetIntoView(shoppingPreviewLink, inside: recipeScroll,
                             progressAnchor: firstInstruction, in: app)
        XCTAssertTrue(shoppingPreviewLink.isHittable)
        shoppingPreviewLink.tap()
        let shoppingSafetyStatus = element("recipe-shopping-safety-status", in: app)
        XCTAssertTrue(shoppingSafetyStatus.waitForExistence(timeout: 10))
        XCTAssertEqual(shoppingSafetyStatus.label, "Review required")
        let shoppingForm = scrollContainer("recipe-shopping-review-form", in: app)
        let toyoShoppingLine = element("recipe-shopping-name-903", in: app)
        scrollTargetIntoView(toyoShoppingLine, inside: shoppingForm, in: app)
        XCTAssertEqual(toyoShoppingLine.label, "toyo",
                       "The shopping preview keeps the recipe's household ingredient name")
        let toyoQuantityDetails = element("recipe-shopping-quantity-details-903", in: app)
        scrollTargetIntoView(toyoQuantityDetails, inside: shoppingForm,
                             progressAnchor: toyoShoppingLine, in: app)
        toyoQuantityDetails.tap()
        let toyoRequiredQuantity = element("recipe-shopping-quantity-required-903", in: app)
        XCTAssertTrue(toyoRequiredQuantity.waitForExistence(timeout: 5))
        XCTAssertTrue(toyoRequiredQuantity.label.contains("15 mL"))
        let confirmShopping = app.navigationBars.buttons["recipe-shopping-confirm"]
        XCTAssertTrue(confirmShopping.waitForExistence(timeout: 5))
        XCTAssertFalse(confirmShopping.isEnabled,
                       "The review-required recipe remains ineligible until the required review is acknowledged")
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

    func testCookWithPipNeedsReviewCandidatesAreActionable() {
        let app = launch(scenario: "recipes-needs-review")
        openCookWithPip(app)

        let reviewSection = element("cook-with-pip-needs-review", in: app)
        XCTAssertTrue(reviewSection.waitForExistence(timeout: 10), "Review-required recipes stay discoverable")
        let candidate = element("cook-with-pip-review-recipe-303", in: app)
        XCTAssertTrue(candidate.waitForExistence(timeout: 10))
        let explanation = element("cook-with-pip-review-explanation-303", in: app)
        XCTAssertTrue(explanation.waitForExistence(timeout: 5))
        XCTAssertTrue(explanation.label.contains("Review the package label"),
                      "The review card gives a concrete package-label action")
        XCTAssertTrue(explanation.label.contains("cannot match kangkong to an ingredient in its catalog"),
                      "The review card identifies the unresolved ingredient mapping")
        XCTAssertTrue(explanation.label.contains("cannot check pantry stock or ingredient-based safety"),
                      "The review card explains which checks remain unavailable")
        XCTAssertTrue(explanation.label.contains("stays under review until the match is corrected"),
                      "The review card keeps the recipe in review until its ingredient is identified")
        XCTAssertFalse(explanation.label.contains("Check quantities and units for kangkong"),
                       "Ingredient mapping uncertainty must not be mislabeled as a quantity issue")
        scrollTargetIntoView(candidate, inside: app.scrollViews["cook-with-pip-recipe-list-scroll"], in: app)
        XCTAssertTrue(candidate.isHittable, "The review card remains tappable after deterministic scrolling")
        capture("Cook_with_Pip_Needs_Review", app: app)

        candidate.tap()
        XCTAssertTrue(element("recipe-detail-title", in: app).waitForExistence(timeout: 10))
        XCTAssertEqual(element("recipe-safety-status", in: app).label, "Review required")
        XCTAssertTrue(element("recipe-review-product-labels", in: app).exists,
                       "The existing detail flow exposes package-label review")
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
        let filipinoCuisine = element("pip-cuisine-filipino", in: app)
        XCTAssertTrue(filipinoCuisine.isHittable, "Common cuisine choices are visible as selectable controls")
        XCTAssertEqual(filipinoCuisine.value as? String, "Selected")
        filipinoCuisine.tap()
        XCTAssertEqual(filipinoCuisine.value as? String, "Not selected")
        filipinoCuisine.tap()
        XCTAssertEqual(filipinoCuisine.value as? String, "Selected")
        cuisines.tap()
        cuisines.typeText("Peruvian")
        let addCuisine = element("pip-cuisine-add-custom", in: app)
        XCTAssertTrue(addCuisine.isHittable, "Custom cuisine entry can be added beside the text field")
        addCuisine.tap()
        let peruvianCuisine = element("pip-cuisine-peruvian", in: app)
        XCTAssertTrue(peruvianCuisine.waitForExistence(timeout: 5))
        XCTAssertEqual(peruvianCuisine.value as? String, "Selected")
        element("pip-preferences-keyboard-done", in: app).tap()
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
        scrollTargetIntoView(
            milkAllergen,
            inside: preferencesForm,
            progressAnchor: allergyHeading,
            in: app
        )
        assertReachable(milkAllergen, in: app)
        scrollTargetIntoView(
            milkSeverity,
            inside: preferencesForm,
            progressAnchor: milkAllergen,
            in: app
        )
        assertReachable(milkSeverity, in: app)
        scrollTargetIntoView(
            milkCrossContact,
            inside: preferencesForm,
            progressAnchor: milkSeverity,
            in: app
        )
        assertReachable(milkCrossContact, in: app)
        XCTAssertEqual(milkAllergen.value as? String, "1")
        XCTAssertEqual(milkCrossContact.value as? String, "1")
        capture("Preferences_Allergy_Declared", app: app)
    }

    func testProductLabelReviewScreens() {
        let app = launch()
        openCookWithPip(app)
        app.buttons["cook-with-pip-management"].tap()
        app.buttons["cook-with-pip-product-labels-link"].tap()
        let labelList = app.buttons["pip-label-product-9903"]
        XCTAssertTrue(labelList.waitForExistence(timeout: 10))
        XCTAssertTrue(labelList.isHittable, "The loaded product-label list exposes the selected fixture")
        capture("Product_Label_List", app: app)
        labelList.tap()
        let labelForm = scrollContainer("pip-label-review-form", in: app)
        let productTitle = labelForm.staticTexts["pip-label-product-title"]
        XCTAssertTrue(productTitle.waitForExistence(timeout: 10))
        let mappingType = identifiedElement("pip-label-mapping-type", inside: labelForm)
        XCTAssertTrue(mappingType.waitForExistence(timeout: 10),
                      "The loaded mapping control is a stable readiness marker for the label form")
        capture("Product_Label_Review", app: app)

        let milkDeclaration = identifiedElement("pip-label-allergen-milk", inside: labelForm)
        scrollTargetIntoView(milkDeclaration, inside: labelForm, progressAnchor: mappingType, in: app)
        milkDeclaration.tap()
        let declaredOption = app.buttons["pip-label-disposition-declared"]
        XCTAssertTrue(declaredOption.waitForExistence(timeout: 5))
        declaredOption.tap()
        XCTAssertEqual(milkDeclaration.value as? String, "Declared on label")

        let source = labelForm.textFields["pip-label-source-reference"]
        scrollTargetIntoView(source, inside: labelForm, progressAnchor: productTitle, in: app)
        source.tap()
        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        XCTAssertTrue(source.isHittable, "The focused label source stays available with the keyboard open")
        typeTextAndWait("Kara Coconut Milk, Original", in: source)
        XCTAssertEqual(source.value as? String, "Kara Coconut Milk, Original")
        let keyboardDone = app.buttons["pip-label-keyboard-done"]
        XCTAssertTrue(keyboardDone.waitForExistence(timeout: 5))
        keyboardDone.tap()
        let keyboardDismissed = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "isHittable == false"), object: keyboard
        )
        XCTAssertEqual(XCTWaiter.wait(for: [keyboardDismissed], timeout: 5), .completed)
        let saveReview = labelForm.buttons["pip-label-save-review"]
        scrollTargetIntoView(saveReview, inside: labelForm, progressAnchor: productTitle, in: app)
        XCTAssertTrue(saveReview.isEnabled, "A verified mapping and source reference enable saving the label review")
        XCTAssertTrue(saveReview.isHittable)
        saveReview.tap()
        let savedLabelMessage = labelForm.staticTexts["pip-label-status-message"]
        let saveError = labelForm.descendants(matching: .any)
            .matching(identifier: "pip-label-error").firstMatch
        let didSave = savedLabelMessage.waitForExistence(timeout: 15)
        let saveFailure = saveError.exists ? saveError.label : "No save status appeared"
        XCTAssertTrue(didSave, "Expected the save result before checking the updated label: \(saveFailure)")
        XCTAssertTrue(savedLabelMessage.label.contains("Package label review recorded"))
        let currentStatus = identifiedElement("pip-label-current-status", inside: labelForm)
        XCTAssertFalse(app.keyboards.firstMatch.isHittable,
                       "The saved review confirmation is captured after keyboard dismissal")
        scrollTargetIntoView(
            savedLabelMessage,
            inside: labelForm,
            progressAnchor: saveReview,
            targetDescription: "saved package label review confirmation",
            in: app
        )
        assertReachable(savedLabelMessage, in: app)
        XCTAssertFalse(currentStatus.isHittable,
                       "The saved-confirmation capture shows the result at the bottom of the form")
        capture("Product_Label_Saved_Keyboard_Dismissed", app: app)

        let packageDeclarationHeading = labelForm.staticTexts["pip-label-package-declaration-heading"]
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
        XCTAssertFalse(savedLabelMessage.isHittable,
                       "The current-label capture is separated from the saved result message")
        XCTAssertEqual(milkDeclaration.value as? String, "Declared on label")
        XCTAssertFalse(app.keyboards.firstMatch.isHittable, "Saving a label review dismisses the keyboard")
        capture("Product_Label_Review_Current", app: app)

        let technicalDetails = labelForm.buttons["pip-label-technical-details"]
        scrollTargetIntoView(
            technicalDetails,
            inside: labelForm,
            progressAnchor: packageDeclarationHeading,
            targetDescription: "pip-label-technical-details",
            in: app,
            initialDirection: .towardStart
        )
        assertReachable(technicalDetails, in: app)
        let reviewRevision = labelForm.staticTexts["pip-label-review-revision"]
        XCTAssertFalse(reviewRevision.exists, "Revision metadata starts collapsed")
        technicalDetails.tap()
        XCTAssertTrue(reviewRevision.waitForExistence(timeout: 5))
        XCTAssertEqual(technicalDetails.value as? String, "Expanded")
        scrollTargetIntoView(reviewRevision, inside: labelForm, progressAnchor: technicalDetails, in: app)
        XCTAssertTrue(reviewRevision.label.contains("v1"))
        assertReachable(reviewRevision, in: app)
        technicalDetails.tap()
        waitUntilGone(reviewRevision)
        XCTAssertEqual(technicalDetails.value as? String, "Collapsed")
        let mappingVerified = labelForm.switches["pip-label-mapping-verified"]
        scrollTargetIntoView(mappingType, inside: labelForm, progressAnchor: packageDeclarationHeading,
                             in: app, initialDirection: .towardStart)
        assertReachable(mappingType, in: app)
        scrollTargetIntoView(mappingVerified, inside: labelForm, progressAnchor: mappingType, in: app)
        assertReachable(mappingVerified, in: app)
    }

    func testFormsStayReadableInDarkModeAndLargeText() {
        let darkApp = launch(appearance: "dark")
        openCookWithPip(darkApp)
        darkApp.buttons["cook-with-pip-management"].tap()
        darkApp.buttons["cook-with-pip-preferences-link"].tap()
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

        navigateBack(
            darkApp,
            to: darkApp.buttons["cook-with-pip-product-labels-link"],
            screen: "Cook with Pip management"
        )
        darkApp.buttons["cook-with-pip-product-labels-link"].tap()
        let darkProduct = darkApp.buttons["pip-label-product-9903"]
        XCTAssertTrue(darkProduct.waitForExistence(timeout: 10),
                      "The dark-mode product list finishes loading before its product is opened")
        XCTAssertTrue(darkProduct.isHittable)
        darkProduct.tap()
        let darkLabelForm = scrollContainer("pip-label-review-form", in: darkApp)
        let darkProductTitle = darkLabelForm.staticTexts["pip-label-product-title"]
        XCTAssertTrue(darkProductTitle.waitForExistence(timeout: 10))
        XCTAssertTrue(darkProductTitle.isHittable)
        capture("Product_Label_Review_Dark_Mode", app: darkApp)

        darkApp.terminate()
        let largeLabel = launch(dynamicType: "accessibility")
        openCookWithPip(largeLabel)
        largeLabel.buttons["cook-with-pip-management"].tap()
        largeLabel.buttons["cook-with-pip-product-labels-link"].tap()
        let largeProduct = largeLabel.buttons["pip-label-product-9903"]
        XCTAssertTrue(largeProduct.waitForExistence(timeout: 10),
                      "The large-text product list finishes loading before its product is opened")
        XCTAssertTrue(largeProduct.isHittable)
        largeProduct.tap()
        let labelForm = scrollContainer("pip-label-review-form", in: largeLabel)
        let productTitle = labelForm.staticTexts["pip-label-product-title"]
        XCTAssertTrue(productTitle.waitForExistence(timeout: 10))
        XCTAssertTrue(productTitle.isHittable)
        assertReachable(productTitle, in: largeLabel)
        XCTAssertTrue(labelForm.waitForExistence(timeout: 5))
        let technicalDetails = labelForm.buttons["pip-label-technical-details"]
        XCTAssertTrue(technicalDetails.waitForExistence(timeout: 5))
        scrollTargetIntoView(technicalDetails, inside: labelForm, progressAnchor: productTitle, in: largeLabel)
        let serverVersion = labelForm.staticTexts["pip-label-server-version"]
        XCTAssertFalse(serverVersion.exists, "Technical metadata starts collapsed below the product details")
        capture("Product_Label_Review_Large_Text", app: largeLabel)
        technicalDetails.tap()
        XCTAssertTrue(serverVersion.waitForExistence(timeout: 5))
        XCTAssertEqual(technicalDetails.value as? String, "Expanded")
        scrollTargetIntoView(serverVersion, inside: labelForm, progressAnchor: technicalDetails, in: largeLabel)
        XCTAssertTrue(serverVersion.label.contains("2026-11-09T00:00:00Z"))
        assertReachable(serverVersion, in: largeLabel)
        scrollTargetIntoView(technicalDetails, inside: labelForm, progressAnchor: serverVersion, in: largeLabel)
        technicalDetails.tap()
        waitUntilGone(serverVersion)
        XCTAssertEqual(technicalDetails.value as? String, "Collapsed")
        let mappingVerified = labelForm.switches["pip-label-mapping-verified"]
        scrollTargetIntoView(mappingVerified, inside: labelForm, progressAnchor: technicalDetails, in: largeLabel)
        assertReachable(mappingVerified, in: largeLabel)
        capture("Product_Label_Review_Scrolled", app: largeLabel)

        let mappingNote = largeLabel.staticTexts[
            "A verified, complete mapping is required before a package label review can be recorded."
        ]
        scrollTargetIntoView(mappingNote, inside: labelForm, progressAnchor: mappingVerified, in: largeLabel)
        assertReachable(mappingNote, in: largeLabel)

        let milkDeclaration = labelForm.descendants(matching: .any)
            .matching(identifier: "pip-label-allergen-milk").firstMatch
        scrollTargetIntoView(milkDeclaration, inside: labelForm, progressAnchor: mappingNote, in: largeLabel)
        XCTAssertTrue(milkDeclaration.label.hasSuffix("Milk label declaration"),
                      "The picker label preserves the allergen declaration description")
        assertReachable(milkDeclaration, in: largeLabel)

        let customAllergensHeading = labelForm.staticTexts["pip-label-custom-allergens-heading"]
        let customAllergensField = labelForm.textFields["pip-label-custom-allergens"]
        scrollTargetIntoView(customAllergensHeading, inside: labelForm, progressAnchor: milkDeclaration, in: largeLabel)
        assertReachable(customAllergensHeading, in: largeLabel)
        scrollTargetIntoView(customAllergensField, inside: labelForm,
                             progressAnchor: customAllergensHeading, in: largeLabel)
        assertReachable(customAllergensField, in: largeLabel)

        let sourceField = labelForm.textFields["pip-label-source-reference"]
        scrollTargetIntoView(sourceField, inside: labelForm, progressAnchor: customAllergensHeading, in: largeLabel)
        XCTAssertEqual(sourceField.label, "Source reference")
        XCTAssertEqual(sourceField.placeholderValue, "Package label, URL, or label section")
        assertReachable(sourceField, in: largeLabel)
    }

    func testStaleProductLabelReviewIsShownAsStale() {
        let app = launch(scenario: "product-label-stale")
        openCookWithPip(app)
        app.buttons["cook-with-pip-management"].tap()
        app.buttons["cook-with-pip-product-labels-link"].tap()
        let staleProduct = app.buttons["pip-label-product-9903"]
        XCTAssertTrue(staleProduct.waitForExistence(timeout: 10),
                      "The stale-review product list finishes loading before its product is opened")
        XCTAssertTrue(staleProduct.isHittable)
        staleProduct.tap()

        let labelForm = scrollContainer("pip-label-review-form", in: app)
        let productTitle = labelForm.staticTexts["pip-label-product-title"]
        XCTAssertTrue(productTitle.waitForExistence(timeout: 10))
        let mappingType = identifiedElement("pip-label-mapping-type", inside: labelForm)
        scrollTargetIntoView(mappingType, inside: labelForm, progressAnchor: productTitle, in: app)
        XCTAssertTrue(mappingType.exists, "The loaded label form exposes its mapping control")
        assertReachable(mappingType, in: app)
        let milkDeclaration = identifiedElement("pip-label-allergen-milk", inside: labelForm)
        let ingredientSearchButton = labelForm.buttons["pip-label-search-ingredients"]
        scrollTargetIntoView(milkDeclaration, inside: labelForm, progressAnchor: mappingType, in: app)
        XCTAssertEqual(milkDeclaration.value as? String, "Declared on label")
        let status = identifiedElement("pip-label-current-status", inside: labelForm)
        let packageDeclarationHeading = labelForm.staticTexts["pip-label-package-declaration-heading"]
        scrollTargetIntoView(status, inside: labelForm, progressAnchor: milkDeclaration, in: app)
        XCTAssertTrue(status.waitForExistence(timeout: 10))
        XCTAssertTrue(status.label.contains("no longer current"))
        let mappingVerified = labelForm.switches["pip-label-mapping-verified"]
        let ingredientSearchField = labelForm.textFields["pip-label-ingredient-search"]
        scrollTargetIntoView(mappingType, inside: labelForm, progressAnchor: status,
                             in: app, initialDirection: .towardStart)
        assertReachable(mappingType, in: app)
        scrollTargetIntoView(mappingVerified, inside: labelForm, progressAnchor: mappingType, in: app)
        assertReachable(mappingVerified, in: app)
        scrollTargetIntoView(ingredientSearchField, inside: labelForm, progressAnchor: mappingVerified,
                             in: app, initialDirection: .towardStart)
        assertReachable(ingredientSearchField, in: app)
        XCTAssertTrue(ingredientSearchButton.waitForExistence(timeout: 5))
        assertReachable(ingredientSearchButton, in: app)
        scrollTargetIntoView(status, inside: labelForm, progressAnchor: ingredientSearchButton, in: app)
        assertReachable(status, in: app)
        XCTAssertTrue(packageDeclarationHeading.waitForExistence(timeout: 5))
        assertReachable(packageDeclarationHeading, in: app)
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

        let shoppingPreview = element("recipe-shopping-preview-link", in: app)
        scrollTargetIntoView(shoppingPreview, inside: app.scrollViews["recipe-detail-scroll"], in: app)
        XCTAssertTrue(shoppingPreview.isHittable)
        shoppingPreview.tap()
        let appliedSubstitutionsHeading = element("recipe-shopping-applied-substitutions", in: app)
        XCTAssertTrue(appliedSubstitutionsHeading.waitForExistence(timeout: 5))
        XCTAssertEqual(appliedSubstitutionsHeading.label, "Applied substitutions")
        let appliedShoppingSubstitution = element("recipe-shopping-applied-substitution-0", in: app)
        XCTAssertTrue(appliedShoppingSubstitution.waitForExistence(timeout: 10))
        XCTAssertTrue(appliedShoppingSubstitution.label.contains("calamansi"))
        XCTAssertTrue(appliedShoppingSubstitution.label.contains("sampalok"))
        capture("Shopping_Preview_Applied_Substitution", app: app)
    }

    func testInventoryQuickAddOffersScannerAndMinimalManualEntry() {
        let app = launch(screen: "inventory-quick-add")
        let inventoryTab = app.tabBars.buttons["Inventory"]
        XCTAssertTrue(inventoryTab.waitForExistence(timeout: 10))
        inventoryTab.tap()

        let addMenu = app.buttons["inventory-add-menu"]
        XCTAssertTrue(addMenu.waitForExistence(timeout: 10))
        addMenu.tap()
        let scanOption = app.buttons["inventory-add-scan-option"]
        XCTAssertTrue(scanOption.waitForExistence(timeout: 5))
        scanOption.tap()

        let receiptMode = app.buttons["Receipt Intake"]
        XCTAssertTrue(receiptMode.waitForExistence(timeout: 10))

        let enterBarcode = element("scan-enter-barcode", in: app)
        XCTAssertTrue(enterBarcode.waitForExistence(timeout: 5))
        enterBarcode.tap()
        let barcodeField = element("manual-intake-barcode", in: app)
        XCTAssertTrue(barcodeField.waitForExistence(timeout: 5))
        barcodeField.tap()
        barcodeField.typeText("4800016644818")
        let lookupBarcode = element("manual-intake-barcode-lookup", in: app)
        XCTAssertTrue(lookupBarcode.isEnabled)
        lookupBarcode.tap()
        let lookedUpTuna = element("intake-preview-item-4800016644818", in: app)
        XCTAssertTrue(lookedUpTuna.waitForExistence(timeout: 10))
        let tunaQuantityUpdated = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label CONTAINS %@", "5 cans"),
            object: lookedUpTuna
        )
        XCTAssertEqual(XCTWaiter.wait(for: [tunaQuantityUpdated], timeout: 10), .completed,
                       "A known barcode should increment the existing household item from four to five cans")

        receiptMode.tap()
        let receiptHeading = app.staticTexts["Supermarket Receipt Scanner"]
        XCTAssertTrue(receiptHeading.waitForExistence(timeout: 5))
        let tunaRow = element("intake-preview-item-4800016644818", in: app)
        XCTAssertTrue(
            tunaRow.waitForExistence(timeout: 5),
            "Preview receipt intake should show the sample item row"
        )
        XCTAssertTrue(
            tunaRow.label.contains("Pantry - Shelf A"),
            "Preview receipt intake should announce the resolved location, got: \(tunaRow.label)"
        )
        capture("Inventory_Receipt_Intake_Entry", app: app)

        inventoryTab.tap()
        addMenu.tap()
        let manualOption = app.buttons["inventory-add-new-option"]
        XCTAssertTrue(manualOption.waitForExistence(timeout: 5))
        manualOption.tap()
        XCTAssertTrue(app.staticTexts["Add New Grocery"].waitForExistence(timeout: 5))

        let productName = element("inventory-add-product-name", in: app)
        XCTAssertTrue(
            productName.waitForExistence(timeout: 10),
            "Choosing Add a new product must show the product-name field"
        )
        let submit = element("inventory-add-submit", in: app)
        XCTAssertFalse(submit.isEnabled, "A new product still needs an identity and a known unit")
        productName.tap()
        productName.typeText("Fresh Kangkong")
        XCTAssertFalse(submit.isEnabled, "The app must not assume an unknown product's unit")
        let unitPicker = element("inventory-add-unit-picker", in: app)
        XCTAssertTrue(unitPicker.waitForExistence(timeout: 5))
        unitPicker.tap()
        let pieces = app.buttons["pcs"]
        XCTAssertTrue(pieces.waitForExistence(timeout: 5))
        pieces.tap()
        XCTAssertTrue(submit.isEnabled, "Product identity, unit, and quantity are enough for Quick Add")
        let optionalDetails = element("inventory-add-optional-details", in: app)
        XCTAssertTrue(optionalDetails.exists)
        capture("Inventory_Quick_Add_Minimal", app: app)
    }

    func testPartialInventoryDiscardUsesActualCountAndUpdatesStock() {
        let app = launch(screen: "inventory-stock-actions")
        let discard = element("inventory-discard-action", in: app)
        XCTAssertTrue(discard.waitForExistence(timeout: 10))
        XCTAssertTrue(discard.isHittable)
        discard.tap()

        let firstBatch = element("inventory-discard-select-batch-3", in: app)
        XCTAssertTrue(firstBatch.waitForExistence(timeout: 5))
        firstBatch.tap()

        let quantity = element("discard-quantity-field", in: app)
        XCTAssertTrue(quantity.waitForExistence(timeout: 5))
        XCTAssertEqual(quantity.value as? String, "4")
        let decrease = element("discard-quantity-decrement", in: app)
        XCTAssertTrue(decrease.isHittable)
        decrease.tap()
        XCTAssertEqual(quantity.value as? String, "3", "The user can record a partial count of discarded stock")

        let reason = element("discard-reason-field", in: app)
        XCTAssertTrue(reason.waitForExistence(timeout: 5))
        XCTAssertEqual(reason.value as? String, "Spoiled / Expired")
        let confirm = element("discard-confirm-button", in: app)
        XCTAssertTrue(confirm.isHittable)
        confirm.tap()

        let remaining = element("inventory-batch-quantity-3", in: app)
        let updatedQuantity = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label == %@", "1 can"), object: remaining
        )
        XCTAssertEqual(XCTWaiter.wait(for: [updatedQuantity], timeout: 10), .completed,
                       "The remaining batch quantity reflects the partial disposal")
        XCTAssertEqual(remaining.label, "1 can", "Discarding three of four cans leaves one can")
        capture("Inventory_Partial_Discard_Recorded", app: app)
    }

    func testPurchasedGroceriesReviewRequiresExplicitDecisions() {
        let app = launch(scenario: "shopping-reconciliation")
        let reviewButton = element("shopping-review-purchased", in: app)
        XCTAssertTrue(reviewButton.waitForExistence(timeout: 10))
        reviewButton.tap()

        let reviewForm = element("shopping-purchased-review-form", in: app)
        XCTAssertTrue(reviewForm.waitForExistence(timeout: 10))
        // Query the actual navigation-bar button, not its accessibility wrapper, so
        // XCTest observes the disabled state of the confirmation control itself.
        let confirm = app.navigationBars.buttons["shopping-confirm-purchased-review"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 5))
        XCTAssertFalse(confirm.isEnabled, "Every purchased item needs an explicit review decision")

        let addRice = element("shopping-reconcile-add-9981", in: app)
        XCTAssertTrue(addRice.waitForExistence(timeout: 5))
        addRice.tap()

        let unitPicker = element("shopping-reconcile-new-product-unit-9981", in: app)
        XCTAssertTrue(unitPicker.waitForExistence(timeout: 5))
        unitPicker.tap()
        let kilograms = app.buttons["kg"]
        XCTAssertTrue(kilograms.waitForExistence(timeout: 5))
        kilograms.tap()

        let actualQuantity = element("shopping-reconcile-actual-quantity-9981", in: app)
        XCTAssertTrue(actualQuantity.waitForExistence(timeout: 5))
        XCTAssertFalse(confirm.isEnabled, "The actual pantry amount must be entered; planned amount is not reused")
        actualQuantity.tap()
        actualQuantity.typeText("2.5")
        let keyboardDone = element("shopping-reconciliation-keyboard-done", in: app)
        if keyboardDone.waitForExistence(timeout: 2) { keyboardDone.tap() }
        XCTAssertFalse(confirm.isEnabled, "The second purchased item still needs a decision")

        let excludeMango = element("shopping-reconcile-exclude-9982", in: app)
        if !excludeMango.isHittable { app.swipeUp() }
        XCTAssertTrue(excludeMango.waitForExistence(timeout: 5))
        XCTAssertTrue(excludeMango.isHittable)
        excludeMango.tap()
        XCTAssertTrue(confirm.isEnabled, "The review can be confirmed once all rows have safe, explicit choices")
        confirm.tap()

        let riceStatus = element("shopping-purchase-status-9981", in: app)
        let mangoStatus = element("shopping-purchase-status-9982", in: app)
        XCTAssertTrue(riceStatus.waitForExistence(timeout: 10))
        XCTAssertEqual(riceStatus.label, "Added to pantry")
        XCTAssertTrue(mangoStatus.waitForExistence(timeout: 5))
        XCTAssertEqual(mangoStatus.label, "Excluded from pantry")
        capture("Shopping_Purchased_Pantry_Review", app: app)
    }

    func testShoppingPreviewEditsConsolidationAndExplicitConfirmation() {
        let app = launch()
        openShoppingPreview(app)
        let shoppingForm = scrollContainer("recipe-shopping-review-form", in: app)
        let safetyStatus = element("recipe-shopping-safety-status", in: app)
        XCTAssertEqual(safetyStatus.label, "Eligible")
        XCTAssertTrue(safetyStatus.isHittable)
        let actionSummary = element("recipe-shopping-action-summary-901", in: app)
        scrollTargetIntoView(actionSummary, inside: shoppingForm, progressAnchor: safetyStatus, in: app)
        XCTAssertEqual(actionSummary.label, "Add 100 g kangkong to shopping list")
        let quantityDetails = element("recipe-shopping-quantity-details-901", in: app)
        XCTAssertEqual(quantityDetails.value as? String, "Collapsed")
        XCTAssertFalse(element("recipe-shopping-unlinked-9920", in: app).exists,
                        "The ready preview fixture does not include an unlinked manual item")
        capture("Shopping_Preview_Ready", app: app)
        quantityDetails.tap()
        let requiredQuantity = element("recipe-shopping-quantity-required-901", in: app)
        XCTAssertTrue(requiredQuantity.waitForExistence(timeout: 5))
        XCTAssertTrue(requiredQuantity.label.contains("120 g"))
        XCTAssertEqual(quantityDetails.value as? String, "Expanded")
        quantityDetails.tap()

        let includeOptional = element("recipe-shopping-include-optional", in: app)
        scrollTargetIntoView(includeOptional, inside: shoppingForm, progressAnchor: safetyStatus,
                             in: app, initialDirection: .towardStart)
        assertReachable(includeOptional, in: app)
        guard setSwitch(includeOptional, to: "1") else { return }
        let stalePreview = element("recipe-shopping-stale-preview", in: app)
        XCTAssertTrue(stalePreview.waitForExistence(timeout: 5))
        let refreshPreview = app.buttons["recipe-shopping-refresh-preview"]
        scrollTargetIntoView(refreshPreview, inside: shoppingForm, in: app)
        XCTAssertTrue(refreshPreview.exists)
        XCTAssertTrue(refreshPreview.isHittable)
        refreshPreview.tap()
        let optionalIngredient = element("recipe-shopping-row-913", in: app)
        scrollTargetIntoView(optionalIngredient, inside: shoppingForm,
                             progressAnchor: includeOptional, in: app)
        XCTAssertTrue(optionalIngredient.waitForExistence(timeout: 10))
        XCTAssertFalse(stalePreview.exists)
        XCTAssertTrue(optionalIngredient.isHittable)
        assertReachable(optionalIngredient, in: app)
        capture("Shopping_Optional_Ingredients", app: app)

        let target = element("recipe-shopping-target-901", in: app)
        scrollTargetIntoView(target, inside: shoppingForm, in: app,
                             initialDirection: .towardStart)
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

    func testShoppingPreviewShowsUnlinkedManualItems() {
        let app = launch(scenario: "shopping-unlinked-manual")
        openShoppingPreview(app)

        let unlinked = element("recipe-shopping-unlinked-9920", in: app)
        let reviewForm = scrollContainer("recipe-shopping-review-form", in: app)
        scrollTargetIntoView(unlinked, inside: reviewForm,
                             progressAnchor: element("recipe-shopping-safety-status", in: app),
                             targetDescription: "recipe-shopping-unlinked-9920", in: app)
        XCTAssertTrue(unlinked.waitForExistence(timeout: 10))
        assertReachable(unlinked, in: app)
        XCTAssertTrue(unlinked.label.contains("Gardenia Classic White Bread"))
        capture("Shopping_Unlinked_Manual_Items", app: app)
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
        let reviewForm = scrollContainer("recipe-shopping-review-form", in: largeApp)
        let safetyStatus = element("recipe-shopping-safety-status", in: largeApp)
        XCTAssertTrue(safetyStatus.waitForExistence(timeout: 10))
        scrollTargetIntoView(servings, inside: reviewForm, progressAnchor: safetyStatus, in: largeApp,
                             initialDirection: .towardStart)
        XCTAssertTrue(servings.isHittable)
        assertReachable(servings, in: largeApp)
        let confirm = largeApp.buttons["recipe-shopping-confirm"]
        XCTAssertTrue(confirm.isHittable, "The confirmation action stays reachable at accessibility text sizes")
        let refresh = element("recipe-shopping-refresh-preview", in: largeApp)
        XCTAssertTrue(refresh.isHittable, "Refresh remains visible at accessibility text sizes")
        let settingsHeading = element("recipe-shopping-preview-settings-heading", in: largeApp)
        scrollTargetIntoView(settingsHeading, inside: reviewForm,
                             progressAnchor: servings, in: largeApp, initialDirection: .towardStart)
        assertReachable(settingsHeading, in: largeApp)
        XCTAssertTrue(servings.isHittable, "Servings remain visible with the settings heading in view")
        XCTAssertTrue(confirm.isHittable, "Confirmation remains available in the navigation bar")
        XCTAssertTrue(refresh.isHittable, "Refresh remains visible after positioning the settings heading")
        capture("Shopping_Preview_Large_Text", app: largeApp)

        let revisionDetails = element("recipe-shopping-revision-details", in: largeApp)
        scrollTargetIntoView(revisionDetails, inside: reviewForm,
                             progressAnchor: servings, in: largeApp)
        XCTAssertTrue(revisionDetails.isHittable)
        let listRevision = element("recipe-shopping-list-revision", in: largeApp)
        XCTAssertFalse(listRevision.exists, "Revision rows remain hidden until the user opens them")
        revisionDetails.tap()
        scrollTargetIntoView(listRevision, inside: reviewForm,
                             progressAnchor: revisionDetails, in: largeApp)
        XCTAssertTrue(listRevision.isHittable)
        XCTAssertTrue(listRevision.label.contains("Shopping list"))
        let pantryRevision = element("recipe-shopping-pantry-revision", in: largeApp)
        XCTAssertTrue(pantryRevision.waitForExistence(timeout: 5))
        XCTAssertTrue(pantryRevision.label.contains("Pantry"))
        let expiration = element("recipe-shopping-expiration-value", in: largeApp)
        XCTAssertTrue(expiration.waitForExistence(timeout: 5))
        XCTAssertFalse(expiration.label.isEmpty)
        scrollTargetIntoView(expiration, inside: reviewForm, progressAnchor: listRevision, in: largeApp)
        assertReachable(expiration, in: largeApp)
        capture("Shopping_Preview_Revision_Details_Large_Text", app: largeApp)
    }

    func testShoppingReviewRequiredAndBlockedStates() {
        let reviewApp = launch(scenario: "shopping-review-required")
        openShoppingPreview(reviewApp)
        let reviewSafetyStatus = element("recipe-shopping-safety-status", in: reviewApp)
        XCTAssertEqual(reviewSafetyStatus.label, "Review required")
        let reviewGuidance = element("recipe-shopping-safety-guidance", in: reviewApp)
        XCTAssertTrue(reviewGuidance.waitForExistence(timeout: 5))
        XCTAssertTrue(reviewGuidance.label.contains("ingredient match"))
        XCTAssertTrue(reviewGuidance.label.contains("package allergen label"))
        let reviewConfirm = reviewApp.navigationBars.buttons["recipe-shopping-confirm"]
        XCTAssertFalse(reviewConfirm.isEnabled)
        capture("Shopping_Preview_Review_Required", app: reviewApp)
        let reviewForm = scrollContainer("recipe-shopping-review-form", in: reviewApp)
        let reviewLineReadiness = element("recipe-shopping-line-readiness-0", in: reviewApp)
        scrollTargetIntoView(reviewLineReadiness, inside: reviewForm,
                             progressAnchor: reviewSafetyStatus,
                             targetDescription: "line readiness for the review-required preview", in: reviewApp)
        XCTAssertTrue(reviewLineReadiness.isHittable)
        XCTAssertTrue(reviewLineReadiness.label.contains("Line ready"))
        let reviewActionSummary = element("recipe-shopping-action-summary-901", in: reviewApp)
        scrollTargetIntoView(reviewActionSummary,
                             inside: reviewForm,
                             progressAnchor: reviewSafetyStatus,
                             targetDescription: "review-required shopping action summary",
                             in: reviewApp)
        XCTAssertTrue(reviewActionSummary.label.contains("Review the food-safety status before adding"))
        XCTAssertTrue(reviewActionSummary.isHittable)
        let acknowledgement = reviewApp.switches["recipe-shopping-safety-acknowledgement"]
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
        let blockedSafetyStatus = element("recipe-shopping-safety-status", in: blockedApp)
        XCTAssertEqual(blockedSafetyStatus.label, "Blocked")
        let blockedGuidance = element("recipe-shopping-safety-guidance", in: blockedApp)
        XCTAssertTrue(blockedGuidance.waitForExistence(timeout: 5))
        XCTAssertTrue(blockedGuidance.label.contains("food-safety conflict"))
        XCTAssertTrue(blockedGuidance.label.contains("before you can confirm"))
        let blockedConfirm = blockedApp.navigationBars.buttons["recipe-shopping-confirm"]
        XCTAssertFalse(blockedConfirm.isEnabled)
        capture("Shopping_Preview_Blocked", app: blockedApp)
        let blockedForm = scrollContainer("recipe-shopping-review-form", in: blockedApp)
        let blockedLineReadiness = element("recipe-shopping-line-readiness-0", in: blockedApp)
        scrollTargetIntoView(blockedLineReadiness, inside: blockedForm,
                             progressAnchor: blockedSafetyStatus,
                             targetDescription: "line readiness for the blocked preview", in: blockedApp)
        XCTAssertTrue(blockedLineReadiness.isHittable)
        XCTAssertTrue(blockedLineReadiness.label.contains("Line ready"))
        let blockedActionSummary = element("recipe-shopping-action-summary-901", in: blockedApp)
        scrollTargetIntoView(blockedActionSummary,
                             inside: blockedForm,
                             progressAnchor: blockedSafetyStatus,
                             targetDescription: "blocked shopping action summary",
                             in: blockedApp)
        XCTAssertTrue(blockedActionSummary.label.contains("Food-safety review blocks adding"))
        XCTAssertTrue(blockedActionSummary.isHittable)
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
        scrollTargetIntoView(offlineReady,
                             inside: scrollContainer("recipe-shopping-review-form", in: offlineApp),
                             in: offlineApp)

        offlineApp.terminate()
        let staleApp = launch(scenario: "shopping-stale")
        openShoppingPreview(staleApp)
        element("recipe-shopping-confirm", in: staleApp).tap()
        let confirmationAlert = staleApp.alerts.firstMatch
        XCTAssertTrue(confirmationAlert.waitForExistence(timeout: 5),
                      "Explicit confirmation appears before submitting the reviewed shopping changes")
        let staleConfirmAction = confirmationAlert.buttons
            .matching(identifier: "recipe-shopping-confirm-action").firstMatch
        XCTAssertTrue(staleConfirmAction.waitForExistence(timeout: 5))
        staleConfirmAction.tap()
        let confirmationDismissed = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"), object: confirmationAlert
        )
        XCTAssertEqual(XCTWaiter.wait(for: [confirmationDismissed], timeout: 10), .completed,
                       "The confirmation alert closes before stale-preview recovery is shown")
        let staleMessage = element("recipe-shopping-status-message", in: staleApp)
        XCTAssertTrue(staleMessage.waitForExistence(timeout: 10))
        XCTAssertTrue(staleMessage.label.contains("Inventory or shopping data changed"))
        XCTAssertTrue(staleMessage.isHittable,
                      "The stale-preview explanation is visible after the server rejects the outdated preview")
        let refresh = element("recipe-shopping-load-preview", in: staleApp)
        XCTAssertTrue(refresh.waitForExistence(timeout: 10))
        XCTAssertTrue(refresh.isHittable,
                      "A fresh preview can be loaded after the server rejects the outdated preview")
        capture("Shopping_Stale_Preview_Refresh", app: staleApp)
        refresh.tap()
        let staleReady = element("recipe-shopping-safety-status", in: staleApp)
        XCTAssertTrue(element("recipe-shopping-servings", in: staleApp).waitForExistence(timeout: 10))
        scrollTargetIntoView(staleReady,
                             inside: scrollContainer("recipe-shopping-review-form", in: staleApp),
                             in: staleApp)
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
        let shoppingForm = scrollContainer("recipe-shopping-review-form", in: app)
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
        let relaunchedForm = scrollContainer("recipe-shopping-review-form", in: relaunched)
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
        assertReachable(sourceError, in: app)
        XCTAssertTrue(element("recipe-safety-status", in: app).exists)
        capture("Source_Error_Retry", app: app)
        element("recipe-source-retry", in: app).tap()
        waitUntilGone(sourceError)
    }

    func testCookWithPipDarkModeGallery() {
        let darkApp = launch(appearance: "dark")
        openCookWithPip(darkApp)
        capture("Cook_with_Pip_Dark_Mode", app: darkApp)
    }

    func testLargeTextFilipinoRecipeSafetyGallery() {
        let largeApp = launch(dynamicType: "accessibility")
        openCookWithPip(largeApp)
        let recipeList = largeApp.scrollViews["cook-with-pip-recipe-list-scroll"]
        let myRecipesMode = largeApp.buttons["cook-mode-myRecipes"]
        XCTAssertTrue(myRecipesMode.waitForExistence(timeout: 10))
        scrollTargetIntoView(myRecipesMode, inside: recipeList, in: largeApp)
        XCTAssertTrue(myRecipesMode.isHittable, "The My Recipes filter is visible and usable at accessibility text size")
        myRecipesMode.tap()
        let householdRecipe = element("recipe-card-303", in: largeApp)
        XCTAssertTrue(
            householdRecipe.waitForExistence(timeout: 10),
            "Selecting My Recipes loads the household recipe result at accessibility text size"
        )
        let longRecipe = element("recipe-card-304", in: largeApp)
        scrollTargetIntoView(longRecipe, inside: recipeList, progressAnchor: householdRecipe, in: largeApp)
        XCTAssertTrue(longRecipe.isHittable, "The long Filipino recipe result is visible before opening it")
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
        let safetyReason = element("recipe-safety-reason-0", in: largeApp)
        XCTAssertTrue(safetyReason.waitForExistence(timeout: 5), "The blocked recipe exposes its deterministic allergen reason")
        scrollTargetIntoView(
            safetyReason,
            inside: recipeDetailScroll,
            progressAnchor: safetyNotice,
            targetDescription: "blocked recipe safety reason",
            in: largeApp
        )
        assertReachable(safetyReason, in: largeApp)
        XCTAssertFalse(largeTitle.isHittable, "The safety detail capture follows the long recipe title")
        capture("Recipe_Detail_Large_Text_Safety_Filipino", app: largeApp)
        scrollTargetIntoView(largeSummary, inside: recipeDetailScroll, in: largeApp,
                             initialDirection: .towardStart)
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
    }

    func testCookWithPipSearchKeyboardGallery() {
        let searchApp = launch()
        openCookWithPip(searchApp)
        let myRecipesMode = searchApp.buttons["cook-mode-myRecipes"]
        XCTAssertTrue(myRecipesMode.waitForExistence(timeout: 10))
        XCTAssertTrue(myRecipesMode.isHittable, "The My Recipes filter is available before search starts")
        myRecipesMode.tap()
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
        search.typeText("Chicken Adobo")
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
        scrollTargetIntoView(revisionDetails,
                             inside: scrollContainer("recipe-shopping-review-form", in: app),
                             in: app)
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
                        useKeychain: Bool = false, screen: String? = nil) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments.append(contentsOf: [
            "-cook-with-pip-ui-tests",
            "-pip-ui-scenario", scenario,
            "-pip-ui-fixture-id", String(fixtureID ?? Int.random(in: 10_000...90_000))
        ])
        if useKeychain { app.launchArguments.append(contentsOf: ["-pip-ui-use-keychain", "1"]) }
        if let screen { app.launchArguments.append(contentsOf: ["-pip-ui-screen", screen]) }
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
        let dashboardLoaded = element("home-dashboard-loaded", in: app)
        XCTAssertTrue(dashboardLoaded.waitForExistence(timeout: timeout),
                      "The home dashboard finishes rendering before navigation")
        XCTAssertTrue(entry.isHittable,
                      "The Cook with Pip navigation link is visible before it is tapped")
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
        XCTAssertTrue(recipe.label.contains("Ginataang Kangkong"))
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
            let reviewForm = scrollContainer("recipe-shopping-review-form", in: app)
            scrollTargetIntoView(ready, inside: reviewForm, in: app)
        }
    }

    private enum ScrollDirection {
        case towardEnd
        case towardStart
    }

    private enum ScrollAxis {
        case vertical
        case horizontal
    }

    private func scrollContainer(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        let collection = app.collectionViews.matching(identifier: identifier).firstMatch
        if collection.exists { return collection }
        let table = app.tables.matching(identifier: identifier).firstMatch
        if table.exists { return table }
        let scrollView = app.scrollViews.matching(identifier: identifier).firstMatch
        if scrollView.exists { return scrollView }
        return app.descendants(matching: .any).matching(identifier: identifier).firstMatch
    }

    private func identifiedElement(_ identifier: String, inside container: XCUIElement) -> XCUIElement {
        container.descendants(matching: .any).matching(identifier: identifier).firstMatch
    }

    private func scrollTargetIntoView(
        _ target: XCUIElement,
        inside container: XCUIElement,
        progressAnchor: XCUIElement? = nil,
        targetDescription: String? = nil,
        in app: XCUIApplication,
        maximumSwipes: Int = 12,
        initialDirection: ScrollDirection = .towardEnd,
        axis: ScrollAxis = .vertical
    ) {
        let targetName = targetDescription ?? "target element"
        guard container.waitForExistence(timeout: 5) else {
            XCTFail("Expected scroll container '\(container.identifier)' while locating \(targetName)")
            return
        }
        var targetExists = target.exists
        if targetExists && isSafelyHittable(target, inside: container, in: app) { return }

        let anchor = progressAnchor ?? container.descendants(matching: .any).firstMatch
        let containerFrame = measurableFrame(of: container, exists: true)
        var anchorExists = anchor.exists
        var previousTargetFrame = targetExists ? measurableFrame(of: target, exists: true) : nil
        var previousAnchorFrame = anchorExists ? measurableFrame(of: anchor, exists: true) : nil
        var consecutiveNoProgressSwipes = 0

        for swipeNumber in 1...maximumSwipes {
            let direction: ScrollDirection
            if let targetFrame = previousTargetFrame,
               let visibleFrame = unobscuredViewport(in: app, inside: container) {
                switch axis {
                case .vertical:
                    if targetFrame.midY < visibleFrame.minY {
                        direction = .towardStart
                    } else if targetFrame.midY > visibleFrame.maxY {
                        direction = .towardEnd
                    } else {
                        direction = initialDirection
                    }
                case .horizontal:
                    if targetFrame.midX < visibleFrame.minX {
                        direction = .towardStart
                    } else if targetFrame.midX > visibleFrame.maxX {
                        direction = .towardEnd
                    } else {
                        direction = initialDirection
                    }
                }
            } else if let targetFrame = previousTargetFrame, let containerFrame {
                switch axis {
                case .vertical:
                    if targetFrame.minY < containerFrame.minY {
                        direction = .towardStart
                    } else if targetFrame.maxY > containerFrame.maxY {
                        direction = .towardEnd
                    } else {
                        direction = initialDirection
                    }
                case .horizontal:
                    if targetFrame.minX < containerFrame.minX {
                        direction = .towardStart
                    } else if targetFrame.maxX > containerFrame.maxX {
                        direction = .towardEnd
                    } else {
                        direction = initialDirection
                    }
                }
            } else {
                direction = initialDirection
            }

            switch direction {
            case .towardEnd:
                switch axis {
                case .vertical: container.swipeUp()
                case .horizontal: container.swipeLeft()
                }
            case .towardStart:
                switch axis {
                case .vertical: container.swipeDown()
                case .horizontal: container.swipeRight()
                }
            }

            targetExists = target.exists
            if targetExists && isSafelyHittable(target, inside: container, in: app) { return }

            let currentTargetFrame = targetExists ? measurableFrame(of: target, exists: true) : nil
            anchorExists = anchor.exists
            let currentAnchorFrame = anchorExists ? measurableFrame(of: anchor, exists: true) : nil
            let madeProgress = frameMoved(from: previousTargetFrame, to: currentTargetFrame)
                || frameMoved(from: previousAnchorFrame, to: currentAnchorFrame)
            consecutiveNoProgressSwipes = madeProgress ? 0 : consecutiveNoProgressSwipes + 1
            guard consecutiveNoProgressSwipes < 2 else {
                XCTFail(
                    "Scrolling stopped before \(targetName) entered the unobscured viewport and became hittable. "
                    + "container='\(container.identifier)', targetFrame=\(describe(currentTargetFrame)), "
                    + "visibleFrame=\(describe(unobscuredViewport(in: app, inside: container))), "
                    + "anchorFrame=\(describe(currentAnchorFrame)), "
                    + "completedSwipes=\(swipeNumber), "
                    + "consecutiveNoProgressSwipes=\(consecutiveNoProgressSwipes), "
                    + "targetExists=\(targetExists), "
                    + "appState=\(app.state)"
                )
                return
            }
            previousTargetFrame = currentTargetFrame
            previousAnchorFrame = currentAnchorFrame
        }

        XCTAssertTrue(
            target.exists,
            "Expected \(targetName) after at most \(maximumSwipes) swipes in '\(container.identifier)'; "
                + "targetFrame=\(describe(measurableFrame(of: target, exists: target.exists))), "
                + "anchorFrame=\(describe(measurableFrame(of: anchor, exists: anchor.exists)))"
        )
        XCTAssertTrue(
            isSafelyHittable(target, inside: container, in: app),
            "Expected \(targetName) to be visible below the navigation bar and interactable after \(maximumSwipes) swipes; "
                + "targetFrame=\(describe(measurableFrame(of: target, exists: target.exists))), "
                + "visibleFrame=\(describe(unobscuredViewport(in: app, inside: container))), appState=\(app.state)"
        )
    }

    private func isSafelyHittable(
        _ target: XCUIElement,
        inside container: XCUIElement? = nil,
        in app: XCUIApplication
    ) -> Bool {
        guard target.exists, target.isHittable,
              let targetFrame = measurableFrame(of: target, exists: true),
              let visibleFrame = unobscuredViewport(in: app, inside: container) else {
            return false
        }
        return visibleFrame.contains(CGPoint(x: targetFrame.midX, y: targetFrame.midY))
    }

    private func unobscuredViewport(in app: XCUIApplication, inside container: XCUIElement? = nil) -> CGRect? {
        let window = app.windows.firstMatch
        guard let windowFrame = measurableFrame(of: window, exists: window.exists) else { return nil }
        var viewport = windowFrame

        if let container, container.exists,
           let containerFrame = measurableFrame(of: container, exists: true) {
            let intersection = viewport.intersection(containerFrame)
            guard !intersection.isNull, !intersection.isEmpty else { return nil }
            viewport = intersection
        }

        let navigationBar = app.navigationBars.firstMatch
        if navigationBar.exists, let navigationFrame = measurableFrame(of: navigationBar, exists: true) {
            let unobscuredTop = max(viewport.minY, navigationFrame.maxY)
            guard unobscuredTop < viewport.maxY else { return nil }
            let visibleBottom = viewport.maxY
            viewport.origin.y = unobscuredTop
            viewport.size.height = visibleBottom - unobscuredTop
        }
        return viewport
    }

    private func measurableFrame(of element: XCUIElement, exists: Bool) -> CGRect? {
        guard exists else { return nil }
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
            isSafelyHittable(target, in: app),
            "Expected \(target.identifier) to be visible below the navigation bar and interactable; "
                + "targetFrame=\(describe(measurableFrame(of: target, exists: target.exists))), "
                + "visibleFrame=\(describe(unobscuredViewport(in: app))), appState=\(app.state)"
        )
    }

    private func tapSwitchControl(_ toggle: XCUIElement) {
        XCTAssertTrue(toggle.isHittable, "Expected \(toggle.identifier) to be interactable before tapping")
        toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
    }

    @discardableResult
    private func setSwitch(_ toggle: XCUIElement, to value: String) -> Bool {
        guard toggle.waitForExistence(timeout: 5) else {
            XCTFail("Expected \(toggle.identifier) to exist before changing its value")
            return false
        }
        if toggle.value as? String != value {
            tapSwitchControl(toggle)
        }
        let expectedValue = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", value), object: toggle
        )
        let result = XCTWaiter.wait(for: [expectedValue], timeout: 5)
        XCTAssertEqual(result, .completed,
                       "Expected \(toggle.identifier) to have value \(value); found \(String(describing: toggle.value))")
        return result == .completed
    }

    private func replaceText(_ field: XCUIElement, with value: String) {
        field.tap()
        let oldValue = field.value as? String ?? ""
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: oldValue.count) + value)
    }

    private func typeTextAndWait(_ text: String, in field: XCUIElement) {
        let currentValue = field.value as? String
        let currentText = currentValue == (field.placeholderValue as? String) ? "" : currentValue ?? ""
        let expectedValue = currentText + text
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
        assertDemoScreenshotHasNoDeveloperText(name, app: app)
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func assertDemoScreenshotHasNoDeveloperText(_ name: String, app: XCUIApplication) {
        let generatedIdentifier = "(?:[0-9a-f]{8}-[0-9a-f-]{27,}|(?:fixture|synthetic|mock)[-_]?[0-9]+)"
        let developerText = "(?is).*(?:synthetic|mock|test[ _-]?fixtures?|fixture|e2e|debug|\(generatedIdentifier)).*"
        let matchingElements = app.descendants(matching: .any).matching(
            NSPredicate(format: "label MATCHES %@ OR value MATCHES %@", developerText, developerText)
        )
        XCTAssertFalse(matchingElements.firstMatch.exists,
                       "Screenshot \(name) must not expose developer labels or generated identifiers")
    }

    private func capturePipChat(_ name: String, app: XCUIApplication) {
        guard ProcessInfo.processInfo.environment["PROVISION_SKIP_CHAT_SCREENSHOTS"] != "1" else { return }
        capture(name, app: app)
    }
}
extension CookWithPipUITests {
    func testRealDemoAccountSessionAndBarcodeLookup() throws {
        let environment = ProcessInfo.processInfo.environment
        guard environment["PROVISION_REAL_DEMO_ACCOUNT_TEST"] == "true",
              let baseURL = environment["PROVISION_API_BASE_URL"],
              let email = environment["PROVISION_STAGING_TEST_EMAIL"],
              let password = environment["PROVISION_STAGING_TEST_PASSWORD"] else {
            throw XCTSkip("Real demo account credentials are supplied only by the manual staging workflow")
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
        guard finishStagingSignInIfNeeded(
            app: app,
            signIn: signIn,
            signedInTab: inventoryTab,
            signedInTabLabel: "Inventory",
            failureMessage: "The real demo account did not reach Inventory after sign-in"
        ) else { return }
        dismissSavePasswordPromptIfPresent(app: app, readyElement: inventoryTab)
        assertStagingDashboardLoaded(app, phase: "The real demo household dashboard loaded")

        app.terminate()
        app.launchArguments = []
        app.launch()
        XCTAssertTrue(inventoryTab.waitForExistence(timeout: 40),
                      "The real demo account session did not recover after app relaunch")
        assertStagingDashboardLoaded(app, phase: "The real demo household session restored after relaunch")

        inventoryTab.tap()
        let productRows = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier BEGINSWITH %@", "product-row-")
        )
        let firstProduct = productRows.firstMatch
        XCTAssertTrue(firstProduct.waitForExistence(timeout: 30),
                      "The real demo household inventory did not load after relaunch")
        XCTAssertTrue(firstProduct.isHittable,
                      "A real demo household product should be visible in Inventory")

        let addMenu = app.buttons["inventory-add-menu"]
        XCTAssertTrue(addMenu.waitForExistence(timeout: 10))
        addMenu.tap()
        let scanOption = app.buttons["inventory-add-scan-option"]
        XCTAssertTrue(scanOption.waitForExistence(timeout: 10))
        scanOption.tap()

        let enterBarcode = element("scan-enter-barcode", in: app)
        XCTAssertTrue(enterBarcode.waitForExistence(timeout: 10))
        enterBarcode.tap()
        let barcodeField = element("manual-intake-barcode", in: app)
        XCTAssertTrue(barcodeField.waitForExistence(timeout: 10))
        barcodeField.tap()
        barcodeField.typeText("4800016644818")

        let lookupBarcode = element("manual-intake-barcode-lookup", in: app)
        XCTAssertTrue(lookupBarcode.isEnabled,
                      "Manual barcode entry should allow a lookup against the staging catalog")
        lookupBarcode.tap()
        let lookedUpTuna = element("intake-preview-item-4800016644818", in: app)
        XCTAssertTrue(lookedUpTuna.waitForExistence(timeout: 20),
                      "The staging catalog did not resolve the real household's Century Tuna barcode")
        XCTAssertTrue(lookedUpTuna.label.localizedCaseInsensitiveContains("Century Tuna"),
                      "The barcode lookup should show the matching grocery, got: \(lookedUpTuna.label)")
    }

    func testRealDemoAccountReceiptOCRIntake() throws {
        let environment = ProcessInfo.processInfo.environment
        guard environment["PROVISION_REAL_DEMO_ACCOUNT_TEST"] == "true",
              let baseURL = environment["PROVISION_API_BASE_URL"],
              let email = environment["PROVISION_STAGING_TEST_EMAIL"],
              let password = environment["PROVISION_STAGING_TEST_PASSWORD"] else {
            throw XCTSkip("The receipt OCR run requires the authorized staging demo account")
        }

        let bundle = Bundle(for: CookWithPipUITests.self)
        let manifestURL = bundle.url(
            forResource: "Provision_Receipt_OCR_Expected",
            withExtension: "json",
            subdirectory: "Resources"
        ) ?? bundle.url(forResource: "Provision_Receipt_OCR_Expected", withExtension: "json")
        let manifestData = try Data(contentsOf: XCTUnwrap(manifestURL))
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let manifest = try decoder.decode(ReceiptOCRManifest.self, from: manifestData)
        XCTAssertEqual(manifest.items.count, manifest.lineCount)
        XCTAssertEqual(manifest.itemCount, 10, "The tuna line represents two cans, while receipt headers are excluded")
        XCTAssertEqual(manifest.store, "Bayani Fresh Mart")
        XCTAssertEqual(manifest.totalPhp, 632, accuracy: 0.001)

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
        guard finishStagingSignInIfNeeded(
            app: app,
            signIn: signIn,
            signedInTab: inventoryTab,
            signedInTabLabel: "Inventory",
            failureMessage: "The real demo account did not reach Inventory for receipt intake"
        ) else { return }
        dismissSavePasswordPromptIfPresent(app: app, readyElement: inventoryTab)
        assertStagingDashboardLoaded(app, phase: "The real demo household dashboard loaded before receipt intake")
        inventoryTab.tap()

        let addMenu = app.buttons["inventory-add-menu"]
        XCTAssertTrue(addMenu.waitForExistence(timeout: 15))
        addMenu.tap()
        let scanOption = app.buttons["inventory-add-scan-option"]
        XCTAssertTrue(scanOption.waitForExistence(timeout: 10))
        scanOption.tap()
        let receiptMode = app.buttons["Receipt Intake"]
        XCTAssertTrue(receiptMode.waitForExistence(timeout: 10))
        receiptMode.tap()

        let importReceipt = app.buttons["receipt-import-photo-picker"]
        XCTAssertTrue(importReceipt.waitForExistence(timeout: 10))
        guard importReceipt.isEnabled else {
            XCTFail("Receipt photo import is disabled while receipt processing or intake recovery is active")
            return
        }
        importReceipt.tap()
        let pickerScreenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        pickerScreenshot.name = "real-receipt-photo-picker-open"
        pickerScreenshot.lifetime = .keepAlways
        add(pickerScreenshot)

        // iOS shows a limited-library information banner on the first picker open.
        // Dismiss it so it cannot intercept the imported receipt thumbnail.
        let privateAccessClose = app.buttons["Close"]
        if privateAccessClose.waitForExistence(timeout: 2), privateAccessClose.isHittable {
            privateAccessClose.tap()
        }

        let photoThumbnail = app.images.matching(
            NSPredicate(
                format: "identifier == %@ AND label BEGINSWITH[c] %@",
                "PXGGridLayout-Info", "Photo,"
            )
        ).firstMatch
        guard photoThumbnail.waitForExistence(timeout: 30) else {
            XCTFail("The system photo picker did not expose its imported photo thumbnail after waiting for the library to load")
            return
        }

        let photoGrid = app.otherElements["PXGGridLayout-Group"]
        guard photoGrid.waitForExistence(timeout: 5), photoGrid.frame.width > 0, photoGrid.frame.height > 0 else {
            XCTFail("The Photos picker exposed a thumbnail without a usable grid container")
            return
        }
        // The thumbnail belongs to a remote Photos view. Anchor the tap to the grid
        // container and use the matched thumbnail's center within that container.
        let thumbnailFrame = photoThumbnail.frame
        let thumbnailCenterInGrid = CGVector(
            dx: (thumbnailFrame.midX - photoGrid.frame.minX) / photoGrid.frame.width,
            dy: (thumbnailFrame.midY - photoGrid.frame.minY) / photoGrid.frame.height
        )
        photoGrid.coordinate(withNormalizedOffset: thumbnailCenterInGrid).tap()

        let selectionScreenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        selectionScreenshot.name = "real-receipt-photo-picker-after-thumbnail-tap"
        selectionScreenshot.lifetime = .keepAlways
        add(selectionScreenshot)

        let addPhoto = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] %@", "Add")).firstMatch
        if addPhoto.waitForExistence(timeout: 3) && addPhoto.isHittable {
            addPhoto.tap()
        }
        let pickerCancel = app.buttons.matching(NSPredicate(format: "label == %@", "Cancel")).firstMatch
        guard pickerCancel.waitForNonExistence(timeout: 5) else {
            XCTFail("The Photos picker stayed open after tapping the imported receipt thumbnail")
            return
        }

        let totalLabel = element("intake-summary-total", in: app)
        let workspaceButton = app.buttons["intake-review-workspace-open"]
        XCTAssertTrue(workspaceButton.waitForExistence(timeout: 75),
                      "Vision OCR did not produce the nine expected grocery lines")
        XCTAssertEqual(totalLabel.label, "Total: \(manifest.lineCount)",
                       "Store details, transaction numbers, and payment totals must not become grocery items")
        workspaceButton.tap()

        let search = element("intake-workspace-search", in: app)
        XCTAssertTrue(search.waitForExistence(timeout: 10))
        for item in manifest.items {
            let row = try findReceiptWorkspaceRow(item, search: search, app: app)
            let expectedQuantity = formatReceiptQuantity(item.quantity)
            XCTAssertTrue(row.label.localizedCaseInsensitiveContains("\(expectedQuantity) \(item.unit)"),
                          "\(item.sourceName) should be recognized as \(expectedQuantity) \(item.unit), got: \(row.label)")
            print("REAL_RECEIPT_OCR_ROW \(row.label)")
            row.tap()

            let detailScroll = app.scrollViews["intake-item-review-scroll"]
            XCTAssertTrue(detailScroll.waitForExistence(timeout: 10))
            let catalogSelector = element("intake-product-catalog-selector", in: app)
            let hasCatalogSelector = catalogSelector.waitForExistence(timeout: 2)
            if item.catalogAction == "select", let catalogSearchText = item.catalogSearch {
                if hasCatalogSelector {
                    scrollTargetIntoView(catalogSelector, inside: detailScroll, in: app)
                    catalogSelector.tap()
                    let catalogSearch = app.textFields["catalog-product-search"]
                    XCTAssertTrue(catalogSearch.waitForExistence(timeout: 10))
                    catalogSearch.tap()
                    catalogSearch.typeText(catalogSearchText)
                    let matchingProduct = app.buttons.matching(
                        NSPredicate(
                            format: "identifier BEGINSWITH %@ AND label CONTAINS[c] %@",
                            "catalog-product-", catalogSearchText
                        )
                    ).firstMatch
                    XCTAssertTrue(matchingProduct.waitForExistence(timeout: 10),
                                  "The staging catalog did not contain the expected reviewed match for \(item.sourceName)")
                    matchingProduct.tap()
                } else {
                    XCTAssertTrue(row.label.localizedCaseInsensitiveContains(catalogSearchText),
                                  "Vision's confident match for \(item.sourceName) should resolve to \(catalogSearchText), got: \(row.label)")
                }
            // A resolved receipt product has no catalog selector. Keep its
            // existing link and let the required detail confirmation below
            // verify that the item is eligible before intake.
            } else if item.catalogAction == "register",
                      hasCatalogSelector,
                      let productName = item.productName {
                var usedExistingCatalogProduct = false
                if hasCatalogSelector {
                    scrollTargetIntoView(catalogSelector, inside: detailScroll, in: app)
                    catalogSelector.tap()
                    let catalogSearch = app.textFields["catalog-product-search"]
                    XCTAssertTrue(catalogSearch.waitForExistence(timeout: 10))
                    catalogSearch.tap()
                    catalogSearch.typeText(productName)
                    let catalogKeyboardDone = app.buttons["catalog-product-search-keyboard-done"]
                    XCTAssertTrue(catalogKeyboardDone.waitForExistence(timeout: 5),
                                  "The catalog search should expose a keyboard dismissal action")
                    catalogKeyboardDone.tap()
                    let exactProduct = app.buttons.matching(
                        NSPredicate(
                            format: "identifier BEGINSWITH %@ AND label CONTAINS[c] %@",
                            "catalog-product-", productName
                        )
                    ).firstMatch
                    if exactProduct.waitForExistence(timeout: 2) {
                        exactProduct.tap()
                        usedExistingCatalogProduct = true
                    } else {
                        app.buttons["Cancel"].tap()
                    }
                }

                if !usedExistingCatalogProduct {
                    let disclosure = app.buttons["intake-register-product-disclosure"]
                    scrollTargetIntoView(disclosure, inside: detailScroll, in: app)
                    disclosure.tap()
                    let nameField = element("intake-register-product-name", in: app)
                    XCTAssertTrue(nameField.waitForExistence(timeout: 5))
                    replaceText(nameField, with: productName)
                    let registrationKeyboardDone = app.buttons["intake-register-keyboard-done"]
                    XCTAssertTrue(registrationKeyboardDone.waitForExistence(timeout: 5),
                                  "The receipt product form should expose a keyboard dismissal action")
                    registrationKeyboardDone.tap()
                    if let brand = item.brand {
                        let brandField = element("intake-register-product-brand", in: app)
                        scrollTargetIntoView(brandField, inside: detailScroll, in: app)
                        replaceText(brandField, with: brand)
                        XCTAssertTrue(registrationKeyboardDone.waitForExistence(timeout: 5),
                                      "The receipt product form should expose a keyboard dismissal action for the brand")
                        registrationKeyboardDone.tap()
                    }
                    if let category = item.category {
                        chooseReceiptPickerValue("intake-register-product-category", value: category, scroll: detailScroll, app: app)
                    }
                    if let unit = item.productUnit {
                        chooseReceiptPickerValue("intake-register-product-unit", value: unit, scroll: detailScroll, app: app)
                    }
                    let register = app.buttons["intake-register-product-submit"]
                    XCTAssertTrue(register.isEnabled, "The receipt item needs a complete product identity and unit")
                    register.tap()
                    XCTAssertTrue(app.buttons["intake-confirm-details"].waitForExistence(timeout: 15),
                                  "The reviewed receipt product was not linked to the intake item")
                }
            }

            if item.unit == "kg" || item.unit == "L" {
                let quantityField = app.textFields.matching(
                    NSPredicate(format: "identifier BEGINSWITH %@", "intake-measured-quantity-")
                ).firstMatch
                XCTAssertTrue(quantityField.waitForExistence(timeout: 5),
                              "Measured receipt quantity should be editable for \(item.sourceName)")
                XCTAssertEqual(quantityField.value as? String, expectedQuantity,
                               "The measured amount for \(item.sourceName) must match the receipt package size")
            }

            let lineTotal = element("intake-item-line-total", in: app)
            scrollTargetIntoView(lineTotal, inside: detailScroll, in: app)
            XCTAssertTrue(lineTotal.waitForExistence(timeout: 5), "The receipt line price should remain visible during review")
            XCTAssertEqual(lineTotal.label, String(format: "Total: ₱%.2f", item.lineTotalPhp),
                           "The normalized quantity and unit price must preserve the printed line total for \(item.sourceName)")

            let locationPicker = element("intake-review-location-picker", in: app)
            scrollTargetIntoView(locationPicker, inside: detailScroll, in: app)
            locationPicker.tap()
            let location = app.buttons.matching(NSPredicate(format: "label == %@", item.storageLocation)).firstMatch
            XCTAssertTrue(location.waitForExistence(timeout: 5), "The selected pantry location must exist")
            location.tap()

            let confirmDetails = app.buttons["intake-confirm-details"]
            scrollTargetIntoView(confirmDetails, inside: detailScroll, in: app)
            XCTAssertTrue(confirmDetails.isEnabled, "Each receipt line needs a reviewed product, quantity, and location")
            confirmDetails.tap()
            let done = app.buttons["intake-review-done"]
            XCTAssertTrue(done.waitForExistence(timeout: 5))
            done.tap()

            let rowSearchTerm = item.productName ?? item.catalogSearch ?? item.searchTerms[0]
            setReceiptWorkspaceSearch(search, to: rowSearchTerm, app: app)
            let reviewedRow = app.buttons.matching(
                NSPredicate(format: "identifier BEGINSWITH %@ AND label CONTAINS[c] %@", "intake-workspace-item-", rowSearchTerm)
            ).firstMatch
            XCTAssertTrue(reviewedRow.waitForExistence(timeout: 5),
                          "The confirmed receipt item should remain in the workspace after review")
            XCTAssertTrue(reviewedRow.label.localizedCaseInsensitiveContains("location: \(item.storageLocation)"),
                          "The reviewed location should match the receipt plan for \(item.sourceName): \(reviewedRow.label)")
            XCTAssertTrue(reviewedRow.label.localizedCaseInsensitiveContains("confirmed"),
                          "The receipt row should be confirmed only after the details review: \(reviewedRow.label)")
        }

        let workspaceDone = app.buttons["intake-workspace-done"]
        XCTAssertTrue(workspaceDone.waitForExistence(timeout: 10))
        workspaceDone.tap()
        let commit = app.buttons["intake-commit-session"]
        XCTAssertTrue(commit.waitForExistence(timeout: 10))
        XCTAssertTrue(commit.isEnabled, "All nine receipt lines must be explicitly confirmed before intake")
        commit.tap()
        XCTAssertTrue(app.staticTexts["Committed 9 items to household inventory!"].waitForExistence(timeout: 45),
                      "The staging inventory intake did not complete")

        XCTAssertTrue(inventoryTab.waitForExistence(timeout: 10))
        inventoryTab.tap()
        let refresh = app.buttons["Refresh Inventory"]
        if refresh.waitForExistence(timeout: 5) { refresh.tap() }
        let inventorySearch = element("inventory-search", in: app)
        XCTAssertTrue(inventorySearch.waitForExistence(timeout: 10))
        inventorySearch.tap()
        inventorySearch.typeText("Fresh Sampalok")
        let sampalokRow = app.buttons.matching(
            NSPredicate(format: "identifier BEGINSWITH %@ AND label CONTAINS[c] %@", "product-row-", "Fresh Sampalok")
        ).firstMatch
        XCTAssertTrue(sampalokRow.waitForExistence(timeout: 20), "The OCR intake did not add Fresh Sampalok to staging inventory")
        XCTAssertTrue(sampalokRow.label.localizedCaseInsensitiveContains("0.1 kg"),
                      "Staging inventory should contain the receipt's 100 g sampalok amount, got: \(sampalokRow.label)")
        print("STAGING_RECEIPT_INVENTORY_VERIFIED \(sampalokRow.label)")
    }

    private func findReceiptWorkspaceRow(
        _ item: ReceiptOCRManifestItem,
        search: XCUIElement,
        app: XCUIApplication
    ) throws -> XCUIElement {
        let rowCollection = app.buttons.matching(
            NSPredicate(format: "identifier BEGINSWITH %@", "intake-workspace-item-")
        )
        for term in item.searchTerms {
            setReceiptWorkspaceSearch(search, to: term, app: app)
            let row = rowCollection.matching(
                NSPredicate(format: "label CONTAINS[c] %@", term)
            ).firstMatch
            if row.waitForExistence(timeout: 5) {
                XCTAssertTrue(row.isHittable, "Receipt row for \(item.sourceName) should be interactable")
                return row
            }
        }
        XCTFail("Vision did not produce a review row for \(item.sourceName). Search terms: \(item.searchTerms). Current search: \(String(describing: search.value)). Rows: \(rowCollection.allElementsBoundByIndex.map(\.label))")
        throw NSError(domain: "ProvisionReceiptOCR", code: 1, userInfo: [NSLocalizedDescriptionKey: "Receipt row missing for \(item.sourceName)"])
    }

    private func setReceiptWorkspaceSearch(_ search: XCUIElement, to term: String, app: XCUIApplication) {
        let clearButton = app.buttons["intake-workspace-search-clear"]
        if clearButton.exists {
            clearButton.tap()
        }

        search.tap()
        search.typeText(term)
        let expectedValue = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", term),
            object: search
        )
        XCTAssertEqual(XCTWaiter.wait(for: [expectedValue], timeout: 5), .completed,
                       "Receipt workspace search should contain the requested item name")

        let keyboardDone = app.buttons["intake-workspace-search-keyboard-done"]
        XCTAssertTrue(keyboardDone.waitForExistence(timeout: 5),
                      "The intake workspace search should expose a keyboard dismissal action")
        keyboardDone.tap()
    }

    private func formatReceiptQuantity(_ amount: Double) -> String {
        String(format: "%.2f", amount)
            .replacingOccurrences(of: #"0+$"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"\.$"#, with: "", options: .regularExpression)
    }

    private func chooseReceiptPickerValue(
        _ identifier: String,
        value: String,
        scroll: XCUIElement,
        app: XCUIApplication
    ) {
        let picker = element(identifier, in: app)
        scrollTargetIntoView(picker, inside: scroll, in: app)
        XCTAssertTrue(picker.isHittable, "Picker \(identifier) should be reachable before selecting \(value)")
        picker.tap()
        let option = app.buttons.matching(NSPredicate(format: "label == %@", value)).firstMatch
        XCTAssertTrue(option.waitForExistence(timeout: 5), "Picker \(identifier) did not offer \(value)")
        option.tap()
    }

    func testStagingLivePipChatResponseIsDisplayed() throws {
        let environment = ProcessInfo.processInfo.environment
        guard environment["PROVISION_LIVE_PIP_CHAT_TEST"] == "true",
              let baseURL = environment["PROVISION_API_BASE_URL"],
              let email = environment["PROVISION_STAGING_TEST_EMAIL"],
              let password = environment["PROVISION_STAGING_TEST_PASSWORD"],
              let productID = environment["PROVISION_STAGING_TEST_PRODUCT_ID"].flatMap(Int.init),
              let productName = environment["PROVISION_STAGING_TEST_PRODUCT_NAME"] else {
            throw XCTSkip("The live Pip Chat test runs only in its explicitly authorized staging workflow")
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
        let signIn = app.buttons["login-submit"]
        signIn.tap()

        let homeTab = app.buttons["Home"]
        guard finishStagingSignInIfNeeded(
            app: app,
            signIn: signIn,
            signedInTab: homeTab,
            signedInTabLabel: "Home",
            failureMessage: "The synthetic staging account did not reach Home for Pip Chat verification"
        ) else { return }
        dismissSavePasswordPromptIfPresent(app: app, readyElement: homeTab)
        assertStagingDashboardLoaded(app, phase: "The synthetic household dashboard loaded before Pip Chat")

        let inventoryTab = app.buttons["Inventory"]
        XCTAssertTrue(inventoryTab.waitForExistence(timeout: 15))
        inventoryTab.tap()
        let productRow = element("product-row-\(productID)", in: app)
        XCTAssertTrue(productRow.waitForExistence(timeout: 20))
        productRow.tap()
        let askPip = app.buttons["product-ask-pip-link"]
        XCTAssertTrue(askPip.waitForExistence(timeout: 15))
        askPip.tap()

        let contextTitle = app.staticTexts["pip-chat-context-title"]
        XCTAssertTrue(contextTitle.waitForExistence(timeout: 15))
        XCTAssertEqual(contextTitle.label, productName)

        let chatConsent = app.switches["pip-chat-consent-chat"]
        let allergyConsent = app.switches["pip-chat-consent-allergies"]
        XCTAssertTrue(chatConsent.waitForExistence(timeout: 15))
        let chatScroll = app.scrollViews["pip-chat-scroll"]
        scrollTargetIntoView(chatConsent, inside: chatScroll, in: app)
        scrollTargetIntoView(allergyConsent, inside: chatScroll, progressAnchor: chatConsent, in: app)
        XCTAssertEqual(chatConsent.value as? String, "1", "The synthetic chat consent was granted before this request")
        XCTAssertEqual(allergyConsent.value as? String, "0", "Allergy sharing remains separately disabled")
        assertReachable(chatConsent, in: app)
        assertReachable(allergyConsent, in: app)
        capture("Pip_Chat_Consent_Enabled", app: app)

        let input = element("pip-chat-input", in: app)
        XCTAssertTrue(input.waitForExistence(timeout: 15))
        scrollTargetIntoView(input, inside: chatScroll, in: app)
        input.tap()
        input.typeText("How much kangkong do I have in the pantry?")
        let send = app.buttons["pip-chat-send"]
        XCTAssertTrue(send.isEnabled)
        send.tap()

        let assistantReply = element("pip-chat-message-assistant", in: app)
        XCTAssertTrue(assistantReply.waitForExistence(timeout: 75),
                      "Pip Chat did not display a response from the staging provider")
        XCTAssertTrue(element("pip-chat-fact-I1", in: app).waitForExistence(timeout: 10),
                       "The response did not display the server-validated synthetic pantry fact")
        XCTAssertFalse(element("pip-chat-error", in: app).exists,
                         "Pip Chat displayed an error instead of a provider response")
        scrollTargetIntoView(assistantReply, inside: chatScroll, in: app)
        assertReachable(assistantReply, in: app)
        capture("Pip_Chat_Staging_Live_Response", app: app)
    }

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
        let signIn = app.buttons["login-submit"]
        signIn.tap()
        let homeTab = app.buttons["Home"]
        guard finishStagingSignInIfNeeded(
            app: app,
            signIn: signIn,
            signedInTab: homeTab,
            signedInTabLabel: "Home",
            failureMessage: "Staging login did not reach Home for Pip Chat verification"
        ) else { return }
        dismissSavePasswordPromptIfPresent(app: app, readyElement: homeTab)

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
        capture("Pip_Chat_Shopping_Preview_Staging", app: app)

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
              let password = environment["PROVISION_STAGING_TEST_PASSWORD"],
              let productID = environment["PROVISION_STAGING_TEST_PRODUCT_ID"].flatMap(Int.init) else {
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
        guard finishStagingSignInIfNeeded(
            app: app,
            signIn: signIn,
            signedInTab: inventoryTab,
            signedInTabLabel: "Inventory",
            failureMessage: "Staging login did not establish an authorized household session"
        ) else { return }
        dismissSavePasswordPromptIfPresent(app: app, readyElement: inventoryTab)
        assertStagingDashboardLoaded(app, phase: "The authenticated dashboard finished loading")
        capture("Staging_Authenticated_Home", app: app)

        app.terminate()
        app.launchArguments = []
        app.launch()
        XCTAssertTrue(inventoryTab.waitForExistence(timeout: 40), "The verified staging session did not recover after relaunch")
        assertStagingDashboardLoaded(app, phase: "The persisted session restored the dashboard after relaunch")
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
        guard finishStagingSignInIfNeeded(
            app: app,
            signIn: signIn,
            signedInTab: inventoryTab,
            signedInTabLabel: "Inventory",
            failureMessage: "The synthetic staging account could not log in again"
        ) else { return }
        dismissSavePasswordPromptIfPresent(app: app, readyElement: inventoryTab)
        app.terminate()
        app.launchArguments = []
        app.launch()
        XCTAssertTrue(inventoryTab.waitForExistence(timeout: 40), "The new staging session did not survive relaunch")
        assertStagingDashboardLoaded(app, phase: "The new session restored the dashboard after relaunch")
        inventoryTab.tap()
        let recoveredProduct = element("product-row-\(productID)", in: app)
        XCTAssertTrue(recoveredProduct.waitForExistence(timeout: 30),
                      "The synthetic pantry product persists after logging in again and relaunching")
        XCTAssertTrue(recoveredProduct.isHittable,
                      "The recovered synthetic pantry product is visible in Inventory")
        capture("Staging_Relogin_Relaunch_Recovery", app: app)
    }

    private func assertStagingDashboardLoaded(_ app: XCUIApplication, phase: String) {
        let dashboardLoaded = app.staticTexts["home-dashboard-loaded"]
        XCTAssertTrue(dashboardLoaded.waitForExistence(timeout: 30), phase)
        XCTAssertTrue(dashboardLoaded.isHittable, "The loaded pantry dashboard marker is visible")
    }

    private func finishStagingSignInIfNeeded(
        app: XCUIApplication,
        signIn: XCUIElement,
        signedInTab: XCUIElement,
        signedInTabLabel: String,
        failureMessage: String
    ) -> Bool {
        let networkError = element("login-error-message", in: app)
        let signInOutcome = app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier == %@ OR label == %@", "login-error-message", signedInTabLabel))
            .firstMatch
        guard signInOutcome.waitForExistence(timeout: 40) else {
            XCTFail(failureMessage)
            return false
        }
        if signedInTab.exists { return true }

        guard networkError.exists,
              networkError.label.localizedCaseInsensitiveContains("network connection failed") else {
            XCTFail(failureMessage)
            return false
        }
        guard signIn.isHittable else {
            XCTFail("The user cannot retry staging login after a transient network timeout")
            return false
        }

        XCTContext.runActivity(named: "Retry staging sign-in once after the network timeout") { _ in
            signIn.tap()
        }
        guard signedInTab.waitForExistence(timeout: 40) else {
            XCTFail("\(failureMessage) after the single network retry")
            return false
        }
        return true
    }

    private func dismissSavePasswordPromptIfPresent(
        app: XCUIApplication,
        readyElement: XCUIElement
    ) {
        // iOS exposes Password AutoFill's Save Password prompt as a sheet in the app tree.
        // The sheet can arrive after the authorized screen is already visible.
        let savePasswordSheet = app.sheets.matching(
            NSPredicate(format: "label == %@", "Save Password?")
        ).firstMatch
        if savePasswordSheet.waitForExistence(timeout: 15) {
            let notNowButton = savePasswordSheet.buttons.matching(
                NSPredicate(format: "label == %@", "Not Now")
            ).firstMatch
            XCTAssertTrue(notNowButton.waitForExistence(timeout: 5), "The Save Password sheet must offer a dismiss action")
            XCTAssertTrue(notNowButton.isHittable, "The system Save Password prompt must be dismissible")
            notNowButton.tap()
            let promptDismissed = XCTNSPredicateExpectation(
                predicate: NSPredicate(format: "exists == false"),
                object: savePasswordSheet
            )
            XCTAssertEqual(
                XCTWaiter.wait(for: [promptDismissed], timeout: 5),
                .completed,
                "The Save Password sheet should close after selecting Not Now"
            )
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

private struct ReceiptOCRManifest: Decodable {
    let store: String
    let lineCount: Int
    let itemCount: Int
    let totalPhp: Double
    let items: [ReceiptOCRManifestItem]
}

private struct ReceiptOCRManifestItem: Decodable {
    let sourceName: String
    let searchTerms: [String]
    let quantity: Double
    let unit: String
    let lineTotalPhp: Double
    let catalogAction: String
    let catalogSearch: String?
    let productName: String?
    let brand: String?
    let category: String?
    let productUnit: String?
    let storageLocation: String
}
