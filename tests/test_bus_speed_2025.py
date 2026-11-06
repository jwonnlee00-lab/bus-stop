import csv
import hashlib
import importlib.util
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
spec = importlib.util.spec_from_file_location('bus_speed', ROOT / 'scripts/build_bus_speed_2025.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class BusSpeedTests(unittest.TestCase):
    def test_csv_coverage_and_pilot(self):
        with (DATA / 'bus_speed_2025.csv').open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            self.assertEqual(reader.fieldnames,['route_no','route_name','speed_morning','speed_midday',
                                               'speed_evening','speed_average','source_year','source_page'])
            rows = list(reader)
        self.assertEqual(len(rows),108)
        self.assertEqual(len({r['route_no'] for r in rows}),108)
        self.assertEqual(Counter(r['source_page'] for r in rows),
                         {'보고서 332; PDF 338':41,'보고서 333; PDF 339':41,'보고서 334; PDF 340':26})
        pilot = next(r for r in rows if r['route_no']=='106')
        self.assertEqual([float(pilot[k]) for k in builder.SPEEDS],[20.0,19.7,18.0,19.2])
        self.assertFalse(any(r['route_no'] in ['평균','전체 평균'] for r in rows))

    def test_changed_endpoints_held_and_missing_values_not_filled(self):
        obj = json.loads((DATA / 'bus_speed_2025_matching.json').read_text(encoding='utf-8'))
        records = obj['routes_2026']
        self.assertEqual(len(records),169)
        self.assertEqual(sum(r['metadata_match'] for r in records),54)
        for record in records:
            if not record['metadata_match']:
                self.assertTrue(all(v is None for v in record['speed_values_2025'].values()))
            self.assertFalse(record['automatic_application_allowed'])
        current = {r['rte_id']:r for r in records}
        self.assertTrue(current['30300041']['metadata_match'])
        self.assertEqual(current['30300088']['status'],'route_name_or_endpoints_differ_review_required')
        self.assertEqual(current['30300152']['status'],'route_name_or_endpoints_differ_review_required')
        self.assertEqual(current['30300148']['status'],'report_name_uncertain')

    def test_matcher_does_not_guess_aliases_or_mix_village_and_express(self):
        self.assertTrue(builder.endpoint_comparison('601번(비래동-구암동기점지)','601번(구암동기점지비래동)'))
        self.assertFalse(builder.endpoint_comparison('704번(원내차고지-보훈병원)','704번(원내동죽동종점)'))
        self.assertEqual(builder.route_number(dict(rte_no='1',rte_nm='1번(급행.원내동신안동)')),'급행1')
        self.assertEqual(builder.route_number(dict(rte_no='1',rte_nm='1번(마을.충대농대종점청벽산공원)')),'1')

    def test_original_files_and_numeric_review(self):
        report = json.loads((DATA / 'bus_speed_2025_validation.json').read_text(encoding='utf-8'))
        for name,digest in report['original_input_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),digest)
        numeric = report['numeric_review']
        self.assertEqual(numeric['ocr_digits_agree'] + numeric['ocr_disagreements_visually_resolved'],432)
        self.assertEqual(numeric['unresolved_numeric_cells'],0)
        self.assertEqual(report['numeric_uncertainties'],[])


if __name__ == '__main__':
    unittest.main()
