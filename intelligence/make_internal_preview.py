"""Real, user-owned footage -> validated draft blueprint -> silent internal preview.

No service calls, no publishing. Keeps the original full frame and burned-in text.
This limited renderer fails on unsupported features rather than silently ignoring them.
"""
import hashlib,json,subprocess,sys
from pathlib import Path
from core import match_references,validate_blueprint,imageio_ffmpeg

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'live-test'
BRAND='41df58e7c06e8121a5e3d3aa472c0f7a'
TOPIC='41df58e7c06e81578386f8590805d23c'
REF='41df58e7c06e81d7a0bfee36ccef6e83'
ASSET='41ef58e7c06e81c4b972cce9da7439c9'

def page_id(url):return url.rstrip('/').split('/')[-1].replace('-','')
def relation(row,key):return [page_id(u) for u in json.loads(row[key])]
def stamp(seconds):
    cs=round(seconds*100);return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'
def run(args,cwd):
    r=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-hide_banner','-loglevel','error',*map(str,args)],cwd=cwd,capture_output=True,timeout=180)
    if r.returncode:raise RuntimeError(r.stderr.decode('utf-8',errors='replace')[-3000:])

def main():
    refrow=json.loads((BASE/'notion-reference-query.json').read_text('utf-8'))['results'][0]
    assetrow=json.loads((BASE/'notion-asset-query.json').read_text('utf-8'))['results'][0]
    assert page_id(refrow['url'])==REF and page_id(assetrow['url'])==ASSET
    source=BASE/'dk-service-owned.mp4'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest==assetrow['文件哈希']
    refs=[{'id':REF,'brand_ids':relation(refrow,'适用品牌'),'topic_ids':relation(refrow,'Topic'),
           'evidence':[refrow['分析证据']],'required_scene_tags':['process','result']}]
    assets=[{'id':ASSET,'brand_ids':relation(assetrow,'适用品牌'),'topic_ids':relation(assetrow,'适用 Topic'),
             'local_path':str(source),'sha256':digest,'duration':98.08,
             'rights':'owned' if assetrow['版权与使用权限']=='自有' else 'unknown','rights_evidence':assetrow['授权范围'],
             'status':'available' if assetrow['可用状态']=='可用' else 'blocked','scene_tags':['process','result'],
             'allowed_platforms':['xiaohongshu'],'internal_use_only':True,'publication_allowed':False}]
    matched=match_references(BRAND,TOPIC,refs,assets)
    assert len(matched)==1 and matched[0]['asset_ids']==[ASSET]
    specifications=[
        (50,2.3,'先看问题：灶台上的污迹','展示源片真实污迹，不虚构原因'),
        (52.5,4,'再看过程：擦拭灶台表面','接入真实操作，保留原始动作'),
        (24,4,'细节镜头：水龙头擦拭','用近景展示另一个工作位置'),
        (33,3,'结果镜头：洗手盆','展示实际结果，不宣称量化效果'),
        (85,4,'拉远一点：厨房全景','从局部转向空间，不把异机位包装成严格对比'),
        (90,3,'下一次补拍：同机位前后对比','记录本次素材审查发现的缺口')]
    scenes=[];cursor=0
    for i,(source_in,duration,text,purpose) in enumerate(specifications):
        scenes.append({'scene_id':f's{i+1}','start_time':round(cursor,3),'duration':duration,'asset_id':ASSET,
          'source_in':source_in,'source_out':round(source_in+duration,3),'crop_mode':'contain','focal_point':[.5,.5],
          'text_overlay':text,'font_style':'body','text_position':[.5,.09],'animation':'none','transition':'cut',
          'narration':'','audio_cue':'silent','creative_purpose':purpose,'is_illustration':False})
        cursor+=duration
    plan={'schema_version':1,'project_id':'dk-service-internal-preview-2026-11-20','brand_id':BRAND,'topic_id':TOPIC,
          'reference_video_ids':[REF],'asset_ids':[ASSET],'target_platform':'xiaohongshu','aspect_ratio':'9:16',
          'resolution':{'width':720,'height':1280},'target_duration':round(cursor,3),'language':'zh',
          'scenes':scenes,'subtitles':[],
          'typography':{'body':{'family':'Microsoft YaHei','size_ratio':.03,'color':'#FFFFFF','stroke_color':'#000000','stroke_width':1}},
          'transitions':[],'audio':[],'brand_elements':[],
          'output_settings':{'container':'mp4','video_codec':'h264','fps':30,'audio_codec':'aac'},
          'approval_status':'draft','missing_materials':[]}
    refsmap={x['id']:x for x in refs};assetsmap={x['id']:x for x in assets}
    validation=validate_blueprint(plan,assetsmap,refsmap,require_approval=False)
    assert not validation,validation
    production_errors=validate_blueprint(plan,assetsmap,refsmap,require_approval=True)
    assert 'Human approval required' in production_errors
    out=BASE/'internal-preview';out.mkdir(exist_ok=False)
    for name,obj in [('blueprint.json',plan),('assets.json',assetsmap),('references.json',refsmap),('matching.json',matched)]:
        (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    # Draw every declared overlay at its declared coordinates. Preserve complete video
    # in a centered 576x1024 window; top and bottom margins identify the test clearly.
    ass='[Script Info]\nScriptType: v4.00+\nPlayResX: 720\nPlayResY: 1280\n\n[V4+ Styles]\n'
    ass+='Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
    ass+='Style: body,Microsoft YaHei,38.4,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,35,35,35,1\n'
    ass+='Style: note,Microsoft YaHei,25,&H00AAAAAA,&H00AAAAAA,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,35,35,35,1\n\n[Events]\n'
    ass+='Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    ass+=f'Dialogue: 0,0:00:00.00,{stamp(cursor)},note,,0,0,0,,{{\\pos(360,1210)}}DK SERVICE · 内部制作测试 · 未审核\n'
    for s in scenes:
        ass+=f'Dialogue: 1,{stamp(s["start_time"])},{stamp(s["start_time"]+s["duration"])},body,,0,0,0,,{{\\pos(360,115)}}{s["text_overlay"]}\n'
    (out/'captions.ass').write_text(ass,encoding='utf-8-sig')
    inputs=[];graph=[]
    for i,s in enumerate(scenes):
        if s['animation']!='none' or s['transition']!='cut' or s['crop_mode']!='contain':raise ValueError('Unsupported render operation')
        inputs+=['-ss',s['source_in'],'-t',s['duration'],'-i',source]
        graph.append(f'[{i}:v]fps=30,scale=576:1024:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=0x111820,setsar=1,setpts=PTS-STARTPTS[v{i}]')
    graph.append(''.join(f'[v{i}]' for i in range(len(scenes)))+f'concat=n={len(scenes)}:v=1:a=0,ass=captions.ass[v]')
    output=out/'DK-Service-internal-preview.mp4'
    run([*inputs,'-filter_complex',';'.join(graph),'-map','[v]','-an','-c:v','libx264','-preset','fast','-crf','21','-threads','4','-pix_fmt','yuv420p','-movflags','+faststart',output],out)
    reader=imageio_ffmpeg.read_frames(str(output));meta=next(reader);reader.close()
    assert abs(meta['duration']-cursor)<.1 and meta['size']==(720,1280),meta
    run(['-i',output,'-f','null','-'],out)
    for i,s in enumerate(scenes):run(['-ss',s['start_time']+s['duration']/2,'-i',output,'-frames:v','1',out/f'check-{i+1}.jpg'],out)
    report={'mode':'internal_test_only','publish_allowed':False,'original_audio_reused':False,'api_cost_usd':0,
            'real_source':str(source),'matching_method':'Notion live relations plus evidence and verified local assets',
            'selected_references':len(matched),'validated_scenes':len(scenes),'blueprint_errors':validation,
            'production_gate_errors':production_errors,'metadata':meta,'output':str(output),
            'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'full_decode_passed':True}
    (out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))

if __name__=='__main__':main()
