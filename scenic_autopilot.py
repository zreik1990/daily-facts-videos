#!/usr/bin/env python3
"""
Scenic Autopilot
================
Turns folders of your own nature clips into finished YouTube content:

  Raw/<Place name>/  (your phone or drone clips, plus optional nature-sound file)
        |
        v
  1. a long relaxing video (crossfaded scenes, looped to 1-3 hours, music + nature sound)
  2. several vertical Shorts cut from the best moments
  3. a thumbnail with big text
  4. title, description and tags
  5. a publish time (Mon/Wed/Fri for long videos, daily for Shorts)
        |
        v
  Ready/<item>/   ->  uploaded to YouTube as scheduled videos  ->  Uploaded/<item>/

Run:  python scenic_autopilot.py              (process new folders, then upload)
      python scenic_autopilot.py --process    (only build videos)
      python scenic_autopilot.py --upload     (only upload what is in Ready)
      python scenic_autopilot.py --auth       (sign in to YouTube once)
      python scenic_autopilot.py --dry-run    (build videos, show what would upload)
"""

import argparse
import datetime as dt
import json
import logging
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

log = logging.getLogger("autopilot")


# --------------------------------------------------------------------------- setup

def setup_logging(logfile="autopilot.log"):
    log.setLevel(logging.INFO)
    if log.handlers:
        return
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    log.addHandler(console)
    filelog = logging.FileHandler(BASE / logfile, encoding="utf-8")
    filelog.setFormatter(fmt)
    log.addHandler(filelog)


def load_config(name="config.json"):
    cfg = json.loads((BASE / name).read_text(encoding="utf-8"))
    folders = {}
    for key, value in cfg["folders"].items():
        p = Path(value)
        folders[key] = p if p.is_absolute() else BASE / p
        folders[key].mkdir(parents=True, exist_ok=True)
    cfg["folders"] = folders
    return cfg


def load_state():
    path = BASE / "state.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"last_long_slot": None, "last_short_slot": None, "use_index": 0}


def save_state(state):
    (BASE / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- ffmpeg helpers

def ffmpeg_bin(cfg):
    return cfg.get("ffmpeg_path") or "ffmpeg"


def ffprobe_bin(cfg):
    ff = cfg.get("ffmpeg_path")
    if ff and ff != "ffmpeg":
        p = Path(ff)
        return str(p.with_name(p.name.replace("ffmpeg", "ffprobe")))
    return "ffprobe"


def run(cmd):
    log.debug("RUN %s", " ".join(map(str, cmd)))
    result = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"Command failed: {cmd[0]} ...\n{tail}")
    return result.stdout


def probe_duration(cfg, path):
    out = run([ffprobe_bin(cfg), "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", path])
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def encode_args(cfg):
    lv = cfg["long_video"]
    return ["-c:v", "libx264", "-preset", lv.get("encoder_preset", "veryfast"),
            "-crf", str(lv.get("crf", 20)), "-pix_fmt", "yuv420p"]


# --------------------------------------------------------------------------- building blocks

def build_cycle(cfg, clips, out_path, work):
    """Join clips with slow crossfades into one 'cycle' video (no audio)."""
    lv = cfg["long_video"]
    width, height = map(int, lv["resolution"].lower().split("x"))
    fps = lv.get("fps", 30)
    fade = float(lv.get("crossfade_seconds", 3))
    max_len = float(lv.get("max_clip_seconds", 60))

    inputs, durations = [], []
    for clip, length in clips:
        d = min(length, max_len)
        inputs += ["-i", clip]
        durations.append(d)

    parts = []
    for i, d in enumerate(durations):
        parts.append(
            f"[{i}:v]trim=0:{d:.3f},setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps},settb=AVTB,format=yuv420p,setsar=1[v{i}]")

    if len(durations) == 1:
        last, total = "v0", durations[0]
    else:
        last, total = "v0", durations[0]
        for i in range(1, len(durations)):
            offset = total - fade
            label = f"x{i}"
            parts.append(f"[{last}][v{i}]xfade=transition=fade:duration={fade}:offset={offset:.3f}[{label}]")
            last, total = label, total + durations[i] - fade

    edge = min(2.0, total / 4)
    parts.append(f"[{last}]fade=t=in:st=0:d={edge},fade=t=out:st={total - edge:.3f}:d={edge}[out]")

    script = work / "cycle_filter.txt"
    script.write_text(";\n".join(parts), encoding="utf-8")
    run([ffmpeg_bin(cfg), "-y", *inputs, "-filter_complex_script", script,
         "-map", "[out]", *encode_args(cfg), "-an", "-movflags", "+faststart", out_path])
    return total


