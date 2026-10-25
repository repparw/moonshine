#!/usr/bin/env bash
exec /nix/store/1wny0m2f29ikrps7vfdv3b6vx1lb551y-mpv-0.41.0/bin/mpv \
  --no-config --audio=no --hwdec=no --vo=gpu-next --gpu-api=vulkan --gpu-context=waylandvk \
  --fullscreen --target-colorspace-hint=yes --target-colorspace-hint-mode=source \
  --video-sync=display-resample --interpolation=no --loop-file=inf \
  --osd-level=0 --cursor-autohide=always \
  /tmp/moonshine-4k60-investigation/async-validation/pattern-sdr.mkv
