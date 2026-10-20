"""Collect only the two approved services, using locally archived official specs."""
import argparse
import csv
import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen
from urllib.parse import urlencode, unquote
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
NOW = datetime.now(timezone(timedelta(hours=9)))
parser = argparse.ArgumentParser()
parser.add_argument('--date', default='20261021')
parser.add_argument('--probe', action='store_true')
args = parser.parse_args()
env = (ROOT / '.env').read_text(encoding='utf-8-sig')
match = re.search(r'^\s*DATA_GO_KR_(?:API_KEY|SERVICE_KEY)\s*=\s*([^\r\n]*)', env, re.M)
if not match or not match[1]:
    raise SystemExit('DATA_GO_KR_API_KEY is empty or absent')
key = unquote(match[1].strip().strip('\"\''))
raw = DATA / 'raw' / args.date
raw.mkdir(parents=True, exist_ok=True)
requests = []

def fetch(dataset, extra, page=1):
    spec = json.loads((DATA / 'sources' / f'{dataset}.openapi.json').read_text(encoding='utf-8-sig'))
    operation = next(iter(spec['paths']))
    params = dict(pageNo=page, numOfRows=1000, opr_ymd=args.date, ctpv_cd='30', dataType='JSON', **extra)
    url = 'https://' + spec['host'] + operation + '?' + urlencode(dict(params, serviceKey=key))
    label = f'{dataset}_{extra.get("sgg_cd", "all")}_{page}'
    record = dict(dataset=dataset, parameters=params, collected_at=datetime.now(timezone(timedelta(hours=9))).isoformat())
    requests.append(record)
    try:
        with urlopen(url, timeout=60) as response:
            content = response.read()
            record['http_status'] = response.status
    except HTTPError as exc:
        record['http_status'] = exc.code
        content = exc.read()
    except Exception as exc:
        record['error'] = type(exc).__name__
        raise RuntimeError(type(exc).__name__) from None
    # Never persist a reflected credential, including URL-encoded forms.
    text = content.decode('utf-8-sig').replace(key, '[REDACTED]').replace(match[1], '[REDACTED]')
    (raw / f'{label}.txt').write_text(text, encoding='utf-8')
    try:
        obj = json.loads(text)
    except ValueError:
        record['error'] = 'Non-JSON response; see raw file'
        raise RuntimeError(record['error']) from None
    response = obj.get('Response', obj.get('response', obj))
    if 'Error' in obj:
        record['api_error'] = obj['Error']
    record['header'] = response.get('header', {})
    body = response.get('body') or {}
    record['totalCount'] = body.get('totalCount')
    print(json.dumps(record, ensure_ascii=False), flush=True)
    if str(record['header'].get('resultCode')) not in ('00', '0', '0000', '200'):
        raise RuntimeError('API returned unsuccessful header')
    items = body.get('items') or {}
    items = items.get('item', []) if isinstance(items, dict) else items
    if isinstance(items, dict):
        items = [items]
    return items, int(body.get('totalCount', 0))

def all_pages(dataset, extra):
    rows, total = fetch(dataset, extra)
    page = 1
    while len(rows) < total:
        page += 1
        time.sleep(.3)
        more, check = fetch(dataset, extra, page)
        if not more or check != total:
            raise RuntimeError('Pagination incomplete or total changed')
        rows.extend(more)
    if len(rows) != total:
        raise RuntimeError('Row count mismatch')
    return rows

try:
    routes = all_pages('15142030', {})
    if args.probe:
        print('Route count:', len(routes))
        print(json.dumps(routes[:2], ensure_ascii=False))
    else:
        stops = []
        for district in ('30110', '30140', '30170', '30200', '30230'):
            stops.extend(all_pages('15142031', {'sgg_cd': district}))
        for name, rows in [('bus_routes', routes), ('bus_route_stops', stops)]:
            if not rows:
                raise RuntimeError('No rows: refusing to write misleading empty datasets')
            columns = list(dict.fromkeys(k for row in rows for k in row))
            with (DATA / f'{name}.csv').open('w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
        (DATA / 'bus_routes.json').write_text(json.dumps(dict(collected_at=NOW.isoformat(), operation_date=args.date, routes=routes, route_stops=stops), ensure_ascii=False, indent=2), encoding='utf-8')
except RuntimeError as exc:
    print('Collection stopped:', str(exc))
finally:
    (raw / 'requests.json').write_text(json.dumps(requests, ensure_ascii=False, indent=2), encoding='utf-8')