def concat_audio(cfg, files, out_path):
    """Join several audio files into one track (48 kHz stereo)."""
    inputs, labels, parts = [], [], []
    for i, f in enumerate(files):
        inputs += ["-i", f]
        parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        labels.append(f"[a{i}]")
    parts.append("".join(labels) + f"concat=n={len(files)}:v=0:a=1[out]")
    run([ffmpeg_bin(cfg), "-y", *inputs, "-filter_complex", ";".join(parts),
         "-map", "[out]", "-c:a", "aac", "-b:a", "192k", out_path])


def build_audio(cfg, music_track, nature_track, total_seconds, out_path):
    """Loop music and nature sound to the full length and mix them."""
    lv = cfg["long_video"]
    inputs, chains, mix = [], [], []
    for track, vol in [(music_track, lv.get("music_volume", 0.9)),
                       (nature_track, lv.get("nature_volume", 0.6))]:
        if track is None:
            continue
        n = len(mix)
        inputs += ["-stream_loop", "-1", "-i", track]
        chains.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,volume={vol}[m{n}]")
        mix.append(f"[m{n}]")
    if not mix:
        return False
    fade_out = max(total_seconds - 6, 0)
    if len(mix) == 1:
        graph = ";".join(chains) + f";{mix[0]}afade=t=in:d=3,afade=t=out:st={fade_out:.3f}:d=6[out]"
    else:
        graph = (";".join(chains) + ";" + "".join(mix) +
                 f"amix=inputs={len(mix)}:duration=longest:normalize=0,"
                 f"afade=t=in:d=3,afade=t=out:st={fade_out:.3f}:d=6[out]")
    run([ffmpeg_bin(cfg), "-y", *inputs, "-filter_complex", graph, "-map", "[out]",
         "-t", f"{total_seconds:.3f}", "-c:a", "aac", "-b:a", "192k", out_path])
    return True


def build_long_video(cfg, cycle_path, audio_path, total_seconds, out_path):
    """Repeat the cycle to the target length (no re-encode) and add the audio."""
    cmd = [ffmpeg_bin(cfg), "-y", "-stream_loop", "-1", "-i", cycle_path]
    if audio_path:
        cmd += ["-i", audio_path, "-map", "0:v", "-map", "1:a", "-c:a", "copy"]
    else:
        cmd += ["-map", "0:v"]
    cmd += ["-t", f"{total_seconds:.3f}", "-c:v", "copy", "-movflags", "+faststart", out_path]
    run(cmd)


def build_short(cfg, clip, clip_len, music, out_path):
    sh = cfg["shorts"]
    seconds = min(float(sh.get("seconds", 20)), max(clip_len - 0.5, 3))
    start = max((clip_len - seconds) / 2, 0)
    edge = 0.6
    vf = (f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,"
          f"format=yuv420p,setsar=1,fade=t=in:st=0:d={edge},fade=t=out:st={seconds - edge:.3f}:d={edge}")
    cmd = [ffmpeg_bin(cfg), "-y", "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", clip]
    if music:
        track, track_len = music
        m_start = random.uniform(0, max(track_len - seconds - 1, 0))
        cmd += ["-ss", f"{m_start:.3f}", "-t", f"{seconds:.3f}", "-i", track,
                "-filter_complex",
                f"[0:v]{vf}[v];[1:a]aresample=48000,volume={sh.get('music_volume', 0.8)},"
                f"afade=t=in:d=1,afade=t=out:st={seconds - 1.5:.3f}:d=1.5[a]",
                "-map", "[v]", "-map", "[a]", "-c:a", "aac", "-b:a", "160k"]
    else:
        cmd += ["-vf", vf, "-an"]
    cmd += ["-t", f"{seconds:.3f}", *encode_args(cfg), "-movflags", "+faststart", out_path]
    run(cmd)


