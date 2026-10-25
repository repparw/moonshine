# Async GPU conversion on Alpha — 2026-10-25

Recommendation: retain as a draft requiring further work. Host correctness checks
passed after fixing ownership and accounting. The controlled host workload does
not reproduce the deployed 39–42 FPS 4K HDR limit, so it cannot establish that
async conversion fixes that limit. No extra converter slots or buffering are
justified by these results. Production was unchanged. The user subsequently
authorized TV testing: the LG C3 was muted and verified muted, but no TV streaming
session was launched before preparing the review handoff.

## Revisions and build

The original prototype was `f44faf4`. Fixes are `d3205ed` (development shell and
the Cargo.lock-matching ash vendor key) and `b1459f2` (source lifetime and
in-flight accounting). Baseline behavior is upstream main `559699e`, with the
same tooling fix. Both use pixelforge 0.10.0 `4f3ff5e`, ferriscope `a5b1205`.
The deployed production executable remains
`/nix/store/l7jyskwjgjn1yjshlc5ca0j53wiz571k-moonshine-pr227-reload-fix-0.16.1/bin/moonshine`,
PID 3458425, v0.16.1 with PR #227 and the reload patch, pixelforge 0.9.1.
This is not an A/B comparison against that deployed revision.

Alpha: RX 6700 XT, kernel 7.2.10, Mesa 26.2.4, 12 logical CPUs. The Nix shell
used the explicit fleet Nixpkgs override documented in README. Locked Cargo
dependencies were unchanged. `cargo fmt --all -- --check`, workspace/all-targets
`cargo check`, workspace tests, and workspace/all-targets Clippy with
`-D warnings` passed. Tests: 139 passed, zero failed, one ignored manual Bottles
integration test. Nix formatting passed. Release benchmark binaries built.
The candidate standalone server also built in release mode; it was not launched.

## Matched host performance

[Full per-run results and ranges](results/matrix.md), [parsed measurements](results/matrix.json)
and archived raw logs are checked in separately from the behavior change. Five
alternating A/B pairs covered each of four profiles, 40 successful runs total,
150 Mbps HEVC, 20 seconds including five seconds warmup. No validation layer or
bitstream dump was active in performance runs. Both variants had zero admission
drops. The candidate retained at most one source; in-flight maxima stayed at
three or fewer. CPU load varied across runs; paired ordering reduces but does
not eliminate background-load effects.

Median per-run capture-to-packet-channel-enqueue p50:

- 1440p HDR: 8.73 ms baseline, 8.56 ms candidate; about 60 FPS both.
- 4K HDR passthrough: 17.22 ms baseline, 17.06 ms candidate; about 60 FPS both.
- 4K SDR: 18.46 ms baseline, 18.45 ms candidate; about 60 FPS both.
- 4K HDR forced compositing: 17.99 ms baseline, 17.80 ms candidate; about 60 FPS both.

The 4K HDR p50 ranges overlap (17.09–17.32 ms baseline, 16.48–17.21 ms candidate).
Tail latency varies and forced-compositing p99 is slightly higher in the
candidate's median result. There is no demonstrated throughput improvement or
consistent tail-latency win, and no observed 1440p throughput regression.

For 4K HDR, the median-of-window conversion-call p50 falls from about 5.36 ms to
0.10 ms while the encode-future-wait p50 rises from 11.52 ms to 16.55 ms. The GPU
encode-command window p50 remains about 9.47 ms. This demonstrates a moved CPU
synchronization point, not removal of five milliseconds from the critical path.
The workload is capped at 60 FPS and neither side reproduces the deployed
39–42 FPS condition; that pacing cap prevents a maximum-throughput test.

## Ownership and synchronization

The prototype put a raw captured Frame into the Tokio consumer and accumulated
failed sources in a vector. The fix owns captured sources on the encoder thread
with their converter. It retains both Frame and imported-image Arc until the
conversion timeline point completes, and keeps the import alive until the
converter destroys its previous image view. It polls completion once per producer
iteration, so a completed source can remain held until the next iteration.

