import csv
import json
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from engine import content, pipeline, publishers, trends
from engine.core import ROOT, Store, due_time, read_json, safe_path, settings, stamp, write_json


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for directory in ('config', 'data', 'brands'):
            shutil.copytree(ROOT / directory, self.root / directory)
        self.brand = read_json(self.root / 'brands/demo.json')
        self.cfg = settings(self.root)
        self.store = Store(self.root)
        self.payload = {'demo': False, 'video': 'output/test.mp4'}

    def tearDown(self):
        self.tmp.cleanup()

    def enqueue(self, index=0, platform='youtube', payload=None):
        b = {**self.brand, 'demo': False, 'auto_publish': True}
        return self.store.enqueue('batch' + str(index), b, platform, 'hash' + str(index), payload or self.payload, stamp(datetime(2020,1,1,tzinfo=timezone.utc)))

    def test_same_day_batch_runs_once(self):
        first = self.store.begin_batch('a', '2026-11-14', 0)
        self.assertIsNotNone(first)
        self.assertIsNone(self.store.begin_batch('a', '2026-11-14', 0))
        self.store.end_batch(first, {'topic': 'x'})
        self.assertIsNone(self.store.begin_batch('a', '2026-11-14', 0))

    def test_failed_generation_can_retry(self):
        ident = self.store.begin_batch('a', '2026-11-14', 0)
        self.store.end_batch(ident, error='model offline')
        self.assertEqual(ident, self.store.begin_batch('a', '2026-11-14', 0))

    def test_content_dedup_per_brand_platform(self):
        self.assertIsNotNone(self.enqueue())
        self.assertIsNone(self.store.enqueue('different-day', self.brand, 'youtube', 'hash0', self.payload, stamp()))
        self.assertIsNotNone(self.enqueue(platform='instagram'))

    def test_claim_atomic_with_two_workers(self):
        self.enqueue()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: Store(self.root).claim(), range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_future_job_waits(self):
        self.store.enqueue('b', {**self.brand, 'demo': False, 'auto_publish': True}, 'youtube', 'x', self.payload, stamp(datetime(2030,1,1,tzinfo=timezone.utc)))
        self.assertIsNone(self.store.claim(datetime(2026,11,14,tzinfo=timezone.utc)))

    def test_crashed_remote_send_is_unknown_not_retried(self):
        ident = self.enqueue()
        self.store.claim(datetime(2026,11,14,tzinfo=timezone.utc))
        self.assertIsNone(self.store.claim(datetime(2026,11,14,1,tzinfo=timezone.utc)))
        self.assertEqual(self.store.jobs()[0]['status'], 'unknown')

    def test_submitted_poll_is_delayed(self):
        ident = self.enqueue()
        self.store.finish(ident, 'submitted', {'video_id': 'abc'})
        self.assertIsNone(self.store.claim())

    def test_demo_cannot_be_approved(self):
        ident = self.store.enqueue('demo', self.brand, 'youtube', 'demo', {'demo': True}, stamp())
        with self.assertRaises(ValueError):
            self.store.approve(ident)

    def test_demo_cannot_reach_upload(self):
        with self.assertRaises(publishers.Blocked):
            publishers.ensure_video(self.root, {'payload': {'demo': True}})

    def test_manual_platform_is_not_claimed(self):
        self.enqueue(platform='tiktok')
        self.assertIsNone(self.store.claim())
        self.assertEqual(self.store.jobs()[0]['status'], 'manual')

    def test_asset_scope_and_rights(self):
        (self.root / 'assets').mkdir()
        (self.root / 'assets/p.png').write_bytes(b'data')
        rows = [dict(id='a',brand_id='demo',path='assets/p.png',rights='owned',commercial_use=True,evidence='self shot'),
                dict(id='b',brand_id='other',path='assets/p.png',rights='owned',commercial_use=True,evidence='self shot'),
                dict(id='c',brand_id='demo',path='assets/p.png',rights='owned',commercial_use=False,evidence='self shot')]
        write_json(self.root / 'data/assets.json', rows)
        self.assertEqual([a['id'] for a in content.eligible_assets(self.root, self.brand)], ['a'])

    def test_path_traversal_blocked(self):
        with self.assertRaises(ValueError):
            safe_path(self.root, '../outside.txt')

    def test_stale_trend_not_labelled_current(self):
        with (self.root / 'data/trends.csv').open('a',encoding='utf-8',newline='') as f:
            csv.writer(f).writerow(['demo','old','x','https://example.com','2000-01-01T00:00:00+00:00','DK','20','10','24'])
        self.assertEqual(trends.collect(self.root,self.cfg,self.brand,offline=True)['signals'], [])

    def test_rss_growth_is_not_invented(self):
        xml = '<rss><channel><item><title>Topic</title><pubDate>Sat, 14 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>'
        row = trends.parse_rss(xml,'google_trends')[0]
        self.assertIsNone(row['growth'])
        self.assertEqual(row['signal_type'],'search_trend')

    def test_growth_requires_comparable_nonzero_previous(self):
        self.assertIsNone(trends.growth(10,0))
        self.assertIsNone(trends.growth('nan',10))
        self.assertEqual(trends.growth(20,10),1)

    def test_copenhagen_dst(self):
        self.assertIn('17:00:00',due_time(self.cfg,'2026-11-14'))
        self.assertIn('16:00:00',due_time(self.cfg,'2026-07-14'))

    def test_script_claim_guard(self):
        script = content.generate(self.root,self.cfg,self.brand,{'topic':'x'},[],demo=True)
        script['scenes'][0]['narration']='100% guaranteed'
        with self.assertRaises(ValueError):
            content.validate_script(script,self.brand,set())

    def test_tracking_keeps_existing_parameters(self):
        url=content.tracking_url('https://example.com/?product=a','brand','youtube','batch')
        self.assertIn('product=a',url)
        self.assertIn('utm_source=youtube',url)

    def test_no_real_brands_does_not_render_or_publish(self):
        with patch('engine.media.render') as render:
            result=pipeline.run(self.root,offline=True)
        render.assert_not_called()
        self.assertEqual(result[0]['status'],'blocked')

    def test_metrics_latest_snapshot_not_double_counted(self):
        ident=self.enqueue(payload={'demo':False,'topic':'video'})
        with (self.root/'data/metrics.csv').open('a',encoding='utf-8',newline='') as f:
            writer=csv.writer(f)
            writer.writerow([ident,'2026-11-13',100,10,2,1,0,0,'DKK'])
            writer.writerow([ident,'2026-11-14',200,20,3,2,1,30,'DKK'])
        result=pipeline.metrics(self.root,self.store)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['views'],200)

    def test_report_escapes_html(self):
        ident=self.enqueue()
        self.store.finish(ident,'blocked',error='<script>alert(1)</script>')
        path=pipeline.report(self.root)
        self.assertNotIn('<script>',Path(path).read_text(encoding='utf-8'))

    def test_backup_readable(self):
        self.enqueue()
        self.store.backup()
        self.assertEqual(len(list((self.root/'state/backups').glob('*.sqlite3'))),1)


if __name__=='__main__':
    unittest.main()
