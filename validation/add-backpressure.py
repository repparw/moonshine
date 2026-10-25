#!/usr/bin/env python3
"""Add exact admission-drop counts and producer retention gauges to disposable builds."""

import argparse
from pathlib import Path


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

    anchor = "let mut last_drop_warn: Option<std::time::Instant> = None;"
    replace(anchor, anchor + "\n\t\tlet mut admission_drops = 0u64;"
            "\n\t\tlet mut in_flight_max = 0usize;\n\t\tlet mut source_max = 0usize;"
            "\n\t\tlet mut backpressure_started = std::time::Instant::now();")
    owned = ("color_converters.values().filter(|c| c.source.as_ref().is_some_and(|s| s.frame.is_some())).count()"
             if "struct AsyncColorConverter" in source else "0usize")
    anchor = "while !stop_session_manager.is_shutdown_triggered() {"
    replace(anchor, anchor + f'''
			in_flight_max = in_flight_max.max(in_flight.load(Ordering::Relaxed));
			source_max = source_max.max({owned});
			if backpressure_started.elapsed() >= std::time::Duration::from_secs(5) {{
				tracing::debug!(admission_drops, in_flight_max, source_max,
					"Validation backpressure (cumulative drops; producer sources are not total pool occupancy)");
				backpressure_started = std::time::Instant::now();
			}}
''')
    anchor = "if in_flight.load(Ordering::Relaxed) >= MAX_FRAMES_IN_FLIGHT {"
    replace(anchor, anchor + "\n\t\t\t\t\tadmission_drops += 1;")
    anchor = "// Drain in-flight encodes (barrier so every packet reaches the channel),"
    replace(anchor, 'tracing::debug!(admission_drops, in_flight_max, source_max, "Validation final backpressure");\n\n\t\t' + anchor)
    path.write_text(source)


if __name__ == "__main__":
    main()
