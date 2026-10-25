# LG C3 diagnostic continuation — 2026-10-25

Thirteen controlled diagnostic cases completed: three upstream-baseline cases
and ten candidate cases, including a real active-session resume and a targeted
1440p repeat. Every case produced encoded-frame summaries, retained TV uptime,
and ended with the TV muted. No host ERROR or unexpected-session-stop lines
occurred in the controlled logs. This is additional runtime evidence for source
review, not sufficient reason to undraft automatically.

## Scope and results

Baseline: 1440p HDR, 4K HDR, 4K SDR. Candidate: HDR/SDR at both resolutions,
4K HDR compositing, rapid HDR/SDR changes, repeated window replacement, fresh
reconnection, active-session resume, and repeated 1440p HDR. Each case sampled
uptime every five seconds for roughly 30 seconds and captured two performance
overlays. The resume case closed/reopened Moonlight without cancelling the host
application. Logs confirmed RTSP resume, video-stream reset and forced IDR.

All controlled cases had zero pre-encode admission drops. In-flight maxima were
at most three. The candidate retained at most two captured sources during window
replacement, otherwise one. This is not total compositor GBM occupancy.
Forced compositing logged NotOpaque; ordinary HDR logged buffer passthrough.
The transition case logged 30 HDR and 29 SDR changes; window replacement logged
seven HDR and five SDR changes. Neither caused a reset or host error.

Selected final overlay snapshots, transcribed from the archived PNGs:

| Case | Format shown | Network FPS | Network drops | Host average ms | Decoder average ms |
|---|---|---:|---:|---:|---:|
| Baseline 1440p HDR | H265 10bit | 60.28 | 0% | 10.24 | 10.14 |
| Baseline 4K HDR | H265 10bit | 59.98 | 0% | 16.61 | 13.87 |
| Baseline 4K SDR | H265 | 56.10 | 0% | 21.45 | 13.61 |
| Candidate 4K HDR | H265 10bit | 56.81 | 0% | 16.74 | 13.04 |
| Candidate 4K SDR | H265 | 59.88 | 0% | 18.62 | 13.36 |
| Candidate 1440p HDR repeat | H265 10bit | 59.98 | 0% | 8.64 | 9.10 |

These are short client statistics windows, not run-wide percentiles or matched
A/B performance results. Baseline cases preceded candidate cases, host build load
varied, and screenshots/overlay activity perturb client scheduling. They do not
establish a speedup or regression. The earlier 40 alternating host runs remain
the matched performance experiment. PR #230 timing semantics match across these
upstream/candidate builds, not the older deployed baseline.

One initial candidate run configured for 1440p HDR displayed plain H265 rather
than H265 10bit, despite host HDR-state logs. It is not counted as confirmed
Main10 validation. A clean repeat confirmed H265 10bit. The intermittent
negotiation/label discrepancy remains a review question; its cause has not been
isolated or attributed to async conversion. Do not hide it by changing decoder
settings or assuming the HDR configuration flag proves the negotiated profile.

## Interference and remaining limits

Two earlier attempts lost the TV and observed uptime resets. The user then
confirmed another session had been working on the TV launcher. Those attempts
are quarantined under `uncontrolled/` in the archive; they are not evidence of
an async regression or successful validation. An uncontrolled timeout also logged
a Smithay syncobj-release error and a private-app stop timeout. Neither appeared
in controlled baseline/candidate runs; abrupt-timeout teardown remains worth
reviewing independently.

DISPLAY captures show Moonlight's UI but exclude the video plane. A separate
BLENDED attempt returned ERROR_INTERNAL. Thus these tests do not validate visible
corruption, flicker, HDR color accuracy or physical display frame delivery.
Earlier host bitstream decoding and Vulkan diagnostics remain separate evidence.
No device loss or actual encoder submission failure was injected, no no-new-frame
IDR re-encode was forced, and no long-duration stability test was performed.

## Isolation, reproduction and cleanup

Both servers were local release builds with the checked-in runtime isolation
patches. Production stayed PID 3458425, with no drop-ins or activation. Private
ports were 1717 HTTP, 1718 HTTPS, 1719 RTSP, 1720 video, 1721 control, 1722 audio,
inside existing firewall allow ranges; no firewall change was made. Private
XDG_DATA_HOME used copied pairing state with a new host UUID; keys stayed on
their original devices and were not copied into the evidence archive.

The installed TV client was 1.6.37, `ndl-webos5`, decoder selection unchanged.
Only requested dimensions, 60 FPS, 150 Mbps and HDR enablement varied. Existing
HEVC, AV1, packet size, decoder and audio preferences were preserved. The workload
and runtime environment are in the parent validation README. The TV helpers here
are Alpha-specific and require explicit session authorization and exclusive TV
ownership; never run them concurrently with another launcher/control agent.

`tv.py` backs up/restores the two INI files. `run-cases.py --label baseline
--only hdr1440,hdr4k,sdr4k` runs baseline diagnostics against an already running
private server; `--label candidate` runs the candidate cases. App IDs are derived
from the exact configured titles with appids.rs. ROOT, SSH alias, private host
UUID, private configuration and workload paths must be prepared as documented in
REVIEW-HANDOFF; helpers are not a production deployment mechanism.
The archived first candidate reconnect case was a fresh connection; the separate
`candidate-resume` record exercised the actual close/relaunch path. The current
helper includes that resume action for its reconnect case.

Both INI files were restored byte-for-byte to the restoration point taken after
launcher coordination. `results/restoration.json` records hashes and verified
muteStatus=true, volume setting 7 unchanged. All temporary servers/application
units were stopped. Production needs no rollback. Raw records, overlays and logs
are in `results/evidence.tar.gz`; parsed host windows are in `results/summary.json`.