# --------------------------------------------------------------------------- thumbnail

def find_font(size):
    from PIL import ImageFont
    candidates = ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                  "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default()


def frame_score(img):
    from PIL import ImageStat
    hsv = img.convert("HSV")
    _, s, v = ImageStat.Stat(hsv).mean
    contrast = ImageStat.Stat(img.convert("L")).stddev[0]
    too_dark = v < 60
    return (s * 0.5 + v * 0.3 + contrast * 1.2) - (200 if too_dark else 0)


def build_thumbnail(cfg, clips, text, out_path, work):
    from PIL import Image, ImageDraw, ImageEnhance
    best, best_score = None, -1e9
    for n, (clip, length) in enumerate(clips[:8]):
        for frac in (0.25, 0.5, 0.75):
            frame = work / f"frame_{n}_{int(frac * 100)}.jpg"
            try:
                run([ffmpeg_bin(cfg), "-y", "-ss", f"{length * frac:.2f}", "-i", clip, "-frames:v", "1",
                     "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720", frame])
                img = Image.open(frame).convert("RGB")
            except Exception:
                continue
            score = frame_score(img)
            if score > best_score:
                best, best_score = img, score
    if best is None:
        raise RuntimeError("Could not grab any frame for the thumbnail")

    img = ImageEnhance.Brightness(best).enhance(1.06)
    img = ImageEnhance.Color(img).enhance(1.25)
    img = ImageEnhance.Contrast(img).enhance(1.12)

    draw = ImageDraw.Draw(img)
    size = 130
    font = find_font(size)
    while size > 40 and draw.textlength(text, font=font) > 1280 - 120:
        size -= 6
        font = find_font(size)
    x, y = 60, 720 - 60 - size
    draw.text((x, y), text, font=font, fill=(255, 255, 255), stroke_width=max(size // 18, 3), stroke_fill=(0, 0, 0))
    img.save(out_path, "JPEG", quality=90)


# --------------------------------------------------------------------------- text

def duration_text(hours):
    if hours < 1:
        return f"{int(round(hours * 60))} Minutes"
    return "1 Hour" if hours == 1 else f"{hours:g} Hours"


def music_credits(cfg):
    credits = cfg["folders"]["music"] / "credits.txt"
    return credits.read_text(encoding="utf-8").strip() if credits.exists() else ""


def make_text(cfg, place, use, kind):
    t = cfg["text"]
    hours = cfg["long_video"]["hours"]
    values = {
        "place": place,
        "use": use,
        "use_lower": use.lower(),
        "duration": duration_text(hours),
        "channel_name": t.get("channel_name", ""),
        "hashtags": " ".join(t.get("hashtags", [])),
        "music_credits": music_credits(cfg),
    }
    if kind == "long":
        title = t["title_template"].format(**values)
        description = "\n".join(t["description_template"]).format(**values)
    else:
        title = t["short_title_template"].format(**values)
        description = "\n".join(t["short_description_template"]).format(**values)
    title = title[:100]
    tags, total = [], 0
    for tag in [place, f"{place} 4k", use.lower(), *t.get("tags", [])]:
        if total + len(tag) + 1 > 480:
            break
        tags.append(tag)
        total += len(tag) + 1
    return title, description.strip()[:4900], tags


# --------------------------------------------------------------------------- scheduling

def parse_hhmm(s):
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def next_slot(cfg, last_iso, days, at_time):
    tz = ZoneInfo(cfg["timezone"])
    now = dt.datetime.now(tz) + dt.timedelta(hours=cfg["schedule"].get("min_lead_hours", 2))
    floor = now
    if last_iso:
        last = dt.datetime.fromisoformat(last_iso).astimezone(tz)
        floor = max(floor, last + dt.timedelta(minutes=1))
    day = floor.date()
    for _ in range(400):
        if DAY_NAMES[day.weekday()] in days:
            slot = dt.datetime.combine(day, at_time, tzinfo=tz)
            if slot >= floor:
                return slot
        day += dt.timedelta(days=1)
    raise RuntimeError("Could not find a publish slot")


# --------------------------------------------------------------------------- processing

def folder_is_settled(folder, minutes):
    newest = max((f.stat().st_mtime for f in folder.rglob("*") if f.is_file()), default=0)
    return (time.time() - newest) > minutes * 60


def write_item(ready_dir, name, files, meta):
    item = ready_dir / name
    if item.exists():
        shutil.rmtree(item)
    item.mkdir(parents=True)
    for src, dst_name in files:
        shutil.move(str(src), str(item / dst_name))
    (item / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [f"TITLE:\n{meta['title']}", f"\nPUBLISH AT:\n{meta['publish_at']}",
             f"\nDESCRIPTION:\n{meta['description']}", f"\nTAGS:\n{', '.join(meta['tags'])}"]
    (item / "upload_info.txt").write_text("\n".join(lines), encoding="utf-8")
    return item


def process_folder(cfg, state, folder):
    place = folder.name.replace("_", " ").replace("-", " ").strip()
    log.info("=== Processing '%s'", place)
    lv, sh, sched = cfg["long_video"], cfg["shorts"], cfg["schedule"]
    fade = float(lv.get("crossfade_seconds", 3))

    clips = []
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() in VIDEO_EXT:
            length = probe_duration(cfg, f)
            if length >= fade * 2 + 1:
                clips.append((f, length))
            else:
                log.warning("  skipping %s (too short: %.1fs)", f.name, length)
    if not clips:
        log.warning("  no usable clips in %s, skipping", folder)
        return False
    clips = clips[: int(lv.get("max_clips", 12))]
    nature = next((f for f in sorted(folder.iterdir()) if f.suffix.lower() in AUDIO_EXT), None)
    music_files = sorted(f for f in cfg["folders"]["music"].iterdir() if f.suffix.lower() in AUDIO_EXT)
    random.shuffle(music_files)
    log.info("  %d clips, nature sound: %s, music tracks: %d",
             len(clips), nature.name if nature else "none", len(music_files))

    work = cfg["folders"]["work"] / folder.name
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    uses = cfg["text"]["uses"]
    use = uses[state.get("use_index", 0) % len(uses)]
    total_seconds = float(lv["hours"]) * 3600
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    safe = "".join(ch if ch.isalnum() else "-" for ch in place).strip("-")[:40]

    # Long video
    log.info("  building scene cycle ...")
    cycle_len = build_cycle(cfg, clips, work / "cycle.mp4", work)
    log.info("  cycle is %.0f s, looping to %s", cycle_len, duration_text(lv["hours"]))
    music_track = None
    if music_files:
        music_track = work / "music.m4a"
        concat_audio(cfg, music_files, music_track)
    audio = work / "audio.m4a"
    has_audio = build_audio(cfg, music_track, nature, total_seconds, audio)
    if not has_audio:
        log.warning("  no music and no nature sound found: the long video will be silent")
    long_out = work / "video.mp4"
    build_long_video(cfg, work / "cycle.mp4", audio if has_audio else None, total_seconds, long_out)

    thumb_text = cfg["text"]["thumbnail_template"].format(
        duration=duration_text(lv["hours"]).upper(), use=use.upper(), place=place.upper())
    thumb = work / "thumbnail.jpg"
    build_thumbnail(cfg, clips, thumb_text, thumb, work)

    slot = next_slot(cfg, state.get("last_long_slot"), sched["long_days"], parse_hhmm(sched["long_time"]))
    title, desc, tags = make_text(cfg, place, use, "long")
    write_item(cfg["folders"]["ready"], f"{stamp}_{safe}_long",
               [(long_out, "video.mp4"), (thumb, "thumbnail.jpg")],
               {"kind": "long", "title": title, "description": desc, "tags": tags,
                "publish_at": slot.isoformat(), "place": place, "use": use})
    state["last_long_slot"] = slot.isoformat()
    log.info("  long video ready -> publishes %s", slot.strftime("%a %d %b %H:%M"))

    # Shorts
    music_info = [(m, probe_duration(cfg, m)) for m in music_files]
    ranked = sorted(clips, key=lambda c: c[1], reverse=True)[: int(sh.get("per_video", 6))]
    for n, (clip, length) in enumerate(ranked, 1):
        out = work / f"short_{n}.mp4"
        music = random.choice(music_info) if music_info else None
        build_short(cfg, clip, length, music, out)
        s_slot = next_slot(cfg, state.get("last_short_slot"), DAY_NAMES, parse_hhmm(sched["short_time"]))
        s_title, s_desc, s_tags = make_text(cfg, place, use, "short")
        write_item(cfg["folders"]["ready"], f"{stamp}_{safe}_short{n:02d}", [(out, "video.mp4")],
                   {"kind": "short", "title": s_title, "description": s_desc, "tags": s_tags,
                    "publish_at": s_slot.isoformat(), "place": place, "use": use})
        state["last_short_slot"] = s_slot.isoformat()
        log.info("  short %d ready -> publishes %s", n, s_slot.strftime("%a %d %b %H:%M"))

    state["use_index"] = state.get("use_index", 0) + 1
    save_state(state)
    shutil.rmtree(work, ignore_errors=True)
    dest = cfg["folders"]["done"] / folder.name
    if dest.exists():
        dest = cfg["folders"]["done"] / f"{folder.name}_{stamp}"
    shutil.move(str(folder), str(dest))
    log.info("  moved raw clips to %s", dest)
    return True


def process_all(cfg, state):
    raw = cfg["folders"]["raw"]
    settle = cfg.get("settle_minutes", 10)
    loose = [f for f in raw.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXT]
    if loose:
        log.warning("%d clips are loose in Raw. Put each location's clips in its own folder, "
                    "named after the place (e.g. Raw/Desert Sunset/).", len(loose))
    done = 0
    for folder in sorted(p for p in raw.iterdir() if p.is_dir()):
        if not folder_is_settled(folder, settle):
            log.info("'%s' changed in the last %d minutes, will process next run", folder.name, settle)
            continue
        try:
            if process_folder(cfg, state, folder):
                done += 1
        except Exception as exc:
            log.error("Failed on '%s': %s", folder.name, exc)
    log.info("Processing finished: %d new folder(s)", done)


# --------------------------------------------------------------------------- YouTube

def youtube_client(interactive, token_name="token.json"):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token, secret = BASE / token_name, BASE / "client_secret.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if not interactive:
            raise RuntimeError("Not signed in to YouTube. Run the --auth command from the README first.")
        if not secret.exists():
            raise RuntimeError("client_secret.json is missing. See README, step 3.")
        flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
        creds = flow.run_local_server(port=0)
        token.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload_item(cfg, yt, item):
    from googleapiclient.http import MediaFileUpload
    meta = json.loads((item / "meta.json").read_text(encoding="utf-8"))
    up = cfg["upload"]
    tz = ZoneInfo(cfg["timezone"])
    publish_at = dt.datetime.fromisoformat(meta["publish_at"])
    earliest = dt.datetime.now(tz) + dt.timedelta(minutes=30)
    if publish_at < earliest:
        publish_at = earliest.replace(second=0, microsecond=0)
        log.info("  publish time had passed, moved to %s", publish_at.strftime("%a %d %b %H:%M"))

    status = {"privacyStatus": "private",
              "publishAt": publish_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "selfDeclaredMadeForKids": bool(up.get("made_for_kids", False)),
              "containsSyntheticMedia": bool(up.get("contains_synthetic_media", False))}
    body = {"snippet": {"title": meta["title"], "description": meta["description"], "tags": meta["tags"],
                        "categoryId": str(up.get("category_id", "19")),
                        "defaultLanguage": up.get("language", "en")},
            "status": status}
    media = MediaFileUpload(str(item / "video.mp4"), chunksize=16 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media,
                                 notifySubscribers=bool(up.get("notify_subscribers", True)))
    response, last_pct = None, -1
    while response is None:
        progress, response = request.next_chunk()
        if progress:
            pct = int(progress.progress() * 100)
            if pct // 10 != last_pct // 10:
                log.info("  uploading %s: %d%%", item.name, pct)
                last_pct = pct
    video_id = response["id"]
    log.info("  uploaded: https://youtu.be/%s  (scheduled %s)", video_id, publish_at.strftime("%a %d %b %H:%M"))

    thumb = item / "thumbnail.jpg"
    if thumb.exists():
        try:
            yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumb))).execute()
        except Exception as exc:
            log.warning("  thumbnail not set (verify your channel by phone to allow custom thumbnails): %s", exc)
    meta["video_id"] = video_id
    meta["uploaded_at"] = dt.datetime.now(tz).isoformat()
    (item / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    dest = cfg["folders"]["uploaded"] / item.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(item), str(dest))


