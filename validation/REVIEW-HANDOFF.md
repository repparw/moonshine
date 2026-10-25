# Review handoff: async conversion before undrafting

Review https://github.com/repparw/moonshine/pull/1 on
`experiment/async-color-conversion`. Keep it draft; do not merge, deploy, or mark
ready. The user accepts proceeding with source review even if this change does
not improve the original critical path. Return findings with file/line evidence,
severity, a concrete failure sequence, and an explicit undraft recommendation.

## What to review

Base: upstream `559699ee2af57ec003d98b832fff185530d50b0f`.
Original prototype: `88a7727`, `f44faf4`.
Fixes: `d3205ed` (Nix shell/vendor key), `b1459f2` (behavior).
The later validation commit contains scripts, local-only instrumentation patches,
reports and evidence, not further runtime behavior changes. Start with the full
PR diff, then `b1459f2` in `src/session/stream/video/pipeline/mod.rs`.

Check the **exact locked** pixelforge 0.10.0 revision
`4f3ff5e963a733e4036fd0bcb62df33daeb4ca94` and ferriscope
`a5b1205d7f7c1177a73b3b0896a97b17917c90a5` rather than current library main.

Challenge these claims independently:

1. The source Frame remains on the encoder thread and is retained with its
   imported-image Arc until its conversion timeline value completes. Imports
   remain alive until the old view is destroyed. Verify cache eviction and
   pointer/FD reuse cannot invalidate an in-flight source.
2. Field-drop order waits through ColorConverter teardown before dropping
   retained sources. Check command-recording failure, failed queue submission,
   failed completion query, device loss and teardown wait errors. Pixelforge
   ignores a Drop wait error; do not mistake normal validation success for proof
   of those exceptional paths.
3. The reusable converter command/output buffers wait before reuse, and the
   two encoder input slots cannot be overwritten while a prior encode uses them.
   Confirm semaphore stage masks, ownership barriers and semaphore retirement.
4. Encode-future cancellation or packet-consumer failure cannot free DMA-BUFs
   early. InFlightGuard must decrement exactly once after rejected delivery,
   queue cancellation, readback failure and every consumer early exit.
5. `has_encoded`, admission dropping, IDR re-encode, source-format changes,
   encoder-description updates and early-return destruction order remain valid.
   Review the duplicated device-loss/non-device-loss return in the normal encode
   error arm; it is redundant but currently terminates safely in both cases.
6. Releasing completed sources only on the next producer iteration does not
   cause starvation or unacceptable latency for a single-buffer source. Host
   matrix retention was one; total GBM occupancy was not measured.

## Evidence and interpretation

Read REPORT.md, results/matrix.md, README.md and the raw log archives. Formatting,
check, 139 tests and Clippy passed in the documented Nix shell with an explicit
Nixpkgs override. Release binaries compiled. Eight captured diagnostic streams
decoded without errors or consecutive duplicate frames. Vulkan-layer diagnostics
covered HDR/SDR, both capture paths, rapid color transitions and repeated window
replacement. An intentional consumer panic shut down the private pipeline.

Forty alternating host runs found about 60 FPS on baseline and candidate across
all profiles. 4K HDR capture-to-packet-enqueue p50 was 17.22 → 17.06 ms, with
overlapping ranges; the conversion call became shorter but encode-future waiting
grew. This does not establish a throughput improvement. Do not call enc_wait
hardware encoding time, subtract percentiles, or conflate packet enqueue with
bitstream ready or display. PR #230 timestamp semantics match across this A/B.

## TV continuation and remaining runtime work

Read [tv/REPORT.md](tv/REPORT.md) and its evidence first. Thirteen controlled TV
cases have now completed, including real active-session resume, with no uptime
reset or host ERROR/unexpected-stop lines. Settings were restored byte-for-byte,
all private servers stopped, TV mute verified. Earlier uncontrolled resets
overlapped another session's launcher work and are quarantined, not attributed
to this change. One configured 1440p HDR run showed plain H265 in the overlay;
a clean repeat confirmed Main10. Investigate that discrepancy before treating
the HDR flag alone as profile validation. Physical video-plane visual checks,
exceptional GPU failures and dedicated idle-frame IDR re-encode remain open.

Production Moonshine remains PID 3458425 with no drop-ins; no NixOS configuration
or service activation changed. During TV preparation Alpha had unrelated
Chromium/Qt builds and load average over 50 on 12 logical CPUs. Load fell during
tests but varied; do not present these short, sequential diagnostics as matched
performance evidence. The full Nix package/vendor build was not validated;
independently verify the changed ash output-hash key and hash before packaging.

The tested private real-server configuration used ports
1717 HTTP, 1718 HTTPS, 1719 RTSP, 1720 video, 1721 control, 1722 audio. They are
inside the **already deployed** eth0 1714–1764 TCP/UDP allow ranges. Do not edit
the firewall or replace production. Use an isolated XDG_DATA_HOME and copied
pairing state/new host UUID, read the existing certificate paths without exposing
private keys, and back up/restore TV hosts.ini and moonlight.ini before edits.
Preserve decoder settings;
vary only requested resolution/HDR and keep 150 Mbps. Verify mute before/after.

Still missing: physical playback inspection, actual GPU submission errors/device
loss, dedicated idle-frame runtime
IDR re-encode exercise, exact capture-to-bitstream-ready distributions, GPU
conversion timestamps, compositor tick/GBM pool occupancy and capture skips.
Do not waive a concrete ownership defect because performance is not the goal.

## Existing local artifacts

- Source/validation branch: `/tmp/moonshine-async-validation`.
- Disposable candidate: `/tmp/moonshine-async-runtime` at b1459f2 plus local patches.
- Disposable baseline: `/tmp/moonshine-async-baseline` at ae27c5a (upstream + tooling).
- Dependency clones: `/tmp/moonshine-4k60-investigation/{pixelforge,ferriscope,client}`.
- Raw captures, workload and distinct binaries:
  `/tmp/moonshine-4k60-investigation/async-validation/`.
- Full candidate executable: that directory's `bin/candidate-server`.
- Nix repo has earlier uncommitted research docs; do not commit them with this PR.

Use separate target directories when rebuilding baseline/candidate, or clean the
Moonshine packages between builds: shared Cargo target reuse initially selected
the wrong executable. That artifact was discarded before matched measurements.
No benchmark, test TV session or temporary server remains running. Leave the TV
muted unless the user asks otherwise.
