"""Build a credential-free n8n workflow from the real Apify run snapshot."""
import json
from pathlib import Path
from uuid import UUID, uuid5

ROOT = Path(__file__).resolve().parent
RUN = 'cQyC37yEd8EOE3aD7'
NAMESPACE = UUID('4dba8e7e-4c63-49f4-9ff8-e95f4be713e1')
VALIDATE = r'''
const input = $input.first().json;
const rows = input.rows;
if (!Array.isArray(rows)) throw new Error('Invalid snapshot: rows must be an array');
const accepted = [], quarantine = [], duplicates = [];
const seen = new Set();
let ignored = 0;
const cleanCount = (value) => Number.isSafeInteger(value) && value >= 0 ? value : null;
for (let rowIndex = 0; rowIndex < rows.length; rowIndex++) {
  const row = rows[rowIndex];
  if (row?.record_type === 'target') { ignored++; continue; }
  let reason;
  if (row?.record_type !== 'note' || row.status !== 'ok') reason = 'not_successful_note';
  else if (row.noteType !== 'video') reason = 'not_video';
  else if (!row.url) reason = 'missing_original_url';
  else if (!/^[a-f0-9]{24}$/.test(row.id ?? '') ||
      !(new RegExp('^https?://www\\.(xiaohongshu|rednote)\\.com/(explore|discovery/item)/' + row.id + '$')).test(row.url)) {
    reason = 'invalid_original_url_or_id';
  }
  if (reason) { quarantine.push({row_index: rowIndex, reason}); continue; }
  const key = `xiaohongshu:${row.id}`;
  if (seen.has(key)) { duplicates.push({row_index: rowIndex, key}); continue; }
  seen.add(key);
  accepted.push({key, original_url: row.url, likes: cleanCount(row.likes),
    saves: cleanCount(row.collects), comments: cleanCount(row.comments), shares: cleanCount(row.shares),
    counts_exact: typeof row.countsExact === 'boolean' ? row.countsExact : null,
    views: null, collected_at: row.scraped_at ?? null});
}
return [{json: {mode: 'actual_snapshot_replay', source_run_id: input.source_run_id,
  input_rows: rows.length, accepted_count: accepted.length, quarantined_count: quarantine.length,
  ignored_count: ignored, duplicate_count: duplicates.length, empty: rows.length === 0,
  accepted, quarantine, duplicates}}];
'''.strip()


def build():
    rows = json.loads((ROOT / 'live-test' / f'apify-run-{RUN}.json').read_text('utf-8-sig'))
    required = ('record_type', 'status', 'noteType', 'likes', 'collects', 'comments', 'shares', 'countsExact', 'scraped_at')
    filtered = []
    for row in rows:
        clean = {field: row.get(field) for field in required}
        # Drop URL tokens, opaque search IDs, author records, comments, and media links.
        clean['url'] = row['url'].split('?', 1)[0] if row.get('url') else None
        clean['id'] = row.get('id') if clean['url'] else None
        filtered.append(clean)
    snapshot = {'source_run_id': RUN, 'rows': filtered}
    nodes = [
        ('Manual Trigger', 'manualTrigger', 1, {}, [0, 0]),
        ('Load actual Apify snapshot', 'code', 2, {'jsCode': 'return [{json: ' + json.dumps(snapshot) + '}];'}, [240, 0]),
        ('Validate discovery rows', 'code', 2, {'jsCode': VALIDATE}, [480, 0]),
        ('Scope', 'stickyNote', 1, {'content': '## 实际采集数据回放\n基于 Apify 真实历史运行 cQyC37yEd8EOE3aD7。只校验原始数据结构和隔离规则。无外部调用，无凭证，无发布，无定时任务。', 'width': 540, 'height': 140}, [0, -200]),
    ]
    return {'name': 'DK Service | A | Real dataset replay', 'active': False,
            'nodes': [{'id': str(uuid5(NAMESPACE, name)), 'name': name, 'type': f'n8n-nodes-base.{node_type}',
                       'typeVersion': version, 'position': position, 'parameters': parameters}
                      for name, node_type, version, parameters, position in nodes],
            'connections': {nodes[index][0]: {'main': [[{'node': nodes[index + 1][0], 'type': 'main', 'index': 0}]]}
                            for index in range(2)},
            'settings': {'executionOrder': 'v1', 'saveManualExecutions': True}, 'pinData': {}}


if __name__ == '__main__':
    path = ROOT / 'n8n-real-dataset-replay.json'
    path.write_text(json.dumps(build(), ensure_ascii=False, indent=2), encoding='utf-8')
    print(path.name)
