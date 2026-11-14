#!/usr/bin/env python3
"""Extract per-test XCTest durations for GitHub Actions summaries."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


CASE_LINE = re.compile(
    r"^Test Case ['\"](?P<identifier>.+?)['\"] "
    r"(?P<result>passed|failed|skipped) "
    r"\((?P<seconds>[0-9]+(?:\.[0-9]+)?) seconds\)"
)


def parse_log(path: Path) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = CASE_LINE.match(line.strip())
        if match:
            cases.append(
                {
                    "testIdentifier": match.group("identifier"),
                    "result": match.group("result"),
                    "durationSeconds": float(match.group("seconds")),
                }
            )
    return cases


def markdown(cases: list[dict[str, object]], title: str) -> str:
    if not cases:
        return f"### {title}\n\nNo XCTest case durations were found.\n"
    ordered = sorted(cases, key=lambda case: float(case["durationSeconds"]), reverse=True)
    lines = [f"### {title}", "", "| Test | Result | Duration |", "| --- | --- | ---: |"]
    for case in ordered:
        identifier = str(case["testIdentifier"]).replace("|", "\\|")
        lines.append(
            f"| `{identifier}` | {case['result']} | {float(case['durationSeconds']):.3f}s |"
        )
    total = sum(float(case["durationSeconds"]) for case in cases)
    lines.extend(["", f"Measured XCTest time: **{total:.3f}s**.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-log", type=Path, help="captured xcodebuild output")
    source.add_argument("--aggregate-dir", type=Path, help="directory of per-job duration JSON files")
    parser.add_argument("--json-output", type=Path, help="write parsed case durations as JSON")
    parser.add_argument("--summary", type=Path, help="append Markdown to this GitHub step summary")
    args = parser.parse_args()

    try:
        if args.input_log:
            cases = parse_log(args.input_log)
            if args.json_output:
                args.json_output.parent.mkdir(parents=True, exist_ok=True)
                args.json_output.write_text(
                    json.dumps(cases, indent=2) + "\n", encoding="utf-8"
                )
        else:
            files = sorted(args.aggregate_dir.glob("*.json"))
            cases = []
            for path in files:
                value = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                    raise ValueError(f"Expected an XCTest duration list in {path}")
                cases.extend(value)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Could not collect XCTest durations: {error}", file=sys.stderr)
        return 1

    title = "XCTest case durations" if args.input_log else "All XCTest case durations"
    report = markdown(cases, title)
    print(report)
    if args.summary:
        try:
            with args.summary.open("a", encoding="utf-8") as output:
                output.write(report)
        except OSError as error:
            print(f"Could not update GitHub step summary: {error}", file=sys.stderr)
            return 1
    return 0 if cases else 1


if __name__ == "__main__":
    raise SystemExit(main())
