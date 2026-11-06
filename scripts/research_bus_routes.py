"""Archive official route registers for the original operation date; never log keys."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlencode, quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/sources/bus_cleaning'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    env = (ROOT / '.env').read_text(encoding='utf-8-sig')
    match = re.search(r'^\s*DATA_GO_KR_(?:API_KEY|SERVICE_KEY)\s*=\s*([^\r\n]*)', env, re.M)
    if not match:
        raise SystemExit('API key variable not found; no credential printed')
    key = unquote(match[1].strip().strip('\"\''))
    spec = json.loads((ROOT / 'data/sources/15142030.openapi.json').read_text(encoding='utf-8-sig'))
    endpoint = 'https://' + spec['host'] + next(iter(spec['paths']))
    manifest = []
    # Neighbouring administrations may own routes whose stops are inside Daejeon.
    for region in ['30', '36', '43', '44']:
        collected, total, page = [], None, 1
        record = dict(ctpv_cd=region, opr_ymd='20260901', endpoint=endpoint,
                      source='https://www.data.go.kr/data/15142030/openapi.do',
                      retrieved_at=datetime.now(timezone.utc).isoformat(), files=[])
        try:
            while total is None or len(collected) < total:
                params = dict(serviceKey=key, pageNo=page, numOfRows=1000,
                              opr_ymd='20260901', ctpv_cd=region, dataType='JSON')
                with urlopen(endpoint + '?' + urlencode(params), timeout=30) as response:
                    text = response.read().decode('utf-8-sig')
                for secret in {key, match[1], quote(key, safe=''), quote(quote(key, safe=''), safe='')}:
                    if secret:
                        text = text.replace(secret, '[REDACTED]')
                name = f'routes_20260901_{region}_{page}.json'
                (OUT / name).write_text(text, encoding='utf-8')
                record['files'].append(name)
                obj = json.loads(text)
                response = obj.get('Response', obj.get('response', obj))
                header = response.get('header', {})
                record['header'] = header
                if str(header.get('resultCode')) not in ('0', '00', '0000', '200'):
                    raise ValueError('unsuccessful_api_header')
                body = response.get('body') or {}
                count = int(body.get('totalCount', 0))
                if total is not None and total != count:
                    raise ValueError('changed_total')
                total = count
                items = body.get('items') or {}
                items = items.get('item', []) if isinstance(items, dict) else items
                if isinstance(items, dict):
                    items = [items]
                collected.extend(items)
                if not items and len(collected) < total:
                    raise ValueError('incomplete_pagination')
                page += 1
            assert len(collected) == total
            record.update(status='complete', total=total)
        except Exception as exc:
            record.update(status='failed', error_type=type(exc).__name__)
        manifest.append(record)
        print(region, record['status'], record.get('total', 'unknown'), flush=True)
    (OUT / 'route_research_requests.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
