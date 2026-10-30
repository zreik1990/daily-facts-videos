# Daily Facts: cloud runbook

This repo is run once a day by a scheduled Claude task. The task makes 3 animated
videos and schedules them on YouTube Shorts, Instagram Reels and TikTok through
the Metricool connector. Follow these steps exactly.

Constants:
- GitHub repo: `zreik1990/daily-facts-videos`
- Metricool brand (blogId): `7763850`, timezone `Asia/Riyadh`
- Posting times: 09:00 education, 15:00 health, 20:00 fun (Riyadh time)
- The task runs every evening (about 21:40 Riyadh) and prepares the NEXT day's posts.
  `DATE` = tomorrow's date in Riyadh (YYYY-MM-DD).

## 1. Get the code
If this repo is not attached to the session yet, call the `add_repo` tool for
`zreik1990/daily-facts-videos` with access `push` first.
```
git clone https://github.com/zreik1990/daily-facts-videos.git && cd daily-facts-videos
pip install --break-system-packages -r requirements.txt
```
ffmpeg must be installed (`which ffmpeg`; if missing: `apt-get install -y ffmpeg`).

## 2. Skip if already done
If `out/DATE/plan.json` already exists (or Metricool `getScheduledPosts` already shows
posts on DATE), move DATE forward one day; if that day is also done, stop and report
"already scheduled through DATE".

## 3. Top up scripts if running low
Run `python validate_scripts.py`. If fewer than 9 unused scripts remain
(unused = ids not in `facts_state.json` `used_ids`), write 30 new scripts into a new
file `FactScripts/batch_NNN.json` (next number), same JSON format as `batch_002.json`:
- 10 education, 10 health, 10 fun; ids like `edu-041-...`, never reusing an id.
- Title, hook, 8 points (each under 25 words), `tags` (3 search phrases), and an `anim`
  on the hook and every point, chosen from the list `validate_scripts.py` prints.
- Health: only well-established advice from bodies like WHO, CDC, NHS, AAP; include
  `sources`; no diagnosis, dosing or treatment claims.
- Only facts you are confident are true; no topics already covered.
Run `python validate_scripts.py` again and fix every problem.

## 4. Make the videos
```
python daily_run.py --date DATE --repo zreik1990/daily-facts-videos
```
It renders 3 videos (about 5 minutes), force-pushes them as the only files on the
`media` branch, and writes `out/DATE/plan.json` (also printed on the line starting
`PLAN_JSON`). Each `video_url` is a jsDelivr link pinned to that commit. Check each item
has a `video_url` and `seconds` between 60 and 100. Metricool copies the video to its own
storage when the post is created, so the media branch only needs today's files.

## 5. Schedule in Metricool
For each item in plan.json call `createScheduledPost` with blogId 7763850 and:
- `date`: publish_at + "+03:00"; `publicationDate`: {dateTime: publish_at, timezone: "Asia/Riyadh"}
- `providers`: youtube, instagram, tiktok; `media`: [video_url]; `text`: caption; autoPublish true
- `youtubeData`: {title, type "short", privacy "public", tags: youtube_tags, category: youtube_category, madeForKids false, isAiGeneratedContent false}
- `instagramData`: {type "REEL", showReelOnFeed true, isAiGenerated false}
- `tiktokData`: {title, privacyOption "PUBLIC_TO_EVERYONE", disableComment false, disableDuet false, disableStitch false, commercialContentThirdParty false, commercialContentOwnBrand false, autoAddMusic false, isAigc false}
If a post is rejected, fix the stated problem once and retry; otherwise report it.

## 6. Save state
```
python3 - <<'PY'
import json; s=json.load(open('facts_state.json')); s['last_scheduled_date']='DATE'; json.dump(s,open('facts_state.json','w'),indent=2)
PY
git add facts_state.json FactScripts out/DATE/plan.json
git commit -m "Daily run DATE"
git push
```
(Do not commit the .mp4 files; they live on the media branch.)

## 7. Report
Post a short summary: the 3 titles with times, any failures, and scripts remaining.
