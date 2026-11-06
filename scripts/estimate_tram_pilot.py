"""Reproduce the 211/218 pilot from saved official-plan pixels and OSM geometry.

The affine transform is fitted to image pixels, never to unverified CAD X/Y.
Requires the optional dependencies in requirements-tram.txt.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'data/sources/tram_pilot'


def polygon_centroid(vertices):
    p = np.asarray(vertices, dtype=float)
    q = np.roll(p, -1, axis=0)
    cross = p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1]
    area = cross.sum() / 2
    if abs(area) < 1e-10:
        raise ValueError('Zero-area platform polygon')
    center = ((p + q) * cross[:, None]).sum(axis=0) / (6 * area)
    return abs(area), center


def calculate():
    inputs = json.loads((EVIDENCE / 'pilot_inputs.json').read_text(encoding='utf-8'))
    osm = json.loads((EVIDENCE / 'osm_raw.json').read_text(encoding='utf-8'))
    ways = {e['id']: e for e in osm['elements'] if e['type'] == 'way'}
    projection = '+proj=aeqd +lat_0=36.3575 +lon_0=127.3815 +datum=WGS84 +units=m +type=crs'
    forward = Transformer.from_crs(4326, projection, always_xy=True)
    inverse = Transformer.from_crs(projection, 4326, always_xy=True)
    controls = []
    for source in inputs['controls']:
        c = dict(source)
        way = ways[c['way']]
        i = c['vertex']
        assert way['nodes'][i] == c['node_id'], 'OSM node reference changed'
        point = way['geometry'][i]
        c.update(map_lon_lat=[point['lon'], point['lat']],
                 map_xy=list(forward.transform(point['lon'], point['lat'])),
                 way_version=way['version'], way_timestamp=way['timestamp'])
        controls.append(c)
    fit = [c for c in controls if c['role'] == 'fit']
    assert len(fit) == 3
    design = np.array([c['pixel'] + [1] for c in fit], dtype=float)
    assert np.linalg.matrix_rank(design) == 3, 'Collinear fit points'
    matrix = np.linalg.solve(design, np.array([c['map_xy'] for c in fit]))
    for c in controls:
        predicted = np.array(c['pixel'] + [1]) @ matrix
        c['residual_m'] = float(np.linalg.norm(predicted - c['map_xy']))
    checks = [c['residual_m'] for c in controls if c['role'] == 'check']
    assert len(checks) >= 3
    # Consistency gate for this pilot; this is not a claimed survey accuracy.
    if max(checks) > 15:
        raise ValueError('Holdout discrepancy exceeds the pilot consistency gate')
    polygons = [polygon_centroid(p) for p in inputs['platform_polygons_218']]
    total_area = sum(area for area, _ in polygons)
    pixel = sum(area * center for area, center in polygons) / total_area
    representative_xy = np.r_[pixel, 1] @ matrix
    lon, lat = inverse.transform(*representative_xy)
    assert 36 < lat < 37 and 127 < lon < 128
    # An alternative fit checks sensitivity to a different set of building corners.
    alternate = [c for c in controls if c['label'] in ('Police SW', 'Samsung SW', 'Bank NE main')]
    alternate_matrix = np.linalg.solve(np.array([c['pixel'] + [1] for c in alternate]),
                                       np.array([c['map_xy'] for c in alternate]))
    sensitivity = float(np.linalg.norm(np.r_[pixel, 1] @ (alternate_matrix - matrix)))
    barycentric = np.linalg.solve(design.T, np.r_[pixel, 1])
    triangle = np.array([c['map_xy'] for c in fit])
    edge_distances = []
    for i in range(3):
        a, b = triangle[i], triangle[(i + 1) % 3]
        fraction = np.clip(np.dot(representative_xy - a, b - a) / np.dot(b - a, b - a), 0, 1)
        edge_distances.append(float(np.linalg.norm(representative_xy - (a + fraction * (b - a)))))
    rmse = float(np.sqrt(np.mean(np.square(checks))))
    rows = [
        dict(station_no='211', station_name='대전복합터미널', latitude='', longitude='',
             position_type='unresolved_platform', confidence='B',
             source_page='station_locations.pdf#page=13;station_names.pdf#page=1',
             map_evidence='sources/tram_pilot/osm_211_extension_raw.json;https://www.openstreetmap.org/way/30817599',
             review_note='한밭대로 도로 구간만 확인. 도면 승강장과 지도 사이의 확실한 대응점 부족. 주소·건물·버스정류장 좌표로 대체하지 않음.'),
        dict(station_no='218', station_name='정부청사(서구청·둔산경찰서·을지대병원)',
             latitude=f'{lat:.6f}', longitude=f'{lon:.6f}',
             position_type='platform_pair_centroid', confidence='A',
             source_page='station_locations.pdf#page=20;station_names.pdf#page=2',
             map_evidence='sources/tram_pilot/validation.json;https://www.openstreetmap.org/way/502541396;https://www.openstreetmap.org/way/502541394;https://www.openstreetmap.org/way/502531462;https://www.openstreetmap.org/way/502531463',
             review_note=f'공식 도면 양방향 승강장 영역의 면적가중 중심. 적합 3점·검사 5점 RMSE {rmse:.2f}m, 최대 {max(checks):.2f}m. 절대 위치 정확도와 최신 설계 변경 미검증.'),
    ]
    report = dict(scope='211/218 pilot; remaining stations not reviewed', date=inputs['date'],
                  crs='WGS84 / EPSG:4326; CSV latitude then longitude',
                  osm_snapshot=osm['osm3s']['timestamp_osm_base'], source_pdf_sha256=inputs['official_pdf_sha256'],
                  controls=controls, image_affine_matrix=matrix.tolist(),
                  platform_pixel_centroid=pixel.tolist(), platform_polygon_area_pixels=total_area,
                  check_rmse_m=rmse, check_max_m=max(checks),
                  alternative_fit_displacement_m=sensitivity,
                  fit_triangle_barycentric_weights=barycentric.tolist(),
                  outside_fit_triangle=bool(np.any(barycentric < 0)),
                  distance_to_fit_triangle_m=min(edge_distances) if np.any(barycentric < 0) else 0,
                  interpretation='Map-to-plan consistency only; not absolute positional accuracy or statistical confidence interval.',
                  grade_counts={'A': 1, 'B': 1, 'C': 0}, reviewed_count=2,
                  station_numbers_missing_from_45=[str(i) for i in range(201, 246) if str(i) not in {r['station_no'] for r in rows}],
                  duplicate_station_numbers=[], rows=rows)
    return rows, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/tram_stations_estimated.csv')
    parser.add_argument('--report', type=Path, default=EVIDENCE / 'validation.json')
    args = parser.parse_args()
    if args.output.exists() or args.report.exists():
        raise SystemExit('Output already exists; choose new --output and --report paths')
    rows, report = calculate()
    assert len(rows) == len({r['station_no'] for r in rows}) == 2
    with args.output.open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with args.report.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({'reviewed': 2, 'grade_counts': report['grade_counts'],
                      'check_rmse_m': report['check_rmse_m'],
                      'check_max_m': report['check_max_m'],
                      'alternative_fit_displacement_m': report['alternative_fit_displacement_m'],
                      'rows': rows}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
