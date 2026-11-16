"""フル取得をせずに、キャッシュへ相性・地名データだけ再計算して入れる。"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import matchups
p = ROOT / "data" / "cache.json"
d = json.loads(p.read_text(encoding="utf-8"))
d["matchups"] = matchups.build(d["chars"], d.get("mapInfo"))
mn_def = json.loads((ROOT / "data" / "mapnames.json").read_text(encoding="utf-8"))
mn_info = json.loads((ROOT / "web" / "mapnames" / "info.json").read_text(encoding="utf-8"))
d["mapNames"] = {"source": mn_def.get("_source", ""), "maps": {
    v["name"]: {"key": k, "img": f"mapnames/{k}.jpg", "hatches": mn_info[k], "tips": v.get("tips", []),
                "basement": v.get("basement", []), "areas": [l[0] for l in v["labels"]]}
    for k, v in mn_def.items() if not k.startswith("_") and k in mn_info}}
p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
print("ok", len(d["matchups"]["chars"]), list(d["mapNames"]["maps"]))
