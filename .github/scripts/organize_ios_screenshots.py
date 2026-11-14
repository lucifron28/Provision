#!/usr/bin/env python3
"""Organize XCUITest screenshots and validate capture integrity, not visual quality."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


ATTACHMENT_SUFFIX = re.compile(r"_\d+_[0-9A-Fa-f-]{36}$")
SCENARIO_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
COMMIT_SHA = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\Z")
VISUAL_REVIEW_STATUS = "not_reviewed_automatically"


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_png(path: Path) -> tuple[str, str]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("file is missing or empty")

    with Image.open(path) as image:
        if image.format != "PNG":
            raise ValueError(f"expected PNG data, found {image.format or 'unknown format'}")
        image.verify()

    with Image.open(path) as image:
        image.load()
        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError(f"invalid image dimensions: {width}x{height}")
        rgba_pixels = image.convert("RGBA").tobytes()
        pixel_digest = hashlib.sha256(
            f"{width}x{height}:RGBA:".encode("ascii") + rgba_pixels
        ).hexdigest()

    return _digest_file(path), pixel_digest


def _load_requirements(path: Path) -> tuple[list[str], dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("required screenshot manifest must be a JSON object")

    required = data.get("requiredScreenshots")
    if not isinstance(required, list) or not required:
        raise TypeError("requiredScreenshots must be a non-empty array")
    if any(not isinstance(name, str) or not SCENARIO_NAME.fullmatch(name) for name in required):
        raise TypeError("every required screenshot name must be a safe non-empty string")
    if len(required) != len(set(required)):
        raise ValueError("required screenshot manifest contains duplicate scenario names")

    descriptions = data.get("scenarioDescriptions", {})
    if not isinstance(descriptions, dict) or any(
        name not in required or not isinstance(description, str) or not description.strip()
        for name, description in descriptions.items()
    ):
        raise TypeError("scenarioDescriptions must map required names to non-empty descriptions")
    return required, descriptions


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
    parser.add_argument("--commit-sha", required=True, help="full commit SHA that produced the test run")
    parser.add_argument(
        "--test-outcome",
        required=True,
        choices=("success", "failure", "cancelled", "skipped", "unknown"),
        help="outcome reported by the Xcode test step",
    )
    args = parser.parse_args()

    if not COMMIT_SHA.fullmatch(args.commit_sha):
        print("Commit SHA must contain 40 or 64 hexadecimal characters.", file=sys.stderr)
        return 1

    try:
        required, descriptions = _load_requirements(args.required)
        exported_tests: list[tuple[Path, dict[str, Any]]] = []
        for input_dir in args.input:
            source_manifest = input_dir / "manifest.json"
            if not source_manifest.is_file():
                raise FileNotFoundError(f"Missing XCUITest attachment manifest: {source_manifest}")
            exported = json.loads(source_manifest.read_text(encoding="utf-8"))
            if not isinstance(exported, list) or any(not isinstance(test, dict) for test in exported):
                raise TypeError(f"Expected a list of XCUITest attachments in {source_manifest}")
            exported_tests.extend((input_dir, test) for test in exported)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(f"Could not read screenshot manifests: {error}", file=sys.stderr)
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "xcresult-attachments.json").write_text(
        json.dumps([test for _, test in exported_tests], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    errors: list[str] = []
    occurrence_counts: Counter[str] = Counter()
    scenarios: list[dict[str, Any]] = []
    scenario_hashes: dict[str, tuple[str, str]] = {}

    for input_dir, test in exported_tests:
        test_id = test.get("testIdentifier")
        attachments = test.get("attachments", [])
        if not isinstance(attachments, list):
            errors.append(f"Invalid attachments list for test {test_id!r}")
            continue

        for attachment in attachments:
            if not isinstance(attachment, dict):
                errors.append(f"Invalid attachment entry for test {test_id!r}")
                continue
            suggested = attachment.get("suggestedHumanReadableName", "")
            exported_name = attachment.get("exportedFileName", "")
            is_png = (
                isinstance(suggested, str) and suggested.lower().endswith(".png")
            ) or (
                isinstance(exported_name, str) and exported_name.lower().endswith(".png")
            )
            if not is_png:
                continue

            if not isinstance(exported_name, str) or not exported_name or Path(exported_name).name != exported_name:
                errors.append(f"PNG attachment {suggested!r} has an invalid exported filename")
                continue
            source = input_dir / exported_name
            try:
                byte_hash, pixel_hash = _validate_png(source)
            except (OSError, UnidentifiedImageError, ValueError) as error:
                errors.append(f"Invalid PNG attachment {suggested!r} ({source}): {error}")
                continue

            if not isinstance(suggested, str) or not suggested.lower().endswith(".png"):
                errors.append(f"PNG attachment {exported_name!r} has no screenshot scenario name")
                continue

            stem = Path(suggested).stem
            scenario = ATTACHMENT_SUFFIX.sub("", stem)
            if not SCENARIO_NAME.fullmatch(scenario):
                errors.append(f"Invalid screenshot scenario name: {scenario!r}")
                continue
            occurrence_counts[scenario] += 1
            if occurrence_counts[scenario] > 1:
                errors.append(f"Screenshot scenario {scenario!r} occurs more than once")

            if not isinstance(test_id, str) or not test_id.strip() or test_id == "unknown-test":
                errors.append(f"Screenshot {scenario!r} has no traceable XCUITest testIdentifier")
                continue

            if args.only_required and scenario not in required:
                continue
            if occurrence_counts[scenario] > 1:
                continue

            destination_name = f"{scenario}.png"
            shutil.copy2(source, args.output / destination_name)
            associated_with_failure = bool(attachment.get("isAssociatedWithFailure", False))
            if associated_with_failure:
                errors.append(f"Screenshot {scenario!r} is associated with a failed UI assertion")
            scenario_hashes[scenario] = (byte_hash, pixel_hash)
            scenarios.append(
                {
                    "scenario": scenario,
                    "purpose": descriptions.get(scenario),
                    "file": destination_name,
                    "commitSHA": args.commit_sha,
                    "testIdentifier": test_id,
                    "deviceName": attachment.get("deviceName"),
                    "configurationName": attachment.get("configurationName"),
                    "fixtureStatus": "synthetic_fixture",
                    "liveDataUsed": False,
                    "associatedWithFailure": associated_with_failure,
                    "uiTestOutcome": args.test_outcome,
                    "captureIntegrityStatus": "failed" if associated_with_failure else "passed",
                    "visualReviewStatus": VISUAL_REVIEW_STATUS,
                }
            )

    missing = sorted(name for name in required if name not in scenario_hashes)
    duplicate_screenshots = sorted(
        name for name in required if occurrence_counts[name] > 1
    )
    if missing:
        errors.append("Missing required screenshot(s): " + ", ".join(missing))

    duplicate_image_pairs: list[dict[str, Any]] = []
    available_required = [name for name in required if name in scenario_hashes]
    for index, first_name in enumerate(available_required):
        first_byte_hash, first_pixel_hash = scenario_hashes[first_name]
        for second_name in available_required[index + 1 :]:
            second_byte_hash, second_pixel_hash = scenario_hashes[second_name]
            byte_identical = first_byte_hash == second_byte_hash
            pixel_identical = first_pixel_hash == second_pixel_hash
            if byte_identical or pixel_identical:
                duplicate_image_pairs.append(
                    {
                        "first": first_name,
                        "second": second_name,
                        "byteIdentical": byte_identical,
                        "pixelIdentical": pixel_identical,
                    }
                )
                errors.append(
                    f"Required scenarios {first_name!r} and {second_name!r} have identical image content"
                )

    if args.test_outcome != "success":
        errors.append(f"XCUITest outcome was {args.test_outcome!r}; screenshots are not verified")

    integrity_errors = [error for error in errors if not error.startswith("XCUITest outcome was ")]
    capture_integrity_status = "failed" if integrity_errors else "passed"
    manifest = {
        "commitSHA": args.commit_sha,
        "testOutcome": args.test_outcome,
        "fixtureStatus": "synthetic_fixture",
        "liveDataUsed": False,
        "overallStatus": "passed" if not errors else "failed",
        "captureIntegrityStatus": capture_integrity_status,
        "visualReviewStatus": VISUAL_REVIEW_STATUS,
        "verificationScope": (
            "Checks required scenario completeness, test attribution, PNG decoding, and exact or pixel-identical "
            "required captures. Automated checks do not assess visual quality."
        ),
        "requiredScreenshots": required,
        "capturedScreenshots": sorted(scenarios, key=lambda item: str(item["scenario"])),
        "missingScreenshots": missing,
        "duplicateScreenshots": duplicate_screenshots,
        "duplicateImagePairs": duplicate_image_pairs,
        "errors": errors,
    }
    (args.output / "scenario-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"Organized {len(scenarios)} screenshot(s); capture integrity: {capture_integrity_status}.")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
