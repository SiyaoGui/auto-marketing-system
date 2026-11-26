import copy, json, tempfile, unittest
from pathlib import Path
from core import Ledger, validate_blueprint, normalize_note, match_references, prepare_media, ffmpeg

def fixture(path):
    asset={'id':'synthetic-test','local_path':str(path),'duration':4,'rights':'owned',
           'rights_evidence':'Generated color bars for software tests, not real business footage',
           'status':'available','brand_ids':['test-brand'],'topic_ids':['test-topic'],
           'allowed_platforms':['xiaohongshu'],'illustration':True,'scene_tags':['process']}
    plan={'schema_version':1,'project_id':'test-only','brand_id':'test-brand','topic_id':'test-topic',
          'reference_video_ids':[],'asset_ids':['synthetic-test'],'target_platform':'xiaohongshu',
          'aspect_ratio':'16:9','resolution':{'width':640,'height':360},'target_duration':4,'language':'zh',
          'scenes':[{'scene_id':'s1','start_time':0,'duration':4,'asset_id':'synthetic-test','source_in':0,'source_out':4,
                     'crop_mode':'contain','focal_point':[0.5,0.5],'text_overlay':'示意：软件测试画面',
                     'font_style':'body','text_position':[0.5,0.8],'animation':'none','transition':'cut',
                     'narration':'','audio_cue':'','creative_purpose':'验证素材引用与时长','is_illustration':True}],
          'subtitles':[],'typography':{'body':{'family':'sans-serif','size_ratio':0.05,'color':'#FFFFFF','stroke_color':'#000000','stroke_width':2}},
          'transitions':[],'audio':[],'brand_elements':[],
          'output_settings':{'container':'mp4','video_codec':'h264','fps':30,'audio_codec':'aac'},
          'approval_status':'approved','missing_materials':[]}
    return plan,{'synthetic-test':asset}

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.file=self.root/'test.mp4';self.file.write_bytes(b'validation fixture only')
        self.plan,self.assets=fixture(self.file)
    def tearDown(self):self.tmp.cleanup()
    def test_valid_structure(self):self.assertEqual([],validate_blueprint(self.plan,self.assets))
    def test_missing_asset(self):self.assertTrue(validate_blueprint(self.plan,{}))
    def test_unknown_rights(self):
        self.assets['synthetic-test']['rights']='unknown';self.assertTrue(validate_blueprint(self.plan,self.assets))
    def test_wrong_brand(self):
        self.plan['brand_id']='other';self.assertTrue(validate_blueprint(self.plan,self.assets))
    def test_expired_rights(self):
        self.assets['synthetic-test']['expires_on']='2000-01-01';self.assertTrue(validate_blueprint(self.plan,self.assets))
    def test_time_out_of_range(self):
        self.plan['scenes'][0]['source_out']=99;self.assertTrue(validate_blueprint(self.plan,self.assets))
    def test_missing_label(self):
        self.plan['scenes'][0]['text_overlay']='';self.assertTrue(validate_blueprint(self.plan,self.assets))
    def test_unapproved(self):
        self.plan['approval_status']='draft';self.assertTrue(validate_blueprint(self.plan,self.assets))
    def test_missing_font(self):
        self.plan['scenes'][0]['font_style']='missing';self.assertTrue(validate_blueprint(self.plan,self.assets))
    def test_nan(self):
        self.plan['target_duration']=float('nan');self.assertTrue(validate_blueprint(self.plan,self.assets))
    def test_unknown_reference(self):
        self.plan['reference_video_ids']=['invented'];self.assertTrue(validate_blueprint(self.plan,self.assets))
    def test_unknown_metrics_stay_null(self):
        note=normalize_note({'id':'test','url':'https://example.com/test','type':'video'},'data_dino/xiaohongshu-rednote-note-scraper','test')
        self.assertIsNone(note['likes']);self.assertIsNone(note['views'])
    def test_formatted_metrics_rejected(self):
        with self.assertRaises(ValueError):normalize_note({'id':'x','url':'https://example.com','engagement':{'liked_count':'1.2万'}},'data_dino/xiaohongshu-rednote-note-scraper','test')
    def test_duplicate_job(self):
        ledger=Ledger(self.root/'state.db')
        self.assertTrue(ledger.claim('key','analysis',{'x':1}));self.assertFalse(ledger.claim('key','analysis',{'x':1}))
        with self.assertRaises(ValueError):ledger.claim('key','analysis',{'x':2})
        ledger.db.close()
    def test_unknown_outcome_no_retry(self):
        ledger=Ledger(self.root/'state.db');ledger.claim('key','notion',{})
        ledger.finish('key',{},'uncertain');self.assertFalse(ledger.claim('key','notion',{},True));ledger.db.close()
    def test_retry_limit(self):
        ledger=Ledger(self.root/'state.db');self.assertTrue(ledger.claim('x','read',{}))
        for _ in range(2):ledger.finish('x',{},'failed');self.assertTrue(ledger.claim('x','read',{},True))
        ledger.finish('x',{},'failed');self.assertFalse(ledger.claim('x','read',{},True));ledger.db.close()
    def test_budget_limit(self):
        ledger=Ledger(self.root/'state.db');ledger.reserve('a',400)
        with self.assertRaises(ValueError):ledger.reserve('b',101)
        with self.assertRaises(ValueError):ledger.reserve('a',1)
        ledger.reserve('c',100);ledger.db.close()
    def test_empty_matching(self):self.assertEqual([],match_references('test-brand','test-topic',[],[]))
    def test_reference_requires_assets_and_evidence(self):
        refs=[{'id':'ref','brand_ids':['test-brand'],'topic_ids':['test-topic'],'evidence':['test-only'],'required_scene_tags':['process']}]
        self.assertEqual([],match_references('test-brand','test-topic',refs,[]))
        self.assertEqual(1,len(match_references('test-brand','test-topic',refs,list(self.assets.values()))))
        refs[0]['evidence']=[];self.assertEqual([],match_references('test-brand','test-topic',refs,list(self.assets.values())))
    def test_media_authorization(self):
        with self.assertRaises(ValueError):prepare_media(self.file,self.root/'out',{})

if __name__=='__main__':unittest.main(verbosity=2)
