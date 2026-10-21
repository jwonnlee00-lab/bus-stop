"""Join the Daejeon station API to the archived stop list by exact node ID."""
import argparse
import csv
import hashlib
import json
import math
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote, quote_plus, unquote, urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://www.data.go.kr/data/15157895/openapi.do'


def parse_response(text, stop_id):
    root = ET.fromstring(text)
    # Ignore XML namespace prefixes while retaining the official field names.
    for node in root.iter():
        node.tag = node.tag.split('}')[-1]
    code = root.findtext('.//headerCd')
    if code == '4' and root.findtext('.//itemCnt') == '0' and not root.findall('.//itemList'):
        return {'status': 'not_found', 'code': code}
    if code not in ('0', '00', '0000'):
        return {'status': 'api_error', 'code': code or root.findtext('.//returnReasonCode') or 'unknown'}
    items = [{child.tag: child.text or '' for child in item} for item in root.findall('.//itemList')]
    if not items:
        return {'status': 'not_found'}
    exact = [item for item in items if item.get('BUS_NODE_ID') == stop_id]
    if not exact:
        return {'status': 'id_mismatch', 'returned_ids': sorted({i.get('BUS_NODE_ID', '') for i in items})}
    if len(exact) != 1:
        return {'status': 'ambiguous_id'}
    item = exact[0]
    lat, lon = item.get('GPS_LATI', ''), item.get('GPS_LONG', '')
    result = {'api_stop_id': stop_id, 'api_stop_name': item.get('BUSSTOP_NM', ''),
              'ars_id': item.get('ARO_BUSSTOP_ID', ''), 'latitude': '', 'longitude': ''}
    if not lat.strip() or not lon.strip():
        return dict(result, status='missing_coordinates')
    try:
        a, b = float(lat), float(lon)
    except ValueError:
        return dict(result, status='invalid_coordinates')
    if not (math.isfinite(a) and math.isfinite(b) and -90 <= a <= 90 and -180 <= b <= 180) or a == 0 or b == 0:
        return dict(result, status='invalid_coordinates')
    return dict(result, status='matched', latitude=lat, longitude=lon)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true', help='Only request the two 106 stops; do not create CSV')
    parser.add_argument('--run', required=True, help='New snapshot folder name; reuse it to resume cached responses')
    parser.add_argument('--offline', action='store_true', help='Use only saved XML; do not make API requests')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run):
        parser.error('run must contain only letters, digits, underscores or hyphens')
    output = ROOT / 'data/bus_stops_geocoded.csv'
    report_path = ROOT / 'data/geocoding_validation.json'
    if not args.probe and (output.exists() or report_path.exists()):
        raise SystemExit('Output CSV or validation already exists; refusing to overwrite')
    env = (ROOT / '.env').read_text(encoding='utf-8-sig')
    match = re.search(r'^\s*DATA_GO_KR_(?:API_KEY|SERVICE_KEY)\s*=\s*([^\r\n]*)', env, re.M)
    if not match or not match[1].strip():
        raise SystemExit('API key is empty or absent')
    key = unquote(match[1].strip().strip('\"\''))
    secrets = {key, match[1].strip(), quote(key, safe=''), quote_plus(key)}
    spec = json.loads((ROOT / 'data/sources/15157895.openapi.json').read_text(encoding='utf-8'))
    endpoint = 'https://' + spec['host'] + '/getStationByStopID'
    cache = ROOT / 'data/raw/station_info' / args.run
    cache.mkdir(parents=True, exist_ok=True)
    input_path = ROOT / 'data/bus_stops.csv'
    before = hashlib.sha256(input_path.read_bytes()).hexdigest()
    with input_path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames
        stops = list(reader)
    lock = threading.Lock()
    last_request = [0.0]

    def fetch(stop_id):
        path = cache / f'{stop_id}.xml'
        if path.exists():
            text = path.read_text(encoding='utf-8')
        else:
            if args.offline:
                return {'status': 'not_cached'}
            # Bound total request rate across workers, including retries.
            for attempt in range(3):
                with lock:
                    time.sleep(max(0, last_request[0] + .12 - time.monotonic()))
                    last_request[0] = time.monotonic()
                try:
                    with urlopen(endpoint + '?' + urlencode({'serviceKey': key, 'BusStopID': stop_id}), timeout=30) as response:
                        text = response.read().decode('utf-8-sig')
                    for secret in sorted(secrets, key=len, reverse=True):
                        if secret:
                            text = text.replace(secret, '[REDACTED]')
                    ET.fromstring(text)
                    path.write_text(text, encoding='utf-8')
                    break
                except Exception as exc:
                    # Exception strings can contain the credential-bearing URL.
                    if attempt == 2:
                        return {'status': 'request_error', 'error_type': type(exc).__name__}
                    time.sleep(attempt + 1)
        try:
            return parse_response(text, stop_id)
        except ET.ParseError:
            return {'status': 'invalid_response'}

    probes = {sid: fetch(sid) for sid in ('8001096', '8002159')}
    print(json.dumps({'probes': probes}, ensure_ascii=False), flush=True)
    (cache / 'probes.json').write_text(json.dumps(probes, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.probe:
        return
    if any(p['status'] != 'matched' for p in probes.values()):
        raise SystemExit('Probe failed: bulk requests stopped; inspect ID or API errors')
    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        for index, result in enumerate(executor.map(fetch, [s['sttn_id'] for s in stops]), 1):
            results.append(result)
            if index % 200 == 0:
                print('Processed:', index, dict(Counter(r['status'] for r in results)), flush=True)
    added = ['latitude', 'longitude', 'geocode_status', 'api_stop_id', 'api_stop_name', 'ars_id', 'name_check']
    if output.exists():
        raise SystemExit('Output already exists; refusing to overwrite')
    assert before == hashlib.sha256(input_path.read_bytes()).hexdigest(), 'Input changed during collection'
    with output.open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns + added)
        writer.writeheader()
        for stop, result in zip(stops, results):
            name_check = ('exact' if stop['sttn_nm'] == result['api_stop_name'] else 'different') if result.get('api_stop_name') else 'unavailable'
            values = {k: result.get(k, '') for k in added if k not in ('geocode_status', 'name_check')}
            writer.writerow(dict(stop, **values, geocode_status=result['status'], name_check=name_check))
    matched = [r for r in results if r['status'] == 'matched']
    report = {
        'source': SOURCE, 'endpoint': endpoint, 'collected_at': datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'input_operation_date': '2026-09-01', 'coordinate_operation_date': None,
        'temporal_note': 'Real-time station API; coordinates are not a historical snapshot for 2026-09-01.',
        'join': 'sttn_id == BUS_NODE_ID (exact string); no name, ARS-ID or proximity fallback',
        'input_sha256': before, 'input_rows': len(stops), 'matched': len(matched),
        'failed': len(stops) - len(matched), 'success_percent': round(100 * len(matched) / len(stops), 4),
        'matched_with_exact_name': sum(r['status'] == 'matched' and s['sttn_nm'] == r.get('api_stop_name') for s, r in zip(stops, results)),
        'response_saved_at_range': [datetime.fromtimestamp(fn([p.stat().st_mtime for p in cache.glob('*.xml')]), timezone(timedelta(hours=9))).isoformat() for fn in (min, max)],
        'status_counts': dict(Counter(r['status'] for r in results)),
        'id_prefix_counts': {
            prefix: dict(Counter(r['status'] for s, r in zip(stops, results) if s['sttn_id'].startswith(prefix)))
            for prefix in sorted({s['sttn_id'][:2] for s in stops})
        },
        'missing_latitude': sum(not r.get('latitude') for r in results),
        'missing_longitude': sum(not r.get('longitude') for r in results),
        'latitude_range': [min(float(r['latitude']) for r in matched), max(float(r['latitude']) for r in matched)] if matched else None,
        'longitude_range': [min(float(r['longitude']) for r in matched), max(float(r['longitude']) for r in matched)] if matched else None,
        'name_differences': [dict(sttn_id=s['sttn_id'], original_name=s['sttn_nm'], api_name=r.get('api_stop_name')) for s,r in zip(stops, results) if r.get('api_stop_name') and s['sttn_nm'] != r['api_stop_name']],
        'failures': [dict(sttn_id=s['sttn_id'], **r) for s,r in zip(stops,results) if r['status'] != 'matched'],
        'probes': probes,
    }
    (cache / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with report_path.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k,v in report.items() if k not in ('failures','name_differences','probes')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
