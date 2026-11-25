from __future__ import annotations

import csv
import hashlib
import html
import json
import shutil
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import content, media, publishers, trends
from .core import ROOT, Store, due_time, load_brands, now, read_json, settings, stamp, write_json


def run(root=ROOT, brand_id=None, demo=False, offline=False, board_only=False):
    cfg = settings(root)
    store = Store(root)
    metrics(root, store)
    day = now().astimezone(ZoneInfo(cfg['timezone'])).date().isoformat()
    outcomes = []
    brands = [b for b in load_brands(root) if (not brand_id or b['id'] == brand_id) and
              ((demo and b.get('demo')) or (not demo and b.get('enabled') and not b.get('demo')))]
    for brand in brands:
        collected = trends.collect(root, cfg, brand, offline=offline)
        for slot in range(brand['videos_per_day']):
            ident = store.begin_batch(brand['id'], day, slot)
            if not ident:
                outcomes.append({'brand': brand['id'], 'slot': slot, 'status': 'already_generated_or_running'})
                continue
            try:
                recent = store.recent_topics(brand['id'])
                candidates = trends.rank(root, brand, collected, recent)
                script = content.generate(root, cfg, brand, candidates[0], recent, demo=demo)
                folder = root / 'output' / ident
                write_json(folder / 'selection.json', {'chosen': candidates[0], 'candidates': candidates, 'warnings': collected['warnings']})
                if board_only:
                    media.storyboard(root, cfg, brand, script, folder)
                    # A storyboard is not a finished production batch; it must not enqueue publication.
                    store.end_batch(ident, error='Storyboard preview only; render to complete')
                    outcomes.append({'batch': ident, 'status': 'storyboard_only', 'path': str(folder)})
                    continue
                quality = media.render(root, cfg, brand, script, folder)
                with (folder / 'video.mp4').open('rb') as stream:
                    video_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
                for platform in brand['platforms']:
                    tracking = content.tracking_url(brand.get('landing_url'), brand['id'], platform, ident)
                    # Most short-video captions are not clickable landing pages. Keep UTM links for profile/link-in-bio setup.
                    caption = script['captions'][platform]
                    if platform == 'youtube' and tracking:
                        caption += '\n\n' + tracking
                    target = (brand.get('youtube', {}).get('channel_id') if platform == 'youtube' else
                              brand.get('instagram', {}).get('account_id') if platform == 'instagram' else '')
                    payload = {'title': script['title'][:20] if platform == 'xiaohongshu' else script['title'],
                               'caption': caption, 'demo': demo, 'topic': script['topic'],
                               'video': str((folder / 'video.mp4').relative_to(root)), 'video_sha256': video_hash,
                               'tracking_url': tracking, 'target_account': target, 'quality': quality}
                    export = folder / platform
                    export.mkdir(exist_ok=True)
                    write_json(export / 'post.json', payload)
                    (export / 'caption.txt').write_text(payload['title'] + '\n\n' + caption, encoding='utf-8')
                    if platform in ('xiaohongshu', 'tiktok'):
                        (export / 'PUBLISH-MANUALLY.txt').write_text(
                            'This package has NOT been posted. Use the platform creator center, select ../video.mp4, '
                            'review caption and disclosures, then publish. No browser automation or account cookies are included.', encoding='utf-8')
                    store.enqueue(ident, brand, platform, content.content_hash(script), payload, due_time(cfg, day))
                store.end_batch(ident, {'topic': script['topic'], 'folder': str(folder.relative_to(root)), 'quality': quality})
                outcomes.append({'batch': ident, 'status': 'rendered', 'demo': demo, 'path': str(folder)})
            except Exception as exc:
                # Do not persist a raw requests exception because it may contain credential-bearing URLs.
                message = str(exc) if isinstance(exc, (ValueError, RuntimeError, FileNotFoundError)) else type(exc).__name__
                store.end_batch(ident, error=message[:400])
                outcomes.append({'batch': ident, 'status': 'failed', 'reason': message[:400]})
    if not brands:
        outcomes.append({'status': 'blocked', 'reason': 'No enabled real brands. Fill company profiles and assets first.'})
    report(root)
    return outcomes


