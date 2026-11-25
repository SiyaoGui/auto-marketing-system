from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import requests

from .core import read_json, safe_path, stamp, write_json


class Blocked(Exception):
    """Known prerequisite missing. Nothing has been published."""


class RemoteError(Exception):
    """Deliberately excludes response bodies and credential-bearing request URLs."""


def ensure_success(r):
    if not 200 <= r.status_code < 300:
        raise RemoteError(f'Platform returned HTTP {r.status_code}; inspect account dashboard')


def response_json(r):
    ensure_success(r)
    return r.json()


def youtube_token(root, brand):
    path = root / 'secrets' / (brand['id'] + '-youtube.json')
    if not path.exists():
        raise Blocked('Authorize this brand with auth-youtube first')
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        raise Blocked('Install google-auth and google-auth-oauthlib using setup.ps1')
    creds = Credentials.from_authorized_user_file(str(path))
    if not creds.valid:
        if not creds.refresh_token:
            raise Blocked('YouTube login expired; reauthorize')
        creds.refresh(Request())
        write_json(path, __import__('json').loads(creds.to_json()))
    return creds.token


def instagram_token(root, brand):
    info = brand['instagram']
    token = os.getenv(info['token_env'])
    if not token:
        token = read_json(root / 'secrets' / (brand['id'] + '-instagram.json'), {}).get('access_token')
    if not token:
        raise Blocked('Instagram Page token is missing')
    return token


def ensure_video(root, job):
    if job['payload'].get('demo'):
        raise Blocked('Demo content cannot be published')
    file = safe_path(root, job['payload']['video'])
    if not file.is_file():
        raise Blocked('Rendered video is missing')
    import hashlib
    with file.open('rb') as f:
        actual = hashlib.file_digest(f, 'sha256').hexdigest()
    if actual != job['payload']['video_sha256']:
        raise Blocked('Video changed since quality checks; regenerate before publishing')
    return file


def youtube(root, cfg, brand, job, checkpoint):
    conf = brand['youtube']
    if not conf.get('enabled') or not conf.get('channel_id'):
        raise Blocked('Enable and configure this brand YouTube channel first')
    if conf['privacy'] not in ('private', 'unlisted', 'public'):
        raise Blocked('Invalid YouTube privacy setting')
    if job['payload']['target_account'] != conf['channel_id']:
        raise Blocked('Target channel changed; regenerate the job for the new channel')
    video = ensure_video(root, job)
    token = youtube_token(root, brand)
    headers = {'Authorization': 'Bearer ' + token}
    timeout = cfg['network_timeout']
    channels = response_json(requests.get('https://www.googleapis.com/youtube/v3/channels', headers=headers,
                                          params={'part': 'id', 'mine': 'true'}, timeout=timeout))
    if conf['channel_id'] not in [i['id'] for i in channels.get('items', [])]:
        raise Blocked('Authorized YouTube channel does not match this brand')
    remote = dict(job['remote'])
    if not remote.get('video_id'):
        if remote:
            raise Blocked('Existing upload state needs reconciliation; will not create a duplicate')
        metadata = {'snippet': {'title': job['payload']['title'], 'description': job['payload']['caption'], 'categoryId': '22'},
                    'status': {'privacyStatus': conf['privacy'], 'selfDeclaredMadeForKids': conf['made_for_kids'],
                               'containsSyntheticMedia': conf.get('contains_synthetic_media', False)}}
        checkpoint({'phase': 'upload_session_requested', 'started_at': stamp()})
        r = requests.post('https://www.googleapis.com/upload/youtube/v3/videos',
                          params={'uploadType': 'resumable', 'part': 'snippet,status'},
                          headers={**headers, 'X-Upload-Content-Type': 'video/mp4', 'X-Upload-Content-Length': str(video.stat().st_size)},
                          json=metadata, timeout=timeout)
        # Resumable initialization may have an empty body. The session is in Location.
        ensure_success(r)
        location = r.headers.get('Location', '')
        parsed = urlparse(location)
        if parsed.scheme != 'https' or parsed.hostname not in ('www.googleapis.com', 'youtube.googleapis.com'):
            raise RemoteError('Unexpected upload host; credentials were not forwarded')
        remote = {'phase': 'upload_attempted', 'session_url': location, 'started_at': stamp()}
        checkpoint(remote)
        with video.open('rb') as stream:
            result = response_json(requests.put(location, headers={**headers, 'Content-Type': 'video/mp4'}, data=stream, timeout=(30, 600)))
        remote.update(video_id=result['id'], phase='processing')
        remote.pop('session_url', None)
        checkpoint(remote)
    result = response_json(requests.get('https://www.googleapis.com/youtube/v3/videos', headers=headers,
                                       params={'part': 'snippet,status,processingDetails', 'id': remote['video_id']}, timeout=timeout))
    if not result.get('items'):
        return 'submitted', remote
    item = result['items'][0]
    if item.get('snippet', {}).get('channelId') != conf['channel_id']:
        raise Blocked('Remote video channel identity does not match this brand')
    status = item.get('status', {})
    processing = item.get('processingDetails', {}).get('processingStatus')
    if status.get('uploadStatus') in ('failed', 'rejected', 'deleted') or processing in ('failed', 'terminated'):
        return 'failed', {**remote, 'phase': 'platform_processing_failed'}
    if status.get('uploadStatus') != 'processed' and processing != 'succeeded':
        return 'submitted', remote
    privacy = status.get('privacyStatus', 'unknown')
    remote.update(phase='complete', privacy=privacy, url='https://www.youtube.com/watch?v=' + remote['video_id'])
    return ('published' if privacy == 'public' else 'uploaded_' + privacy), remote


