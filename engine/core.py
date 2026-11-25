from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager, closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = {'youtube', 'instagram', 'tiktok', 'xiaohongshu'}


def now():
    return datetime.now(timezone.utc)


def stamp(dt=None):
    return (dt or now()).astimezone(timezone.utc).isoformat()


def read_json(path, default=None):
    if not Path(path).exists() and default is not None:
        return default
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def settings(root=ROOT):
    cfg = read_json(root / 'config/settings.json')
    machine = read_json(root / 'config/machine.json', {})
    if machine.get('ffmpeg'):
        cfg['media']['ffmpeg'] = machine['ffmpeg']
    ZoneInfo(cfg['timezone'])
    for key in ('generation_time', 'publication_time'):
        datetime.strptime(cfg[key], '%H:%M')
    return cfg


def safe_path(root, relative):
    candidate = (Path(root) / relative).resolve()
    if not candidate.is_relative_to(Path(root).resolve()):
        raise ValueError('File must be inside the project directory')
    return candidate


def load_brands(root=ROOT):
    brands = []
    ids = set()
    for p in sorted((root / 'brands').glob('*.json')):
        b = read_json(p)
        ident = b.get('id', '')
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,49}', ident) or ident in ids:
            raise ValueError('Brand IDs must be unique, lowercase letters, digits, _ or -')
        if not set(b.get('platforms', [])) <= PLATFORMS:
            raise ValueError(f'Unsupported platform in {ident}')
        if not 1 <= b.get('videos_per_day', 1) <= 10:
            raise ValueError('videos_per_day must be between 1 and 10')
        if b.get('enabled') and not b.get('demo'):
            if not b.get('approved_facts') or not b.get('facts_reviewed'):
                raise ValueError(f'{ident}: fill and review approved_facts first')
        ids.add(ident)
        brands.append(b)
    return brands


