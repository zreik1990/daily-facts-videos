"""
Cartoon style for Daily Facts videos.

Draws flat, colorful cartoon scenes (sky, space, ocean, city, park) and an original
mascot called "Pip" (a round, friendly character with a little leaf sprout).
Everything is drawn in code, so there is nothing to license.
"""

import math
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H = 1080, 1920
SS = 2  # supersampling for smooth edges

SCENE_KEYWORDS = {
    "space": ["space", "star", "planet", "galaxy", "moon", "nebula", "astronaut", "black hole", "telescope",
              "milky way", "saturn", "venus", "orbit", "sun space", "space station"],
    "ocean": ["ocean", "sea", "underwater", "whale", "fish", "dolphin", "octopus", "reef", "beach", "wave",
              "jellyfish", "plankton", "otter", "boat", "ship", "water", "swimming", "salt", "aquarium"],
    "night": ["night", "sleep", "bed", "dark", "storm", "lightning", "thunder", "rain", "evening"],
    "sky": ["sky", "cloud", "sunset", "sunrise", "sunlight", "airplane", "plane", "flying", "bird", "rainbow",
            "light", "sun", "weather"],
    "city": ["city", "office", "desk", "computer", "laptop", "phone", "train", "clock", "museum", "library",
             "building", "street", "work", "calendar", "screen", "kitchen", "food", "market"],
    "desert": ["desert", "pyramid", "egypt", "sand", "dune", "ancient", "ruins", "hieroglyph", "stone"],
}
CATEGORY_DEFAULT = {"education": "city", "health": "park", "fun": "sky"}


def pick_scene(search, category, index):
    s = (search or "").lower()
    for scene, words in SCENE_KEYWORDS.items():
        if any(w in s for w in words):
            return scene
    rotation = {"education": ["city", "sky", "desert"], "health": ["park", "sky", "city"],
                "fun": ["sky", "park", "ocean"]}.get(category, ["park"])
    return rotation[index % len(rotation)]


# --------------------------------------------------------------------------- helpers

def _canvas(color=(0, 0, 0, 0)):
    return Image.new("RGBA", (W * SS, H * SS), color)


def _done(img):
    return img.resize((W, H), Image.LANCZOS)


def _gradient(top, bottom):
    img = Image.new("RGB", (1, 256))
    for y in range(256):
        f = y / 255
        img.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * f) for i in range(3)))
    return img.resize((W * SS, H * SS), Image.BICUBIC).convert("RGBA")


def _s(v):
    return int(v * SS)


def _circle(d, cx, cy, r, fill, outline=None, width=0):
    d.ellipse((_s(cx - r), _s(cy - r), _s(cx + r), _s(cy + r)), fill=fill, outline=outline, width=_s(width))


def _hill(d, cx, top, half_width, color):
    d.ellipse((_s(cx - half_width), _s(top), _s(cx + half_width), _s(top + half_width * 1.2)), fill=color)


def _tree(d, x, base, scale, trunk=(120, 80, 50), leaves=(60, 160, 90)):
    d.rounded_rectangle((_s(x - 10 * scale), _s(base - 90 * scale), _s(x + 10 * scale), _s(base)),
                        radius=_s(6 * scale), fill=trunk)
    for dx, dy, r in ((0, -130, 60), (-38, -100, 45), (38, -100, 45)):
        _circle(d, x + dx * scale, base + dy * scale, r * scale, leaves)


def _cloud(d, x, y, scale, color=(255, 255, 255, 245)):
    for dx, dy, r in ((0, 0, 55), (60, -25, 70), (130, 0, 55), (65, 20, 55)):
        _circle(d, x + dx * scale, y + dy * scale, r * scale, color)


# --------------------------------------------------------------------------- scenes

def scene_sky(rng):
    img = _gradient((92, 178, 255), (210, 238, 255))
    d = ImageDraw.Draw(img)
    for r, a in ((190, 40), (150, 70)):
        _circle(d, 930, 190, r, (255, 230, 120, a))
    _circle(d, 930, 190, 110, (255, 214, 70))
    _hill(d, 200, 1560, 700, (120, 200, 110))
    _hill(d, 950, 1610, 650, (90, 175, 95))
    for x in (140, 900, 1010):
        _tree(d, x, 1700 + rng.randint(-20, 20), 1.0)
    for _ in range(4):
        bx, by = rng.randint(150, 900), rng.randint(1350, 1450)
        d.arc((_s(bx), _s(by), _s(bx + 40), _s(by + 25)), 200, 340, fill=(60, 60, 80), width=_s(5))
        d.arc((_s(bx + 38), _s(by), _s(bx + 78), _s(by + 25)), 200, 340, fill=(60, 60, 80), width=_s(5))
    return _done(img)


