#!/usr/bin/env python3
"""Render median/range of per-run summaries; never merge percentile estimates."""
import collections
import json
import statistics
import sys

runs = json.load(open(sys.argv[1]))
groups = collections.defaultdict(list)
for run in runs:
    profile, repetition, variant = run["name"].rsplit("-", 2)
    groups[profile, variant].append(run)
assert len(runs) == 40 and all(len(v) == 5 for v in groups.values())


def span(values, scale=1):
    values = [v / scale for v in values]
    return f"{statistics.median(values):.2f} [{min(values):.2f}–{max(values):.2f}]"


print("# Matched host results\n")
print("Five alternating A/B pairs per profile, 20 seconds including 5 seconds warmup.")
print("Cells are median [minimum–maximum] across five per-run results. Percentiles")
print("are not pooled. Release builds; Vulkan validation/dumping disabled.\n")
print("| Profile | Variant | FPS | Total p50 ms | Total p95 ms | Total p99 ms |")
print("|---|---|---|---|---|---|")
for (profile, variant), rs in sorted(groups.items()):
    vals = [span([r["fps"] for r in rs])]
    vals += [span([r["total"][p + "_us"] for r in rs], 1000) for p in ("p50", "p95", "p99")]
    print("| " + " | ".join([profile, variant, *vals]) + " |")
print("\nTotal is capture-to-packet-channel enqueue, not capture-to-display.\n")
print("| Profile | Variant | Process CPU % of one core | System CPU % | GPU busy % | Admission drops | In-flight maximum | Retained source maximum |")
print("|---|---|---|---|---|---|---|---|")
for (profile, variant), rs in sorted(groups.items()):
    vals = [span([r[key] for r in rs]) for key in ("process_cpu_percent_steady", "system_cpu_percent_steady")]
    vals += [span([r["gpu_busy_percent_whole_run"]["median"] for r in rs])]
    vals += [str(sum(r["backpressure"]["admission_drops"] for r in rs))]
    vals += [str(max(r["backpressure"][key] for r in rs)) for key in ("in_flight_max", "source_max")]
    print("| " + " | ".join([profile, variant, *vals]) + " |")
print("\nCPU intervals exclude warmup; GPU busy samples span startup through teardown.")
print("GPU busy is the exposed DRM counter, not isolated video-engine utilization.")
print("Source retention is a producer gauge, not total compositor pool occupancy.\n")
print("| Profile | Variant | Converter-call window p50 ms | GPU encode-command window p50 ms | Encode-future wait p50 ms |")
print("|---|---|---|---|---|")
for (profile, variant), rs in sorted(groups.items()):
    # Each run contributes one median window percentile, then report its span.
    converter = [statistics.median(w["converter_call_p50_us"] for w in r["conversion_windows"]) for r in rs]
    gpu = [statistics.median(w["gpu_encode_p50_us"] for w in r["gpu_windows"]) for r in rs]
    wait = [r["enc_wait"]["p50_us"] for r in rs]
    print("| " + " | ".join([profile, variant, span(converter, 1000), span(gpu, 1000), span(wait, 1000)]) + " |")
print("\nWindow metrics include warmup and are descriptive, not a pooled frame distribution.")
print("The GPU encode-command interval may include pipeline waits. Async encode-future")
print("wait includes conversion, queueing, readback and scheduling. Per-run p50/p95/p99")
print("for all sampled stages remain in matrix.json; raw logs are in matrix-logs.tar.gz.")
