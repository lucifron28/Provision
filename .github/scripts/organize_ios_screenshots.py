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
    parser.add_argument("--input", required=True, type=Path, help="xcresulttool attachment export directory")
    parser.add_argument("--output", required=True, type=Path, help="organized screenshot directory")
    parser.add_argument("--required", required=True, type=Path, help="JSON file listing required screenshot names")
    args = parser.parse_args()

    source_manifest = args.input / "manifest.json"
    if not source_manifest.is_file():
        print(f"Missing XCUITest attachment manifest: {source_manifest}", file=sys.stderr)
        return 1

    try:
        exported = json.loads(source_manifest.read_text(encoding="utf-8"))
        required_data = json.loads(args.required.read_text(encoding="utf-8"))
        required = required_data["requiredScreenshots"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"Could not read screenshot manifests: {error}", file=sys.stderr)
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_manifest, args.output / "xcresult-attachments.json")
    scenarios: list[dict[str, object]] = []
    names: set[str] = set()

    for test in exported if isinstance(exported, list) else []:
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

            source = args.input / exported_name
            if not source.is_file():
                print(f"Screenshot attachment is missing: {source}", file=sys.stderr)
                return 1
            destination_name = f"{scenario}.png"
            shutil.copy2(source, args.output / destination_name)
            names.add(scenario)
            scenarios.append(
                {
                    "scenario": scenario,
                    "file": destination_name,
                    "testIdentifier": test_id,
                    "deviceName": attachment.get("deviceName"),
                    "configurationName": attachment.get("configurationName"),
                    "associatedWithFailure": attachment.get("isAssociatedWithFailure", False),
                }
            )

    missing = sorted(set(required) - names)
    manifest = {
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
