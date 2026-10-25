# Matched host results

Five alternating A/B pairs per profile, 20 seconds including 5 seconds warmup.
Cells are median [minimum–maximum] across five per-run results. Percentiles
are not pooled. Release builds; Vulkan validation/dumping disabled.

| Profile | Variant | FPS | Total p50 ms | Total p95 ms | Total p99 ms |
|---|---|---|---|---|---|
| 2560x1440-hdr | baseline | 60.00 [60.00–60.10] | 8.73 [8.70–8.81] | 9.83 [9.23–10.27] | 12.54 [12.36–12.55] |
| 2560x1440-hdr | candidate | 60.10 [60.00–60.10] | 8.56 [8.55–8.70] | 9.76 [9.29–9.90] | 12.30 [11.94–13.25] |
| 3840x2160-hdr | baseline | 60.00 [59.80–60.00] | 17.22 [17.09–17.32] | 18.04 [17.69–27.17] | 21.29 [20.47–35.82] |
| 3840x2160-hdr | candidate | 60.00 [59.70–60.10] | 17.06 [16.48–17.21] | 17.64 [16.90–24.06] | 19.01 [17.15–35.18] |
| 3840x2160-hdr-composite | baseline | 60.00 [60.00–60.10] | 17.99 [17.51–18.07] | 18.80 [18.48–19.09] | 21.41 [19.82–22.39] |
| 3840x2160-hdr-composite | candidate | 60.00 [60.00–60.00] | 17.80 [17.05–17.89] | 18.58 [17.83–21.03] | 22.31 [20.92–23.54] |
| 3840x2160-sdr | baseline | 60.00 [60.00–60.10] | 18.46 [17.93–18.62] | 19.28 [19.04–23.94] | 22.33 [21.17–32.27] |
| 3840x2160-sdr | candidate | 60.00 [60.00–60.00] | 18.45 [18.15–18.57] | 19.14 [18.84–26.49] | 21.94 [21.74–30.86] |

Total is capture-to-packet-channel enqueue, not capture-to-display.

| Profile | Variant | Process CPU % of one core | System CPU % | GPU busy % | Admission drops | In-flight maximum | Retained source maximum |
|---|---|---|---|---|---|---|---|
| 2560x1440-hdr | baseline | 27.17 [27.02–27.67] | 15.22 [14.67–18.43] | 30.00 [27.00–30.00] | 0 | 2 | 0 |
| 2560x1440-hdr | candidate | 27.03 [26.96–28.82] | 16.17 [15.04–33.06] | 30.00 [24.00–35.00] | 0 | 2 | 1 |
| 3840x2160-hdr | baseline | 28.24 [27.60–29.81] | 17.33 [15.87–29.61] | 28.00 [20.00–32.00] | 0 | 3 | 0 |
| 3840x2160-hdr | candidate | 27.17 [23.04–28.38] | 18.00 [14.88–23.85] | 27.00 [26.00–29.00] | 0 | 3 | 1 |
| 3840x2160-hdr-composite | baseline | 30.88 [26.82–31.31] | 16.02 [15.05–18.16] | 29.00 [27.00–33.00] | 0 | 2 | 0 |
| 3840x2160-hdr-composite | candidate | 31.38 [26.89–31.88] | 18.41 [14.94–24.23] | 28.00 [27.00–33.00] | 0 | 3 | 1 |
| 3840x2160-sdr | baseline | 31.03 [30.67–33.09] | 17.75 [15.34–30.76] | 29.00 [27.00–31.00] | 0 | 3 | 0 |
| 3840x2160-sdr | candidate | 31.66 [31.38–32.45] | 16.37 [15.75–25.44] | 34.00 [29.00–35.00] | 0 | 3 | 1 |

CPU intervals exclude warmup; GPU busy samples span startup through teardown.
GPU busy is the exposed DRM counter, not isolated video-engine utilization.
Source retention is a producer gauge, not total compositor pool occupancy.

| Profile | Variant | Converter-call window p50 ms | GPU encode-command window p50 ms | Encode-future wait p50 ms |
|---|---|---|---|---|
| 2560x1440-hdr | baseline | 1.67 [1.66–1.67] | 4.83 [4.70–4.84] | 6.82 [6.70–6.85] |
| 2560x1440-hdr | candidate | 0.11 [0.10–0.12] | 4.82 [4.65–4.83] | 8.12 [8.11–8.18] |
| 3840x2160-hdr | baseline | 5.36 [5.16–5.39] | 9.47 [9.47–9.47] | 11.52 [11.49–11.58] |
| 3840x2160-hdr | candidate | 0.10 [0.10–0.12] | 9.47 [9.47–9.48] | 16.55 [16.08–16.66] |
| 3840x2160-hdr-composite | baseline | 4.93 [4.90–4.96] | 9.46 [9.46–9.47] | 11.64 [11.04–11.65] |
| 3840x2160-hdr-composite | candidate | 0.12 [0.11–0.12] | 9.46 [9.46–9.46] | 16.20 [15.52–16.29] |
| 3840x2160-sdr | baseline | 5.60 [5.37–5.63] | 9.51 [9.50–9.52] | 11.93 [11.17–12.04] |
| 3840x2160-sdr | candidate | 0.12 [0.12–0.12] | 9.49 [9.49–9.54] | 17.22 [16.99–17.34] |

Window metrics include warmup and are descriptive, not a pooled frame distribution.
The GPU encode-command interval may include pipeline waits. Async encode-future
wait includes conversion, queueing, readback and scheduling. Per-run p50/p95/p99
for all sampled stages remain in matrix.json; raw logs are in matrix-logs.tar.gz.
