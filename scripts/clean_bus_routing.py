"""Build directed routing sections without joining across missing stops or sequences."""
import csv
import hashlib
import json
import math
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
EVIDENCE = DATA / 'sources/bus_cleaning'
OUT = DATA / 'bus_routing'


def normalized_name(name):
    return ''.join(c for c in unicodedata.normalize('NFC', name or '')
                   if not c.isspace() and not unicodedata.category(c).startswith('P'))


def read_csv(name):
    with (DATA / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def stop_reason(row):
    if not row.get('latitude') or not row.get('longitude'):
        return 'missing_coordinates'
    try:
        lat, lon = float(row['latitude']), float(row['longitude'])
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            return 'invalid_coordinates'
    except ValueError:
        return 'invalid_coordinates'
    if row.get('geocode_status') != 'matched' or row.get('api_stop_id') != row['sttn_id']:
        return 'coordinate_id_unverified'
    if not normalized_name(row.get('api_stop_name')):
        return 'coordinate_name_unavailable'
    if normalized_name(row['sttn_nm']) != normalized_name(row['api_stop_name']):
        return 'substantive_name_difference'
    return None


def build_connections(records, accepted_stops, route_allowed):
    """Inspect adjacent ORIGINAL rows. Filtering must never precede adjacency."""
    edges, gaps = [], []
    seq_counts = Counter(r['sttn_seq'] for r in records)
    def sequence(row):
        try:
            return int(row['sttn_seq'])
        except ValueError:
            return -1
    ordered = sorted(records, key=sequence)
    for a, b in zip(ordered, ordered[1:]):
        reasons = []
        if not route_allowed:
            reasons.append('route_id_not_officially_verified')
        if sequence(a) < 0 or sequence(b) < 0:
            reasons.append('invalid_sequence')
        if seq_counts[a['sttn_seq']] > 1 or seq_counts[b['sttn_seq']] > 1:
            reasons.append('ambiguous_sequence')
        if sequence(b) != sequence(a) + 1:
            reasons.append('missing_intermediate_sequence')
        for label, row in [('from', a), ('to', b)]:
            if row['sttn_id'] not in accepted_stops:
                reasons.append(label + '_stop_excluded')
            elif normalized_name(row['sttn_nm']) != normalized_name(accepted_stops[row['sttn_id']]['sttn_nm']):
                reasons.append(label + '_occurrence_name_conflict')
        connection = dict(from_seq=a['sttn_seq'], to_seq=b['sttn_seq'],
                          from_stop_id=a['sttn_id'], to_stop_id=b['sttn_id'])
        if reasons:
            gaps.append({**connection, 'routing_allowed': False, 'reasons': reasons,
                         'missing_sequence_count': max(0, sequence(b) - sequence(a) - 1)})
        else:
            edges.append({**connection, 'routing_allowed': True, 'direction': 'sequence_forward_only'})
    return edges, gaps


def main():
    inputs = ['bus_routes.csv', 'bus_route_stops.csv', 'bus_stops.csv', 'bus_stops_geocoded.csv']
    hashes = {n: hashlib.sha256((DATA / n).read_bytes()).hexdigest() for n in inputs}
    routes, rows = read_csv(inputs[0]), read_csv(inputs[1])
    stops = read_csv(inputs[3])
    catalog = {r['sttn_id']: r for r in stops}
    assert len(catalog) == len(stops)
    accepted, audit = {}, []
    for row in stops:
        reason = stop_reason(row)
        comparison = ('exact' if row['sttn_nm'] == row.get('api_stop_name') else 'spacing_or_punctuation_only') if not reason else 'not_accepted'
        audit.append(dict(sttn_id=row['sttn_id'], sttn_nm=row['sttn_nm'],
                          api_stop_name=row.get('api_stop_name'), accepted=not reason,
                          reason=reason, name_comparison=comparison))
        if not reason:
            accepted[row['sttn_id']] = row
    manifest = json.loads((EVIDENCE / 'route_research_requests.json').read_text(encoding='utf-8'))
    official = defaultdict(list)
    for request in manifest:
        if request['status'] != 'complete':
            continue
        for name in request['files']:
            obj = json.loads((EVIDENCE / name).read_text(encoding='utf-8'))
            body = obj.get('Response', obj.get('response', obj)).get('body') or {}
            items = body.get('items') or {}
            items = items.get('item', []) if isinstance(items, dict) else items
            items = [items] if isinstance(items, dict) else items
            for item in items:
                assert item['opr_ymd'] == '20260901'
                official[str(item['rte_id'])].append((item, name))
    known = {r['rte_id']: r for r in routes}
    groups = defaultdict(list)
    for row in rows:
        groups[(row['opr_ymd'], row['rte_id'])].append(row)
    reviews, results = [], []
    occurrence_counts = Counter()
    for (date, route_id), records in sorted(groups.items()):
        matches = official.get(route_id, [])
        confirmed = [m for m in matches if m[0]['opr_ymd'] == date]
        allowed = route_id in known or bool(confirmed)
        metadata = known.get(route_id) or (confirmed[0][0] if confirmed else {})
        if route_id not in known:
            reviews.append(dict(
                rte_id=route_id, input_rte_no=records[0]['rte_no'], input_rte_nm=records[0]['rte_nm'],
                operation_date=date, routing_eligible=allowed,
                status='official_register_exact_id_match' if confirmed else 'unverified_hold',
                official_matches=[dict(route=m, source_file='data/sources/bus_cleaning/' + f) for m, f in confirmed],
                note=('동일 기준일 공식 노선 명부의 ID 확인. 현재 실시간 차량 운행 확인과는 다름.' if confirmed else
                      '대전·세종·충북·충남의 같은 기준일 명부에서 ID를 찾지 못함. 폐선 판정 아님. 번호·이름으로 ID를 대체하지 않음.'),
            ))
        edges, gaps = build_connections(records, accepted, allowed)
        if route_id not in known:
            reviews[-1]['route_id_verified'] = allowed
            reviews[-1]['routing_eligible'] = bool(edges)
            reviews[-1]['usable_edge_count'] = len(edges)
            reviews[-1]['routing_hold_reason'] = None if edges else ('no_verified_adjacent_coordinate_pair' if allowed else 'unverified_route_id')
        occurrences = []
        for row in sorted(records, key=lambda r: int(r['sttn_seq'])):
            reasons = []
            if not allowed:
                reasons.append('route_id_not_officially_verified')
            if row['sttn_id'] not in accepted:
                reasons.append(stop_reason(catalog[row['sttn_id']]) if row['sttn_id'] in catalog else 'stop_absent_from_catalog')
            elif normalized_name(row['sttn_nm']) != normalized_name(accepted[row['sttn_id']]['sttn_nm']):
                reasons.append('occurrence_name_conflict')
            occurrences.append(dict(sequence=row['sttn_seq'], stop_id=row['sttn_id'],
                                    stop_name=row['sttn_nm'], routing_eligible=not reasons, exclusion_reasons=reasons))
            occurrence_counts['retained' if not reasons else 'excluded'] += 1
        # Segments are maximal runs of validated adjacent edges; no synthetic gap edges.
        segments = []
        for edge in edges:
            if not segments or segments[-1]['sequences'][-1] != edge['from_seq']:
                segments.append(dict(segment_id=f'{date}:{route_id}:{len(segments) + 1}',
                                     sequences=[edge['from_seq']], stop_ids=[edge['from_stop_id']]))
            segments[-1]['sequences'].append(edge['to_seq'])
            segments[-1]['stop_ids'].append(edge['to_stop_id'])
            edge['segment_id'] = segments[-1]['segment_id']
        endpoints = []
        for key in ['dptre_sttn_id', 'arvl_sttn_id']:
            stop_id = metadata.get(key)
            endpoints.append(dict(field=key, stop_id=stop_id,
                                  present_in_catalog=bool(stop_id and stop_id in catalog),
                                  observed_on_route=bool(stop_id and any(r['sttn_id'] == stop_id for r in records)),
                                  routing_coordinate_eligible=bool(stop_id and stop_id in accepted)))
        results.append(dict(rte_id=route_id, operation_date=date, rte_no=metadata.get('rte_no') or records[0]['rte_no'],
                            rte_nm=metadata.get('rte_nm') or records[0]['rte_nm'], route_id_verified=allowed, routing_eligible=bool(edges),
                            route_verification='original_official_register' if route_id in known else ('neighbour_official_register' if allowed else 'unverified_hold'),
                            endpoints=endpoints, occurrences=occurrences, segments=segments, edges=edges, blocked_connections=gaps,
                            coverage='대전 내부 수집 경유 기록의 확인된 연속 구간만 제공. 전체 노선 복원·종점 연장·왕복 추정 없음.'))
    missing_original_endpoints = sorted({r[k] for r in routes for k in ['dptre_sttn_id', 'arvl_sttn_id'] if r[k] not in catalog})
    review_by_id = {r['rte_id']: r for r in reviews}
    extra_url = 'https://www.daejeon.go.kr/drh/board/boardNormalView.do?boardId=normal_0189&menuSeq=1632&ntatcSeq=1485743605&pageIndex=75'
    review_by_id['30300155']['additional_official_evidence'] = dict(
        url=extra_url, title='대전시, 6월 27일부터 시내버스 노선 조정·신설 운행',
        finding='123번 신설 운행 발표는 확인되지만 본문에 30300155 ID 연결 근거가 없어 보류 유지.')
    report = dict(
        operation_date='20260901', source_sha256=hashes,
        counts_before=dict(stop_catalog=len(stops), geocoded=sum(bool(r['latitude'] and r['longitude']) for r in stops),
                           original_route_register=len(routes), observed_route_ids=len(groups), route_stop_records=len(rows)),
        counts_after=dict(coordinate_eligible_stops=len(accepted), routing_route_ids=sum(bool(r['edges']) for r in results),
                          officially_eligible_route_ids=sum(r['route_id_verified'] for r in results),
                          stops_used_by_edges=len({e[k] for r in results for e in r['edges'] for k in ['from_stop_id', 'to_stop_id']}),
                          eligible_route_stop_records=occurrence_counts['retained'], excluded_route_stop_records=occurrence_counts['excluded'],
                          directed_edges=sum(len(r['edges']) for r in results), blocked_connections=sum(len(r['blocked_connections']) for r in results),
                          continuous_segments=sum(len(r['segments']) for r in results)),
        stop_exclusion_reasons=dict(Counter(a['reason'] for a in audit if not a['accepted'])),
        spacing_or_punctuation_matches=sum(a['name_comparison'] == 'spacing_or_punctuation_only' for a in audit),
        route_id_research=dict(total=len(reviews), exact_id_registered=sum(r['route_id_verified'] for r in reviews),
                               with_usable_edges=sum(r['routing_eligible'] for r in reviews),
                               verified_but_no_usable_edges=sum(r['route_id_verified'] and not r['routing_eligible'] for r in reviews),
                               region_counts=dict(Counter(r['official_matches'][0]['route']['ctpv_cd'] for r in reviews if r['official_matches'])),
                               unresolved_ids=[r['rte_id'] for r in reviews if not r['route_id_verified']]),
        missing_original_endpoint_ids=missing_original_endpoints,
        affected_original_routes=[dict(rte_id=r['rte_id'], rte_no=r['rte_no']) for r in routes
                                  if any(r[k] in missing_original_endpoints for k in ['dptre_sttn_id','arvl_sttn_id'])],
        blocked_reason_counts=dict(Counter(reason for r in results for gap in r['blocked_connections'] for reason in gap['reasons'])),
        original_csv_unchanged=all(hashlib.sha256((DATA / n).read_bytes()).hexdigest() == h for n,h in hashes.items()),
        scope='공식 명부는 2026-09-01 등록 근거. 2026-10-21 실시간 운행·시간표를 보장하지 않음. 정류장명 정규화는 비교용이며 ID·원래 이름을 합치거나 덮어쓰지 않음.',
    )
    assert report['original_csv_unchanged']
    assert len(reviews) == 51
    assert len(missing_original_endpoints) == 6
    graph = dict(schema_version=1, operation_date='20260901',
                 policy=dict(direction='sequence_forward_only', reverse_edges_inferred=False,
                             bridge_excluded_stops=False, bridge_missing_sequences=False,
                             name_comparison='NFC; remove whitespace and Unicode punctuation only; preserve IDs',
                             route_state='경로 탐색 시 route_id·operation_date·sequence·segment_id를 유지. 다른 연속 구간으로 같은 버스 탑승 상태를 이어 붙이지 않음.',
                             transfers='정제 데이터는 승하차 가능 ID만 제공. 도보·환승 연결은 생성하지 않음.'),
                 stops=[dict(stop_id=r['sttn_id'], name=r['sttn_nm'], latitude=float(r['latitude']), longitude=float(r['longitude'])) for r in accepted.values()],
                 routes=results)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in [('bus_routing.json', graph), ('cleaning_report.json', {**report, 'stop_audit':audit}), ('route_id_review.json', dict(request_manifest='data/sources/bus_cleaning/route_research_requests.json', routes=reviews))]:
        (OUT / name).write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
