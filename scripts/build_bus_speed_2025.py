"""Export visually transcribed report rows and conservative 2026 matching audit."""
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
EVIDENCE = DATA / 'sources/bus_speed_2025'
SPEEDS = ['speed_morning', 'speed_midday', 'speed_evening', 'speed_average']


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFC', text) if not c.isspace() and not unicodedata.category(c).startswith('P'))


def route_number(route):
    number = route['rte_no'] or re.match(r'([^번]+)번', route['rte_nm'])[1]
    # The original route register has both village 1/3 and express 1/3.
    if '급행' in route['rte_nm'] or '(급.' in route['rte_nm']:
        number = '급행' + number.removeprefix('급행')
    return number


def endpoint_comparison(report_name, current_name):
    report_body = report_name[report_name.index('(') + 1:-1]
    a, b = report_body.split('-', 1)
    current_body = current_name[current_name.index('(') + 1:-1]
    for prefix in ['급행.', '급.']:
        current_body = current_body.removeprefix(prefix)
    return normalize(current_body) in {normalize(a + b), normalize(b + a)}


def main():
    outputs = [DATA / 'bus_speed_2025.csv', DATA / 'bus_speed_2025_matching.json', DATA / 'bus_speed_2025_validation.json']
    if any(p.exists() for p in outputs):
        raise SystemExit('Refusing to overwrite existing speed outputs.')
    originals = list(DATA.glob('*.csv')) + [DATA / 'bus_routing/bus_routing.json']
    before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    with (EVIDENCE / 'transcribed_rows.tsv').open(encoding='utf-8', newline='') as f:
        raw = list(csv.DictReader(f, delimiter='\t'))
    assert Counter(r['pdf_page'] for r in raw) == {'338':41, '339':41, '340':26}
    assert len({r['route_no'] for r in raw}) == len(raw) == 108
    for row in raw:
        assert all(re.fullmatch(r'\d{2}\.\d', row[k]) for k in SPEEDS)
        values = [float(row[k]) for k in SPEEDS]
        assert all(0 < value < 100 for value in values)
        assert min(values[:3]) <= values[3] <= max(values[:3])
    pilot = next(r for r in raw if r['route_no'] == '106')
    assert [pilot[k] for k in SPEEDS] == ['20.0','19.7','18.0','19.2']
    rows = [dict(route_no=r['route_no'], route_name=r['route_name'],
                 **{k:r[k] for k in SPEEDS}, source_year='2025',
                 source_page=f"보고서 {int(r['pdf_page'])-6}; PDF {r['pdf_page']}") for r in raw]
    graph = json.loads((DATA / 'bus_routing/bus_routing.json').read_text(encoding='utf-8'))
    by_number = {r['route_no']:r for r in rows}
    matches = []
    for route in graph['routes']:
        number = route_number(route)
        report = by_number.get(number)
        status = ('not_in_2025_report' if report is None else
                  'report_name_uncertain' if '[판독불확실]' in report['route_name'] else
                  'route_id_unverified' if not route['route_id_verified'] else
                  'number_and_named_endpoints_match' if endpoint_comparison(report['route_name'], route['rte_nm']) else
                  'route_name_or_endpoints_differ_review_required')
        matched = status == 'number_and_named_endpoints_match'
        matches.append(dict(rte_id=route['rte_id'], route_no_2026=route['rte_no'],
                            route_name_2026=route['rte_nm'], comparison_route_no=number,
                            report_route_no=report['route_no'] if report else None,
                            report_route_name=report['route_name'] if report else None,
                            status=status, metadata_match=matched,
                            automatic_application_allowed=False,
                            full_stop_sequence_stability='not_verifiable_from_speed_table',
                            speed_values_2025={k:float(report[k]) if matched else None for k in SPEEDS},
                            source_page=report['source_page'] if report else None,
                            current_route_has_routing_edges=route['routing_eligible']))
    report_matches = []
    for row in rows:
        candidates = [m for m in matches if m['comparison_route_no'] == row['route_no']]
        report_matches.append(dict(route_no=row['route_no'],
                                   matched_route_ids=[m['rte_id'] for m in candidates if m['metadata_match']],
                                   candidate_route_ids=[m['rte_id'] for m in candidates],
                                   review_reasons=sorted({m['status'] for m in candidates if not m['metadata_match']}) if candidates else ['no_2026_route_number']))
    # Preserve totals outside the route CSV, so they can never become fallback speeds.
    summary = dict(
        source_pdf='C:/Users/User/Downloads/2025 대전광역시 교통현황조사 및 분석 보고서업로드용.pdf',
        source_pdf_sha256=hashlib.sha256(Path('C:/Users/User/Downloads/2025 대전광역시 교통현황조사 및 분석 보고서업로드용.pdf').read_bytes()).hexdigest(),
        source_pages=dict(pdf=[337,338,339,340], printed=[331,332,333,334], graph_only_pdf_page=337),
        extraction_method='이미지 기반 PDF를 렌더링하고 108개 행을 직접 전사. Windows 한국어 OCR의 위치별 숫자와 대조 후 원본 이미지 확인. OCR을 최종 값으로 자동 채택하지 않음.',
        units='km/h', periods=dict(morning='07:00–09:00', midday='12:00–14:00', evening='17:00–19:00'),
        extracted_route_count=len(rows), table_route_rows_by_pdf_page={'338':41,'339':41,'340':26},
        numeric_review=dict(total_cells=432, ocr_digits_agree=368, ocr_disagreements_visually_resolved=64,
                            unresolved_numeric_cells=0, evidence='data/sources/bus_speed_2025/ocr_comparison.json',
                            column_order=['오전','낮','오후','전체 평균'], visual_source_review_completed=True),
        category_counts={'급행':4,'도시':70,'외곽':34}, missing_table_rows=[], duplicate_route_numbers=[],
        numeric_uncertainties=[], name_uncertainties=[dict(route_no='33-2', field='route_name',
            note='PDF 340쪽 도착지의 마지막 글자가 동/창으로 불명확해 [판독불확실]로 보존. 속도 네 값은 판독 가능. 자동 연결 보류.')],
        report_summary_rows=[dict(category='급행',values=[23.0,23.0,21.1,22.4],pdf_page=338),
                             dict(category='도시',values=[20.6,20.3,18.7,19.9],pdf_page=339),
                             dict(category='외곽',values=[25.7,25.0,24.1,24.9],pdf_page=340),
                             dict(category='전체',values=[22.3,21.9,20.5,21.6],pdf_page=340)],
        route_106={k:float(pilot[k]) for k in SPEEDS},
        matching_counts=dict(target_2026_route_ids=len(matches), metadata_matched_ids=sum(m['metadata_match'] for m in matches),
                             unmatched_ids=sum(not m['metadata_match'] for m in matches),
                             matched_report_numbers=sum(bool(r['matched_route_ids']) for r in report_matches),
                             unmatched_report_numbers=sum(not r['matched_route_ids'] for r in report_matches),
                             reasons=dict(Counter(m['status'] for m in matches))),
        matching_limit='번호와 표기된 양 끝 지점이 일치한 경우만 연결 후보로 인정. 약칭·시설 별명·다른 ID·노선 번호를 추정 변환하지 않음. 2025년 전체 경유 순서는 표에 없어 중간 구간 변경을 검증할 수 없으므로 자동 적용은 전부 보류. 보고서에 없는 노선과 보류 노선의 값은 null이며 전체 평균 대체 없음.',
        original_input_sha256=before,
        originals_unchanged=all(hashlib.sha256((ROOT / n).read_bytes()).hexdigest()==h for n,h in before.items()))
    assert summary['originals_unchanged']
    with outputs[0].open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    for path, content in [(outputs[1],dict(routes_2026=matches, report_routes=report_matches)),(outputs[2],summary)]:
        with path.open('x', encoding='utf-8') as f:
            json.dump(content,f,ensure_ascii=False,indent=2); f.write('\n')
    print(json.dumps(summary['matching_counts'],ensure_ascii=False))


if __name__ == '__main__':
    main()
