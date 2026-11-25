from __future__ import annotations

import json

import requests

from .core import write_json


def auth_youtube(root, brand, client_file):
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not brand['youtube'].get('channel_id'):
        raise ValueError('Fill the intended YouTube channel_id before authorizing')
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), scopes=[
        'https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly'])
    creds = flow.run_local_server(host='127.0.0.1', port=0, access_type='offline', prompt='consent')
    response = requests.get('https://www.googleapis.com/youtube/v3/channels',
                            headers={'Authorization': 'Bearer ' + creds.token}, params={'part': 'id', 'mine': 'true'}, timeout=30)
    response.raise_for_status()
    if brand['youtube']['channel_id'] not in [c['id'] for c in response.json().get('items', [])]:
        raise ValueError('Wrong YouTube channel selected; credentials were not saved')
    write_json(root / 'secrets' / (brand['id'] + '-youtube.json'), json.loads(creds.to_json()))
    return {'brand': brand['id'], 'authorized': True}