def scene_space(rng):
    img = _gradient((14, 16, 52), (52, 30, 96))
    d = ImageDraw.Draw(img)
    for _ in range(260):
        x, y, r = rng.randint(0, W), rng.randint(0, H), rng.choice((1.5, 2, 2.5, 3.5))
        _circle(d, x, y, r, (255, 255, 255, rng.randint(140, 255)))
    _circle(d, 900, 210, 90, (240, 236, 210))
    _circle(d, 940, 185, 85, (14, 16, 52))  # crescent
    cx, cy = 850, 1580
    d.ellipse((_s(cx - 260), _s(cy - 55), _s(cx + 260), _s(cy + 55)), outline=(255, 200, 140), width=_s(16))
    _circle(d, cx, cy, 150, (240, 150, 90))
    d.chord((_s(cx - 150), _s(cy - 150), _s(cx + 150), _s(cy + 150)), 20, 160, fill=(215, 110, 70))
    d.arc((_s(cx - 260), _s(cy - 55), _s(cx + 260), _s(cy + 55)), 0, 180, fill=(255, 200, 140), width=_s(16))
    _circle(d, 180, 1750, 70, (110, 190, 255))
    _circle(d, 160, 1735, 25, (90, 200, 120))
    return _done(img)


def scene_ocean(rng):
    img = _gradient((120, 200, 255), (0, 70, 140))
    d = ImageDraw.Draw(img)
    _circle(d, 880, 260, 100, (255, 220, 90))
    d.rectangle((0, _s(820), _s(W), _s(H)), fill=(20, 120, 200))
    sea = _gradient((30, 140, 215), (5, 40, 100))
    mask = Image.new("L", sea.size, 0)
    ImageDraw.Draw(mask).rectangle((0, _s(820), _s(W), _s(H)), fill=255)
    img.paste(sea, (0, 0), mask)
    d = ImageDraw.Draw(img)
    for row in range(6):
        y = 840 + row * 28
        for x in range(-40, W, 120):
            d.arc((_s(x), _s(y), _s(x + 120), _s(y + 40)), 200, 340, fill=(255, 255, 255, 120), width=_s(5))
    for _ in range(7):
        fx, fy, sc = rng.randint(80, 950), rng.randint(1200, 1800), rng.uniform(0.7, 1.3)
        col = rng.choice([(255, 170, 60), (255, 120, 120), (250, 220, 90)])
        d.ellipse((_s(fx), _s(fy), _s(fx + 70 * sc), _s(fy + 38 * sc)), fill=col)
        d.polygon([(_s(fx), _s(fy + 19 * sc)), (_s(fx - 30 * sc), _s(fy)), (_s(fx - 30 * sc), _s(fy + 38 * sc))], fill=col)
        _circle(d, fx + 52 * sc, fy + 15 * sc, 5 * sc, (30, 30, 30))
    for x in range(0, W, 140):
        h = rng.randint(80, 200)
        d.rounded_rectangle((_s(x + 20), _s(H - h), _s(x + 40), _s(H)), radius=_s(10), fill=(40, 160, 110))
    return _done(img)


def scene_night(rng):
    img = _gradient((20, 30, 80), (70, 60, 130))
    d = ImageDraw.Draw(img)
    for _ in range(120):
        _circle(d, rng.randint(0, W), rng.randint(0, 1100), rng.choice((1.5, 2, 3)), (255, 255, 230, 220))
    _circle(d, 880, 230, 95, (255, 245, 200))
    _hill(d, 250, 1550, 750, (40, 70, 110))
    _hill(d, 950, 1620, 650, (30, 55, 95))
    for x in range(60, W, 170):
        hgt = rng.randint(220, 380)
        d.rectangle((_s(x), _s(H - hgt), _s(x + 120), _s(H)), fill=(25, 35, 70))
        for wy in range(H - hgt + 30, H - 40, 60):
            for wx in (x + 20, x + 70):
                if rng.random() < 0.55:
                    d.rectangle((_s(wx), _s(wy), _s(wx + 28), _s(wy + 32)), fill=(255, 220, 120))
    return _done(img)


