"""Local validation and media preparation; no paid API calls or publishing."""
from __future__ import annotations
import argparse, hashlib, json, math, re, sqlite3, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
from jsonschema import Draft202012Validator
import imageio_ffmpeg

def stable_key(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        return False
    if isinstance(value, dict):
        return all(finite(v) for v in value.values())
    if isinstance(value, list):
        return all(finite(v) for v in value)
    return True

def validate_blueprint(plan, assets, references=None, require_approval=True):
    errors = []
    schema = json.loads((ROOT / 'blueprint.schema.json').read_text('utf-8'))
    if not finite(plan):
        return ['Non-finite number']
    errors.extend(f'{list(e.path)}: {e.message}' for e in Draft202012Validator(schema).iter_errors(plan))
    if errors:
        return errors
    if require_approval and plan['approval_status'] != 'approved':
        errors.append('Human approval required')
    if plan['missing_materials']:
        errors.append('Missing materials must be resolved')
    width, height = plan['resolution']['width'], plan['resolution']['height']
    a, b = map(int, plan['aspect_ratio'].split(':'))
    if width * b != height * a or width % 2 or height % 2:
        errors.append('Resolution/aspect ratio mismatch or odd H264 dimensions')
    refmap = references or {}
    for rid in plan['reference_video_ids']:
        ref = refmap.get(rid)
        if not ref or plan['brand_id'] not in ref.get('brand_ids', []) or not ref.get('evidence'):
            errors.append(f'Unverified reference: {rid}')
    used = {s['asset_id'] for s in plan['scenes']} | {a['asset_id'] for a in plan['audio']} | {b['asset_id'] for b in plan['brand_elements']}
    if used != set(plan['asset_ids']):
        errors.append('Asset manifest differs from actual references')
    today = datetime.now(timezone.utc).date().isoformat()
    for aid in used:
        asset = assets.get(aid)
        if not asset:
            errors.append(f'Missing asset: {aid}')
            continue
        if asset.get('rights') not in ['owned', 'licensed'] or not asset.get('rights_evidence'):
            errors.append(f'Unverified rights: {aid}')
        if asset.get('status') != 'available' or plan['brand_id'] not in asset.get('brand_ids', []):
            errors.append(f'Unavailable or wrong-brand asset: {aid}')
        if plan['target_platform'] not in asset.get('allowed_platforms', []):
            errors.append(f'Platform not authorized: {aid}')
        if asset.get('expires_on') and asset['expires_on'] < today:
            errors.append(f'Expired asset: {aid}')
        path = Path(asset.get('local_path', ''))
        if not path.is_file():
            errors.append(f'Local file missing: {aid}')
        elif asset.get('sha256') and hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
            errors.append(f'Hash mismatch: {aid}')
    end, ids = 0.0, set()
    for scene in plan['scenes']:
        sid = scene['scene_id']
        if sid in ids:
            errors.append(f'Duplicate scene: {sid}')
        ids.add(sid)
        if abs(scene['start_time'] - end) > 0.001:
            errors.append(f'Timeline gap or overlap: {sid}')
        end = scene['start_time'] + scene['duration']
        if abs(scene['source_out'] - scene['source_in'] - scene['duration']) > 0.001:
            errors.append(f'Source duration mismatch: {sid}')
        asset = assets.get(scene['asset_id'], {})
        if scene['source_out'] > asset.get('duration', -1) + 0.001:
            errors.append(f'Source out of range: {sid}')
        if scene['font_style'] not in plan['typography']:
            errors.append(f'Unknown font style: {sid}')
        if (asset.get('ai_generated') or asset.get('illustration')) and not scene['is_illustration']:
            errors.append(f'Illustration must be declared: {sid}')
        if scene['is_illustration'] and '示意' not in scene['text_overlay']:
            errors.append(f'Illustration label missing: {sid}')
    if abs(end - plan['target_duration']) > 0.001:
        errors.append('Target duration mismatch')
    for sub in plan['subtitles']:
        if not 0 <= sub['start_time'] < sub['end_time'] <= end:
            errors.append('Subtitle time out of range')
        if sub['font_style'] not in plan['typography']:
            errors.append('Subtitle font style missing')
    for track in plan['audio']:
        if track['source_out'] <= track['source_in'] or track['source_out'] > assets.get(track['asset_id'], {}).get('duration', -1):
            errors.append('Audio source out of range')
        if track['start_time'] + track['source_out'] - track['source_in'] > end + 0.001:
            errors.append('Audio exceeds timeline')
    for transition in plan['transitions']:
        if transition['after_scene_id'] not in ids or transition['duration'] > 1:
            errors.append('Invalid transition')
    return errors

class Ledger:
    """Single local worker. Unknown outcomes retain reservations; never blindly re-run."""
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=30)
        self.db.executescript('''CREATE TABLE IF NOT EXISTS jobs (
            job_key TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL,
            payload_hash TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 1,
            result TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS budget (
            call_id TEXT PRIMARY KEY, reserved_cents INTEGER NOT NULL CHECK(reserved_cents>0),
            state TEXT NOT NULL DEFAULT 'reserved');''')
    def claim(self, key, kind, payload, retry_failed=False):
        digest = stable_key(payload)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT state,payload_hash,attempts FROM jobs WHERE job_key=?',(key,)).fetchone()
            if row:
                if row[1] != digest:
                    raise ValueError('Idempotency key reused for different payload')
                if retry_failed and row[0] == 'failed' and row[2] < 3:
                    self.db.execute("UPDATE jobs SET state='running',attempts=attempts+1,updated_at=CURRENT_TIMESTAMP WHERE job_key=?",(key,))
                    return True
                return False
            self.db.execute('INSERT INTO jobs(job_key,kind,state,payload_hash) VALUES (?,?,?,?)',(key,kind,'running',digest))
            return True
    def finish(self, key, result, state='succeeded'):
        if state not in ['succeeded','failed','uncertain','blocked']:
            raise ValueError('Unknown state')
        with self.db:
            self.db.execute('UPDATE jobs SET state=?,result=?,updated_at=CURRENT_TIMESTAMP WHERE job_key=?',(state,json.dumps(result,ensure_ascii=False),key))
    def reserve(self, call_id, upper_bound_cents):
        if type(upper_bound_cents) is not int or upper_bound_cents <= 0:
            raise ValueError('Reliable positive integer upper cost bound required')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self.db.execute('SELECT 1 FROM budget WHERE call_id=?',(call_id,)).fetchone():
                raise ValueError('Call already reserved; reconcile outcome before retry')
            spent = self.db.execute('SELECT COALESCE(SUM(reserved_cents),0) FROM budget').fetchone()[0]
            if spent + upper_bound_cents > 500:
                raise ValueError('Test budget exceeds USD 5')
            self.db.execute('INSERT INTO budget(call_id,reserved_cents) VALUES (?,?)',(call_id,upper_bound_cents))

