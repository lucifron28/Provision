import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_routine_visual_smoke_requires_12_scenarios_from_the_full_gallery():
    scripts = REPOSITORY_ROOT / ".github" / "scripts"
    smoke = json.loads(
        (scripts / "required_ios_smoke_screenshots.json").read_text(encoding="utf-8")
    )["requiredScreenshots"]
    full_gallery = json.loads(
        (scripts / "required_ios_screenshots.json").read_text(encoding="utf-8")
    )["requiredScreenshots"]

    assert len(full_gallery) == 55
    assert len(full_gallery) == len(set(full_gallery))
    assert len(smoke) == 12
    assert len(smoke) == len(set(smoke))
    assert set(smoke) <= set(full_gallery)


def test_pull_request_workflow_runs_representative_screenshots_only():
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )

    smoke_tests = {
        "testPreferencesAllergySettings",
        "testProductLabelReviewScreens",
        "testFormsStayReadableInDarkModeAndLargeText",
        "testHomeNavigationAndCaptureRecipeScreens",
        "testSafetyAndAvailabilityStatesWithLongFilipinoNames",
        "testPipChatConsentConversationAndValidatedRecipeAction",
        "testPipChatShoppingActionOpensTheExistingReviewScreen",
        "testPipChatPrivacyControlsAtAccessibilitySizeInDarkMode",
        "testShoppingReviewRequiredAndBlockedStates",
        "testAmbiguousShoppingConfirmationSurvivesAppRelaunch",
        "testShoppingOfflineRetryAndStalePreviewRecovery",
    }
    assert "-only-testing:frontendTests" in workflow
    assert workflow.count("- shard: ") == 4
    assert "- shard: preferences-product-label" in workflow
    assert all(
        f"-only-testing:frontendUITests/CookWithPipUITests/{test}" in workflow
        for test in smoke_tests
    )
    assert "concurrency:" in workflow
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow
    assert "name: Fast PR feedback" in workflow
    assert "needs: [swift-unit-tests, backend]" in workflow
    assert "needs: [swift-unit-tests, ios-ui-smoke, ios-screenshot-evidence]" in workflow
    assert "--required .github/scripts/required_ios_smoke_screenshots.json" in workflow
    assert "name: cook-with-pip-xcresult" not in workflow


def test_required_smoke_screenshots_are_captured_by_the_pr_ui_tests():
    scripts = REPOSITORY_ROOT / ".github" / "scripts"
    required = json.loads(
        (scripts / "required_ios_smoke_screenshots.json").read_text(encoding="utf-8")
    )["requiredScreenshots"]
    source = (
        REPOSITORY_ROOT / "frontend" / "frontendUITests" / "CookWithPipUITests.swift"
    ).read_text(encoding="utf-8")

    assert all(f'capture("{scenario}"' in source for scenario in required)


def test_manual_gallery_keeps_full_screenshot_suite_and_result_bundle():
    workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "cook-with-pip-visual-gallery.yml"
    ).read_text(encoding="utf-8")
    selected_tests = workflow.split(
        "      - name: Run selected iOS XCUITest suite\n", 1
    )[1].split("\n      - name: Report XCTest durations", 1)[0]
    focused_run = selected_tests.split(
        'if [[ "$GALLERY_SUITE" == "toggle-regressions" ]]; then', 1
    )[1].split("\n          else", 1)[0]
    full_run = selected_tests.split("\n          else", 1)[1]

    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert "- full-gallery" in workflow
    assert "- toggle-regressions" in workflow
    assert "xcodebuild test \"${common_args[@]}\"" in full_run
    assert "-only-testing:" not in full_run
    assert (
        "-only-testing:frontendUITests/CookWithPipUITests/testPipChatConsentControlsGallery"
        in focused_run
    )
    assert (
        "-only-testing:frontendUITests/CookWithPipUITests/testShoppingPreviewEditsConsolidationAndExplicitConfirmation"
        in focused_run
    )
    focused_manifest = json.loads(
        (
            REPOSITORY_ROOT
            / ".github"
            / "scripts"
            / "required_ios_toggle_regressions.json"
        ).read_text(encoding="utf-8")
    )["requiredScreenshots"]
    assert set(focused_manifest) == {
        "Pip_Chat_Consent_Controls",
        "Shopping_Optional_Ingredients",
    }
    assert set(focused_manifest) <= set(
        json.loads(
            (
                REPOSITORY_ROOT
                / ".github"
                / "scripts"
                / "required_ios_screenshots.json"
            ).read_text(encoding="utf-8")
        )["requiredScreenshots"]
    )
    assert "--required .github/scripts/required_ios_screenshots.json" in workflow
    assert "-resultBundlePath artifacts/frontend.xcresult" in workflow
    assert "cook-with-pip-${{ github.event.inputs.suite || 'full-gallery' }}-xcresult" in workflow
