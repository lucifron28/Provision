#!/usr/bin/env python3
"""Summarize queue and named phase durations from the current Actions run."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


PHASES = {
    "Simulator preparation": ("Prepare the exact iPhone 17 simulator",),
    "Xcode compilation": (
        "Build Swift unit test products",
        "Build selected UI test products",
        "Build selected gallery UI test products",
        "Build staging iPhone UI test products",
    ),
    "Swift unit tests": ("Run Swift unit tests without rebuilding",),
    "XCUITest methods": (
        "Run UI smoke without rebuilding",
        "Run selected XCUITest methods without rebuilding",
        "Run selected XCUITest suite",
        "Run staging login, offline recovery, and Keychain relaunch tests",
    ),
    "Screenshot extraction": (
        "Export shard screenshots",
        "Export simulator screenshot attachments",
    ),
    "Screenshot organization": (
        "Organize and verify the 12 required screenshot scenarios",
        "Organize and verify all 55 required screenshots",
        "Organize and verify gallery screenshots",
        "Organize and verify the selected regression screenshots",
    ),
    "Artifact upload": ("Upload",),
}


def timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def seconds(start: str | None, end: str | None) -> float | None:
    start_time = timestamp(start)
    end_time = timestamp(end)
    if start_time is None or end_time is None:
        return None
    return max(0.0, (end_time - start_time).total_seconds())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    try:
        payload = json.loads(args.jobs.read_text(encoding="utf-8"))
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise ValueError("workflow jobs response has no jobs array")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Could not read workflow job timings: {error}", file=sys.stderr)
        return 1

    rows: dict[str, list[float]] = {name: [] for name in PHASES}
    waits: list[tuple[str, float]] = []
    job_durations: list[tuple[str, float, str]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        wait = seconds(job.get("created_at"), job.get("started_at"))
        if wait is not None:
            waits.append((str(job.get("name", "unknown job")), wait))
        duration = seconds(job.get("started_at"), job.get("completed_at"))
        if duration is not None:
            job_durations.append((str(job.get("name", "unknown job")), duration, str(job.get("conclusion", "unknown"))))
        for step in job.get("steps", []):
            if not isinstance(step, dict):
                continue
            duration = seconds(step.get("started_at"), step.get("completed_at"))
            if duration is None:
                continue
            step_name = str(step.get("name", ""))
            for phase, names in PHASES.items():
                if any(step_name.startswith(name) for name in names):
                    rows[phase].append(duration)
                    break

    lines = ["### CI phase timings", ""]
    if waits:
        max_wait_job, max_wait = max(waits, key=lambda row: row[1])
        mean_wait = sum(duration for _, duration in waits) / len(waits)
        lines.extend([
            f"Runner allocation: maximum wait **{max_wait:.1f}s** ({max_wait_job}); mean across {len(waits)} jobs **{mean_wait:.1f}s**.",
            "",
        ])
    else:
        lines.extend(["Runner allocation timings were not available.", ""])
    lines.extend(["| Phase | Jobs | Cumulative runner time | Longest job |", "| --- | ---: | ---: | ---: |"])
    for phase, durations in rows.items():
        if durations:
            lines.append(f"| {phase} | {len(durations)} | {sum(durations):.1f}s | {max(durations):.1f}s |")
        else:
            lines.append(f"| {phase} | 0 | — | — |")
    lines.extend(["", "### Job durations", "", "| Job | Result | Wall time |", "| --- | --- | ---: |"])
    for name, duration, conclusion in sorted(job_durations, key=lambda row: row[1], reverse=True):
        safe_name = name.replace("|", "\\|")
        lines.append(f"| {safe_name} | {conclusion} | {duration:.1f}s |")
    report = "\n".join(lines) + "\n"
    print(report)
    if args.summary:
        try:
            with args.summary.open("a", encoding="utf-8") as output:
                output.write(report)
        except OSError as error:
            print(f"Could not update GitHub step summary: {error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
