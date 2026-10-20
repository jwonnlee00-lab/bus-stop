"""Build stop table and an auditable validation report from collected data."""
import csv
import json
from collections import defaultdict
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data = root / 'data'
p = data / 'bus_routes.json'
d = json.loads(p.read_text(encoding='utf-8'))
routes, rows = d['routes'], d['route_stops']
rows.sort(key=lambda x: (x['rte_id'], int(x['sttn_seq'])))
sources = ['https://www.data.go.kr/data/15142030/openapi.do', 'https://www.data.go.kr/data/15142031/openapi.do']
by_stop = defaultdict(list)
for row in rows:
    by_stop[row['sttn_id']].append(row)
stop_columns = ['sttn_id', 'sttn_nm', 'ctpv_cd', 'ctpv_nm', 'sgg_cd', 'sgg_nm', 'emd_cd', 'emd_nm']
stops = [{k: group[0].get(k, '') for k in stop_columns} for _, group in sorted(by_stop.items())]
route_ids = {r['rte_id'] for r in routes}
stop_route_ids = {r['rte_id'] for r in rows}
endpoint_ids = {r[k] for r in routes for k in ('dptre_sttn_id', 'arvl_sttn_id')}
stop_ids = set(by_stop)
r106 = [r for r in rows if r['rte_no'] == '106']
report = dict(collected_at=d['collected_at'], operation_date=d['operation_date'], sources=sources,
              scope='대전광역시 5개 구 내부 정류장; 시외 구간 미포함. 최신 제공일 보장 없음.',
              counts=dict(routes=len(routes), route_stops=len(rows), stops=len(stops)),
              columns=dict(bus_routes=list(routes[0]), bus_route_stops=list(rows[0]), bus_stops=stop_columns),
              routes_without_stop_rows=sorted(route_ids-stop_route_ids),
              stop_route_ids_absent_from_routes=sorted(stop_route_ids-route_ids),
              endpoint_ids_absent_from_stops=sorted(endpoint_ids-stop_ids),
              conflicting_stop_names={k: sorted({r['sttn_nm'] for r in group}) for k, group in by_stop.items() if len({r['sttn_nm'] for r in group}) > 1},
              duplicate_route_sequence_rows=len(rows)-len({(r['rte_id'], r['sttn_seq']) for r in rows}),
              route_106_stops=r106,
              route_106_matches=[r for r in r106 if r['sttn_nm'] in ('복합터미널', '아이빌딩')],
              coordinates='두 승인 API의 명세 및 응답에 좌표 없음. 임의 보완하지 않음.',
              errors=['20261021 및 20261001 노선 조회: HTTP 200, Error.code=50, NO_DATA_FOUND',
                      '실제 정상 응답은 Response와 resultCode=200 사용. 수집기에서 반영함.'])
for name, records, columns in [('bus_route_stops', rows, list(rows[0])), ('bus_stops', stops, stop_columns)]:
    with (data / f'{name}.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)
d.update(sources=sources, scope=report['scope'], stops=stops, validation=report)
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
(data / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: v for k,v in report.items() if k not in ('route_106_stops', 'columns', 'conflicting_stop_names')}, ensure_ascii=False, indent=2))