Rust field order drops ColorConverter before its retained sources. In the exact
pixelforge dependency, converter teardown waits for its in-flight conversion
fence, destroys its source view and retires its timeline semaphore into
VideoContext. The next convert_async also waits before reusing its command
buffer/output buffer. An encode waits on the conversion's ALL_COMMANDS timeline
signal. Thus a successful encode completion implies conversion completion, but
source safety does not rely on the consumer awaiting the encode future.

Failed conversion retains the incoming Frame/import as well as any previous
source and terminates the session. Failed encoder submission and failed IDR
re-encode terminate instead of continuing with uncertain state. `has_encoded`
is set after successful submission. An InFlightGuard increments before delivery
and decrements on every drop path, including failed delivery and cancellation;
two new unit tests exercise rejected delivery and queued-message cancellation.

The encoder already has two input slots and waits before reusing a busy slot.
The converter still has one reusable command buffer; this patch does not add
conversion parallelism. Captured source lifetime ends after conversion, rather
than after potentially delayed packet consumption. No Frame crosses into the
Tokio consumer with this fix.

This assessment relies on pixelforge's current fence/timeline contract, not a
formal proof. Device loss and actual Vulkan submission failures were not induced.
The converter ignores a teardown wait error internally; exceptional driver/device
failure remains a dependency-level risk requiring separate validation.

## Correctness diagnostics

Private application unit, audio directory and video port prevented interference
with production. Validation-layer runs and bitstream dumps were separate from
performance runs. Valid runs covered SDR/HDR at 1440p and 4K, nested-compositor
passthrough and forced HDR compositing, repeated SDR/HDR transitions, repeated
window replacement, and repeated independent session startup/shutdown.

No VUIDs or Vulkan validation errors appeared in valid diagnostics. FFmpeg
decoded all eight retained captures without errors: 648, 675, 675, 678, 1025,
756, 652 and 676 frames respectively. Consecutive identical-frame runs never
exceeded one. HDR captures were Main10, 10-bit, BT.2020/PQ; SDR output was Main,
8-bit BT.709. Mixed-content sessions changed descriptions as expected.
These checks do not establish visual color accuracy or detect every stale-buffer
or lifetime defect.

An intentionally invalid dump path panicked the packet consumer; the pipeline
reported the failed task, stopped and released its private application unit.
Production identity remained unchanged. This tests consumer failure/cancellation,
not encoder submission failure. One early workload used an unsupported mpv alpha
option and failed before capture; teardown logged EGL_BAD_DISPLAY. It is excluded
from correctness/performance successes. A first SDR launch without Xwayland in
PATH also failed before encoding and was repeated with the correct environment.

## Measurement limits and next work

The host-only receiver is not the LG C3. TV decode/drop statistics, display
latency, disconnect/reconnect via Moonlight, visual HDR transitions, and real
network queue age were not measured. Exact capture-to-bitstream-ready
percentiles, isolated GPU conversion timestamps, actual total GBM occupancy,
compositor render ticks and capture-pool skip counts are still missing. The
reported total is capture-to-packet-channel enqueue; enc_wait is not hardware
encoding time. PR #230 timestamp semantics are identical across A/B, unlike the
older deployed baseline.

Ranked next steps:

1. Reproduce the original limiting workload against deployed and current upstream
   in an authorized TV run. Benefit unknown; this is necessary to identify the
   actual 4K limiter. Preserve the exact workload and capture timestamp semantics.
2. Keep the bounded source-lifetime/accounting fix if async conversion proceeds.
   Its demonstrated benefit is cancellation safety; performance benefit must be
   judged from full-path results, not the shorter conversion call.
3. Instrument exact GPU conversion completion and full capture-to-ready latency
   in separate profiling runs. Benefit unknown; this distinguishes moved CPU
   waits from genuine queue overlap.
4. Consider multiple converter command buffers only if those profiles show a
   throughput-limiting reusable-buffer wait. No measured benefit justifies that
   complexity here. Do not enlarge buffering speculatively.

Independent source review can proceed on the draft even without a throughput
win. No deployment PR is warranted. Do not undraft automatically: assess the
ownership contract and outstanding runtime gates first. Reproduction and rollback
are in README; production needs no rollback because it was never changed.
