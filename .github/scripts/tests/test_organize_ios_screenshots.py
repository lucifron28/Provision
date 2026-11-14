from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


SCRIPT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPT_DIR / "organize_ios_screenshots.py"


class ScreenshotOrganizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.input_dir = self.root / "raw"
        self.input_dir.mkdir()
        self.output_dir = self.root / "organized"
        self.required_path = self.root / "required.json"
        self.required_path.write_text(
            json.dumps(
                {
                    "requiredScreenshots": ["Cook_with_Pip", "Cook_Now"],
                    "scenarioDescriptions": {"Cook_Now": "Selected recipe mode."},
                }
            ),
            encoding="utf-8",
        )
        self.attachments: list[dict[str, object]] = []
        self.write_png("Cook_with_Pip", "red.png", (240, 20, 10), mode="RGB")
        self.write_png("Cook_Now", "green.png", (10, 180, 30), mode="RGB")
        self.write_export_manifest()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_png(self, scenario: str, filename: str, color: tuple[int, ...], *, mode: str = "RGBA") -> None:
        Image.new(mode, (3, 2), color).save(self.input_dir / filename, format="PNG")
        self.attachments.append(
            {
                "suggestedHumanReadableName": (
                    f"{scenario}_1_12345678-1234-1234-1234-123456789abc.png"
                ),
                "exportedFileName": filename,
                "deviceName": "iPhone 17",
                "configurationName": "Default",
                "isAssociatedWithFailure": False,
            }
        )

    def write_export_manifest(self, *, test_identifier: str = "frontendUITests.CookWithPipUITests/testGalleryCaptures()") -> None:
        (self.input_dir / "manifest.json").write_text(
            json.dumps([{"testIdentifier": test_identifier, "attachments": self.attachments}]),
            encoding="utf-8",
        )

    def run_organizer(self, *, outcome: str = "success", only_required: bool = False) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(self.input_dir),
            "--output",
            str(self.output_dir),
            "--required",
            str(self.required_path),
            "--commit-sha",
            "a" * 40,
            "--test-outcome",
            outcome,
        ]
        if only_required:
            command.append("--only-required")
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def manifest(self) -> dict[str, object]:
        return json.loads((self.output_dir / "scenario-manifest.json").read_text(encoding="utf-8"))

    def test_valid_scenarios_record_producer_test_and_capture_only_scope(self) -> None:
        result = self.run_organizer()

        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = self.manifest()
        self.assertEqual(manifest["overallStatus"], "passed")
        self.assertEqual(manifest["captureIntegrityStatus"], "passed")
        self.assertEqual(manifest["visualReviewStatus"], "not_reviewed_automatically")
        self.assertIn("do not assess visual quality", manifest["verificationScope"])
        captured = {item["scenario"]: item for item in manifest["capturedScreenshots"]}
        self.assertEqual(
            captured["Cook_Now"]["testIdentifier"],
            "frontendUITests.CookWithPipUITests/testGalleryCaptures()",
        )
        self.assertEqual(captured["Cook_Now"]["purpose"], "Selected recipe mode.")

    def test_duplicate_scenario_attachment_fails_exactly_once_check(self) -> None:
        self.write_png("Cook_Now", "green-duplicate.png", (20, 30, 40), mode="RGB")
        self.write_export_manifest()

        result = self.run_organizer()

        self.assertNotEqual(result.returncode, 0)
        manifest = self.manifest()
        self.assertEqual(manifest["overallStatus"], "failed")
        self.assertEqual(manifest["duplicateScreenshots"], ["Cook_Now"])

    def test_pixel_identical_images_with_different_png_encodings_fail(self) -> None:
        Image.new("RGBA", (3, 2), (10, 180, 30, 255)).save(self.input_dir / "red.png", format="PNG")

        result = self.run_organizer()

        self.assertNotEqual(result.returncode, 0)
        pairs = self.manifest()["duplicateImagePairs"]
        self.assertEqual(len(pairs), 1)
        self.assertFalse(pairs[0]["byteIdentical"])
        self.assertTrue(pairs[0]["pixelIdentical"])

    def test_byte_identical_required_images_fail(self) -> None:
        (self.input_dir / "green.png").write_bytes((self.input_dir / "red.png").read_bytes())

        result = self.run_organizer()

        self.assertNotEqual(result.returncode, 0)
        pairs = self.manifest()["duplicateImagePairs"]
        self.assertEqual(len(pairs), 1)
        self.assertTrue(pairs[0]["byteIdentical"])
        self.assertTrue(pairs[0]["pixelIdentical"])

    def test_invalid_optional_png_fails_even_when_only_required_is_requested(self) -> None:
        (self.input_dir / "broken.png").write_bytes(b"not a PNG")
        self.attachments.append(
            {
                "suggestedHumanReadableName": "Optional_1_12345678-1234-1234-1234-123456789abc.png",
                "exportedFileName": "broken.png",
                "testIdentifier": "ignored-because-the-test-identifier-is-on-the-result",
                "isAssociatedWithFailure": False,
            }
        )
        self.write_export_manifest()

        result = self.run_organizer(only_required=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any("Invalid PNG" in error for error in self.manifest()["errors"]))

    def test_failed_ui_run_never_produces_a_successful_manifest(self) -> None:
        result = self.run_organizer(outcome="failure")

        self.assertNotEqual(result.returncode, 0)
        manifest = self.manifest()
        self.assertEqual(manifest["testOutcome"], "failure")
        self.assertEqual(manifest["overallStatus"], "failed")
        self.assertEqual(manifest["visualReviewStatus"], "not_reviewed_automatically")

    def test_missing_test_identifier_fails_provenance_check(self) -> None:
        self.write_export_manifest(test_identifier="")

        result = self.run_organizer()

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any("testIdentifier" in error for error in self.manifest()["errors"]))


if __name__ == "__main__":
    unittest.main()
