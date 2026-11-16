#!/usr/bin/env bash
set -euo pipefail

runtime="com.apple.CoreSimulator.SimRuntime.iOS-26-5"
device_name="iPhone 17"
devices_json="$(xcrun simctl list devices available --json)"
device_record="$(python3 -c '
import json
import sys

data = json.load(sys.stdin)
matches = [
    (device["udid"], device["state"])
    for runtime, devices in data.get("devices", {}).items()
    if runtime == sys.argv[1]
    for device in devices
    if device.get("name") == sys.argv[2]
]
if len(matches) != 1:
    available = sorted(data.get("devices", {}).keys())
    print(f"Expected one {sys.argv[2]} on {sys.argv[1]}; found {len(matches)}. Runtimes: {available}", file=sys.stderr)
    raise SystemExit(1)
print(matches[0][0] + "\t" + matches[0][1])
' "$runtime" "$device_name" <<< "$devices_json")"

simulator_udid="${device_record%%$'\t'*}"
simulator_state="${device_record#*$'\t'}"
if [[ "$simulator_state" != "Booted" ]]; then
  xcrun simctl boot "$simulator_udid"
fi
xcrun simctl bootstatus "$simulator_udid" -b
printf 'SIMULATOR_UDID=%s\n' "$simulator_udid" >> "$GITHUB_ENV"
echo "Prepared $device_name on iOS 26.5 ($simulator_udid)."