def due_time(cfg, date):
    return stamp(datetime.fromisoformat(date + 'T' + cfg['publication_time']).replace(tzinfo=ZoneInfo(cfg['timezone'])))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class Store:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        (self.root / 'state').mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'state/engine.sqlite3'
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS batches (
              id TEXT PRIMARY KEY, brand_id TEXT NOT NULL, day TEXT NOT NULL,
              slot INTEGER NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL,
              error TEXT, payload TEXT, UNIQUE(brand_id,day,slot));
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, brand_id TEXT NOT NULL,
              platform TEXT NOT NULL, content_hash TEXT NOT NULL, status TEXT NOT NULL,
              due_at TEXT NOT NULL, updated_at TEXT NOT NULL, attempts INTEGER DEFAULT 0,
              payload TEXT NOT NULL, remote TEXT NOT NULL DEFAULT '{}', error TEXT,
              UNIQUE(brand_id,platform,content_hash));
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, time TEXT NOT NULL, job_id TEXT,
              event TEXT NOT NULL, detail TEXT);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def event(self, job, event, detail=''):
        with self.db() as db:
            db.execute('INSERT INTO events(time,job_id,event,detail) VALUES(?,?,?,?)', (stamp(), job, event, detail))

    def begin_batch(self, brand, day, slot):
        ident = f'{brand}-{day}-{slot}'
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM batches WHERE id=?', (ident,)).fetchone()
            if row and row['status'] in ('complete', 'generating'):
                return None
            db.execute('''INSERT INTO batches VALUES(?,?,?,?,?,?,NULL,NULL)
              ON CONFLICT(id) DO UPDATE SET status='generating',updated_at=excluded.updated_at,error=NULL''',
                       (ident, brand, day, slot, 'generating', stamp()))
        return ident

    def end_batch(self, ident, payload=None, error=None):
        with self.db() as db:
            db.execute('UPDATE batches SET status=?,updated_at=?,payload=?,error=? WHERE id=?',
                       ('failed' if error else 'complete', stamp(), json.dumps(payload, ensure_ascii=False), error, ident))

    def enqueue(self, batch, brand, platform, content_hash, payload, due):
        ident = batch + '-' + platform
        status = 'ready' if brand.get('auto_publish') and not brand.get('demo') else 'review'
        if platform in ('xiaohongshu', 'tiktok'):
            status = 'manual'
        with self.db() as db:
            cursor = db.execute('''INSERT OR IGNORE INTO jobs
                (id,batch_id,brand_id,platform,content_hash,status,due_at,updated_at,payload)
                VALUES(?,?,?,?,?,?,?,?,?)''',
                (ident, batch, brand['id'], platform, content_hash, status, due, stamp(), json.dumps(payload, ensure_ascii=False)))
        return ident if cursor.rowcount else None

    def jobs(self):
        with self.db() as db:
            rows = db.execute('SELECT * FROM jobs ORDER BY due_at DESC,id').fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['payload'] = json.loads(item['payload'])
            item['remote'] = json.loads(item['remote'])
            result.append(item)
        return result

    def recent_topics(self, brand):
        with self.db() as db:
            rows = db.execute("SELECT payload FROM batches WHERE brand_id=? AND status='complete' ORDER BY day DESC LIMIT 30", (brand,)).fetchall()
        return [json.loads(r['payload']).get('topic', '') for r in rows if r['payload']]

    def claim(self, current=None):
        current = current or now()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            # A process crash during a remote mutation must never trigger a blind second post.
            db.execute("UPDATE jobs SET status='unknown',error='Worker stopped during publication; reconcile remote state' WHERE status='sending' AND updated_at<?",
                       (stamp(current - timedelta(minutes=30)),))
            row = db.execute("SELECT id FROM jobs WHERE status IN ('ready','submitted') AND due_at<=? ORDER BY due_at,id LIMIT 1", (stamp(current),)).fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET status='sending',updated_at=?,attempts=attempts+1 WHERE id=?", (stamp(current), row['id']))
            result = dict(db.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone())
        result['payload'] = json.loads(result['payload'])
        result['remote'] = json.loads(result['remote'])
        return result

    def checkpoint(self, ident, remote):
        with self.db() as db:
            db.execute('UPDATE jobs SET remote=?,updated_at=? WHERE id=?', (json.dumps(remote), stamp(), ident))

    def finish(self, ident, status, remote=None, error=None):
        with self.db() as db:
            if remote is not None:
                db.execute('UPDATE jobs SET remote=? WHERE id=?', (json.dumps(remote), ident))
            db.execute('UPDATE jobs SET status=?,updated_at=?,error=? WHERE id=?', (status, stamp(), error, ident))
            if status == 'submitted':
                db.execute('UPDATE jobs SET due_at=? WHERE id=?', (stamp(now() + timedelta(minutes=2)), ident))
        self.event(ident, status, error or '')

    def approve(self, ident):
        with self.db() as db:
            row = db.execute('SELECT payload,status FROM jobs WHERE id=?', (ident,)).fetchone()
            if not row or row['status'] not in ('review', 'blocked'):
                raise ValueError('Only review or blocked jobs can be approved')
            if json.loads(row['payload']).get('demo'):
                raise ValueError('Demo content cannot be published')
            db.execute("UPDATE jobs SET status='ready',error=NULL,updated_at=? WHERE id=?", (stamp(), ident))
        self.event(ident, 'approved')

    def recover_generation(self):
        # Invoke only when no other generator is running; publication states are unaffected.
        with self.db() as db:
            db.execute("UPDATE batches SET status='failed',error='Recovered interrupted generation' WHERE status='generating'")

    def backup(self):
        dest = self.root / 'state/backups' / (now().strftime('%Y-%m-%d') + '.sqlite3')
        dest.parent.mkdir(exist_ok=True)
        with self.db() as src, closing(sqlite3.connect(dest)) as target:
            src.backup(target)
        for old in sorted(dest.parent.glob('*.sqlite3'))[:-7]:
            old.unlink()
