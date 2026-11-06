"""Compute straight-line distances for existing, allowed, directed bus edges only."""
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/bus_routing/bus_routing.json'
OUTPUT = ROOT / 'data/bus_routing/bus_distances.json'
EARTH_RADIUS_KM = 6371.0088


def haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(max(0.0, min(1.0, h))))


def coordinate(stop):
    if stop is None or stop.get('latitude') is None or stop.get('longitude') is None:
        raise ValueError('missing_coordinates')
    try:
        lat, lon = float(stop['latitude']), float(stop['longitude'])
    except (TypeError, ValueError):
        raise ValueError('invalid_coordinates') from None
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('invalid_coordinates')
    return lat, lon


def edge_key(route, edge):
    return (route['operation_date'], route['rte_id'], edge['from_seq'], edge['to_seq'],
            edge['from_stop_id'], edge['to_stop_id'])


def main():
    if OUTPUT.exists():
        raise SystemExit('Refusing to overwrite existing bus_distances.json')
    original = SOURCE.read_bytes()
    graph = json.loads(original)
    stops = {s['stop_id']:s for s in graph['stops']}
    assert len(stops) == len(graph['stops']), 'Duplicate stop IDs'
    blocked = {edge_key(route, edge) for route in graph['routes'] for edge in route['blocked_connections']}
    records, failures, review, seen = [], [], [], set()
    occurrence_keys = set()
    input_count = 0
    pair_counts = Counter()
    for route in graph['routes']:
        for edge in route['edges']:
            input_count += 1
            key = edge_key(route, edge)
            occurrence = key[:4]
            base = dict(operation_date=route['operation_date'], rte_id=route['rte_id'], rte_no=route['rte_no'], **edge)
            try:
                if key in seen:
                    raise ValueError('duplicate_connection')
                if occurrence in occurrence_keys:
                    raise ValueError('conflicting_sequence_connection')
                seen.add(key)
                occurrence_keys.add(occurrence)
                if key in blocked or not edge.get('routing_allowed'):
                    raise ValueError('blocked_connection')
                if int(edge['to_seq']) != int(edge['from_seq']) + 1 or edge['direction'] != 'sequence_forward_only':
                    raise ValueError('invalid_direction_or_sequence')
                a = coordinate(stops.get(edge['from_stop_id']))
                b = coordinate(stops.get(edge['to_stop_id']))
                distance = haversine_km(a, b)
                if not math.isfinite(distance) or distance < 0:
                    raise ValueError('invalid_distance')
                flags = []
                if distance == 0:
                    flags.append('zero_straight_line_distance')
                elif distance < 0.001:
                    flags.append('under_one_metre_review')
                if distance > 5:
                    flags.append('over_5km_review')
                result = {**base, 'distance_km':round(distance,4), 'review_flags':flags}
                records.append(result)
                pair_counts[(edge['from_stop_id'],edge['to_stop_id'])] += 1
                if flags:
                    review.append(result)
            except (ValueError, KeyError) as error:
                failures.append({**base, 'reason':str(error)})
    assert input_count == 8756
    blocked_count = sum(len(r['blocked_connections']) for r in graph['routes'])
    assert blocked_count == 500
    assert SOURCE.read_bytes() == original
    result = dict(
        schema_version=1, operation_date=graph['operation_date'],
        source='data/bus_routing/bus_routing.json', source_sha256=hashlib.sha256(original).hexdigest(),
        distance_definition='연속된 두 정류장 사이 Haversine 직선거리. 정류장 사이 직선거리의 합산을 위한 추정값이며 실제 도로 주행거리·버스 주행거리와 다름.',
        unit='km', decimal_places=4, earth_radius_km=EARTH_RADIUS_KM,
        policy=dict(direction='원본 간선 방향과 순번 유지. 역방향·보류 구간·누락 정류장 우회 연결 생성 없음.',
                    aggregation='각 간선은 소수점 넷째 자리로 반올림. 합산값에는 구간별 반올림 오차가 누적될 수 있음.',
                    anomaly_rule='0km, 0km 초과 0.001km 미만, 5km 초과는 검토 표시. 실측 오류 판정이나 도로 거리 보정 없이 계산값 유지.',
                    duplicates='운행일·노선 ID·출발/도착 순번·정류장 ID가 모두 같은 경우 중복. 다른 노선이나 다른 순번에서 같은 정류장 쌍이 반복되는 것은 유지.'),
        distances=records,
        validation=dict(input_allowed_edges=input_count, success_count=len(records), failure_count=len(failures),
                        excluded_blocked_connections=blocked_count, blocked_connections_calculated=0,
                        source_unchanged=True, failure_reasons=dict(Counter(f['reason'] for f in failures)),
                        min_distance_km=min(r['distance_km'] for r in records),
                        max_distance_km=max(r['distance_km'] for r in records),
                        review_count=len(review), review_reason_counts=dict(Counter(f for r in review for f in r['review_flags'])),
                        unique_directed_stop_pairs=len(pair_counts),
                        repeated_pair_occurrences=sum(n-1 for n in pair_counts.values()),
                        failures=failures, review_connections=review))
    serialized = json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
    # Keep a JSON number, including trailing zeroes to exactly four decimal places.
    serialized = re.sub(r'("distance_km": )([0-9]+(?:\.[0-9]+)?)',
                        lambda m:m[1]+format(float(m[2]),'.4f'),serialized)
    with OUTPUT.open('x',encoding='utf-8') as f:
        f.write(serialized+'\n')
    print(json.dumps({k:v for k,v in result['validation'].items() if k not in ['failures','review_connections']},ensure_ascii=False))


if __name__ == '__main__':
    main()
