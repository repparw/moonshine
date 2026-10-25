#!/usr/bin/env python3
"""Apply identical local-only isolation and diagnostic edits to a disposable checkout."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    edits = {
        "src/session/mod.rs": [
            ('unit_name: "moonshine-session.service".to_string(),',
             'unit_name: format!("moonshine-async-validation-{}.service", std::process::id()),'),
        ],
        "src/session/stream/audio/mod.rs": [
            ('.join("moonshine/pulse")',
             '.join(format!("moonshine-async-validation-{}/pulse", std::process::id()))'),
        ],
        "tools/src/bin/bench.rs": [
            ('about = "Benchmark Moonshine\'s encoding pipeline"',
             'about = "Isolated Moonshine async validation benchmark"'),
            ('VideoStreamConfig::default(),',
             'VideoStreamConfig { port: 57998, ..Default::default() },'),
            ('"127.0.0.1:47998"', '"127.0.0.1:57998"'),
            ('title: "bench".to_string(),',
             'title: "async-validation".to_string(),\n'
             '\t\tstdout: Some("journal".to_string()),\n'
             '\t\tstderr: Some("journal".to_string()),'),
        ],
        "src/session/stream/video/pipeline/mod.rs": [
            ('let context = VideoContextBuilder::new()\n',
             'let context = VideoContextBuilder::new()\n'
             '\t\t\t.enable_validation(std::env::var_os("MOONSHINE_VALIDATION_VULKAN").is_some())\n'),
            ('\t\tlet encoded_bytes = packet.data.len();',
             '\t\tif let Some(path) = std::env::var_os("MOONSHINE_VALIDATION_DUMP") {\n'
             '\t\t\tlet mut file = std::fs::OpenOptions::new().create(true).append(true).open(path)\n'
             '\t\t\t\t.expect("validation bitstream output");\n'
             '\t\t\tstd::io::Write::write_all(&mut file, &packet.data).expect("validation bitstream write");\n'
             '\t\t}\n\n\t\tlet encoded_bytes = packet.data.len();'),
        ],
    }
    prepared = {}
    for relative, replacements in edits.items():
        path = args.checkout / relative
        original = path.read_text()
        for before, after in replacements:
            if original.count(before) != 1:
                raise SystemExit(f"Expected exactly one occurrence in {path}: {before!r}")
            original = original.replace(before, after, 1)
        prepared[path] = original
    for path, content in prepared.items():
        path.write_text(content)
    print("Prepared disposable checkout; do not push these runtime isolation edits.")


if __name__ == "__main__":
    main()
