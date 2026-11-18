import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _read_manifest(name: str) -> list[str]:
    path = REPOSITORY_ROOT / ".github" / "scripts" / name
    return json.loads(path.read_text(encoding="utf-8"))["requiredScreenshots"]


def test_routine_visual_smoke_requires_12_scenarios_from_the_full_gallery():
    smoke = _read_manifest("required_ios_smoke_screenshots.json")
    full_gallery = _read_manifest("required_ios_screenshots.json")

    assert len(full_gallery) == 58
    assert len(full_gallery) == len(set(full_gallery))
    assert len(smoke) == 12
    assert len(smoke) == len(set(smoke))
    assert set(smoke) <= set(full_gallery)


def test_pull_request_workflow_runs_four_ui_shards_and_preserves_safety_coverage():
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
        "testCookWithPipNeedsReviewCandidatesAreActionable",
        "testShoppingReviewRequiredAndBlockedStates",
        "testAmbiguousShoppingConfirmationSurvivesAppRelaunch",
        "testShoppingOfflineRetryAndStalePreviewRecovery",
        "testPurchasedGroceriesReviewRequiresExplicitDecisions",
    }
    assert "-only-testing:frontendTests" in workflow
    assert workflow.count("- shard: ") == 4
    assert "- shard: preferences\n" in workflow
    assert "- shard: product-label\n" in workflow
    assert "max-parallel: 4" in workflow
    assert "- shard: shopping-recovery" not in workflow
    confirmation_shard = workflow.split(
        "- shard: shopping-confirmation", 1
    )[1].split("- shard:", 1)[0]
    assert "testShoppingOfflineRetryAndStalePreviewRecovery" in confirmation_shard
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
    assert "build-for-testing" in workflow
    assert "test-without-building" in workflow
    assert "-parallel-testing-enabled NO" in workflow
    assert "id=${SIMULATOR_UDID}" in workflow
    assert "name: cook-with-pip-xcresult" not in workflow


def test_required_smoke_screenshots_are_captured_by_the_pr_ui_tests():
    source = (
        REPOSITORY_ROOT / "frontend" / "frontendUITests" / "CookWithPipUITests.swift"
    ).read_text(encoding="utf-8")
    assert all(
        f'capture("{scenario}"' in source
        for scenario in _read_manifest("required_ios_smoke_screenshots.json")
    )
    smoke_manifest = json.loads(
        (REPOSITORY_ROOT / ".github" / "scripts" / "required_ios_smoke_screenshots.json").read_text(
            encoding="utf-8"
        )
    )
    assert all(f'capture("{scenario}"' in source for scenario in smoke_manifest["supplementalScreenshots"])


def test_live_deepseek_smoke_allows_only_main_or_exact_open_pr_11_head():
    workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "live-deepseek-smoke.yml"
    ).read_text(encoding="utf-8")

    assert "deployment_source:" in workflow
    assert "options:\n          - main\n          - pr-11" in workflow
    assert "git merge-base --is-ancestor \"$actual\" refs/remotes/origin/main" in workflow
    assert "pulls/11" in workflow
    assert '"$head_sha" == "$actual"' in workflow
    assert '"$head_ref" == "feat/pip-chat-foundation"' in workflow
    assert '"$base_ref" == "main"' in workflow
    assert "RUN_ONE_SYNTHETIC_DEEPSEEK_REQUEST" in workflow
    assert 'PROVISION_LIVE_DEEPSEEK_ENABLED" != "true"' in workflow


