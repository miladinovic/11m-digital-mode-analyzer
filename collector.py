#!/usr/bin/env python3
"""Maintain a rolling 24-hour PSK Reporter reception-spot snapshot."""
import hashlib
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path

API = 'https://retrieve.pskreporter.info/query'
OUT = Path(__file__).parent / 'data' / 'reports.json'
DAILY = Path(__file__).parent / 'data' / 'daily.json'
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

    # Preserve daily totals and per-protocol counts across collector runs.
    # Existing archives may have totals but no historical mode breakdown.
    if DAILY.exists():
        archive = json.loads(DAILY.read_text(encoding='utf-8'))
        daily = {str(k): int(v) for k, v in archive.get('days', {}).items()}
        protocol_counts = {
            str(day): Counter({str(mode): int(count) for mode, count in modes.items()})
            for day, modes in archive.get('protocol_counts', {}).items()
        }
    else:
        daily = {}
        protocol_counts = {}
        for r in old_reports:
            try:
                date = datetime.fromtimestamp(int(r['t']), timezone.utc).date().isoformat()
                mode = str(r['m'])
                daily[date] = daily.get(date, 0) + 1
                protocol_counts.setdefault(date, Counter())[mode] += 1
            except (KeyError, ValueError, TypeError, OverflowError):
                continue

    # On upgrade, seed breakdown for days not yet represented, using only
    # available rolling reports. Earlier reports cannot be reconstructed.
    for r in old_reports:
        try:
            date = datetime.fromtimestamp(int(r['t']), timezone.utc).date().isoformat()
            if date in daily and date not in protocol_counts:
                protocol_counts[date] = Counter()
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
    if DAILY.exists() and not archive.get('protocol_counts'):
        for r in old_reports:
            try:
                date = datetime.fromtimestamp(int(r['t']), timezone.utc).date().isoformat()
                protocol_counts.setdefault(date, Counter())[str(r['m'])] += 1
            except (KeyError, ValueError, TypeError, OverflowError):
                continue

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
            date = datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
            daily[date] = daily.get(date, 0) + 1
            protocol_counts.setdefault(date, Counter())[mode] += 1
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
    daily_payload = {
        'updated_at': payload['updated_at'],
        'timezone': 'UTC',
        'days': dict(sorted(daily.items())),
        'protocol_counts': {day: dict(sorted(counts.items())) for day, counts in sorted(protocol_counts.items())},
        'top_5_protocols': {day: [{'mode': mode, 'reports': count} for mode, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]] for day, counts in sorted(protocol_counts.items())},
    }
    daily_tmp = DAILY.with_suffix('.json.tmp')
    daily_tmp.write_text(json.dumps(daily_payload, separators=(',', ':')), encoding='utf-8')
    daily_tmp.replace(DAILY)
    print(f'Saved {len(ordered)} rolling 24h reports ({added} new; {returned} returned by API)')


if __name__ == '__main__':
    main()
