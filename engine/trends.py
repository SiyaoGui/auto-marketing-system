from __future__ import annotations

import csv
import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests

from .core import now, read_json, stamp, write_json


def keyword_rows(root, brand):
    with (root / 'data/keywords.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = [r for r in csv.DictReader(f) if r['brand_id'] == brand['id']]
    for r in rows:
        r['weight'] = max(0, min(10, float(r.get('weight') or 1)))
    return rows


def parse_rss(text, source, region=''):
    tree = ET.fromstring(text)
    results = []
    for item in tree.findall('.//item')[:50]:
        title = (item.findtext('title') or '').strip()
        if not title:
            continue
        date = item.findtext('pubDate')
        try:
            observed = parsedate_to_datetime(date).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            observed = None
        traffic = next((n.text for n in item if n.tag.endswith('approx_traffic')), None)
        results.append({'keyword': title, 'source': source, 'source_url': item.findtext('link') or '',
                        'observed_at': observed, 'fetched_at': stamp(), 'region': region,
                        'traffic_label': traffic, 'growth': None,
                        'signal_type': 'search_trend' if source == 'google_trends' else 'rss_item'})
    return results


def growth(current, previous):
    try:
        a, b = float(current), float(previous)
        return (a - b) / b if a >= 0 and b > 0 and math.isfinite(a) and math.isfinite(b) else None
    except (TypeError, ValueError):
        return None


def collect(root, cfg, brand, offline=False):
    signals, warnings = [], []
    timeout = cfg['network_timeout']
    if not offline:
        endpoints = [('google_trends', f'https://trends.google.com/trending/rss?geo={country}', country)
                     for country in cfg['trends']['countries']]
        endpoints += [(f['name'], f['url'], f.get('region', '')) for f in cfg['trends'].get('rss', [])]
        for name, url, region in endpoints:
            try:
                if urlparse(url).scheme != 'https':
                    raise ValueError('RSS requires HTTPS')
                r = requests.get(url, timeout=timeout, headers={'User-Agent': 'LocalMarketingEngine/0.1'})
                r.raise_for_status()
                signals.extend(parse_rss(r.text, name, region))
            except (requests.RequestException, ValueError, ET.ParseError):
                warnings.append(f'{name}/{region}: unavailable; no fabricated fallback data')
        base = cfg['trends'].get('searxng_url', '').rstrip('/')
        if base:
            for k in keyword_rows(root, brand)[:cfg['trends']['max_queries_per_brand']]:
                try:
                    r = requests.get(base + '/search', params={'q': k['keyword'], 'format': 'json', 'time_range': 'day'}, timeout=timeout)
                    r.raise_for_status()
                    for item in r.json().get('results', [])[:5]:
                        signals.append({'keyword': item['title'], 'source': 'searxng',
                                        'source_url': item['url'], 'observed_at': None,
                                        'fetched_at': stamp(), 'region': '', 'growth': None,
                                        'signal_type': 'search_result'})
                except (requests.RequestException, KeyError, ValueError):
                    warnings.append('searxng: unavailable')
    path = root / 'data/trends.csv'
    if path.exists():
        with path.open(encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                if r['brand_id'] not in ('*', brand['id']):
                    continue
                signals.append({**r, 'fetched_at': stamp(), 'growth': growth(r.get('current_value'), r.get('previous_value')),
                                'signal_type': 'imported_platform_signal'})
    cutoff = now() - timedelta(hours=cfg['trends']['max_age_hours'])
    fresh = []
    for s in signals:
        try:
            date = datetime.fromisoformat(s['observed_at'].replace('Z', '+00:00'))
            if date.tzinfo is None or date < cutoff or date > now() + timedelta(minutes=5):
                continue
        except (ValueError, TypeError, AttributeError):
            # Search hits without a source date are inspiration, never labelled rising today.
            if s['signal_type'] != 'search_result':
                continue
        fresh.append(s)
    out = {'retrieved_at': stamp(), 'signals': fresh, 'warnings': warnings, 'offline': offline}
    write_json(root / 'state/trends' / (brand['id'] + '.json'), out)
    return out


def rank(root, brand, collected, recent):
    seeds = keyword_rows(root, brand)
    if not seeds:
        raise ValueError(f"{brand['id']}: add keywords to data/keywords.csv")
    allowed = [x.casefold() for x in brand.get('allowed_terms', [])]
    candidates = []
    past_results = read_json(root / 'state/metrics-summary.json', [])
    for row in seeds:
        key = row['keyword']
        matching = [s for s in collected['signals'] if key.casefold() in s['keyword'].casefold()]
        score = row['weight'] + min(len(matching), 5) * 0.5
        if key in recent:
            score -= 10
        feedback = [m for m in past_results if m.get('brand_id') == brand['id'] and m.get('topic') == key and m.get('views', 0) >= 100]
        if feedback:
            views = sum(m['views'] for m in feedback)
            leads = sum(m.get('qualified_leads', 0) for m in feedback)
            score += min(2, leads / views * 100)
        if allowed and not any(t in key.casefold() or key.casefold() in t for t in allowed):
            score -= 3
        candidates.append({'topic': key, 'score': score, 'signals': matching[:4],
                           'basis': 'recent_source_match' if matching else 'evergreen_keyword'})
    return sorted(candidates, key=lambda x: (-x['score'], x['topic']))