def upload_all(cfg, dry_run=False, token_name="token.json"):
    up = cfg["upload"]
    items = []
    for item in cfg["folders"]["ready"].iterdir():
        if item.is_dir() and (item / "meta.json").exists() and (item / "video.mp4").exists():
            meta = json.loads((item / "meta.json").read_text(encoding="utf-8"))
            items.append((meta["publish_at"], item, meta))
    items.sort(key=lambda x: x[0])
    if not items:
        log.info("Nothing waiting in Ready.")
        return
    limit = int(up.get("max_uploads_per_run", 6))
    if dry_run or not up.get("enabled", True):
        log.info("Upload is %s. %d item(s) ready:", "a dry run" if dry_run else "turned off in config.json", len(items))
        for publish_at, item, meta in items:
            log.info("  %s  |  %s  |  %s", publish_at[:16].replace("T", " "), meta["kind"], meta["title"])
        return
    from googleapiclient.errors import HttpError
    yt = youtube_client(interactive=False, token_name=token_name)
    for _, item, _ in items[:limit]:
        try:
            upload_item(cfg, yt, item)
        except HttpError as exc:
            text = str(exc)
            if "quotaExceeded" in text or "uploadLimitExceeded" in text:
                log.warning("YouTube daily limit reached; the rest will upload on the next run.")
                break
            log.error("Upload failed for %s: %s", item.name, text)
        except Exception as exc:
            log.error("Upload failed for %s: %s", item.name, exc)
    if len(items) > limit:
        log.info("%d item(s) left for the next run (max %d per run).", len(items) - limit, limit)


# --------------------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="Scenic Autopilot")
    parser.add_argument("--process", action="store_true", help="only build videos from Raw")
    parser.add_argument("--upload", action="store_true", help="only upload what is in Ready")
    parser.add_argument("--auth", action="store_true", help="sign in to YouTube and save the token")
    parser.add_argument("--dry-run", action="store_true", help="build videos but do not upload")
    args = parser.parse_args()

    setup_logging()
    cfg = load_config()
    state = load_state()

    if shutil.which(ffmpeg_bin(cfg)) is None and not Path(ffmpeg_bin(cfg)).exists():
        log.error("ffmpeg was not found. Run setup_windows.bat, or set ffmpeg_path in config.json.")
        sys.exit(1)

    if args.auth:
        youtube_client(interactive=True)
        log.info("Signed in. Token saved to token.json; uploads can now run on their own.")
        return
    if not args.upload:
        process_all(cfg, state)
    if not args.process:
        upload_all(cfg, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