def scene_city(rng):
    img = _gradient((255, 180, 120), (255, 230, 190))
    d = ImageDraw.Draw(img)
    _circle(d, 880, 300, 120, (255, 245, 210, 200))
    palette = [(90, 110, 170), (110, 90, 160), (70, 130, 160), (130, 100, 150)]
    x = -20
    while x < W:
        w, h = rng.randint(130, 210), rng.randint(380, 760)
        col = rng.choice(palette)
        d.rectangle((_s(x), _s(H - h), _s(x + w), _s(H)), fill=col)
        for wy in range(H - h + 40, H - 60, 70):
            for wx in range(x + 22, x + w - 30, 52):
                d.rectangle((_s(wx), _s(wy), _s(wx + 28), _s(wy + 36)),
                            fill=(255, 235, 150) if rng.random() < 0.4 else (200, 210, 240))
        x += w + rng.randint(4, 18)
    return _done(img)


def scene_park(rng):
    img = _gradient((150, 220, 255), (230, 250, 230))
    d = ImageDraw.Draw(img)
    _circle(d, 920, 230, 95, (255, 215, 80))
    _hill(d, 300, 1450, 800, (130, 210, 120))
    _hill(d, 900, 1520, 700, (100, 190, 105))
    d.rounded_rectangle((_s(-50), _s(1760), _s(W + 50), _s(1840)), radius=_s(40), fill=(230, 200, 150))
    for x in (90, 260, 870, 1010):
        _tree(d, x, 1720 + rng.randint(-30, 10), rng.uniform(0.9, 1.25))
    for _ in range(14):
        fx, fy = rng.randint(30, W - 30), rng.randint(1620, 1900)
        col = rng.choice([(255, 120, 150), (255, 220, 90), (255, 255, 255), (180, 130, 255)])
        for a in range(5):
            ang = a * 2 * math.pi / 5
            _circle(d, fx + 10 * math.cos(ang), fy + 10 * math.sin(ang), 8, col)
        _circle(d, fx, fy, 6, (255, 200, 60))
    return _done(img)


def scene_desert(rng):
    img = _gradient((255, 200, 120), (255, 235, 190))
    d = ImageDraw.Draw(img)
    _circle(d, 870, 260, 110, (255, 240, 170))
    for bx, w, col in ((560, 520, (220, 160, 90)), (180, 420, (200, 140, 80))):
        base = 1560
        d.polygon([(_s(bx - w / 2), _s(base)), (_s(bx), _s(base - w * 0.75)), (_s(bx + w / 2), _s(base))], fill=col)
        d.polygon([(_s(bx), _s(base - w * 0.75)), (_s(bx + w / 2), _s(base)), (_s(bx + w * 0.15), _s(base))],
                  fill=tuple(max(c - 30, 0) for c in col))
    _hill(d, 250, 1500, 900, (240, 195, 120))
    _hill(d, 950, 1560, 750, (225, 175, 105))
    cx = 880
    d.rounded_rectangle((_s(cx - 18), _s(1480), _s(cx + 18), _s(1700)), radius=_s(18), fill=(70, 150, 90))
    d.rounded_rectangle((_s(cx - 80), _s(1540), _s(cx - 50), _s(1620)), radius=_s(15), fill=(70, 150, 90))
    d.rounded_rectangle((_s(cx - 80), _s(1600), _s(cx), _s(1625)), radius=_s(12), fill=(70, 150, 90))
    return _done(img)


SCENES = {"sky": scene_sky, "space": scene_space, "ocean": scene_ocean, "night": scene_night,
          "city": scene_city, "park": scene_park, "desert": scene_desert}


def draw_scene(name, seed, path):
    SCENES[name](random.Random(seed)).convert("RGB").save(path)


