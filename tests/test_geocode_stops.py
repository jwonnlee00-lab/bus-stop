"""Exercise ID safeguards and missing/invalid coordinate handling offline."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from geocode_stops import parse_response


def response(node='8001096', lat='36.349014', lon='127.43567'):
    return f'''<ServiceResult><msgHeader><headerCd>0</headerCd></msgHeader>
    <msgBody><itemList><BUS_NODE_ID>{node}</BUS_NODE_ID>
    <BUSSTOP_NM>복합터미널</BUSSTOP_NM><GPS_LATI>{lat}</GPS_LATI>
    <GPS_LONG>{lon}</GPS_LONG></itemList></msgBody></ServiceResult>'''


class ResponseTests(unittest.TestCase):
    def test_exact_id(self):
        result = parse_response(response(), '8001096')
        self.assertEqual(result['status'], 'matched')
        self.assertEqual(result['latitude'], '36.349014')

    def test_same_name_different_id_is_rejected(self):
        result = parse_response(response(node='8001097'), '8001096')
        self.assertEqual(result['status'], 'id_mismatch')
        self.assertNotIn('latitude', result)

    def test_missing_coordinate(self):
        self.assertEqual(parse_response(response(lat=''), '8001096')['status'], 'missing_coordinates')

    def test_invalid_coordinates(self):
        for lat, lon in [('127.43567', '36.349014'), ('NaN', '127'), ('0', '0'), ('abc', '127')]:
            with self.subTest(lat=lat, lon=lon):
                self.assertEqual(parse_response(response(lat=lat, lon=lon), '8001096')['status'], 'invalid_coordinates')

    def test_no_station(self):
        xml = '<ServiceResult><msgHeader><headerCd>0</headerCd></msgHeader><msgBody/></ServiceResult>'
        self.assertEqual(parse_response(xml, '8001096')['status'], 'not_found')

    def test_api_error_is_not_not_found(self):
        xml = '<ServiceResult><msgHeader><headerCd>2</headerCd></msgHeader></ServiceResult>'
        self.assertEqual(parse_response(xml, '8001096')['status'], 'api_error')

    def test_actual_empty_response(self):
        xml = '<ServiceResult><msgHeader><headerCd>4</headerCd><itemCnt>0</itemCnt></msgHeader><msgBody/></ServiceResult>'
        self.assertEqual(parse_response(xml, '2900175')['status'], 'not_found')

    def test_duplicate_id_is_rejected(self):
        xml = response().replace('</msgBody>', response().split('<msgBody>')[1].split('</msgBody>')[0] + '</msgBody>')
        self.assertEqual(parse_response(xml, '8001096')['status'], 'ambiguous_id')


if __name__ == '__main__':
    unittest.main()
