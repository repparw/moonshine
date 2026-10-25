#!/usr/bin/env python3
"""Decode diagnostic captures and report format and consecutive identical frames."""

import argparse
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path)
    args = parser.parse_args()
    reports = []
    for path in args.captures:
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
            "stream=profile,width,height,pix_fmt,color_space,color_transfer,color_primaries",
            "-of", "json", str(path),
        ], capture_output=True, text=True, check=True)
        decoded = subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-xerror", "-threads", "2",
            "-i", str(path), "-map", "0:v", "-f", "framemd5", "-",
        ], capture_output=True, text=True)
        hashes = [line.rsplit(",", 1)[-1].strip() for line in decoded.stdout.splitlines()
                  if line and not line.startswith("#")]
        longest = current = 0
        previous = None
        for value in hashes:
            current = current + 1 if value == previous else 1
            longest = max(longest, current)
            previous = value
        reports.append({
            "capture": path.name, "decode_exit_code": decoded.returncode,
            "decode_errors": decoded.stderr, "frames": len(hashes),
            "unique_frames": len(set(hashes)), "longest_identical_run": longest,
            "streams": json.loads(probe.stdout)["streams"],
        })
    print(json.dumps(reports, indent=2))
    if any(r["decode_exit_code"] != 0 or not r["frames"] for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
