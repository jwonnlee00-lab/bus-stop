"""Build the offline tram review map and check numbering/range/connectivity."""
import csv
import html
import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
EVIDENCE = DATA / 'sources/tram_estimation'


def main():
    with (DATA / 'tram_stations_estimated.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    expected = {str(i) for i in range(201, 246)}
    counts = Counter(r['station_no'] for r in rows)
    missing = sorted(expected - counts.keys())
    duplicates = [s for s, n in counts.items() if n > 1]
    assert not missing and not duplicates and set(counts) == expected
    available = [r for r in rows if r['latitude'] and r['longitude']]
    invalid = [r['station_no'] for r in available if not (36.26 <= float(r['latitude']) <= 36.41 and 127.29 <= float(r['longitude']) <= 127.48)]
    assert not invalid
    nodes = {r['station_no']: dict(id=r['station_no'], name=r['station_name'], kind='station',
                                  latitude=float(r['latitude']), longitude=float(r['longitude']),
                                  confidence=r['confidence'], position_type=r['position_type']) for r in available}
    # The official overview branches between 212 and 213; the junction is not a station.
    rail = json.loads((EVIDENCE / 'rail.json').read_text(encoding='utf-8'))
    junction_id = 13503883963
    junction = next(g for e in rail['elements'] if e['type'] == 'way'
                    for node, g in zip(e.get('nodes', []), e.get('geometry', [])) if node == junction_id)
    nodes['J_중리'] = dict(id='J_중리', name='중리네거리 분기', kind='junction',
                         latitude=junction['lat'], longitude=junction['lon'], source_osm_node=junction_id)
    edges = []
    def connect(a, b, section):
        edges.append(dict(from_id=str(a), to_id=str(b), section=section, direction='undirected', source_page=2))
    for i in range(201, 240):
        if i == 212:
            connect(212, 'J_중리', 'main_loop')
            connect('J_중리', 213, 'main_loop')
        else:
            connect(i, i + 1, 'main_loop')
    connect(240, 201, 'main_loop')
    for a, b in [('J_중리', 241), (241, 242), (242, 243), (243, 244)]:
        connect(a, b, 'yeonchuk_branch')
    connect(233, 245, 'jinjam_branch')
    adjacency = defaultdict(set)
    for e in edges:
        assert e['from_id'] in nodes and e['to_id'] in nodes
        adjacency[e['from_id']].add(e['to_id'])
        adjacency[e['to_id']].add(e['from_id'])
    visited = {'201'}
    queue = deque(['201'])
    while queue:
        for other in adjacency[queue.popleft()] - visited:
            visited.add(other)
            queue.append(other)
    assert visited == set(nodes)
    assert adjacency['244'] == {'243'} and adjacency['245'] == {'233'}
    graph = dict(description='Official overview adjacency for virtual navigation; straight links are schematic, not surveyed tracks or service patterns.',
                 source='station_locations.pdf#page=2', nodes=list(nodes.values()), edges=edges)
    (DATA / 'tram_route_graph.json').write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding='utf-8')
    with (DATA / 'tram_route_edges.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(edges[0]))
        writer.writeheader()
        writer.writerows(edges)
    report = dict(total_rows=len(rows), coordinates_available=len(available), missing_coordinates=[r['station_no'] for r in rows if r not in available],
                  grade_counts=dict(Counter(r['confidence'] for r in rows)), missing_station_numbers=missing,
                  duplicate_station_numbers=duplicates, out_of_range=invalid,
                  latitude_range=[min(float(r['latitude']) for r in available), max(float(r['latitude']) for r in available)],
                  longitude_range=[min(float(r['longitude']) for r in available), max(float(r['longitude']) for r in available)],
                  graph_nodes=len(nodes), graph_station_nodes=len(available), graph_edges=len(edges), connected=True,
                  loop='201-202-...-240-201; 212-J_중리-213', branches=['J_중리-241-242-243-244', '233-245'],
                  validation_scope='numbering, coordinate bounding range, route adjacency only; no travel time, walking distance or positional RMSE validation')
    (DATA / 'tram_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    roads = json.loads((EVIDENCE / 'roads.json').read_text(encoding='utf-8'))
    cos_lat = math.cos(math.radians(36.35))
    bounds = (127.315, 127.458, 36.292, 36.398)
    width, height, margin = 1260, 1150, 45
    def pixel(lon, lat):
        return (margin + (lon - bounds[0]) / (bounds[1] - bounds[0]) * (width - 2 * margin),
                height - margin - (lat - bounds[2]) / (bounds[3] - bounds[2]) * (height - 2 * margin))
    paths = []
    def path_for(points, color, stroke, dash=''):
        xy = [pixel(p['lon'], p['lat']) for p in points]
        if len(xy) < 2:
            return ''
        coords = ' '.join(f'{x:.2f},{y:.2f}' for x, y in xy)
        return f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{stroke}" {dash}/>'
    for e in roads['elements']:
        paths.append(path_for(e.get('geometry', []), '#d4dbe1', .6))
    tram = [e for e in rail['elements'] if e['type'] == 'way' and e.get('tags', {}).get('construction') == 'tram']
    for e in tram:
        paths.append(path_for(e['geometry'], '#2b9188', 1.2))
    for e in edges:
        a, b = nodes[e['from_id']], nodes[e['to_id']]
        paths.append(path_for([dict(lon=a['longitude'], lat=a['latitude']), dict(lon=b['longitude'], lat=b['latitude'])], '#7449aa', 1.2, 'stroke-dasharray="5 4"'))
    for row in available:
        x, y = pixel(float(row['longitude']), float(row['latitude']))
        title = html.escape(f"{row['station_no']} {row['station_name']} | {row['confidence']} | {row['latitude']}, {row['longitude']} | {row['review_note']}")
        color = '#197a43' if row['confidence'] == 'A' else '#d68a20'
        paths.append(f'<g><title>{title}</title><circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{color}" stroke="white"/><text x="{x+7:.2f}" y="{y-6:.2f}" font-size="12" fill="#162736">{row["station_no"]}</text></g>')
    x, y = pixel(junction['lon'], junction['lat'])
    paths.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="#7449aa"><title>중리네거리 분기점 (정거장 아님)</title></circle>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="대전 트램 45개 추정 정거장 검토 지도"><rect width="100%" height="100%" fill="#fafcfd"/>{"".join(paths)}</svg>'
    document = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>대전 트램 추정 좌표 검토 지도</title><style>body{font-family:system-ui,sans-serif;margin:24px;color:#162736}main{max-width:1260px;margin:auto}svg{width:100%;border:1px solid #dde4e8}p{line-height:1.6}</style><main><h1>대전 트램 45개 추정 정거장</h1><p>A 1개 · B 44개 · 좌표 공란 0개. 2026-10-21 검토본. 측량 좌표가 아닙니다.<br>초록: A · 주황: B 도로 구간 대표점 · 청록선: OSM 공사 선형 · 보라 점선: 정거장 연결 개념선.<br>각 점에 마우스를 올리면 명칭·좌표·근거 메모를 볼 수 있습니다. 브라우저 확대 기능을 사용할 수 있습니다.</p>' + svg + '<p>© OpenStreetMap contributors · <a href="https://www.openstreetmap.org/copyright">ODbL</a>. 공식 위치도: 대전광역시. 배경 지도와 점을 파일에 포함했으며 외부 지도 타일·스크립트를 요청하지 않습니다.<br>연결 개념선은 실제 궤도 형상이나 운행계통을 의미하지 않습니다. 도보·이동시간·TMAP 기능은 포함하지 않습니다.</p></main></html>'
    (DATA / 'tram_stations_review.html').write_text(document, encoding='utf-8')

    plt.rcParams['font.family'] = fm.FontProperties(fname='C:/Windows/Fonts/malgun.ttf').get_name()
    fig, ax = plt.subplots(figsize=(14, 13), dpi=160)
    for e in roads['elements']:
        g = e.get('geometry', [])
        if g:
            ax.plot([p['lon'] for p in g], [p['lat'] for p in g], color='#d9dfe2', lw=.35, zorder=0)
    for e in tram:
        ax.plot([p['lon'] for p in e['geometry']], [p['lat'] for p in e['geometry']], color='#2b9188', lw=.8, alpha=.8)
    for e in edges:
        a, b = nodes[e['from_id']], nodes[e['to_id']]
        ax.plot([a['longitude'], b['longitude']], [a['latitude'], b['latitude']], color='#8657ad', ls='--', lw=.8, alpha=.7)
    for row in available:
        lon, lat = float(row['longitude']), float(row['latitude'])
        ax.scatter(lon, lat, s=27, c='#197a43' if row['confidence'] == 'A' else '#d68a20', edgecolors='white', linewidths=.6, zorder=4)
        ax.annotate(row['station_no'], (lon, lat), xytext=(5, 4), textcoords='offset points', fontsize=8, zorder=5)
    ax.set(xlim=bounds[:2], ylim=bounds[2:], xlabel='WGS84 경도', ylabel='WGS84 위도', title='대전 트램 2호선 추정 정거장 45개 — 가상 내비게이션 검토용')
    ax.set_aspect(1 / cos_lat)
    ax.ticklabel_format(useOffset=False)
    ax.grid(alpha=.15)
    fig.text(.12, .055, '초록 A 1개 / 주황 B 44개 · 청록: 지도 공사선형 · 보라 점선: 연결 개념선\nB는 도로 구간 대표점이며 승강장 중심이 아닙니다. © OpenStreetMap contributors / ODbL · 대전광역시 공식 위치도 대조', fontsize=9)
    fig.savefig(DATA / 'tram_stations_review.png', bbox_inches='tight')
    plt.close(fig)
    print(json.dumps({'rows': len(rows), 'grades': report['grade_counts'], 'missing_coordinates': report['missing_coordinates'],
                      'missing_numbers': missing, 'out_of_range': invalid, 'connected': True, 'station_nodes': len(available)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
