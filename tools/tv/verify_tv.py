#!/usr/bin/env python3
"""Fork-only Moonlight/webOS launcher; video quality still needs observation."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid


def launch_command(device, app_id, host_uuid, host_app_id):
    payload = json.dumps({"host_uuid": str(uuid.UUID(host_uuid)), "host_app_id": str(host_app_id)})
    return ["ares-launch", "--device", device, app_id, "--params", payload]


def get_running(device):
    return subprocess.run(["ares-launch", "--device", device, "--running"], capture_output=True, text=True, timeout=20)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "doctor", "start", "collect"))
    parser.add_argument("--device", required=True, help="existing webOS CLI device alias, not an IP address")
    parser.add_argument("--app-id", required=True, help="Moonlight's installed webOS app ID")
    parser.add_argument("--host-uuid", help="UUID of Moonshine host as known to Moonlight")
    parser.add_argument("--host-app-id", type=int, help="positive integer app ID advertised by Moonshine")
    parser.add_argument("--out", type=Path, help="run's evidence directory (required for start/collect)")
    parser.add_argument("--confirm", action="store_true", help="explicitly allow modifying the TV's running app")
    args = parser.parse_args(argv)

    if args.action in ("plan", "start"):
        if not args.host_uuid or args.host_app_id is None or args.host_app_id <= 0:
            parser.error("plan/start require --host-uuid and positive --host-app-id")
        try:
            command = launch_command(args.device, args.app_id, args.host_uuid, args.host_app_id)
        except ValueError as exc:
            parser.error(f"invalid host UUID: {exc}")
        if args.action == "plan":
            print(json.dumps({"mode": "DRY_RUN", "command": command, "warning": "This only requests Moonlight launch; it does not prove a video stream"}, indent=2))
            return 0

    if not shutil.which("ares-launch"):
        print("ares-launch missing; install/configure webOS TV CLI first", file=sys.stderr)
        return 2
    try:
        status = get_running(args.device)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Could not query TV state: {exc}", file=sys.stderr)
        return 2
    if status.returncode != 0:
        print(status.stdout + status.stderr, file=sys.stderr)
        return 2
    is_running = args.app_id in status.stdout
    if args.action == "doctor":
        print(json.dumps({"device": args.device, "app_id": args.app_id, "moonlight_running": is_running, "raw": status.stdout}, indent=2))
        return 0
    if args.action == "collect":
        if args.out is None:
            parser.error("collect requires --out")
        args.out.mkdir(parents=True, exist_ok=True)
        dest = args.out / "webos-running.txt"
        if dest.exists():
            print("Refusing to overwrite collected evidence", file=sys.stderr)
            return 2
        dest.write_text(status.stdout)
        print(json.dumps({"running": is_running, "evidence": str(dest), "stream_verified": False}, indent=2))
        return 0
    if not args.confirm or args.out is None:
        parser.error("start requires --confirm and --out (no implicit TV control)")
    if is_running:
        print("Moonlight is already running: refusing to interrupt an active client", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    if any(args.out.iterdir()):
        print("Refusing to reuse a nonempty evidence directory", file=sys.stderr)
        return 2
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"TV launch failed: {exc}", file=sys.stderr)
        return 2
    report = {
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "device": args.device,
        "app_id": args.app_id,
        "command": command,
        "launch_exit_code": result.returncode,
        "launched": result.returncode == 0,
        "video_stream_verified": False,
        "note": "Launch request only; manual or client telemetry required for decode/HDR/display verification",
    }
    (args.out / "ares-launch.log").write_text(result.stdout + result.stderr)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"report": str(args.out / "report.json"), "launch_exit_code": result.returncode, "stream_verified": False}, indent=2))
    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
