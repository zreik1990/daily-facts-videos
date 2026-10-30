#!/usr/bin/env python3
"""
Daily Facts Autopilot
=====================
Turns written scripts (FactScripts/*.json) into ~90-second vertical videos and
schedules 3 a day on YouTube.

Each video: free Pexels video clips matched to every point, large captions,
a counter, quiet background music. No voice.

Run:  python shorts_autopilot.py              (make today's videos, then upload)
      python shorts_autopilot.py --render     (only make videos)
      python shorts_autopilot.py --upload     (only upload what is in Ready_Facts)
      python shorts_autopilot.py --auth       (sign in to the YouTube channel for these videos)
      python shorts_autopilot.py --dry-run    (make videos, show what would upload)
      python shorts_autopilot.py --preview 1  (make 1 sample video into Preview_Facts, nothing scheduled)
"""

import argparse
import datetime as dt
import json
import random
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import scenic_autopilot as core
from scenic_autopilot import BASE, AUDIO_EXT, log, run, probe_duration, ffmpeg_bin, find_font

CONFIG_NAME = "facts_config.json"
STATE_FILE = BASE / "facts_state.json"
TOKEN_NAME = "token_facts.json"
W, H = 1080, 1920

CATEGORY_STYLE = {
    "education": {"label": "LEARN SOMETHING", "accent": (80, 170, 255), "bg": ("0x0b2a4a", "0x1d6fa5")},
    "health": {"label": "HEALTH TIP", "accent": (70, 210, 140), "bg": ("0x0d3b2e", "0x2a9d72")},
    "fun": {"label": "FUN FACT", "accent": (255, 190, 60), "bg": ("0x4a1d0b", "0xc2571a")},
}
HEALTH_NOTE = "General information only, not medical advice."


