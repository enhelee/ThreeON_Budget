import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from review_data import load_result, TABLES

class ExchangeTest(unittest.TestCase):
    def fixture(self):
        return {'schemaVersion': 1, 'amountUnit': 'KRW_THOUSAND', 'amountMatching': True,
                'reconciliation': {k: [['이름', '금액(천원)'], ['합성', 1.25]] for k in TABLES}}
    def test_amount_preserved(self):
        self.assertEqual(load_result(json.dumps(self.fixture()))['details'][1][1], 1.25)
    def test_unit_rejected(self):
        x = self.fixture(); x['amountUnit'] = 'KRW'
        with self.assertRaises(ValueError): load_result(json.dumps(x))
    def test_missing_table_rejected(self):
        x = self.fixture(); del x['reconciliation']['groups']
        with self.assertRaises(ValueError): load_result(json.dumps(x))
    def test_column_count_rejected(self):
        x = self.fixture(); x['reconciliation']['details'].append(['잘못된 행'])
        with self.assertRaises(ValueError): load_result(json.dumps(x))
    def test_text_only_rejected(self):
        x = self.fixture(); x['amountMatching'] = False
        with self.assertRaises(ValueError): load_result(json.dumps(x))

if __name__ == '__main__': unittest.main()