def draw_clouds(path, night=False):
    img = Image.new("RGBA", (W * 2 * SS, 520 * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (200, 210, 240, 150) if night else (255, 255, 255, 235)
    # second half repeats the first so the scroll loops seamlessly every W pixels
    for x, y, sc in ((120, 150, 1.1), (680, 330, 0.8)):
        _cloud(d, x, y, sc, color)
        _cloud(d, x + W, y, sc, color)
    img.resize((W * 2, 520), Image.LANCZOS).save(path)


# --------------------------------------------------------------------------- mascot "Pip"

def draw_mascot(path, blink=False, wave=False, body=(255, 196, 70)):
    size = 420
    img = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    line = (70, 45, 30)
    cx, cy, r = 210, 235, 140
    # shadow
    d.ellipse((_s(cx - 110), _s(395), _s(cx + 110), _s(415)), fill=(0, 0, 0, 60))
    # feet
    for fx in (cx - 60, cx + 60):
        d.ellipse((_s(fx - 40), _s(350), _s(fx + 40), _s(398)), fill=(240, 140, 60), outline=line, width=_s(6))
    # arms
    d.ellipse((_s(cx - r - 30), _s(cy + 10), _s(cx - r + 30), _s(cy + 70)), fill=body, outline=line, width=_s(6))
    if wave:
        d.ellipse((_s(cx + r - 20), _s(cy - 120), _s(cx + r + 40), _s(cy - 60)), fill=body, outline=line, width=_s(6))
    else:
        d.ellipse((_s(cx + r - 30), _s(cy + 10), _s(cx + r + 30), _s(cy + 70)), fill=body, outline=line, width=_s(6))
    # sprout
    d.line((_s(cx), _s(cy - r + 5), _s(cx + 5), _s(cy - r - 45)), fill=(60, 140, 60), width=_s(9))
    d.ellipse((_s(cx + 2), _s(cy - r - 75), _s(cx + 72), _s(cy - r - 35)), fill=(100, 200, 90), outline=line, width=_s(5))
    d.ellipse((_s(cx - 60), _s(cy - r - 62), _s(cx + 4), _s(cy - r - 28)), fill=(120, 215, 100), outline=line, width=_s(5))
    # body
    d.ellipse((_s(cx - r), _s(cy - r), _s(cx + r), _s(cy + r)), fill=body, outline=line, width=_s(8))
    d.ellipse((_s(cx - r + 30), _s(cy - r + 22), _s(cx - 20), _s(cy - r + 70)), fill=(255, 235, 170))
    # cheeks
    for ch in (cx - 85, cx + 85):
        d.ellipse((_s(ch - 26), _s(cy + 25), _s(ch + 26), _s(cy + 50)), fill=(255, 140, 140))
    # eyes
    for ex in (cx - 50, cx + 50):
        if blink:
            d.arc((_s(ex - 28), _s(cy - 30), _s(ex + 28), _s(cy + 10)), 200, 340, fill=line, width=_s(8))
        else:
            d.ellipse((_s(ex - 30), _s(cy - 48), _s(ex + 30), _s(cy + 18)), fill=(255, 255, 255), outline=line, width=_s(6))
            d.ellipse((_s(ex - 14), _s(cy - 22), _s(ex + 16), _s(cy + 12)), fill=(35, 30, 40))
            d.ellipse((_s(ex - 6), _s(cy - 16), _s(ex + 4), _s(cy - 6)), fill=(255, 255, 255))
    # smile
    d.chord((_s(cx - 40), _s(cy + 15), _s(cx + 40), _s(cy + 75)), 0, 180, fill=(120, 40, 50), outline=line, width=_s(6))
    d.ellipse((_s(cx - 18), _s(cy + 48), _s(cx + 18), _s(cy + 70)), fill=(255, 120, 130))
    img.resize((size, size), Image.LANCZOS).save(path)


MASCOT_COLORS = {"education": (120, 190, 255), "health": (120, 220, 150), "fun": (255, 196, 70)}


def prepare_mascot(work, category):
    body = MASCOT_COLORS.get(category, (255, 196, 70))
    paths = {k: Path(work) / f"pip_{k}.png" for k in ("open", "blink", "wave")}
    draw_mascot(paths["open"], body=body)
    draw_mascot(paths["blink"], blink=True, body=body)
    draw_mascot(paths["wave"], wave=True, body=body)
    return paths


def segment_filter(seconds, has_clouds, mascot_x=330, mascot_y=1250, wave=False, offset=0.0):
    """ffmpeg filter graph: [0]=scene [1]=clouds [2]=pip open [3]=pip blink(or wave) [4]=caption card."""
    bob = f"{mascot_y}+14*sin(2*PI*(t+{offset:.2f})*0.9)"
    parts = [f"[0:v]scale={W}:{H},setsar=1,format=yuv420p[bg]"]
    last = "bg"
    if has_clouds:
        parts.append(f"[{last}][1:v]overlay=x='-mod(t*28+{offset * 97:.0f}\\,{W})':y=60:shortest=0[c]")
        last = "c"
    parts.append(f"[{last}][2:v]overlay=x={mascot_x}:y='{bob}'[m]")
    if wave:
        enable = "between(t\\,0\\,1.2)+between(t\\,1.6\\,2.4)"
    else:
        enable = f"lt(mod(t+{offset:.2f}\\,3.4)\\,0.16)"
    parts.append(f"[m][3:v]overlay=x={mascot_x}:y='{bob}':enable='{enable}'[mb]")
    parts.append("[4:v]format=rgba,fade=t=in:st=0:d=0.35:alpha=1[t]")
    parts.append("[mb][t]overlay=0:0:format=auto,format=yuv420p[v]")
    return ";".join(parts)