# --------------------------------------------------------------------------- state & scripts

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"used_ids": [], "last_slot": None}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_scripts(cfg):
    scripts = []
    for f in sorted(cfg["folders"]["scripts"].glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            log.error("Script file %s is not valid JSON: %s", f.name, exc)
            continue
        for s in data:
            s["_file"] = f.name
            scripts.append(s)
    return scripts


# --------------------------------------------------------------------------- Pexels

def pexels_search(cfg, query):
    key = cfg.get("pexels_api_key", "").strip()
    if not key:
        return []
    cache = cfg["folders"]["cache"] / "searches"
    cache.mkdir(parents=True, exist_ok=True)
    cached = cache / ("".join(c if c.isalnum() else "_" for c in query.lower())[:60] + ".json")
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode(
        {"query": query, "orientation": "portrait", "per_page": 15, "size": "medium"})
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "DailyFactsAutopilot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        videos = json.loads(resp.read().decode("utf-8")).get("videos", [])
    results = []
    for v in videos:
        files = [f for f in v.get("video_files", []) if f.get("width") and f.get("height")
                 and f.get("file_type") == "video/mp4"]
        portrait = [f for f in files if f["height"] > f["width"] and f["height"] >= 1280]
        pool = portrait or [f for f in files if f["height"] >= 720]
        if not pool:
            continue
        best = min(pool, key=lambda f: abs(f["height"] - 1920))
        results.append({"id": v["id"], "url": best["link"], "duration": v.get("duration", 0),
                        "author": (v.get("user") or {}).get("name", "")})
    cached.write_text(json.dumps(results), encoding="utf-8")
    return results


def get_clip(cfg, query, used_ids):
    """Return a local clip path for the query, avoiding clips already used in this video."""
    for q in [query, " ".join(query.split()[:2]), query.split()[0] if query else "nature"]:
        try:
            options = pexels_search(cfg, q)
        except Exception as exc:
            log.warning("  Pexels search failed for '%s': %s", q, exc)
            return None
        fresh = [o for o in options if o["id"] not in used_ids]
        if not fresh:
            continue
        choice = random.choice(fresh[:6])
        path = cfg["folders"]["cache"] / f"pexels_{choice['id']}.mp4"
        if not path.exists():
            req = urllib.request.Request(choice["url"], headers={"User-Agent": "DailyFactsAutopilot/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(path, "wb") as out:
                shutil.copyfileobj(resp, out)
        used_ids.add(choice["id"])
        return path
    return None


# --------------------------------------------------------------------------- caption cards

def wrap(draw, text, font, max_width):
    words, lines, line = text.split(), [], ""
    for w in words:
        test = f"{line} {w}".strip()
        if draw.textlength(test, font=font) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def make_card(path, text, kind, category, counter="", footer="", channel="", area=(520, 620), box_style="dark"):
    from PIL import Image, ImageDraw
    style = CATEGORY_STYLE.get(category, CATEGORY_STYLE["fun"])
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin, box_w = 80, W - 80 - 170          # leave room for YouTube's buttons on the right

    # top label
    label_font = find_font(44)
    label = style["label"]
    lw = draw.textlength(label, font=label_font)
    draw.rounded_rectangle((margin, 230, margin + lw + 60, 310), radius=40, fill=style["accent"] + (235,))
    draw.text((margin + 30, 243), label, font=label_font, fill=(20, 20, 20))
    if channel:
        draw.text((margin, 330), channel, font=find_font(36), fill=(255, 255, 255, 220),
                  stroke_width=2, stroke_fill=(0, 0, 0, 200))

    # main text
    size = 96 if kind == "hook" else (78 if kind == "point" else 74)
    font = find_font(size)
    area_top, area_h = area
    lines = wrap(draw, text, font, box_w - 80)
    while (len(lines) > 7 or int(size * 1.25) * len(lines) > area_h) and size > 48:
        size -= 6
        font = find_font(size)
        lines = wrap(draw, text, font, box_w - 80)
    line_h = int(size * 1.25)
    block_h = line_h * len(lines)
    top = area_top + max(0, (area_h - block_h) // 2)
    pad = 45
    counter_font = find_font(42)
    extra = 70 if counter else 0
    accent = style["accent"]
    if box_style == "light":
        box_fill, text_fill, stroke, counter_fill = (255, 255, 255, 238), (30, 30, 40, 255), 0, accent + (255,)
        hook_fill = tuple(int(c * 0.55) for c in accent) + (255,)
    elif box_style == "color":
        box_fill, text_fill, stroke, counter_fill = accent + (240,), (20, 20, 30, 255), 0, (255, 255, 255, 255)
        hook_fill = (20, 20, 30, 255)
    else:
        box_fill, text_fill, stroke, counter_fill = (0, 0, 0, 165), (255, 255, 255, 255), 3, accent + (255,)
        hook_fill = accent + (255,)
    draw.rounded_rectangle((margin, top - pad - extra, margin + box_w, top + block_h + pad),
                           radius=36, fill=box_fill)
    if counter:
        draw.text((margin + 40, top - pad - extra + 22), counter, font=counter_font, fill=counter_fill)
    color = hook_fill if kind == "hook" else text_fill
    for i, line in enumerate(lines):
        draw.text((margin + 40, top + i * line_h), line, font=font, fill=color,
                  stroke_width=stroke, stroke_fill=(0, 0, 0, 255))

    if footer:
        f_font = find_font(38)
        f_lines = wrap(draw, footer, f_font, box_w - 40)
        y = top + block_h + pad + 40
        for fl in f_lines:
            draw.text((margin + 10, y), fl, font=f_font, fill=(255, 255, 255, 230),
                      stroke_width=2, stroke_fill=(0, 0, 0, 220))
            y += 50
    img.save(path)


def card_seconds(cfg, text, kind):
    wps = float(cfg.get("reading_words_per_second", 2.3))
    words = len(text.split())
    if kind == "hook":
        return max(3.5, min(6.0, words / wps + 1.5))
    if kind == "outro":
        return 4.5
    return max(4.0, min(11.0, words / wps + 2.0))


# --------------------------------------------------------------------------- rendering

def render_segment(cfg, clip, gradient, card_png, seconds, out):
    ff = ffmpeg_bin(cfg)
    fx = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,"
          f"eq=brightness=-0.07:saturation=1.08,setsar=1,format=yuv420p")
    if clip:
        length = probe_duration(cfg, clip)
        start = random.uniform(0, max(length - seconds - 0.2, 0)) if length > seconds else 0
        src = ["-stream_loop", "-1", "-ss", f"{start:.2f}", "-i", clip]
    else:
        c0, c1 = gradient
        src = ["-f", "lavfi", "-i", f"gradients=s={W}x{H}:c0={c0}:c1={c1}:speed=0.008:r=30:d={seconds + 1:.2f}"]
    run([ff, "-y", *src, "-loop", "1", "-t", f"{seconds:.2f}", "-i", card_png,
         "-filter_complex",
         f"[0:v]{fx}[bg];[1:v]format=rgba,fade=t=in:st=0:d=0.35:alpha=1[t];"
         f"[bg][t]overlay=0:0:format=auto,format=yuv420p[v]",
         "-map", "[v]", "-t", f"{seconds:.2f}", "-r", "30",
         "-c:v", "libx264", "-preset", cfg.get("encoder_preset", "veryfast"), "-crf", "21",
         "-pix_fmt", "yuv420p", "-an", out])


def render_video(cfg, script, out_path, work):
    category = script.get("category", "fun")
    style = CATEGORY_STYLE.get(category, CATEGORY_STYLE["fun"])
    channel = cfg.get("channel_label", "")
    is_cartoon = cfg.get("style", "clips") in ("cartoon", "animated")
    if is_cartoon:
        import anim
        import cartoon
        sid = script.get("id", "x")
        look = anim.Look(sid, category)
        sprites = anim.mascot_sprites(work, category, look.outfit, look.glasses, look.mascot_color)
        rng = random.Random(look.seed)
        scene_pool = {"education": ["city", "sky", "desert", "park"], "health": ["park", "sky", "nursery", "city"],
                      "fun": ["sky", "park", "ocean", "nursery"]}.get(category, ["park", "sky"])
        rng.shuffle(scene_pool)
        log.info("  look: captions %s/%s, Pip outfit %s%s", look.box_style, look.entrance, look.outfit,
                 " + sunglasses" if look.glasses else "")

    cards = [("hook", script["hook"]["text"], script["hook"].get("search", ""), script["hook"].get("anim"))]
    for p in script["points"]:
        cards.append(("point", p["text"], p.get("search", ""), p.get("anim")))
    outro = script.get("outro") or cfg.get("default_outro", "Follow for 3 new videos every day")
    cards.append(("outro", outro, script.get("outro_search", "") or script["points"][-1].get("search", ""),
                  script.get("outro_anim") or script["hook"].get("anim")))

    durations = [card_seconds(cfg, t, k) for k, t, _, _ in cards]
    target = float(cfg.get("target_seconds", 90))
    total = sum(durations)
    if total < target * 0.9:
        factor = min(target / total, 1.35)
        durations = [d * factor if k == "point" else d for d, (k, _, _, _) in zip(durations, cards)]

    used_ids = set()
    segments = []
    last_prop = None
    n_points = len(script["points"])
    for i, ((kind, text, search, chosen), seconds) in enumerate(zip(cards, durations)):
        png = work / f"card_{i:02d}.png"
        counter = f"{i} / {n_points}" if kind == "point" else ""
        footer = HEALTH_NOTE if (kind == "outro" and category == "health") else ""
        seg = work / f"seg_{i:02d}.mp4"
        if is_cartoon:
            make_card(png, text, kind, category, counter, footer, channel if kind == "hook" else "",
                      area=(430, 600), box_style=look.box_style)
            prop = chosen if chosen in anim.PROPS else anim.pick_prop(text, search, category, i, rng)
            if not chosen and prop == last_prop:      # avoid the same animation twice in a row
                prop = rng.choice([p for p in ("idea", "book", "globe", "brain", "fruit", "heart", "walk") if p != prop])
            last_prop = prop
            scene = anim.SCENE_FOR_PROP.get(prop) or scene_pool[i % len(scene_pool)]
            scene_png = work / f"scene_{i:02d}.png"
            cartoon.draw_scene(scene, look.seed + i, scene_png)
            anim.render_segment(ffmpeg_bin(cfg), cfg.get("encoder_preset", "veryfast"), scene_png, png, prop,
                                seconds, look, sprites, wave=(kind in ("hook", "outro")), out_path=seg,
                                offset=i * 1.37)
        else:
            make_card(png, text, kind, category, counter, footer, channel if kind == "hook" else "")
            clip = get_clip(cfg, search, used_ids) if search else None
            if clip is None and search and cfg.get("pexels_api_key"):
                log.warning("  no clip found for '%s', using a color background", search)
            render_segment(cfg, clip, style["bg"], png, seconds, seg)
        segments.append(seg)

    listing = work / "list.txt"
    listing.write_text("".join(f"file '{s.as_posix()}'\n" for s in segments), encoding="utf-8")
    silent = work / "silent.mp4"
    run([ffmpeg_bin(cfg), "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", silent])
    length = probe_duration(cfg, silent)

    music_dir = cfg["folders"]["music"]
    tracks = [f for f in music_dir.iterdir() if f.suffix.lower() in AUDIO_EXT] if music_dir.exists() else []
    if tracks:
        track = random.choice(tracks)
        t_len = probe_duration(cfg, track)
        vol = cfg.get("music_volume", 0.35)
        run([ffmpeg_bin(cfg), "-y", "-i", silent, "-stream_loop", "-1", "-i", track,
             "-filter_complex",
             f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={vol},"
             f"afade=t=in:d=1,afade=t=out:st={max(length - 2.5, 0):.2f}:d=2.5[a]",
             "-map", "0:v", "-map", "[a]", "-t", f"{length:.2f}", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_path])
    else:
        shutil.copy(silent, out_path)
    return length


# --------------------------------------------------------------------------- text & schedule

def make_metadata(cfg, script):
    """Caption rules (2026 research): keyword-led first line, 3 topic + 2 category hashtags
    (Instagram allows max 5), a comment prompt, no #shorts (YouTube detects Shorts itself),
    and specific search phrases in YouTube's tags field."""
    category = script.get("category", "fun")
    title = script["title"].strip()
    if len(title) > 90:
        title = title[:90].rsplit(" ", 1)[0]

    def tagify(phrase):
        return "#" + "".join(ch for ch in phrase.lower() if ch.isalnum())

    topic = [tagify(t) for t in script.get("tags", [])][:3]
    broad = cfg.get("hashtags", {}).get(category, [])
    hashtags = []
    for h in topic + broad:
        if h not in hashtags and len(h) > 2:
            hashtags.append(h)
    hashtags = hashtags[: int(cfg.get("max_hashtags", 5))]

    hook = script["hook"]["text"]
    lead = title if title[-1:] in "?!." else title + "."
    norm = lambda x: "".join(ch for ch in x.lower() if ch.isalnum())
    first = hook if norm(title)[:20] in norm(hook) else lead + " " + hook
    lines = [first, ""]
    lines += [f"{i}. {p['text']}" for i, p in enumerate(script["points"], 1)]
    lines += ["", cfg.get("comment_prompt", "Which fact surprised you most? Tell us in the comments, "
                                             "and follow for 3 new videos every day.")]
    if category == "health":
        lines += ["", HEALTH_NOTE + " Talk to a doctor about your own health."]
    if script.get("sources"):
        lines += ["Sources: " + "; ".join(script["sources"])]
    if cfg.get("style", "clips") == "clips":
        lines += ["", "Video clips: Pexels (pexels.com)"]
    lines += ["", " ".join(hashtags)]
    tags = []
    for t in script.get("tags", []) + script.get("search_terms", []) + cfg.get("tags", []):
        if t not in tags:
            tags.append(t)
    return title, "\n".join(lines)[:2100], tags[:15]


def next_slot(cfg, last_iso):
    tz = ZoneInfo(cfg["timezone"])
    times = sorted(core.parse_hhmm(t) for t in cfg["schedule"]["times"])
    floor = dt.datetime.now(tz) + dt.timedelta(hours=cfg["schedule"].get("min_lead_hours", 2))
    if last_iso:
        floor = max(floor, dt.datetime.fromisoformat(last_iso).astimezone(tz) + dt.timedelta(minutes=1))
    day = floor.date()
    for _ in range(400):
        for t in times:
            slot = dt.datetime.combine(day, t, tzinfo=tz)
            if slot >= floor:
                return slot
        day += dt.timedelta(days=1)
    raise RuntimeError("Could not find a publish slot")


# --------------------------------------------------------------------------- main flows

def render_batch(cfg, state, count, preview=False):
    scripts = load_scripts(cfg)
    used = set(state.get("used_ids", []))
    pending = [s for s in scripts if s.get("id") not in used]
    log.info("Script bank: %d total, %d not yet used", len(scripts), len(pending))
    if len(pending) - count < 6:
        note = BASE / "SCRIPTS_RUNNING_LOW.txt"
        note.write_text(f"Only {max(len(pending) - count, 0)} scripts left after this run.\n"
                        "Ask Claude for the next batch and put the .json file in the FactScripts folder.\n",
                        encoding="utf-8")
        log.warning("Scripts are running low (%d left). Ask Claude for the next batch.", len(pending))
    if not pending:
        return 0

    made = 0
    for script in pending[:count]:
        sid = script.get("id", f"video{made}")
        log.info("=== Rendering %s: %s", sid, script["title"])
        work = cfg["folders"]["work"] / sid
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        try:
            out = work / "video.mp4"
            length = render_video(cfg, script, out, work)
            title, desc, tags = make_metadata(cfg, script)
            if preview:
                dest_dir = BASE / "Preview_Facts"
                dest_dir.mkdir(exist_ok=True)
                shutil.move(str(out), str(dest_dir / f"{sid}.mp4"))
                log.info("  preview saved: Preview_Facts/%s.mp4 (%.0f s)", sid, length)
            else:
                slot = next_slot(cfg, state.get("last_slot"))
                core.write_item(cfg["folders"]["ready"], f"{slot.strftime('%Y%m%d-%H%M')}_{sid}", [(out, "video.mp4")],
                                {"kind": "short", "title": title, "description": desc, "tags": tags,
                                 "publish_at": slot.isoformat(), "script_id": sid,
                                 "category": script.get("category")})
                state["last_slot"] = slot.isoformat()
                state.setdefault("used_ids", []).append(sid)
                save_state(state)
                log.info("  ready: %.0f s video, publishes %s", length, slot.strftime("%a %d %b %H:%M"))
            made += 1
        except Exception as exc:
            log.error("  failed on %s: %s", sid, exc)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return made


def main():
    parser = argparse.ArgumentParser(description="Daily Facts Autopilot")
    parser.add_argument("--render", action="store_true", help="only make videos")
    parser.add_argument("--upload", action="store_true", help="only upload what is ready")
    parser.add_argument("--auth", action="store_true", help="sign in to the YouTube channel for these videos")
    parser.add_argument("--dry-run", action="store_true", help="make videos but do not upload")
    parser.add_argument("--preview", type=int, metavar="N", help="make N sample videos, nothing scheduled")
    args = parser.parse_args()

    core.setup_logging("facts_autopilot.log")
    cfg = core.load_config(CONFIG_NAME)
    state = load_state()

    if shutil.which(ffmpeg_bin(cfg)) is None and not Path(ffmpeg_bin(cfg)).exists():
        log.error("ffmpeg was not found. Run setup_windows.bat, or set ffmpeg_path in facts_config.json.")
        sys.exit(1)
    if not cfg.get("pexels_api_key"):
        log.warning("No Pexels key in facts_config.json: videos will use color backgrounds instead of clips.")

    if args.auth:
        core.youtube_client(interactive=True, token_name=TOKEN_NAME)
        log.info("Signed in. Token saved to %s.", TOKEN_NAME)
        return
    if args.preview:
        render_batch(cfg, state, args.preview, preview=True)
        return
    if not args.upload:
        render_batch(cfg, state, int(cfg.get("videos_per_run", 3)))
    if not args.render:
        core.upload_all(cfg, dry_run=args.dry_run, token_name=TOKEN_NAME)


if __name__ == "__main__":
    main()