def normalize_note(raw, actor, collected_at):
    """Accept only reviewed provider schemas; retain unknowns and raw precision."""
    if actor == 'hyperbach/xiaohongshu-scraper':
        if raw.get('record_type') != 'note' or raw.get('status') != 'ok':
            raise ValueError('Not a successful note record')
        note_id, url = raw.get('id'), raw.get('url')
        if not isinstance(note_id, str) or not re.fullmatch(r'[a-fA-F0-9]{24}', note_id) or not isinstance(url, str):
            raise ValueError('Missing canonical identity/link; encrypted search IDs must not become URLs')
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('www.xiaohongshu.com', 'www.rednote.com') or parsed.username or parsed.password or parsed.path.rstrip('/').split('/')[-1] != note_id:
            raise ValueError('Unverified canonical link')
        if raw.get('noteType') != 'video':
            raise ValueError('Not a video note')
        metrics, raw_metrics = {}, {}
        for field, source in [('likes','likes'),('saves','collects'),('comments','comments'),('shares','shares')]:
            value = raw.get(source)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0 or int(value) != value):
                raise ValueError('Unverified metric format; preserve raw text for review')
            metrics[field] = value
            raw_metrics[field] = raw.get(source + 'Text')
        return {'platform':'xiaohongshu','note_id':note_id,'url':url,'type':'video',
                'title':raw.get('title'),'body':raw.get('description'),'published_at':raw.get('publishedAt'),
                'collected_at':raw.get('scraped_at') or collected_at, **metrics,'views':None,
                'counts_exact':raw.get('countsExact') if type(raw.get('countsExact')) is bool else None,
                'raw_metrics':raw_metrics,'duration':raw.get('videoDurationSec'),
                'source':actor,'key':stable_key('xiaohongshu',note_id)}
    if actor != 'data_dino/xiaohongshu-rednote-note-scraper':
        raise ValueError('Unverified Actor output schema')
    if not raw.get('id') or not raw.get('url'):
        raise ValueError('Missing canonical identity/link')
    metrics = raw.get('engagement') or {}
    def count(name):
        value = metrics.get(name)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Unverified metric format; preserve raw text for review')
        return value
    return {'platform':'xiaohongshu','note_id':str(raw['id']),'url':raw['url'],
            'type':raw.get('type'),'title':raw.get('title'),'body':raw.get('desc'),
            'published_at':raw.get('published_at'),'collected_at':collected_at,
            'likes':count('liked_count'),'saves':count('collected_count'),
            'comments':count('comments_count'),'shares':count('shared_count'),
            'views':None,'source':actor,'key':stable_key('xiaohongshu',raw['id'])}

