import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ORGANIZER = REPOSITORY_ROOT / ".github" / "scripts" / "organize_ios_screenshots.py"
DURATION_REPORTER = REPOSITORY_ROOT / ".github" / "scripts" / "report_xcode_test_durations.py"
ATTACHMENT_UUID = "123e4567-e89b-12d3-a456-426614174000"


def _write_export(folder: Path, scenario: str, filename: str) -> None:
    folder.mkdir()
    (folder / filename).write_bytes(b"synthetic screenshot bytes")
    (folder / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "testIdentifier": "CookWithPipUITests/testScreenshotCapture",
                    "attachments": [
                        {
                            "suggestedHumanReadableName": f"{scenario}_1_{ATTACHMENT_UUID}.png",
                            "exportedFileName": filename,
                            "deviceName": "iPhone 17",
                            "configurationName": "iOS Simulator",
                            "isAssociatedWithFailure": False,
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )


def test_screenshot_organizer_merges_shards_and_verifies_every_required_scenario(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_export(first, "Home_Cook_with_Pip", "home.png")
    _write_export(second, "Shopping_Preview_Review_Required", "shopping.png")
    required = tmp_path / "required.json"
    required.write_text(
        json.dumps({"requiredScreenshots": ["Home_Cook_with_Pip", "Shopping_Preview_Review_Required"]}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ORGANIZER),
            "--input",
            str(first),
            "--input",
            str(second),
            "--output",
            str(tmp_path / "organized"),
            "--required",
            str(required),
            "--only-required",
            "--commit-sha",
            "abc123",
            "--test-outcome",
            "success",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    organized = tmp_path / "organized"
    evidence = json.loads((organized / "scenario-manifest.json").read_text(encoding="utf-8"))
    assert evidence["assertionStatus"] == "passed"
    assert evidence["missingScreenshots"] == []
    assert {item["scenario"] for item in evidence["capturedScreenshots"]} == {
        "Home_Cook_with_Pip",
        "Shopping_Preview_Review_Required",
    }
    assert all(item["assertionStatus"] == "passed" for item in evidence["capturedScreenshots"])
    assert len(json.loads((organized / "xcresult-attachments.json").read_text(encoding="utf-8"))) == 2


def test_screenshot_organizer_does_not_verify_missing_required_scenarios(tmp_path):
    source = tmp_path / "source"
    _write_export(source, "Home_Cook_with_Pip", "home.png")
    required = tmp_path / "required.json"
    required.write_text(
        json.dumps({"requiredScreenshots": ["Home_Cook_with_Pip", "Missing_Scenario"]}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ORGANIZER),
            "--input",
            str(source),
            "--output",
            str(tmp_path / "organized"),
            "--required",
            str(required),
            "--only-required",
            "--test-outcome",
            "success",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    evidence = json.loads(
        (tmp_path / "organized" / "scenario-manifest.json").read_text(encoding="utf-8")
    )
    assert evidence["assertionStatus"] == "not_verified"
    assert evidence["missingScreenshots"] == ["Missing_Scenario"]
    assert [item["scenario"] for item in evidence["capturedScreenshots"]] == ["Home_Cook_with_Pip"]


def test_xcode_duration_report_extracts_individual_test_cases(tmp_path):
    log = tmp_path / "xcodebuild.log"
    log.write_text(
        "Test Case '-[frontendUITests.CookWithPipUITests testSlowScreen]' passed (546.095 seconds).\n"
        "Test Case '-[frontendTests.RecipeTests testRecipeSafety]' passed (0.812 seconds).\n",
        encoding="utf-8",
    )
    output = tmp_path / "durations.json"

    result = subprocess.run(
        [
            sys.executable,
            str(DURATION_REPORTER),
            "--input-log",
            str(log),
            "--json-output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    durations = json.loads(output.read_text(encoding="utf-8"))
    assert [case["durationSeconds"] for case in durations] == [546.095, 0.812]


def test_xcode_duration_aggregator_lists_slowest_cases_first(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "unit.json").write_text(
        json.dumps(
            [
                {"testIdentifier": "testFast", "result": "passed", "durationSeconds": 0.8},
                {"testIdentifier": "testSlow", "result": "passed", "durationSeconds": 546.1},
            ]
        ),
        encoding="utf-8",
    )
    summary = tmp_path / "summary.md"

    result = subprocess.run(
        [
            sys.executable,
            str(DURATION_REPORTER),
            "--aggregate-dir",
            str(reports),
            "--summary",
            str(summary),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.index("testSlow") < result.stdout.index("testFast")
    assert "546.100s" in summary.read_text(encoding="utf-8")
