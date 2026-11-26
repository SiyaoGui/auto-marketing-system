"""Regression checks against the actual captured run; never calls paid APIs."""
import copy, json, unittest
from pathlib import Path
from core import normalize_batch, normalize_note

ROOT = Path(__file__).resolve().parent
ACTOR = 'hyperbach/xiaohongshu-scraper'

class LiveDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=json.loads((ROOT/'live-test/apify-run-cQyC37yEd8EOE3aD7.json').read_text('utf-8-sig'))
    def test_actual_run_missing_links_are_quarantined(self):
        result=normalize_batch(self.rows,ACTOR,None)
        self.assertEqual({'input':13,'accepted':1,'quarantined':10,'ignored':2,'duplicates':0},result['summary'])
        own=result['accepted'][0]
        self.assertEqual('6abbd750000000000f03ad4d',own['note_id'])
        self.assertEqual((12,7,3,4),(own['likes'],own['saves'],own['comments'],own['shares']))
        self.assertIsNone(own['views'])
    def test_rerun_deduplicates_actual_note(self):
        result=normalize_batch(self.rows+self.rows,ACTOR,None)
        self.assertEqual(1,len(result['accepted']))
        self.assertEqual(1,len(result['duplicates']))
    def test_unknown_and_rounded_metrics_are_preserved(self):
        row=copy.deepcopy(self.rows[0]);row['likes']=None;row['countsExact']=False;row['likesText']='unknown'
        result=normalize_note(row,ACTOR,None)
        self.assertIsNone(result['likes']);self.assertFalse(result['counts_exact'])
        self.assertEqual('unknown',result['raw_metrics']['likes'])
    def test_external_or_mismatched_links_rejected(self):
        for url in ['https://example.com/'+self.rows[0]['id'],'https://www.xiaohongshu.com/explore/other']:
            row=copy.deepcopy(self.rows[0]);row['url']=url
            with self.assertRaises(ValueError):normalize_note(row,ACTOR,None)
    def test_empty_and_failed_data_are_not_successful_notes(self):
        self.assertTrue(normalize_batch([],ACTOR,None)['empty'])
        row=copy.deepcopy(self.rows[0]);row['status']='error'
        self.assertEqual(1,len(normalize_batch([row],ACTOR,None)['quarantined']))

if __name__=='__main__':unittest.main(verbosity=2)
