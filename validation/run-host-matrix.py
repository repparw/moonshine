#!/usr/bin/env python3
"""Alternate isolated host benchmarks. Never connect to a TV or change deployment."""

import argparse
import datetime as dt
import fcntl
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def production_identity():
    return subprocess.check_output([
        "systemctl", "show", "moonshine", "-p", "MainPID", "-p", "ExecStart", "-p", "DropInPaths",
    ], text=True)


def optional_read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def run_one(binary, workload, resolution, hdr, duration, warmup, output, diagnostic=False, dump=None):
    output.mkdir()
    command = [str(binary), "--resolution", resolution, "--fps", "60", "--codec", "hevc",
               "--bitrate", "150000000", "--duration", str(duration), "--warmup", str(warmup)]
    if hdr:
        command.append("--hdr")
    command.append(str(workload))
    env = os.environ.copy()
    env.pop("MOONSHINE_VALIDATION_DUMP", None)
    env.pop("MOONSHINE_VALIDATION_VULKAN", None)
    if diagnostic:
        env["MOONSHINE_VALIDATION_VULKAN"] = "1"
    if dump is not None:
        env["MOONSHINE_VALIDATION_DUMP"] = str(dump)
    env["MOONSHINE_LOG"] = "warn,moonshine=info,moonshine::session::stream::video::pipeline=debug,ferriscope::passthrough=debug,pixelforge=warn"
    before = production_identity()
    started_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    start = time.monotonic()
    samples = []
    timed_out = False
    with (output / "run.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env,
                                   start_new_session=True)
        try:
            while process.poll() is None:
                samples.append({
                    "elapsed_s": time.monotonic() - start,
                    "loadavg": optional_read("/proc/loadavg"),
                    "process_stat": optional_read(f"/proc/{process.pid}/stat"),
                    "validation_layer_loaded": "libVkLayer_khronos_validation" in (
                        optional_read(f"/proc/{process.pid}/maps") or ""),
                    "cpu_stat": optional_read("/proc/stat"),
                    "gpu_busy": {str(p): optional_read(p) for p in
                                 Path("/sys/class/drm").glob("card[0-9]*/device/gpu_busy_percent")},
                })
                if time.monotonic() - start > duration + 45:
                    timed_out = True
                    raise TimeoutError("benchmark did not stop")
                time.sleep(1)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            # Only the unit name inserted by prepare-isolated-bench.py is eligible for cleanup.
            subprocess.run(["systemctl", "--user", "stop",
                            f"moonshine-async-validation-{process.pid}.service"],
                           capture_output=True, timeout=15)
            metadata = {
                "command": command, "exit_code": process.returncode, "timed_out": timed_out,
                "diagnostic": diagnostic, "bitstream_dump": str(dump) if dump is not None else None,
                "started_utc": started_utc,
                "elapsed_s": time.monotonic() - start,
                "production_before": before, "production_after": production_identity(),
                "samples": samples,
            }
            journal = subprocess.run([
                "journalctl", "--user", "-u", f"moonshine-async-validation-{process.pid}.service",
                "--no-pager", "-o", "cat", "-n", "200",
            ], capture_output=True, text=True, timeout=15)
            (output / "application.log").write_text(journal.stdout)
            (output / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")
    if metadata["production_before"] != metadata["production_after"]:
        raise RuntimeError("production identity changed; discard run and investigate")
    if process.returncode != 0:
        raise RuntimeError(f"benchmark failed: {output}")
    if "Frame latency summary" not in (output / "run.log").read_text():
        raise RuntimeError(f"no encoded-frame summaries: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--hdr-workload", type=Path, required=True)
    parser.add_argument("--sdr-workload", type=Path, required=True)
    parser.add_argument("--composite-workload", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--duration", type=int, default=25)
    parser.add_argument("--warmup", type=int, default=5)
    args = parser.parse_args()
    if args.runs < 1 or args.warmup < 0 or args.duration < args.warmup + 10:
        parser.error("runs must be positive and duration must exceed warmup by at least ten seconds")
    names = ["baseline", "candidate", "hdr_workload", "sdr_workload"]
    if args.composite_workload is not None:
        names.append("composite_workload")
    for name in names:
        path = getattr(args, name).resolve(strict=True)
        if not os.access(path, os.X_OK):
            parser.error(f"not executable: {path}")
        setattr(args, name, path)
    for binary in (args.baseline, args.candidate):
        help_text = subprocess.check_output([str(binary), "--help"], text=True, timeout=15)
        if "Isolated Moonshine async validation benchmark" not in help_text:
            parser.error(f"refusing a binary without the isolation marker: {binary}")
    args.output.mkdir(parents=True)
    with Path("/home/repparw/Projects/moonshine-async-validation.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        profiles = [
            ("2560x1440", True, args.hdr_workload, ""),
            ("3840x2160", True, args.hdr_workload, ""),
            ("3840x2160", False, args.sdr_workload, ""),
        ]
        if args.composite_workload is not None:
            profiles.append(("3840x2160", True, args.composite_workload, "-composite"))
        for resolution, hdr, workload, suffix in profiles:
            for repetition in range(args.runs):
                for label, binary in [("baseline", args.baseline), ("candidate", args.candidate)]:
                    name = f"{resolution}-{'hdr' if hdr else 'sdr'}{suffix}-{repetition + 1}-{label}"
                    print(name, flush=True)
                    run_one(binary, workload, resolution, hdr, args.duration, args.warmup, args.output / name)


if __name__ == "__main__":
    main()
