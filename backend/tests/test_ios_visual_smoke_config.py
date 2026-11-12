import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_routine_visual_smoke_requires_11_scenarios_from_the_full_gallery():
    scripts = REPOSITORY_ROOT / ".github" / "scripts"
    smoke = json.loads(
        (scripts / "required_ios_smoke_screenshots.json").read_text(encoding="utf-8")
    )["requiredScreenshots"]
    full_gallery = json.loads(
        (scripts / "required_ios_screenshots.json").read_text(encoding="utf-8")
    )["requiredScreenshots"]

    assert len(smoke) == 11
    assert len(smoke) == len(set(smoke))
    assert set(smoke) <= set(full_gallery)


def test_pull_request_workflow_runs_representative_screenshots_only():
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )

    assert "-only-testing:frontendTests" in workflow
    assert (
        "-only-testing:frontendUITests/CookWithPipUITests/"
        "testHomeNavigationAndCaptureRecipeScreens"
    ) in workflow
    assert (
        "-only-testing:frontendUITests/CookWithPipUITests/"
        "testShoppingReviewRequiredAndBlockedStates"
    ) in workflow
    assert (
        "-only-testing:frontendUITests/CookWithPipUITests/"
        "testShoppingOfflineRetryAndStalePreviewRecovery"
    ) in workflow
    assert "--required .github/scripts/required_ios_smoke_screenshots.json" in workflow
    assert "name: cook-with-pip-xcresult" not in workflow


def test_manual_gallery_keeps_full_screenshot_suite_and_result_bundle():
    workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "ios-screenshot-gallery.yml"
    ).read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "xcodebuild test" in workflow
    assert "-only-testing:" not in workflow
    assert "--required .github/scripts/required_ios_screenshots.json" in workflow
    assert "name: cook-with-pip-full-xcresult" in workflow
