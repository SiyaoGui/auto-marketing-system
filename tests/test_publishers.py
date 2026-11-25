import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from engine.core import ROOT, Store, read_json, settings, stamp
from engine import publishers


def response(body=None, headers=None, status=200):
    result=Mock(status_code=status,headers=headers or {})
    if body is None:
        result.json.side_effect=ValueError('empty body')
    else:
        result.json.return_value=body
    return result


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/'output').mkdir()
        self.file=self.root/'output/video.mp4'
        self.file.write_bytes(b'unit test video bytes')
        self.cfg=settings(ROOT)
        self.brand=read_json(ROOT/'brands/demo.json')
        self.brand.update(enabled=True,demo=False,auto_publish=True)
        self.brand['youtube'].update(enabled=True,channel_id='UC_TEST',privacy='private')
        self.brand['instagram'].update(enabled=True,account_id='1234')
        self.job={'id':'job','remote':{},'payload':{'demo':False,'video':'output/video.mp4',
            'video_sha256':hashlib.sha256(self.file.read_bytes()).hexdigest(),
            'title':'Test title','caption':'Test caption','target_account':'UC_TEST'}}

    def tearDown(self):
        self.tmp.cleanup()

    @patch('engine.publishers.youtube_token',return_value='not-a-real-token')
    @patch('engine.publishers.requests.put')
    @patch('engine.publishers.requests.post')
    @patch('engine.publishers.requests.get')
    def test_youtube_empty_session_body_and_private_state(self,get,post,put,token):
        get.side_effect=[response({'items':[{'id':'UC_TEST'}]}),
            response({'items':[{'snippet':{'channelId':'UC_TEST'},'status':{'uploadStatus':'processed','privacyStatus':'private'}}]})]
        post.return_value=response(headers={'Location':'https://www.googleapis.com/upload/test'})
        put.return_value=response({'id':'VIDEO_TEST'})
        checkpoints=[]
        state,remote=publishers.youtube(self.root,self.cfg,self.brand,self.job,lambda r:checkpoints.append(dict(r)))
        self.assertEqual(state,'uploaded_private')
        self.assertEqual(remote['video_id'],'VIDEO_TEST')
        self.assertEqual(post.call_count,1)
        self.assertNotIn('session_url',remote)

    @patch('engine.publishers.youtube_token',return_value='not-a-real-token')
    @patch('engine.publishers.requests.post')
    @patch('engine.publishers.requests.get')
    def test_existing_youtube_video_only_polled(self,get,post,token):
        self.job['remote']={'phase':'processing','video_id':'VIDEO_TEST'}
        get.side_effect=[response({'items':[{'id':'UC_TEST'}]}),response({'items':[{'snippet':{'channelId':'UC_TEST'},'status':{'uploadStatus':'processed','privacyStatus':'public'}}]})]
        state,_=publishers.youtube(self.root,self.cfg,self.brand,self.job,lambda r:None)
        self.assertEqual(state,'published')
        post.assert_not_called()

    @patch('engine.publishers.youtube_token',return_value='not-a-real-token')
    @patch('engine.publishers.requests.post')
    @patch('engine.publishers.requests.get')
    def test_wrong_channel_prevents_mutation(self,get,post,token):
        get.return_value=response({'items':[{'id':'WRONG_CHANNEL'}]})
        with self.assertRaises(publishers.Blocked):
            publishers.youtube(self.root,self.cfg,self.brand,self.job,lambda r:None)
        post.assert_not_called()

    def test_changed_file_rejected(self):
        self.file.write_bytes(b'changed')
        with self.assertRaises(publishers.Blocked):
            publishers.ensure_video(self.root,self.job)

    @patch('engine.publishers.instagram_token',return_value='not-a-real-token')
    @patch('engine.publishers.requests.post')
    @patch('engine.publishers.requests.get')
    def test_instagram_waits_for_processing(self,get,post,token):
        self.job['payload']['target_account']='1234'
        self.job['remote']={'phase':'processing','container_id':'555'}
        get.side_effect=[response({'id':'1234'}),response({'status_code':'IN_PROGRESS'})]
        state,_=publishers.instagram(self.root,self.cfg,self.brand,self.job,lambda r:None)
        self.assertEqual(state,'submitted')
        post.assert_not_called()

    @patch('engine.publishers.instagram_token',return_value='not-a-real-token')
    @patch('engine.publishers.requests.post')
    @patch('engine.publishers.requests.get')
    def test_instagram_publish_confirmed_with_permalink(self,get,post,token):
        self.job['payload']['target_account']='1234'
        self.job['remote']={'phase':'processing','container_id':'555'}
        get.side_effect=[response({'id':'1234'}),response({'status_code':'FINISHED'}),response({'id':'666','permalink':'https://www.instagram.com/reel/test/'})]
        post.return_value=response({'id':'666'})
        state,remote=publishers.instagram(self.root,self.cfg,self.brand,self.job,lambda r:None)
        self.assertEqual(state,'published')
        self.assertEqual(remote['media_id'],'666')
        self.assertEqual(post.call_count,1)

    @patch('engine.publishers.instagram_token',return_value='not-a-real-token')
    @patch('engine.publishers.requests.post')
    @patch('engine.publishers.requests.get')
    def test_instagram_uncertain_post_not_repeated(self,get,post,token):
        self.job['payload']['target_account']='1234'
        self.job['remote']={'phase':'publish_attempted','container_id':'555'}
        get.return_value=response({'id':'1234'})
        with self.assertRaises(publishers.Blocked):
            publishers.instagram(self.root,self.cfg,self.brand,self.job,lambda r:None)
        post.assert_not_called()

    @patch('engine.publishers.youtube')
    def test_worker_preserves_unknown_on_mutation_timeout(self,adapter):
        store=Store(self.root)
        store.enqueue('b',self.brand,'youtube','hash',self.job['payload'],'2020-01-01T00:00:00+00:00')
        def uncertain(root,cfg,brand,job,checkpoint):
            checkpoint({'phase':'upload_attempted'})
            raise TimeoutError('simulated network ambiguity')
        adapter.side_effect=uncertain
        outcome=publishers.dispatch(self.root,self.cfg,store,[self.brand])
        self.assertEqual(outcome[0]['status'],'unknown')
        self.assertIsNone(store.claim())

    @patch('engine.publishers.youtube')
    def test_worker_can_retry_known_read_phase(self,adapter):
        store=Store(self.root)
        ident=store.enqueue('b',self.brand,'youtube','hash',self.job['payload'],'2020-01-01T00:00:00+00:00')
        store.checkpoint(ident,{'phase':'processing','video_id':'id'})
        adapter.side_effect=TimeoutError('simulated read timeout')
        outcome=publishers.dispatch(self.root,self.cfg,store,[self.brand])
        self.assertEqual(outcome[0]['status'],'submitted')


if __name__=='__main__':
    unittest.main()
