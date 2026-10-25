---
name: verify-moonshine-tv
description: "Run fork-local, opt-in real Moonlight/webOS TV integration checks for Moonshine, including guarded app launch, host/client evidence collection and cleanup. Use only for TV client and display validation."
---

# Verify Moonshine to a physical LG/webOS TV

Use only in the `repparw/moonshine` fork and only when the TV's operator has authorized control. This is deliberately separate from the upstream-portable `verify-moonshine` skill: a server-only `moonshine-bench` run cannot prove real-client decode, HDR output or display latency.

Read [the TV verification README](../../../tools/tv/README.md) and the source for the *installed* Moonlight/webOS version. Never assume its app ID or launch behavior from upstream's development head.

## Launch and doctor

From the repo root, run `python3 tools/tv/verify_tv.py plan` with the paired host UUID, installed Moonlight app ID, device alias and advertised host application ID. `plan` is offline and shows the command it would run.

Use `python3 tools/tv/verify_tv.py doctor --device <alias> --app-id <app-id>` to query running apps through `ares-launch`. If Moonlight is already running, do not interrupt it. If TV access is not authorized or any identifier is unknown, stop with a concrete blocker.

Only an explicit `start ... --confirm --out <empty-folder>` contacts the TV with a launch request. The helper refuses to start a second Moonlight when the first is listed as running. The CLI response is not proof of a started video stream.

## Drive

Pair host and TV once through the supported Moonlight UI; do not programmatically alter credentials. Create a controlled, identifiable Moonshine streaming application if the intended test workload does not already exist.

For each test, name the host SHA, TV's Moonlight version, codec, bitrate, 4K/1440p mode, HDR/SDR state, and actual render source. Start the client with the guarded helper, then observe the actual video stream and run the test for the intended duration. Never infer decode/display success from an app-launch exit code or a server-side frame count.

When diagnosing the 4K60 HDR shortfall, collect Moonshine per-frame latency and the Moonlight on-screen statistics for matching intervals. Compare baseline and candidate with interleaved runs and equivalent workload/settings. Name the resource that limits FPS before claiming a speedup.

## Evidence

Save `tools/tv` helper's `report.json` and `ares-launch.log`; collect the running-app listing via `collect`. Independently capture client streaming statistics and host logs, with timestamps and source commit.

A live HDR pass requires observing actual HDR content and client/TV HDR operation, not merely setting `--hdr` on the host. A real stream must show video decoding and sustained frame delivery; launch success alone is classified **unverified**.

## Cleanup

Stop the test from Moonlight's normal UI, only after confirming that the session still belongs to the test. Never use a broad `pkill`, close an unrelated TV app, modify persistent TV settings or power-cycle the TV as part of automated cleanup.

Keep the evidence under `target/tv-verification/` after the app stops. If the app remains in an unknown state, record this and ask for an operator to inspect it instead of forcing termination.

## Helper tests and maintenance

```sh
python3 -m unittest discover -s tools/tv -p 'test_*.py'
```

These exercise only dry-run construction and refusal to interrupt an active app. The skill and helper remain **provisional until a real LG C3 session validates parameterized launch**. If the installed Moonlight client differs from the source, update the helper and this skill only after proving the observed behavior.