def instagram(root, cfg, brand, job, checkpoint):
    conf = brand['instagram']
    if not conf.get('enabled') or not conf.get('account_id'):
        raise Blocked('Enable and configure an Instagram professional account first')
    if conf.get('login') != 'facebook':
        raise Blocked('Local upload adapter requires Facebook Login for Business and linked Page')
    if job['payload']['target_account'] != conf['account_id']:
        raise Blocked('Target Instagram account changed; regenerate the job')
    video = ensure_video(root, job)
    token = instagram_token(root, brand)
    version = cfg['platforms']['instagram_api_version']
    import re
    if not re.fullmatch(r'v\d+\.\d+', version) or not str(conf['account_id']).isdigit():
        raise Blocked('Invalid Meta API version or account ID')
    base = 'https://graph.facebook.com/' + version
    headers = {'Authorization': 'Bearer ' + token}
    timeout = cfg['network_timeout']
    account = response_json(requests.get(base + '/' + conf['account_id'], params={'fields': 'id,username'}, headers=headers, timeout=timeout))
    if str(account.get('id')) != str(conf['account_id']):
        raise Blocked('Instagram account identity check failed')
    remote = dict(job['remote'])
    if not remote:
        checkpoint({'phase': 'container_requested', 'started_at': stamp()})
        container = response_json(requests.post(base + '/' + conf['account_id'] + '/media', headers=headers,
                                  json={'media_type': 'REELS', 'upload_type': 'resumable', 'caption': job['payload']['caption'], 'share_to_feed': True}, timeout=timeout))
        remote = {'container_id': container['id'], 'phase': 'upload_attempted', 'started_at': stamp()}
        checkpoint(remote)
        upload = f'https://rupload.facebook.com/ig-api-upload/{version}/{container["id"]}'
        with video.open('rb') as stream:
            response = response_json(requests.post(upload, data=stream,
                headers={'Authorization': 'OAuth ' + token, 'offset': '0', 'file_size': str(video.stat().st_size), 'Content-Type': 'application/octet-stream'}, timeout=(30, 600)))
        if not response.get('success'):
            raise RemoteError('Instagram upload not confirmed')
        remote['phase'] = 'processing'
        checkpoint(remote)
    if remote.get('phase') not in ('processing', 'published'):
        raise Blocked('Uncertain Instagram upload state requires reconciliation')
    if not remote.get('media_id'):
        container_status = response_json(requests.get(base + '/' + remote['container_id'], headers=headers,
                                                     params={'fields': 'status_code'}, timeout=timeout))['status_code']
        if container_status in ('ERROR', 'EXPIRED'):
            return 'failed', {**remote, 'phase': container_status.lower()}
        if container_status == 'PUBLISHED':
            return 'unknown', {**remote, 'phase': 'published_id_needs_reconciliation'}
        if container_status != 'FINISHED':
            return 'submitted', remote
        remote['phase'] = 'publish_attempted'
        checkpoint(remote)
        published = response_json(requests.post(base + '/' + conf['account_id'] + '/media_publish',
                                               headers=headers, json={'creation_id': remote['container_id']}, timeout=timeout))
        remote.update(media_id=published['id'], phase='published')
        checkpoint(remote)
    verified = response_json(requests.get(base + '/' + remote['media_id'], headers=headers, params={'fields': 'id,permalink'}, timeout=timeout))
    if verified.get('id') != remote['media_id']:
        return 'submitted', remote
    remote['url'] = verified.get('permalink', '')
    return 'published', remote


def dispatch(root, cfg, store, brands):
    mapping = {b['id']: b for b in brands}
    outcomes = []
    for _ in range(cfg['max_jobs_per_tick']):
        job = store.claim()
        if not job:
            break
        try:
            brand = mapping.get(job['brand_id'])
            if not brand or not brand.get('enabled'):
                raise Blocked('Brand is disabled or missing')
            if job['platform'] not in ('youtube', 'instagram'):
                raise Blocked('This channel requires manual publication; no verified API adapter')
            adapter = youtube if job['platform'] == 'youtube' else instagram
            status, remote = adapter(root, cfg, brand, job, lambda r: store.checkpoint(job['id'], r))
            store.finish(job['id'], status, remote)
        except Blocked as exc:
            status = 'blocked'
            store.finish(job['id'], status, error=str(exc))
        except Exception as exc:
            # Retry only a known read/processing phase. Any interrupted mutation stays unknown.
            latest = next(j for j in store.jobs() if j['id'] == job['id'])
            safe_poll = latest['remote'].get('phase') in ('processing', 'published')
            status = 'submitted' if safe_poll and job['attempts'] <= 12 else 'unknown'
            store.finish(job['id'], status, error=f'{type(exc).__name__}: check remote account before retrying')
        outcomes.append({'job': job['id'], 'status': status})
    return outcomes
