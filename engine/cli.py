from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys

from . import auth, media, pipeline, publishers
from .core import ROOT, Store, load_brands, read_json, settings, write_json


def doctor(root=ROOT):
    cfg = settings(root)
    checks = []
    try:
        exe = media.ffmpeg_path(cfg)
        checks.append({'check': 'ffmpeg', 'ready': True, 'value': exe})
    except Exception:
        checks.append({'check': 'ffmpeg', 'ready': False, 'action': 'Run scripts/setup.ps1 or set media.ffmpeg'})
    try:
        font = media.font_path(cfg)
        checks.append({'check': 'font', 'ready': True, 'value': font})
    except Exception:
        checks.append({'check': 'font', 'ready': False})
    try:
        import requests
        r = requests.get(cfg['llm']['url'].rstrip('/') + '/api/tags', timeout=3)
        names = [x['name'] for x in r.json().get('models', [])]
        checks.append({'check': 'local_llm', 'ready': cfg['llm']['model'] in names, 'models': names})
    except Exception:
        checks.append({'check': 'local_llm', 'ready': False, 'action': 'Install/start Ollama and pull configured model'})
    try:
        socket.getaddrinfo('trends.google.com', 443)
        checks.append({'check': 'network_dns', 'ready': True})
    except OSError:
        checks.append({'check': 'network_dns', 'ready': False})
    brands = load_brands(root)
    checks.append({'check': 'real_brands', 'ready': any(b.get('enabled') and not b.get('demo') for b in brands)})
    for b in brands:
        if b.get('demo'):
            continue
        for p in ('youtube', 'instagram'):
            checks.append({'check': b['id'] + '/' + p, 'ready': False,
                           'configured': b.get(p, {}).get('enabled', False), 'note': 'A real account test is still required; config alone is not proof'})
    return checks


def main():
    p = argparse.ArgumentParser(description='Local multi-brand marketing workflow')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('doctor', 'status', 'report', 'tick', 'daemon', 'publish', 'recover-generation'):
        sub.add_parser(name)
    r = sub.add_parser('run')
    r.add_argument('--brand')
    r.add_argument('--offline', action='store_true')
    r.add_argument('--storyboard-only', action='store_true')
    d = sub.add_parser('demo')
    d.add_argument('--storyboard-only', action='store_true')
    ap = sub.add_parser('approve')
    ap.add_argument('job_id')
    au = sub.add_parser('auth-youtube')
    au.add_argument('brand')
    au.add_argument('client_file')
    args = p.parse_args()
    store = Store(ROOT)
    if args.command == 'doctor':
        result = doctor()
    elif args.command == 'run':
        result = pipeline.run(brand_id=args.brand, offline=args.offline, board_only=args.storyboard_only)
    elif args.command == 'demo':
        result = pipeline.run(brand_id='demo', demo=True, offline=True, board_only=args.storyboard_only)
    elif args.command == 'status':
        result = [{k: j[k] for k in ('id', 'brand_id', 'platform', 'status', 'due_at', 'error')} for j in store.jobs()]
    elif args.command == 'report':
        result = pipeline.report()
    elif args.command == 'publish':
        result = publishers.dispatch(ROOT, settings(), store, load_brands())
    elif args.command == 'approve':
        store.approve(args.job_id)
        result = {'approved': args.job_id}
    elif args.command == 'recover-generation':
        store.recover_generation()
        result = {'recovered': True}
    elif args.command == 'tick':
        result = pipeline.tick()
    elif args.command == 'daemon':
        pipeline.daemon()
        return
    elif args.command == 'auth-youtube':
        brand = next(b for b in load_brands() if b['id'] == args.brand)
        from pathlib import Path
        result = auth.auth_youtube(ROOT, brand, Path(args.client_file))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command in ('run', 'demo') and any(r.get('status') in ('failed', 'blocked') for r in result):
        return 1
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print(f'Error: {type(exc).__name__}. Check configuration and the local report.', file=sys.stderr)
        sys.exit(1)
