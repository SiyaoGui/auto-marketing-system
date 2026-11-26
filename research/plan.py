"""Build an internal edit decision list from a normalized Notion export (stdin)."""
import json
import sys


def build(data):
    brand, topic = data["brand_id"], data["topic_id"]

    def relevant(row):
        return row["brand_id"] == brand and topic in row["topic_ids"]

    references = sorted(r["id"] for r in data["references"]
                        if relevant(r) and r.get("source_url") and r.get("evidence_ids"))
    inspirations = sorted(r["id"] for r in data["inspirations"] if relevant(r))
    assets = {r["id"]: r for r in data["assets"] if relevant(r)
              and data["purpose"] in r["authorized_uses"]}
    if data["purpose"] != "internal_preview" or not references or not data["scenes"]:
        raise ValueError("Internal preview needs matching evidence and scenes")
    scenes = []
    cursor = 0
    for shot in data["scenes"]:
        asset = assets.get(shot["asset_id"])
        start, end = shot["source_in_ms"], shot["source_out_ms"]
        if not asset or type(start) is not int or type(end) is not int or not 0 <= start < end <= asset["duration_ms"]:
            raise ValueError("Missing asset, permission or valid source interval")
        if not shot["narration"].strip() or not shot["headline"].strip():
            raise ValueError("Missing original script or headline")
        scenes.append(dict(shot, timeline_in_ms=cursor, timeline_out_ms=cursor + end - start))
        cursor += end - start
    return dict(brand_id=brand, topic_id=topic, references=references, inspirations=inspirations,
                purpose=data["purpose"], scenes=scenes, duration_ms=cursor)


if __name__ == "__main__":
    print(json.dumps(build(json.load(sys.stdin)), ensure_ascii=False, indent=2))
