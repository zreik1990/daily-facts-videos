#!/usr/bin/env python3
"""Check every FactScripts/*.json file: valid JSON, required fields, unique ids, known animations."""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import anim  # noqa: E402

errors, ids, count = [], set(), 0
for f in sorted((BASE / "FactScripts").glob("*.json")):
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{f.name}: invalid JSON ({exc})")
        continue
    for s in data:
        count += 1
        sid = s.get("id", "?")
        where = f"{f.name}:{sid}"
        if sid in ids:
            errors.append(f"{where}: duplicate id")
        ids.add(sid)
        if s.get("category") not in ("education", "health", "fun"):
            errors.append(f"{where}: category must be education, health or fun")
        for key in ("title", "hook", "points", "tags"):
            if key not in s:
                errors.append(f"{where}: missing '{key}'")
        if s.get("category") == "health" and not s.get("sources"):
            errors.append(f"{where}: health scripts need 'sources'")
        pts = s.get("points", [])
        if not 6 <= len(pts) <= 9:
            errors.append(f"{where}: needs 6-9 points (has {len(pts)})")
        for p in [s.get("hook", {})] + pts:
            a = p.get("anim")
            if a and a not in anim.PROPS:
                errors.append(f"{where}: unknown anim '{a}'")
            if len(p.get("text", "").split()) > 28:
                errors.append(f"{where}: text too long: {p.get('text', '')[:40]}...")
print(f"{count} scripts checked, {len(errors)} problem(s)")
for e in errors:
    print(" -", e)
print("Available animations:", ", ".join(sorted(anim.PROPS)))
sys.exit(1 if errors else 0)
