#!/usr/bin/env bash
while :; do
  timeout 2s /home/repparw/Projects/moonshine-investigation/async-validation/workload-hdr.sh
  timeout 2s /home/repparw/Projects/moonshine-investigation/async-validation/workload-sdr.sh
done
