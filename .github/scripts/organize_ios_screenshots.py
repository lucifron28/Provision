#!/usr/bin/env python3
"""Give XCUITest screenshot attachments stable names and enforce scenario coverage."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path


ATTACHMENT_SUFFIX = re.compile(r"_\d+_[0-9A-Fa-f-]{36}$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        required=True,
        action="append",
        type=Path,
        help="xcresulttool attachment export directory (repeat once per UI test shard)",
    )
    parser.add_argument("--output", required=True, type=Path, help="organized screenshot directory")
    parser.add_argument("--required", required=True, type=Path, help="JSON file listing required screenshot names")
    parser.add_argument(
        "--only-required",
        action="store_true",
        help="copy only required scenarios (used for the small pull-request smoke gallery)",
    )
    parser.add_argument("--commit-sha", default="unknown", help="commit that produced the test run")
    parser.add_argument(
        "--test-outcome",
        choices=("success", "failure", "cancelled", "skipped", "unknown"),
        default="unknown",
        help="outcome reported by the Xcode test step",
    )
    args = parser.parse_args()

    exported_tests: list[tuple[Path, dict[str, object]]] = []
    try:
        required_data = json.loads(args.required.read_text(encoding="utf-8"))
        required = required_data["requiredScreenshots"]
        for input_dir in args.input:
            source_manifest = input_dir / "manifest.json"
            if not source_manifest.is_file():
                print(f"Missing XCUITest attachment manifest: {source_manifest}", file=sys.stderr)
                return 1
            exported = json.loads(source_manifest.read_text(encoding="utf-8"))
            if not isinstance(exported, list) or any(not isinstance(test, dict) for test in exported):
                raise TypeError(f"Expected a list of XCUITest attachments in {source_manifest}")
            exported_tests.extend((input_dir, test) for test in exported)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"Could not read screenshot manifests: {error}", file=sys.stderr)
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "xcresult-attachments.json").write_text(
        json.dumps([test for _, test in exported_tests], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    scenarios: list[dict[str, object]] = []
    names: set[str] = set()

    def assertion_status(associated_with_failure: bool) -> str:
        if associated_with_failure:
            return "failed"
        if args.test_outcome == "success":
            return "passed"
        if args.test_outcome == "failure":
            return "not_verified"
        if args.test_outcome == "cancelled":
            return "incomplete"
        return "not_run"

    for input_dir, test in exported_tests:
        test_id = test.get("testIdentifier", "unknown-test")
        for attachment in test.get("attachments", []):
            suggested = attachment.get("suggestedHumanReadableName", "")
            exported_name = attachment.get("exportedFileName", "")
            if not suggested.lower().endswith(".png"):
                continue
            stem = Path(suggested).stem
            scenario = ATTACHMENT_SUFFIX.sub("", stem)
            if not scenario or scenario in names:
                print(f"Duplicate or invalid screenshot scenario name: {scenario!r}", file=sys.stderr)
                return 1
            if args.only_required and scenario not in required:
                continue

            source = input_dir / exported_name
            if not source.is_file():
                print(f"Screenshot attachment is missing: {source}", file=sys.stderr)
                return 1
            destination_name = f"{scenario}.png"
            shutil.copy2(source, args.output / destination_name)
            names.add(scenario)
            associated_with_failure = attachment.get("isAssociatedWithFailure", False)
            scenarios.append(
                {
                    "scenario": scenario,
                    "file": destination_name,
                    "commitSHA": args.commit_sha,
                    "testIdentifier": test_id,
                    "deviceName": attachment.get("deviceName"),
                    "configurationName": attachment.get("configurationName"),
                    "fixtureStatus": "synthetic_fixture",
                    "liveDataUsed": False,
                    "associatedWithFailure": associated_with_failure,
                    "assertionStatus": assertion_status(associated_with_failure),
                }
            )

    missing = sorted(set(required) - names)
    failed_screenshots = any(bool(item["associatedWithFailure"]) for item in scenarios)
    if failed_screenshots:
        overall_assertion_status = "failed"
    elif missing:
        overall_assertion_status = "not_verified"
    else:
        overall_assertion_status = assertion_status(False)
    manifest = {
        "commitSHA": args.commit_sha,
        "testOutcome": args.test_outcome,
        "fixtureStatus": "synthetic_fixture",
        "liveDataUsed": False,
        "assertionStatus": overall_assertion_status,
        "requiredScreenshots": required,
        "capturedScreenshots": sorted(scenarios, key=lambda item: str(item["scenario"])),
        "missingScreenshots": missing,
    }
    (args.output / "scenario-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Organized {len(scenarios)} screenshot(s).")
    if missing:
        print("Missing required screenshot(s): " + ", ".join(missing), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
