#!/usr/bin/env bash
while :; do
  timeout 2s /tmp/moonshine-4k60-investigation/async-validation/workload-hdr.sh
  timeout 2s /tmp/moonshine-4k60-investigation/async-validation/workload-sdr.sh
done
