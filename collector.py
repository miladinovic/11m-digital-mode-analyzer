#!/usr/bin/env python3
"""Maintain a rolling 24-hour PSK Reporter reception-spot snapshot."""
import hashlib
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


def identity(report):
    # Legacy snapshots have no unique key. This fallback can merge distinct
    # spots with identical second/frequency/mode, but only during migration.
    return report.get('id') or f"legacy:{report['t']}:{report['f']}:{report['m']}"


def main():
    now = int(datetime.now(timezone.utc).timestamp())
    params = urllib.parse.urlencode({
        'flowStartSeconds': -WINDOW,
        'frange': f'{MIN_HZ}-{MAX_HZ}',
        'rptlimit': LIMIT,
    })
    req = urllib.request.Request(
        f'{API}?{params}',
        headers={'User-Agent': '11mDigitalModeAnalyzer/1.1', 'Accept': 'application/xml,text/xml'},
    )
    # Fetch and parse before writing anything, so an API failure preserves data.
    with urllib.request.urlopen(req, timeout=180) as resp:
        root = ET.fromstring(resp.read())

    if OUT.exists():
        previous = json.loads(OUT.read_text(encoding='utf-8'))
        old_reports = previous.get('reports', [])
        if not isinstance(old_reports, list):
            raise ValueError('Existing reports.json has an invalid reports array')
    else:
        old_reports = []

    reports = {}
    for r in old_reports:
        try:
            t, f, m = int(r['t']), int(r['f']), str(r['m'])
            if now-WINDOW <= t <= now+60 and MIN_HZ <= f <= MAX_HZ and m:
                reports[identity(r)] = r
        except (KeyError, TypeError, ValueError):
            continue

    returned = 0
    added = 0
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
        # Hash all XML attributes to distinguish reception spots, while
        # deduplicating repeated downloads of the same spot.
        canonical = json.dumps(sorted(a.items()), separators=(',', ':'), ensure_ascii=False)
        report_id = hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]
        report = {'t': ts, 'f': hz, 'm': mode, 'id': report_id}
        if report_id not in reports:
            added += 1
        reports[report_id] = report

    ordered = sorted(reports.values(), key=lambda r: (r['t'], r['f'], r['m']))
    payload = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'window_seconds': WINDOW,
        'range_hz': [MIN_HZ, MAX_HZ],
        'returned': returned,
        'limit': LIMIT,
        'possibly_truncated': returned >= LIMIT,
        'oldest_report': min((r['t'] for r in ordered), default=None),
        'newest_report': max((r['t'] for r in ordered), default=None),
        'reports': ordered,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')
    tmp.replace(OUT)
    print(f'Saved {len(ordered)} rolling 24h reports ({added} new; {returned} returned by API)')


if __name__ == '__main__':
    main()
