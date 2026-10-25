# Alpha async-conversion validation

These helpers run a private host-only benchmark. They do not connect to Moonlight,
operate a TV, install a service, or change the production deployment. Do not run
the stock `moonshine-bench` concurrently with production: it shares a session
unit, PulseAudio directory, and video port. The checked-in runtime patches isolate
all three and add a CLI marker which the runner requires.

## Build the exact experiment

The tested behavior is commit `b1459f2`; baseline behavior is upstream
`559699ee2af57ec003d98b832fff185530d50b0f`. Tooling commit `d3205ed` applies to
both. Cargo.lock resolves pixelforge 0.10.0, commit
`4f3ff5e963a733e4036fd0bcb62df33daeb4ca94`.

Create disposable worktrees at those revisions. Apply `candidate-runtime.patch`
to the candidate and `baseline-runtime.patch` to the baseline after cherry-picking
the tooling commit. Do not push those runtime edits. Alternatively the three
`prepare-isolated-bench.py`, `add-profile.py`, `add-backpressure.py` scripts
produce the same edits before rustfmt.

Run in each checkout:

```sh
nix develop --command cargo fmt --all -- --check
nix develop --command cargo check --workspace --all-targets --locked
nix develop --command cargo test --workspace --locked
nix develop --command cargo clippy --workspace --all-targets --locked -- -D warnings
CARGO_TARGET_DIR="$PWD/target-private" nix develop --command \
  cargo build --release --locked -p moonshine-tools --bin moonshine-bench
```

Use separate Cargo target directories. A shared target directory reused across
different worktree paths initially reused the wrong executable; that preliminary
artifact was discarded before comparisons. All measured executables were rebuilt
after `cargo clean --release -p moonshine -p moonshine-tools`, copied to distinct
paths, and checked for candidate-only source markers.

On Alpha the original flake's Nixpkgs fetch stalled. The tested shell used
`--override-input nixpkgs path:/nix/store/87lfqfz7mc5dm4w75qikxhd6lkr9jisr-source --no-write-lock-file`,
the fleet's Nixpkgs revision `02c087f3fe673c9e317f206a627cb6b910336dbe`.
Neither lockfile was edited. This validates that supported shell with an explicit
input override, not a successful build of the original pinned input.

## Workload and runs

`generate-workload.sh NEW_DIRECTORY` makes a two-second 4K60 moving test pattern,
with identical 10-bit pixel data tagged as PQ/BT.2020 or BT.709. It is a synthetic
exercise of the capture/conversion/encoding path, not a calibrated HDR reference
or representative game. Use ffprobe to verify color tags before running.

The measured source was mpv 0.41.0 with:

```sh
mpv --no-config --audio=no --hwdec=no --vo=gpu-next --gpu-api=vulkan \
  --gpu-context=waylandvk --fullscreen --target-colorspace-hint=yes \
  --target-colorspace-hint-mode=source --video-sync=display-resample \
  --interpolation=no --loop-file=inf --osd-level=0 --cursor-autohide=always CLIP
```

Create executable HDR and SDR wrappers with absolute clip and executable paths.
For forced HDR compositing, use the HDR wrapper with `--background=none`;
confirm `NotOpaque` rejection in logs. Ordinary HDR confirmed ferriscope
`passing the client buffer through`. SDR used compositing (`UnsupportedFormat`).
These are the nested capture compositor's paths, not physical-monitor scanout.

Expose the host's production Xwayland in PATH and Mesa Vulkan ICD/loader in the
environment. The measured runtime used:

```sh
export PATH=/nix/store/qy7wiry6wl6hxmcjqkk7fzl3fp9h4dqq-xwayland-24.1.14/bin:$PATH
export LD_LIBRARY_PATH=/run/opengl-driver/lib:/nix/store/aj8kinwyd2whhs3xg4b2p6j6dd9w6x56-vulkan-loader-1.4.363.0/lib:/nix/store/ww5pckflswny9whz04k06xh233jbg5kl-libglvnd-1.7.0/lib
export VK_DRIVER_FILES=/run/opengl-driver/share/vulkan/icd.d/radeon_icd.x86_64.json
python3 validation/run-host-matrix.py --baseline /absolute/baseline-profile \
  --candidate /absolute/candidate-profile --hdr-workload /absolute/hdr.sh \
  --sdr-workload /absolute/sdr.sh --composite-workload /absolute/composite.sh \
  --output /absolute/new-results --runs 5 --duration 20 --warmup 5
python3 validation/summarize.py /absolute/new-results > results.json
python3 validation/render-results.py results.json > results.md
```

The runner alternates A/B, checks production identity before/after, samples CPU
and GPU occupancy once per second, saves logs, and cleans only its own branded
application unit. Duration includes warmup; each result measures about 15 seconds.
150 Mbps, 60 FPS, HEVC and HDR/SDR are identical across sides. Validation layers
and bitstream dumping are disabled in performance runs.

## Diagnostic runs

`run_one` in the runner accepts `diagnostic=True` and a new `dump=Path(...)`.
Set VK_LAYER_PATH to the installed Khronos validation-layer manifest directory.
Confirm `validation_layer_loaded` in run.json, then run `check-bitstreams.py`
on captured streams outside performance runs. It checks decode errors, format,
frame hashes and consecutive repeats; it cannot detect every visual defect.
Changing the dump path to a nonexistent directory intentionally panics the
consumer, exercising cancellation and shutdown, not Vulkan submission failure.

## Timing interpretation and rollback

`total` is capture timestamp to packet-channel enqueue, including packetization
and queue send. It is not exact capture-to-bitstream-ready or client display
latency. PR #230's capture timestamp semantics are identical on both tested
revisions; comparisons with deployed v0.16.1 telemetry are not equivalent.
`enc_wait` includes asynchronous conversion, GPU queueing, readback and consumer
scheduling. GPU command timestamps bracket encode commands and may include
pipeline waits; they are not an isolated hardware-encoder service time.
Converter-call timings include synchronization on the previous reusable command
buffer. Five-second diagnostic-window percentiles are not pooled percentiles.
`source_max` counts producer-retained captured frames, not total GBM occupancy.

No deployment rollback is needed: production was unchanged. Stop only the exact
`moonshine-async-validation-PID.service` owned by a run if interrupted. Stop its
runner process group if necessary. Delete disposable worktrees/build outputs
after preserving evidence. To abandon source changes, close the draft PR or
revert its commits; do not activate the experiment on production.
