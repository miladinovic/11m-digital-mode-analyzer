#!/usr/bin/env python3
"""Fetch PSK Reporter reception reports and publish a compact 24h JSON snapshot."""
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

API = 'https://retrieve.pskreporter.info/query'
OUT = Path(__file__).parent / 'data' / 'reports.json'
MIN_HZ, MAX_HZ = 26_000_000, 27_999_999
WINDOW = 86400
LIMIT = 100000

def main():
    now = int(datetime.now(timezone.utc).timestamp())
    params = urllib.parse.urlencode({'flowStartSeconds': -WINDOW, 'frange': f'{MIN_HZ}-{MAX_HZ}', 'rptlimit': LIMIT})
    req = urllib.request.Request(f'{API}?{params}', headers={'User-Agent':'11mDigitalModeAnalyzer/1.0', 'Accept':'application/xml,text/xml'})
    with urllib.request.urlopen(req, timeout=180) as resp:
        root = ET.fromstring(resp.read())
    reports = []
    returned = 0
    for el in root.iter():
        if el.tag.split('}')[-1] != 'receptionReport':
            continue
        returned += 1
        a = el.attrib
        try:
            hz, ts = int(a.get('frequency', '0')), int(a.get('flowStartSeconds', '0'))
        except ValueError:
            continue
        if not (MIN_HZ <= hz <= MAX_HZ and now-WINDOW <= ts <= now+60):
            continue
        mode = a.get('mode', '').strip()
        if not mode:
            continue
        if mode.upper().startswith('OLIVIA'):
            mode = 'Olivia' + mode[6:]
        reports.append({'t': ts, 'f': hz, 'm': mode})
    payload = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'window_seconds': WINDOW,
        'range_hz': [MIN_HZ, MAX_HZ],
        'returned': returned,
        'limit': LIMIT,
        'possibly_truncated': returned >= LIMIT,
        'oldest_report': min((r['t'] for r in reports), default=None),
        'newest_report': max((r['t'] for r in reports), default=None),
        'reports': reports,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')
    print(f'Saved {len(reports)} reports; {returned} returned')

if __name__ == '__main__':
    main()
