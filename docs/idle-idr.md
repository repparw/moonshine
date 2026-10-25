# Idle-frame IDR: stale rotating input slot

Moonshine upstream `559699e` re-encodes `encoder.input_image()` when no new capture
arrives and an IDR is pending. Pinned pixelforge 0.10.0 `4f3ff5e` documents that
method as the *next* slot. Each successful encode rotates to another slot.

The example initializes both slots, avoiding uninitialized VRAM: black A, white
B, then requests an IDR with no new upload and executes the exact fallback call.
An idle re-encode should remain white. On Alpha/RADV it instead decodes as black.
FFmpeg-decoded mean Y values were 15.99875, 235.0, 15.99875; the intended sequence
is approximately 16, 235, 235. The third packet is an IDR. This is independent of
the async conversion patch; the example calls pixelforge directly.

With Vulkan Video and Moonshine's build dependencies available:

```sh
cargo run --release --locked --example idle_idr_repro -- idle-idr.hevc
ffmpeg -v error -i idle-idr.hevc -pix_fmt yuv420p -f rawvideo idle-idr.yuv
```

Decode three 320×240 YUV420 frames and compare their Y planes. Set the host Vulkan
loader/ICD environment as needed. The pre-existing Nix vendor key/hash defect must
be fixed separately before using this revision's Nix package/development shell.

No fix is included here and no PR was opened. The caller needs a supported way
to re-encode the last image without violating rotating-slot reuse/layout rules.
Simply remembering a raw image handle and passing it to `encode` is insufficient:
the external-image upload path assumes GENERAL layout, while an encoder slot may
be in VIDEO_ENCODE_SRC_KHR, and reuse must remain synchronized. A separate encoder
API or carefully synchronized replay path should be designed and tested on this
reproduction. Do not pin an extra compositor frame or add per-frame copies to
the async PR merely to hide the existing bug.