def tick(root=ROOT):
    cfg = settings(root)
    local = now().astimezone(ZoneInfo(cfg['timezone']))
    clock = read_json(root / 'state/scheduler.json', {})
    results = []
    if local.strftime('%H:%M') >= cfg['generation_time'] and clock.get('last_day') != local.date().isoformat():
        results.extend(run(root))
        # Failed batches are visible and may be retried with `run`; do not hammer a missing model every minute.
        write_json(root / 'state/scheduler.json', {'last_day': local.date().isoformat(), 'ran_at': stamp()})
        Store(root).backup()
    results.extend(publishers.dispatch(root, cfg, Store(root), load_brands(root)))
    write_json(root / 'state/heartbeat.json', {'at': stamp(), 'timezone': cfg['timezone'], 'results': results})
    report(root)
    return results


def daemon(root=ROOT):
    print('Worker running. Keep this computer awake. Ctrl+C stops the worker.', flush=True)
    while True:
        try:
            result = tick(root)
            if result:
                print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as exc:
            Store(root).event(None, 'worker_error', type(exc).__name__)
            print('Worker error: ' + type(exc).__name__, flush=True)
        time.sleep(max(30, settings(root)['poll_seconds']))


def metrics(root, store):
    jobs = {j['id']: j for j in store.jobs()}
    rows = []
    with (root / 'data/metrics.csv').open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            if row['job_id'] not in jobs:
                continue
            for key in ('views', 'clicks', 'leads', 'qualified_leads', 'sales', 'revenue'):
                row[key] = max(0, float(row.get(key) or 0))
            j = jobs[row['job_id']]
            row.update(brand_id=j['brand_id'], platform=j['platform'], topic=j['payload'].get('topic'))
            row['lead_rate'] = row['leads']/row['views'] if row['views'] else None
            rows.append(row)
    # Each row represents a cumulative snapshot. Only the latest snapshot per job is scored.
    latest = {}
    for row in sorted(rows, key=lambda r: r['date']):
        latest[row['job_id']] = row
    write_json(root / 'state/metrics-summary.json', list(latest.values()))
    return list(latest.values())


def report(root=ROOT):
    store = Store(root)
    data = metrics(root, store)
    jobs = store.jobs()
    e = lambda x: html.escape(str(x or ''), quote=True)
    rows = []
    for j in jobs:
        remote = j['remote']
        url = remote.get('url', '')
        link = f'<a href="{e(url)}">平台记录</a>' if url.startswith('https://') else '—'
        rows.append(f'<tr><td>{e(j["id"])}</td><td>{e(j["platform"])}</td><td>{e(j["status"])}</td><td>{e(j["due_at"])}</td><td>{link}</td><td>{e(j["error"])}</td></tr>')
    summary = ', '.join(f'{status}: {sum(j["status"] == status for j in jobs)}' for status in sorted({j['status'] for j in jobs})) or '尚无视频任务'
    report_html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>本地营销工作流</title>
    <style>body{font:16px/1.7 system-ui;background:#101a24;color:#edf5ef;padding:40px;max-width:1500px;margin:auto}h1{font-size:36px}p{color:#b7c8c0}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:14px;text-align:left;border-bottom:1px solid #365958}a{color:#b8f5d1}code{color:#b8f5d1}.box{padding:22px;background:#203e41;border-radius:15px}</style>
    <h1>本地营销工作流 · 运行记录</h1><p>这是本地静态报告；重新运行 report 后更新。演示内容禁止自动发布。</p>'''
    report_html += f'<div class="box">{e(summary)}</div><p>生成于 {e(stamp())} · 数据只表示真实记录的状态，不把上传等同于公开发布。</p>'
    report_html += '<table><tr><th>任务</th><th>平台</th><th>状态</th><th>计划时间 UTC</th><th>结果</th><th>原因</th></tr>' + ''.join(rows) + '</table>'
    report_html += '<h2>转化回流</h2><p>使用 data/metrics.csv 导入平台及落地页数据。每个任务的记录是累计快照；仅最新记录参与选题反馈。</p>'
    report_html += f'<p>有效任务数据：{len(data)}。Instagram / TikTok / 小红书正文链接不默认视为可点击；需设置主页入口或平台支持的获客组件。</p></html>'
    out = root / 'output/report.html'
    out.parent.mkdir(exist_ok=True)
    out.write_text(report_html, encoding='utf-8')
    # Omit secret session URLs from all exported status files.
    write_json(root / 'output/status.json', [{k: v for k, v in j.items() if k not in ('remote', 'payload')} for j in jobs])
    return str(out)