def test_gallery_covers_gallery_methods_and_keeps_full_result_bundles():
    workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "cook-with-pip-visual-gallery.yml"
    ).read_text(encoding="utf-8")
    live_workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "live-pip-chat-smoke.yml"
    ).read_text(encoding="utf-8")
    source = (
        REPOSITORY_ROOT / "frontend" / "frontendUITests" / "CookWithPipUITests.swift"
    ).read_text(encoding="utf-8")
    methods = {
        line.split("func ", 1)[1].split("(", 1)[0]
        for line in source.splitlines()
        if "func test" in line
    }
    live_only_methods = {"testStagingLivePipChatResponseIsDisplayed"}
    gallery_methods = methods - live_only_methods

    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert "- full-gallery" in workflow
    assert "- gallery-regressions" in workflow
    assert "- shopping-preview-regressions" in workflow
    assert "- large-text-regressions" in workflow
    assert "- toggle-regressions" in workflow
    assert "- shopping-recovery" in workflow
    assert len(gallery_methods) == 31
    assert live_only_methods <= methods
    assert all(f'"{method}"' in workflow for method in gallery_methods)
    assert all(f'"{method}"' not in workflow for method in live_only_methods)
    assert all(method in live_workflow for method in live_only_methods)
    assert "build-for-testing" in workflow
    assert "test-without-building" in workflow
    assert "max-parallel: 4" in workflow
    assert "-parallel-testing-enabled NO" in workflow
    assert "id=${SIMULATOR_UDID}" in workflow
    assert "timeout-minutes: 45" in workflow
    assert "--strict-names" in workflow
    assert "cook-with-pip-${{ matrix.suite }}-${{ matrix.shard }}-xcresult" in workflow
    assert "actions/download-artifact@v4" in workflow
    assert "report_github_action_timings.py" in workflow


def test_focused_gallery_runs_prior_failures_and_duplicate_capture_regressions():
    workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "cook-with-pip-visual-gallery.yml"
    ).read_text(encoding="utf-8")
    manifest = _read_manifest("required_ios_gallery_regressions.json")
    failures = {
        "testPipChatConsentControlsGallery",
        "testShoppingPreviewDarkAndLargeTextStates",
        "testShoppingPreviewEditsConsolidationAndExplicitConfirmation",
        "testStaleProductLabelReviewIsShownAsStale",
    }
    duplicate_capture_tests = {
        "testProductLabelReviewScreens",
        "testCookWithPipDarkModeGallery",
        "testLargeTextFilipinoRecipeSafetyGallery",
        "testCookWithPipSearchKeyboardGallery",
    }
    assert all(f'"{test}"' in workflow for test in failures)
    assert all(f'"{test}"' in workflow for test in duplicate_capture_tests)
    assert len(manifest) == 16
    assert len(manifest) == len(set(manifest))
    gallery_manifest = json.loads(
        (REPOSITORY_ROOT / ".github" / "scripts" / "required_ios_screenshots.json").read_text(
            encoding="utf-8"
        )
    )
    gallery = set(gallery_manifest["requiredScreenshots"])
    gallery_supplemental = set(gallery_manifest.get("supplementalScreenshots", []))
    assert set(manifest) <= gallery | gallery_supplemental


def test_large_text_regressions_have_a_focused_capture_manifest():
    workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "cook-with-pip-visual-gallery.yml"
    ).read_text(encoding="utf-8")
    source = (
        REPOSITORY_ROOT / "frontend" / "frontendUITests" / "CookWithPipUITests.swift"
    ).read_text(encoding="utf-8")
    manifest = _read_manifest("required_ios_large_text_regressions.json")
    focused_tests = {
        "testLargeTextFilipinoRecipeSafetyGallery",
        "testCookWithPipSearchKeyboardGallery",
    }

    assert "- large-text-regressions" in workflow
    assert "required_ios_large_text_regressions.json" in workflow
    assert all(f'"{test}"' in workflow for test in focused_tests)
    assert all(f'func {test}()' in source for test in focused_tests)
    assert all(f'capture("{scenario}"' in source for scenario in manifest)
    gallery_manifest = json.loads(
        (REPOSITORY_ROOT / ".github" / "scripts" / "required_ios_screenshots.json").read_text(
            encoding="utf-8"
        )
    )
    gallery_scenarios = set(gallery_manifest["requiredScreenshots"])
    gallery_scenarios.update(gallery_manifest.get("supplementalScreenshots", []))
    assert set(manifest) <= gallery_scenarios


def test_toggle_and_shopping_recovery_regression_manifests_remain_in_the_gallery():
    workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "cook-with-pip-visual-gallery.yml"
    ).read_text(encoding="utf-8")
    full = set(_read_manifest("required_ios_screenshots.json"))
    toggle = set(_read_manifest("required_ios_toggle_regressions.json"))
    recovery = set(_read_manifest("required_ios_shopping_recovery_regressions.json"))

    assert toggle == {"Pip_Chat_Consent_Controls", "Shopping_Optional_Ingredients"}
    assert recovery == {"Shopping_Offline_Error_Retry", "Shopping_Stale_Preview_Refresh"}
    assert toggle <= full
    assert recovery <= full
    assert ".github/scripts/required_ios_screenshots.json" in workflow
