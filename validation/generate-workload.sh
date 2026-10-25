#!/usr/bin/env bash
set -euo pipefail

output=${1:?Provide a new output directory}
mkdir "$output"
ffmpeg -nostdin -hide_banner -loglevel error \
  -f lavfi -i testsrc2=size=3840x2160:rate=60 -frames:v 120 \
  -vf format=yuv420p10le -c:v libx265 -preset ultrafast \
  -x265-params pools=4:frame-threads=2 "$output/pattern-untagged.mkv" \
  > "$output/generate.log" 2>&1
ffmpeg -nostdin -hide_banner -loglevel error -i "$output/pattern-untagged.mkv" \
  -map 0:v -c copy \
  -bsf:v hevc_metadata=colour_primaries=9:transfer_characteristics=16:matrix_coefficients=9 \
  -color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc \
  "$output/pattern-pq.mkv"
ffmpeg -nostdin -hide_banner -loglevel error -i "$output/pattern-untagged.mkv" \
  -map 0:v -c copy \
  -bsf:v hevc_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1 \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
  "$output/pattern-sdr.mkv"
sha256sum "$output"/pattern-*.mkv > "$output/SHA256SUMS"
