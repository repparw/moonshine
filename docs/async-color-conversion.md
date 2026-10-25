# Asynchronous color conversion

The encoding thread submits conversion with `convert_async` and passes its
ALL_COMMANDS timeline point to `encode_after`. A converter owns the captured
frame and imported-image reference until conversion completes. Its previous
image import remains alive until the converter destroys that image view. Normal
converter teardown waits for conversion before the retained sources are dropped.
Submission errors end the session rather than reuse uncertain GPU state.

This removes a CPU wait for the current conversion. It does not make the GPU
conversion faster, add converter command buffers, or increase buffering. The
encoder still protects its two rotating input slots; the converter still waits
for its previous submission before reusing its command buffer. In-flight guards
release admission slots on rejected delivery, queued cancellation and consumer
early exits. Compositor frames stay on the encoding thread.

## Timing compatibility

`FrameStats.convert` is retained for source compatibility. Its preferred label
and accessor are now `convert_submit` / `convert_submit()`: CPU conversion
preparation and submission, including input-slot and previous-conversion waits,
not completion of the current conversion. `encode_wait` includes any remaining
conversion dependency, GPU queueing, encode/readback and consumer scheduling.
`total` ends at packet-channel enqueue, not network transmission or display.

Structured logs expose `convert_submit_us` and `convert_submit_p50/p95/p99_us`.
Legacy `convert_us` and `convert_p50/p95/p99_us` keys remain aliases with the same
values; `conversion_timing="submission"` identifies their changed semantics.
Benchmark text uses `convert_submit`. Existing dashboards must update stage
labels and treat synchronous and asynchronous conversion samples as different
measurements. GPU completion is not measured by these CPU timers. No synchronous
wait or GPU timestamp query was added to preserve the old metric.

## Measurements and reproduction

Five alternating release-build A/B pairs per profile used 60 FPS HEVC, 150 Mbps,
20 seconds including five seconds warmup, on an RX 6700 XT. For 4K HDR:

| Measurement | Synchronous | Async |
|---|---:|---:|
| CPU conversion-call window p50 | 5.36 ms | 0.10 ms |
| Encode-future-wait p50 | 11.52 ms | 16.55 ms |
| Capture-to-packet-enqueue p50 | 17.22 ms | 17.06 ms |
| Throughput | about 60 FPS | about 60 FPS |

Full-path p50 ranges overlap: 17.09–17.32 ms baseline, 16.48–17.21 ms async.
The conversion number is the median of per-run median five-second-window p50s;
the other latency numbers are medians of five per-run p50s, not pooled
percentiles. The workload hit its 60 FPS pacing cap on both versions. These data
demonstrate less CPU blocking, largely shifted into encode-future waiting, not
improved GPU throughput, end-to-end latency or resolution of the reported 4K issue.

Build each revision separately in release mode. On a test host with no production
Moonshine instance, use `moonshine-bench --resolution 3840x2160 --fps 60 --codec
hevc --bitrate 150000000 --hdr --duration 20 --warmup 5 WORKLOAD`, alternating
baseline/candidate five times. Keep workload, drivers and client settings fixed;
disable validation layers and bitstream dumps for performance runs. The stock
benchmark shares session resources with a running service, so shared-host tests
require the isolation edits recorded with the evidence. Do not share a Cargo
target directory across worktrees without forcing the Moonshine packages to
rebuild; verify distinct executable hashes.

Full host/TV evidence and reproduction helpers are preserved in the fork's
[`validation/async-color-conversion-alpha` branch](https://github.com/repparw/moonshine/tree/validation/async-color-conversion-alpha).
TV tests are short sequential diagnostics, not matched performance experiments.
The pre-existing idle-IDR rotating-slot issue is separate from this change.
Exceptional fence-wait failure handling in pinned pixelforge is not established
by successful normal-path validation; see the review audit on the evidence branch.
