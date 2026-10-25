#!/usr/bin/env python3
"""Summarize diagnostic TV sessions, without claiming matched performance."""
import datetime as dt
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
rows = []
for pattern in ('baseline-*.json', 'candidate-*.json'):
    for p in root.glob(pattern):
        row = json.loads(p.read_text())
        if 'started_utc' not in row:
            continue
        assert not row['reboot_detected'], p
        assert json.loads(row['mute'])['muteStatus'], p
        row['record'] = p.name
        rows.append(row)
rows.sort(key=lambda r:r['started_utc'])
result=[]
for i, row in enumerate(rows):
    family = 'baseline' if row['variant']=='baseline' else 'candidate'
    log = root / ('baseline.log' if family=='baseline' else 'candidate-controlled.log')
    start=dt.datetime.fromisoformat(row['started_utc'])
    later=[dt.datetime.fromisoformat(r['started_utc']) for r in rows[i+1:]
           if (r['variant']=='baseline') == (family=='baseline')]
    end=min(later) if later else dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    lines=[]
    for line in log.read_text().splitlines():
        try:stamp=dt.datetime.fromisoformat(line.split()[0])
        except (ValueError, IndexError):continue
        if start <= stamp < end:lines.append(line)
    windows=[{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',s)}
             for s in lines if 'Frame latency summary' in s]
    assert windows, row['record']
    result.append({'record':row['record'],'variant':row['variant'],'case':row['case'],
                   'host_frame_windows':windows,
                   'host_error_lines':[s for s in lines if ' ERROR ' in s or 'stopped unexpectedly' in s],
                   'hdr_changes':sum('Content switched to HDR' in s for s in lines),
                   'sdr_changes':sum('Content switched to SDR' in s for s in lines),
                   'passthrough_seen':any('passing the client buffer through' in s for s in lines),
                   'composite_not_opaque_seen':any('NotOpaque' in s for s in lines),
                   'backpressure_lines':[s for s in lines if 'Validation final backpressure' in s],
                   'resume_lines':[s for s in lines if 'resum' in s.lower()],
                   'relaunch_without_host_cancel':row.get('relaunch_without_host_cancel',False)})
print(json.dumps(result,indent=2))
