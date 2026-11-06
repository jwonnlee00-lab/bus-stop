import hashlib
import importlib.util
import json
import math
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('distances',ROOT / 'scripts/build_bus_distances.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class BusDistanceTests(unittest.TestCase):
    def test_haversine_reference_cases(self):
        self.assertEqual(builder.haversine_km((0,0),(0,0)),0)
        self.assertAlmostEqual(builder.haversine_km((0,0),(0,1)),111.1950802,places=6)
        self.assertAlmostEqual(builder.haversine_km((0,0),(0,180)),math.pi*builder.EARTH_RADIUS_KM,places=6)
        with self.assertRaisesRegex(ValueError,'missing_coordinates'):
            builder.coordinate(None)
        for point in [dict(latitude=91,longitude=127),dict(latitude=float('nan'),longitude=127),dict(latitude=36,longitude=181)]:
            with self.assertRaisesRegex(ValueError,'invalid_coordinates'):
                builder.coordinate(point)

    def test_all_edges_preserve_source_order_and_exclude_blocked(self):
        graph = json.loads(builder.SOURCE.read_bytes())
        result = json.loads(builder.OUTPUT.read_bytes())
        records = result['distances']
        self.assertEqual(len(records),8756)
        expected = [{**e,'rte_id':r['rte_id'],'operation_date':r['operation_date']} for r in graph['routes'] for e in r['edges']]
        seen = set()
        blocked = {builder.edge_key(r,e) for r in graph['routes'] for e in r['blocked_connections']}
        for actual,original in zip(records,expected):
            for name,value in original.items():
                self.assertEqual(actual[name],value)
            key = builder.edge_key(actual,actual)
            self.assertNotIn(key,seen)
            self.assertNotIn(key,blocked)
            seen.add(key)
        self.assertEqual(result['source_sha256'],hashlib.sha256(builder.SOURCE.read_bytes()).hexdigest())
        self.assertEqual(result['validation']['failure_count'],0)

    def test_independent_spherical_cosine_check_and_four_decimals(self):
        graph = json.loads(builder.SOURCE.read_bytes())
        text = builder.OUTPUT.read_text(encoding='utf-8')
        result = json.loads(text)
        stops = {s['stop_id']:s for s in graph['stops']}
        for edge in result['distances']:
            a,b = stops[edge['from_stop_id']],stops[edge['to_stop_id']]
            lat1,lat2 = map(math.radians,(a['latitude'],b['latitude']))
            delta_lon = math.radians(a['longitude']-b['longitude'])
            cos_angle = math.sin(lat1)*math.sin(lat2)+math.cos(lat1)*math.cos(lat2)*math.cos(delta_lon)
            independent = builder.EARTH_RADIUS_KM*math.acos(max(-1,min(1,cos_angle)))
            self.assertLessEqual(abs(edge['distance_km']-independent),0.00015)
        tokens = re.findall(r'"distance_km": ([^,\n]+)',text)
        self.assertEqual(len(tokens),8756+result['validation']['review_count'])
        self.assertTrue(all(re.fullmatch(r'\d+\.\d{4}',token) for token in tokens))
        self.assertEqual(result['validation']['review_count'],6)


if __name__ == '__main__':
    unittest.main()
