import csv
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('clean_bus', ROOT / 'scripts/clean_bus_routing.py')
clean = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clean)


def row(seq, stop):
    return dict(sttn_seq=str(seq), sttn_id=stop, sttn_nm=stop)


class CleaningTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(clean.normalized_name('원앙1.2단지'), clean.normalized_name('원앙 1,2단지'))
        self.assertNotEqual(clean.normalized_name('탑립동'), clean.normalized_name('탑립'))
        self.assertNotEqual(clean.normalized_name('대전복합터미널'), clean.normalized_name('장재리(태련암입구)'))

    def test_excluded_middle_stop_never_bridged(self):
        records = [row(1,'A'), row(2,'B'), row(3,'C'), row(4,'D')]
        accepted = {s:dict(sttn_nm=s) for s in ['A','C','D']}
        edges, gaps = clean.build_connections(records, accepted, True)
        self.assertEqual([(e['from_stop_id'],e['to_stop_id']) for e in edges], [('C','D')])
        self.assertEqual(len(gaps), 2)

    def test_absent_sequence_and_unknown_route(self):
        records = [row(1,'A'), row(3,'C')]
        accepted = {s:dict(sttn_nm=s) for s in ['A','C']}
        edges, gaps = clean.build_connections(records, accepted, True)
        self.assertFalse(edges)
        self.assertIn('missing_intermediate_sequence', gaps[0]['reasons'])
        edges, gaps = clean.build_connections([row(1,'A'),row(2,'C')], accepted, False)
        self.assertFalse(edges)
        self.assertIn('route_id_not_officially_verified',gaps[0]['reasons'])

    def test_duplicate_sequence_not_resolved_arbitrarily(self):
        records = [row(1,'A'),row(2,'B'),row(2,'C'),row(3,'D')]
        edges, gaps = clean.build_connections(records, {s:dict(sttn_nm=s) for s in 'ABCD'}, True)
        self.assertFalse(edges)
        self.assertTrue(all('ambiguous_sequence' in g['reasons'] for g in gaps))

    def test_saved_graph_only_has_original_consecutive_forward_edges(self):
        graph = json.loads((ROOT / 'data/bus_routing/bus_routing.json').read_text(encoding='utf-8'))
        with (ROOT / 'data/bus_route_stops.csv').open(encoding='utf-8-sig', newline='') as f:
            originals = {(r['opr_ymd'],r['rte_id'],r['sttn_seq']):r for r in csv.DictReader(f)}
        stop_ids = {s['stop_id'] for s in graph['stops']}
        checked = 0
        for route in graph['routes']:
            if not route['route_id_verified']:
                self.assertFalse(route['edges'])
            for edge in route['edges']:
                self.assertEqual(int(edge['to_seq']), int(edge['from_seq']) + 1)
                for prefix in ['from','to']:
                    key = route['operation_date'], route['rte_id'], edge[prefix+'_seq']
                    self.assertEqual(originals[key]['sttn_id'], edge[prefix+'_stop_id'])
                    self.assertIn(edge[prefix+'_stop_id'],stop_ids)
                checked += 1
            for segment in route['segments']:
                sequences = list(map(int,segment['sequences']))
                self.assertEqual(sequences,list(range(sequences[0],sequences[-1]+1)))
        self.assertGreater(checked, 8000)
        pilot = next(r for r in graph['routes'] if r['rte_id']=='30300041')
        available = {e['from_seq']:e for e in pilot['edges']}
        self.assertEqual(available['52']['from_stop_id'],'8001096')
        self.assertEqual(available['61']['to_stop_id'],'8002159')
        self.assertTrue(all(str(i) in available for i in range(52,62)))

    def test_report_accounts_for_all_pairs_and_preserves_inputs(self):
        graph = json.loads((ROOT / 'data/bus_routing/bus_routing.json').read_text(encoding='utf-8'))
        report = json.loads((ROOT / 'data/bus_routing/cleaning_report.json').read_text(encoding='utf-8'))
        for name, digest in report['source_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT / 'data' / name).read_bytes()).hexdigest(), digest)
        pairs = sum(max(0,len(r['occurrences'])-1) for r in graph['routes'])
        self.assertEqual(pairs, report['counts_after']['directed_edges'] + report['counts_after']['blocked_connections'])
        self.assertEqual(report['counts_before']['route_stop_records'],
                         report['counts_after']['eligible_route_stop_records'] + report['counts_after']['excluded_route_stop_records'])
        excluded = {a['sttn_id'] for a in report['stop_audit'] if not a['accepted']}
        self.assertFalse(excluded & {s['stop_id'] for s in graph['stops']})


if __name__ == '__main__':
    unittest.main()
