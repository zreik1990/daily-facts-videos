#!/usr/bin/env python3
"""
Cloud daily runner for Daily Facts.

Picks the next N unused scripts, renders them as animated cartoon videos,
pushes the videos to the 'media' branch and links them through jsDelivr (public),
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


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {r.stderr.strip()[:400]}")
    return r.stdout.strip()


def publish_media(repo, date, files):
    """Force-push today's videos as the only content of the 'media' branch and return
    public jsDelivr links pinned to that commit (served as video/mp4, max 20 MB each).
    Metricool copies each video to its own storage when the post is scheduled, so the
    branch only has to hold the current day's files."""
    tmp = BASE / "_media_branch"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    git("init", "-q", "-b", "media", cwd=tmp)
    git("config", "user.name", "Daily Facts Bot", cwd=tmp)
    git("config", "user.email", "noreply@anthropic.com", cwd=tmp)
    for f in files:
        shutil.copy(f, tmp / f.name)
    (tmp / "README.md").write_text(f"Videos for {date}. Replaced every day.\n")
    git("add", "-A", cwd=tmp)
    git("commit", "-q", "-m", f"Videos for {date}", cwd=tmp)
    remote = f"https://github.com/{repo}.git"
    git("push", "-f", remote, "media:media", cwd=tmp)
    sha = git("rev-parse", "HEAD", cwd=tmp)
    shutil.rmtree(tmp, ignore_errors=True)
    return {f.name: f"https://cdn.jsdelivr.net/gh/{repo}@{sha}/{f.name}" for f in files}


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
        url = None
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

    if not args.no_upload:
        links = publish_media(args.repo, args.date, [Path(i["local_file"]) for i in plan])
        for item in plan:
            item["video_url"] = links[Path(item["local_file"]).name]
    remaining = len(scripts) - len(picked)
    result = {"date": args.date, "items": plan, "scripts_remaining": remaining}
    (out_dir / "plan.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    STATE.write_text(json.dumps(state, indent=2))
    print("PLAN_JSON " + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
