from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "report_github_action_timings.py"


class WorkflowTimingReportTests(unittest.TestCase):
    def test_summary_reports_runner_wait_and_named_ci_phases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            jobs_file = root / "jobs.json"
            jobs_file.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "name": "iOS UI smoke (sample)",
                                "created_at": "2026-11-16T07:00:00Z",
                                "started_at": "2026-11-16T07:02:00Z",
                                "completed_at": "2026-11-16T07:10:00Z",
                                "conclusion": "success",
                                "steps": [
                                    {
                                        "name": "Prepare the exact iPhone 17 simulator",
                                        "started_at": "2026-11-16T07:02:00Z",
                                        "completed_at": "2026-11-16T07:02:10Z",
                                    },
                                    {
                                        "name": "Build selected UI test products",
                                        "started_at": "2026-11-16T07:02:10Z",
                                        "completed_at": "2026-11-16T07:03:10Z",
                                    },
                                    {
                                        "name": "Run UI smoke without rebuilding",
                                        "started_at": "2026-11-16T07:03:10Z",
                                        "completed_at": "2026-11-16T07:09:10Z",
                                    },
                                    {
                                        "name": "Export shard screenshots",
                                        "started_at": "2026-11-16T07:09:10Z",
                                        "completed_at": "2026-11-16T07:09:20Z",
                                    },
                                    {
                                        "name": "Upload shard screenshots",
                                        "started_at": "2026-11-16T07:09:20Z",
                                        "completed_at": "2026-11-16T07:09:40Z",
                                    },
                                ],
                            },
                            {
                                "name": "iOS screenshot evidence",
                                "created_at": "2026-11-16T07:10:00Z",
                                "started_at": "2026-11-16T07:10:02Z",
                                "completed_at": "2026-11-16T07:12:00Z",
                                "conclusion": "success",
                                "steps": [
                                    {
                                        "name": "Organize and verify the 12 required screenshot scenarios",
                                        "started_at": "2026-11-16T07:11:00Z",
                                        "completed_at": "2026-11-16T07:11:20Z",
                                    }
                                ],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--jobs", str(jobs_file)],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("maximum wait **120.0s**", result.stdout)
        self.assertIn("Xcode compilation", result.stdout)
        self.assertIn("Swift unit tests", result.stdout)
        self.assertIn("XCUITest methods", result.stdout)
        self.assertIn("Screenshot extraction", result.stdout)
        self.assertIn("Screenshot organization", result.stdout)
        self.assertIn("Artifact upload", result.stdout)


if __name__ == "__main__":
    unittest.main()
