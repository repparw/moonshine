#!/usr/bin/env python3
"""Add the same aggregate timing diagnostics to baseline and async runtime checkouts."""

import argparse
from pathlib import Path


HELPER = '''fn log_conversion_profile(samples: &[(u64, u64)]) {
	let mut slots: Vec<_> = samples.iter().map(|s| s.0).collect();
	let mut calls: Vec<_> = samples.iter().map(|s| s.1).collect();
	slots.sort_unstable();
	calls.sort_unstable();
	let percentile = |v: &[u64], p: f64| v[(v.len() as f64 * p) as usize];
	tracing::debug!(samples = samples.len(),
		input_slot_p50_us = percentile(&slots, 0.50),
		input_slot_p95_us = percentile(&slots, 0.95),
		input_slot_p99_us = percentile(&slots, 0.99),
		converter_call_p50_us = percentile(&calls, 0.50),
		converter_call_p95_us = percentile(&calls, 0.95),
		converter_call_p99_us = percentile(&calls, 0.99),
		"Validation conversion profile (us)");
}

'''

GPU_HELPER = '''
	let mut gpu: Vec<_> = samples.iter().filter_map(|s| s.gpu_us).collect();
	let mut wall: Vec<_> = samples.iter().filter_map(|s| s.gpu_wall_us).collect();
	gpu.sort_unstable();
	wall.sort_unstable();
	let percentile = |v: &[u64], p: f64| if v.is_empty() { 0 } else { v[(v.len() as f64 * p) as usize] };
	tracing::debug!(samples = gpu.len(),
		gpu_encode_p50_us = percentile(&gpu, 0.50),
		gpu_encode_p95_us = percentile(&gpu, 0.95),
		gpu_encode_p99_us = percentile(&gpu, 0.99),
		encode_wall_p50_us = percentile(&wall, 0.50),
		encode_wall_p95_us = percentile(&wall, 0.95),
		encode_wall_p99_us = percentile(&wall, 0.99),
		"Validation GPU profile (us; zero samples means unavailable)");
'''

START = '''let input_slot_started = std::time::Instant::now();
				let input_image = encoder.input_image();
				let input_slot_us = input_slot_started.elapsed().as_micros() as u64;
				let converter_call_started = std::time::Instant::now();
				'''

END = '''conversion_profile.push((input_slot_us, converter_call_started.elapsed().as_micros() as u64));
				if conversion_profile_started.elapsed() >= std::time::Duration::from_secs(5) {
					log_conversion_profile(&conversion_profile);
					conversion_profile.clear();
					conversion_profile_started = std::time::Instant::now();
				}

				'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    path = args.checkout / "src/session/stream/video/pipeline/mod.rs"
    source = path.read_text()

    def replace(before, after):
        nonlocal source
        if source.count(before) != 1:
            raise SystemExit(f"Expected exactly one occurrence: {before!r}")
        source = source.replace(before, after, 1)

    replace("pub(crate) struct VideoPipeline {}", HELPER + "pub(crate) struct VideoPipeline {}")
    replace("struct LatencySample {", "struct LatencySample {\n\tgpu_us: Option<u64>,\n\tgpu_wall_us: Option<u64>,")
    anchor = "let keyframes = samples.iter().filter(|s| s.is_key_frame).count();"
    replace(anchor, anchor + GPU_HELPER)
    anchor = "latency_samples.push(LatencySample {"
    replace(anchor, anchor + "\n\t\t\tgpu_us: packet.stats.as_ref().map(|s| s.gpu_time_ns / 1000),"
            "\n\t\t\tgpu_wall_us: packet.stats.as_ref().map(|s| s.wall_latency_ns / 1000),")
    anchor = "let mut last_drop_warn: Option<std::time::Instant> = None;"
    replace(anchor, anchor + "\n\t\tlet mut conversion_profile = Vec::with_capacity(512);"
            "\n\t\tlet mut conversion_profile_started = std::time::Instant::now();")
    if "let conversion = match converter.convert_async(" in source:
        before = "let conversion = match converter.convert_async(source_image, src_layout, encoder.input_image(), &[]) {"
        replace(before, START + "let conversion = match converter.convert_async(source_image, src_layout, input_image, &[]) {")
        anchor = "// convert_async waited for the previous conversion before reusing its commands."
        replace(anchor, END + anchor)
    else:
        before = "if let Err(e) = converter.convert(source_image, src_layout, encoder.input_image()) {"
        replace(before, START + "if let Err(e) = converter.convert(source_image, src_layout, input_image) {")
        anchor = "// The DMA-BUF content has been read into the encoder's input"
        replace(anchor, END + anchor)
    path.write_text(source)


if __name__ == "__main__":
    main()
