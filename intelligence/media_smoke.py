"""Synthetic fixture only: validates actual FFmpeg operations, not video intelligence."""
import json
from pathlib import Path
from core import ffmpeg, prepare_media, validate_blueprint
from test_core import fixture

base=Path(__file__).resolve().parent/'test-artifacts'
base.mkdir(exist_ok=True)
source=base/'synthetic-test.mp4'
if not source.exists():
    r=ffmpeg(['-f','lavfi','-i','color=c=red:s=640x360:r=30:d=2',
              '-f','lavfi','-i','color=c=blue:s=640x360:r=30:d=2',
              '-f','lavfi','-i','sine=frequency=440:duration=4',
              '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]',
              '-map','[v]','-map','2:a','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)])
    if r.returncode:raise RuntimeError(r.stderr[-1000:])
permission={'processing_allowed':True,'evidence':'Generated locally for software test; synthetic red/blue video, not a reference or user asset.'}
result=prepare_media(source,base/'prepared',permission)
assert result['audio'] and Path(result['audio']).is_file()
hook=[f for f in result['frames'] if f['kind']=='hook']
body=[f for f in result['frames'] if f['kind']=='body']
assert len(hook)==18, len(hook)
assert any(abs(f['timestamp']-2)<0.1 for f in body),body
plan,assets=fixture(source)
errors=validate_blueprint(plan,assets)
assert not errors,errors
for name,obj in [('blueprint.synthetic.json',plan),('assets.synthetic.json',assets),('permission.synthetic.json',permission)]:
    (base/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
summary={'synthetic_only':True,'audio_extracted':True,'hook_frames':len(hook),'detected_scene_times':[f['timestamp'] for f in body],'total_frames':len(result['frames']),'blueprint_valid':True,'real_business_acceptance':False}
(base/'media-test-result.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary))