def normalize_batch(rows, actor, collected_at):
    if not isinstance(rows, list):
        raise ValueError('Expected dataset array')
    accepted, quarantined, ignored, duplicates, seen = [], [], [], [], set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            quarantined.append({'row':i,'reason':'Invalid record shape'})
            continue
        if actor == 'hyperbach/xiaohongshu-scraper' and row.get('record_type') == 'target':
            ignored.append({'row':i,'reason':'Target summary, not a note'})
            continue
        try:
            normalized = normalize_note(row, actor, collected_at)
        except ValueError as error:
            quarantined.append({'row':i,'source_id':row.get('id'),'reason':str(error)})
            continue
        if normalized['key'] in seen:
            duplicates.append({'row':i,'key':normalized['key']})
            continue
        seen.add(normalized['key'])
        accepted.append(normalized)
    return {'accepted':accepted,'quarantined':quarantined,'ignored':ignored,'duplicates':duplicates,
            'empty':len(rows)==0,'summary':{'input':len(rows),'accepted':len(accepted),
            'quarantined':len(quarantined),'ignored':len(ignored),'duplicates':len(duplicates)}}

def match_references(brand_id, topic_id, references, assets):
    """Evidence/asset compatibility shortlist, not a claim of effectiveness."""
    selected=[]
    for ref in references:
        if brand_id not in ref.get('brand_ids',[]) or topic_id not in ref.get('topic_ids',[]) or not ref.get('evidence'):
            continue
        available=[a for a in assets if brand_id in a.get('brand_ids',[]) and topic_id in a.get('topic_ids',[]) and a.get('status')=='available' and a.get('rights') in ['owned','licensed'] and a.get('rights_evidence')]
        needed=set(ref.get('required_scene_tags',[]))
        covered=set().union(*(set(a.get('scene_tags',[])) for a in available)) if available else set()
        if not needed or not needed.issubset(covered):
            continue
        selected.append({'reference_id':ref['id'],'asset_ids':[a['id'] for a in available if needed & set(a.get('scene_tags',[]))],
                         'reasons':['同品牌和 Topic','有分析证据','所需镜头标签均有已授权素材'],'evidence':ref['evidence']})
    return sorted(selected,key=lambda x:x['reference_id'])[:3]

def ffmpeg(args):
    return subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-hide_banner',*args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)

def prepare_media(source, output, permission):
    if permission.get('processing_allowed') is not True or not permission.get('evidence'):
        raise ValueError('Media processing authorization required')
    source=Path(source).resolve()
    if not source.is_file():
        raise ValueError('Source file missing')
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    generator=imageio_ffmpeg.read_frames(str(source))
    metadata=next(generator)
    generator.close()
    duration=metadata['duration']
    if not 0 < duration <= 3600:
        raise ValueError('Unsupported duration')
    manifest={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'metadata':metadata,'permission':permission,'frames':[]}
    # select keeps source PTS; fps would retimestamp sampled frames and could
    # mislabel sparse context frames by seconds. Evidence uses source time.
    filters=[('hook',0,min(3,duration),"select=isnan(prev_selected_t)+gte(t-prev_selected_t\\,0.16)"),('body',0,duration,"select=gt(scene\\,0.25)"),('context',0,duration,"select=isnan(prev_selected_t)+gte(t-prev_selected_t\\,5)"),('ending',max(0,duration-3),duration,"select=isnan(prev_selected_t)+gte(t-prev_selected_t\\,0.5)")]
    for kind,start,end,filter_expr in filters:
        # trim retains original PTS, so showinfo timestamps refer to the source.
        pattern=str(output/f'{kind}-%04d.jpg')
        vf=f'trim=start={start}:end={end},{filter_expr},scale=640:-2,showinfo'
        proc=ffmpeg(['-i',str(source),'-vf',vf,'-fps_mode','vfr','-frames:v','800',pattern])
        if proc.returncode:
            raise RuntimeError('Frame extraction failed: '+proc.stderr[-1000:])
        timestamps=re.findall(r'pts_time:([0-9.]+)',proc.stderr)
        files=sorted(output.glob(f'{kind}-*.jpg'))
        if len(timestamps)<len(files):
            raise RuntimeError('Missing timestamp evidence')
        for file,stamp in zip(files,timestamps):
            manifest['frames'].append({'kind':kind,'timestamp':float(stamp),'path':str(file)})
    proc=ffmpeg(['-i',str(source),'-map','0:a:0','-vn','-ac','1','-ar','16000',str(output/'audio.wav')])
    if proc.returncode:
        if 'matches no streams' in proc.stderr:
            manifest['audio']=None
        else:
            raise RuntimeError('Audio extraction failed')
    else:
        manifest['audio']=str(output/'audio.wav')
    manifest['status']='prepared_not_analyzed'
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['validate','prepare'])
    parser.add_argument('--blueprint'); parser.add_argument('--assets'); parser.add_argument('--references')
    parser.add_argument('--source'); parser.add_argument('--output'); parser.add_argument('--permission')
    args=parser.parse_args()
    read=lambda p:json.loads(Path(p).read_text('utf-8'))
    if args.command=='validate':
        errors=validate_blueprint(read(args.blueprint),read(args.assets),read(args.references) if args.references else {})
        print(json.dumps({'valid':not errors,'errors':errors},ensure_ascii=False));sys.exit(bool(errors))
    else:
        result=prepare_media(args.source,args.output,read(args.permission))
        print(json.dumps({'status':result['status'],'frames':len(result['frames'])}))
