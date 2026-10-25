#!/usr/bin/env python3
"""Summarize completed matrix runs without pooling per-run percentiles."""
import argparse
import datetime as dt
import json
import re
import statistics
from pathlib import Path


def fields(line):
    return {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line)}


def parse(path):
    metadata = json.loads((path / "run.json").read_text())
    log = (path / "run.log").read_text()
    assert metadata["exit_code"] == 0 and not metadata["timed_out"], path
    assert metadata["production_before"] == metadata["production_after"], path
    assert not any(s["validation_layer_loaded"] for s in metadata["samples"]), path
    assert not re.search(r"VUID-|panicked at|ERROR .*pipeline", log), path
    session = re.search(r"Session \[(\d+) frames, ([\d.]+) fps, ([\d.]+) Mbps\]", log)
    assert session, path
    result = dict(name=path.name, frames=int(session[1]), fps=float(session[2]), mbps=float(session[3]))
    for stage in ("total", "submit", "enc_wait"):
        match = re.search(rf"{stage}:\s+avg=(\d+)us.*?p50=(\d+)us\s+p95=(\d+)us\s+p99=(\d+)us", log, re.S)
        assert match, (path, stage)
        result[stage] = dict(zip(("avg_us", "p50_us", "p95_us", "p99_us"), map(int, match.groups())))
    for key, marker in (("conversion_windows", "Validation conversion profile"), ("gpu_windows", "Validation GPU profile")):
        result[key] = [fields(line) for line in log.splitlines() if marker in line]
    result["backpressure"] = fields(next(line for line in log.splitlines() if "Validation final backpressure" in line))
    result["passthrough_events"] = log.count("passing the client buffer through")
    result["composite_not_opaque"] = "NotOpaque" in log
    gpu = [int(v) for s in metadata["samples"] for v in s["gpu_busy"].values() if v is not None]
    result["gpu_busy_percent_whole_run"] = {"median": statistics.median(gpu), "min": min(gpu), "max": max(gpu)} if gpu else None
    active = next(line.split()[0] for line in log.splitlines() if "Session active. Collecting stats" in line)
    warmup = float(metadata["command"][metadata["command"].index("--warmup") + 1])
    steady_start = (dt.datetime.fromisoformat(active) - dt.datetime.fromisoformat(metadata["started_utc"])).total_seconds() + warmup
    samples = [s for s in metadata["samples"] if s["elapsed_s"] >= steady_start and s["process_stat"]]
    if len(samples) >= 2:
        def process_ticks(sample):
            values = sample["process_stat"].rsplit(")", 1)[1].split()
            return int(values[11]) + int(values[12])
        # Linux USER_HZ is 100 on the measured Alpha host; 100% means one core.
        result["process_cpu_percent_steady"] = (process_ticks(samples[-1]) - process_ticks(samples[0])) / (samples[-1]["elapsed_s"] - samples[0]["elapsed_s"])
        first = list(map(int, samples[0]["cpu_stat"].splitlines()[0].split()[1:9]))
        last = list(map(int, samples[-1]["cpu_stat"].splitlines()[0].split()[1:9]))
        delta = [b-a for a, b in zip(first, last)]
        result["system_cpu_percent_steady"] = 100 * (sum(delta) - delta[3] - delta[4]) / sum(delta)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    args = parser.parse_args()
    runs = [parse(p.parent) for p in sorted(args.matrix.glob("*/run.json"))]
    print(json.dumps(runs, indent=2))


if __name__ == "__main__":
    main()
