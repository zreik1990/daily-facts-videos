#!/usr/bin/env python3
"""
Cloud daily runner for Daily Facts.

Picks the next N unused scripts, renders them as animated cartoon videos,
uploads each video as an asset on a GitHub release (public download link),
and writes plan.json with everything needed to schedule the posts in Metricool
(title, caption, YouTube tags, publish time, public video URL).

It does NOT post anything itself: the scheduled Claude session reads plan.json
and schedules each item through the Metricool connector, then commits state.

Usage:
  python daily_run.py --date 2026-11-01 --repo zreik1990/daily-facts-videos [--count 3] [--no-upload]
"""

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import scenic_autopilot as core          # noqa: E402
import shorts_autopilot as facts         # noqa: E402

STATE = BASE / "facts_state.json"


def gh(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {r.stderr.strip()[:400]}")
    return r.stdout


def ensure_release(repo, tag, title):
    try:
        gh("release", "view", tag, "--repo", repo, "--json", "tagName")
    except RuntimeError:
        gh("release", "create", tag, "--repo", repo, "--title", title,
           "--notes", "Daily Facts videos for " + tag.replace("videos-", ""), "--latest=false")


def upload_asset(repo, tag, path):
    gh("release", "upload", tag, str(path), "--repo", repo, "--clobber")
    return f"https://github.com/{repo}/releases/download/{tag}/{path.name}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="publish date YYYY-MM-DD (Riyadh)")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--no-upload", action="store_true")
    args = ap.parse_args()

    core.setup_logging("daily_run.log")
    cfg = core.load_config("facts_config.json")
    cfg["channel_label"] = ""
    state = json.loads(STATE.read_text()) if STATE.exists() else {"used_ids": []}
    used = set(state.get("used_ids", []))

    scripts = [s for s in facts.load_scripts(cfg) if s.get("id") not in used]
    # one of each category per day when possible: education 09:00, health 15:00, fun 20:00
    order = ["education", "health", "fun"]
    picked = []
    for cat in order[: args.count]:
        match = next((s for s in scripts if s.get("category") == cat and s not in picked), None)
        if match:
            picked.append(match)
    for s in scripts:
        if len(picked) >= args.count:
            break
        if s not in picked:
            picked.append(s)
    if not picked:
        print(json.dumps({"error": "no unused scripts left"}))
        sys.exit(2)

    times = cfg["schedule"]["times"]
    out_dir = BASE / "out" / args.date
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"videos-{args.date}"
    if not args.no_upload:
        ensure_release(args.repo, tag, f"Daily Facts {args.date}")

    plan = []
    for i, script in enumerate(picked):
        sid = script["id"]
        work = (BASE / "_work_daily" / sid)
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        video = out_dir / f"{args.date}_{i + 1}_{sid}.mp4"
        length = facts.render_video(cfg, script, video, work)
        shutil.rmtree(work, ignore_errors=True)
        title, caption, yt_tags = facts.make_metadata(cfg, script)
        url = None if args.no_upload else upload_asset(args.repo, tag, video)
        cat = script.get("category", "fun")
        plan.append({
            "script_id": sid,
            "category": cat,
            "publish_at": f"{args.date}T{times[i % len(times)]}:00",
            "timezone": cfg["timezone"],
            "title": title,
            "caption": caption,
            "youtube_tags": yt_tags,
            "youtube_category": {"education": "EDUCATION", "health": "HOWTO_STYLE", "fun": "ENTERTAINMENT"}.get(cat, "ENTERTAINMENT"),
            "video_url": url,
            "local_file": str(video),
            "seconds": round(length, 1),
        })
        state.setdefault("used_ids", []).append(sid)

    remaining = len(scripts) - len(picked)
    result = {"date": args.date, "items": plan, "scripts_remaining": remaining}
    (out_dir / "plan.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    STATE.write_text(json.dumps(state, indent=2))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
