"""
Animation engine for Daily Facts videos (style "cartoon").

Every point of a script gets its own animated illustration ("prop") playing in the
stage area under the caption: a pyramid being built, a football flying into a goal,
a baby rocking, a heart beating, planets orbiting, and so on. Each video also gets
its own caption style, caption entrance, scenes and mascot outfit, so no two
videos look the same.

All drawing is done in code (Pillow), so there is nothing to license.
"""

import math
import random
import subprocess

from PIL import Image, ImageDraw

import cartoon
from functools import lru_cache
from scenic_autopilot import find_font as _find_font


@lru_cache(maxsize=64)
def find_font(size):
    return _find_font(size)

W, H = 1080, 1920
FPS = 24
STAGE_Y, SW, SH = 1170, 1080, 550       # animation stage, under the caption
S = 2                                   # draw stage at 2x, then downscale (smooth edges)
INK = (60, 40, 35)
TAU = math.tau


# --------------------------------------------------------------------------- drawing helper

class G:
    def __init__(self, img):
        self.img = img
        self.d = ImageDraw.Draw(img)

    @staticmethod
    def p(v):
        return int(round(v * S))

    def circle(self, x, y, r, fill=None, outline=None, w=0):
        if r <= 0:
            return
        self.d.ellipse((self.p(x - r), self.p(y - r), self.p(x + r), self.p(y + r)),
                       fill=fill, outline=outline, width=self.p(w))

    def ellipse(self, x, y, rx, ry, fill=None, outline=None, w=0):
        self.d.ellipse((self.p(x - rx), self.p(y - ry), self.p(x + rx), self.p(y + ry)),
                       fill=fill, outline=outline, width=self.p(w))

    def rect(self, x0, y0, x1, y1, fill=None, r=0, outline=None, w=0):
        self.d.rounded_rectangle((self.p(x0), self.p(y0), self.p(x1), self.p(y1)), radius=self.p(r),
                                 fill=fill, outline=outline, width=self.p(w))

    def poly(self, pts, fill=None, outline=None, w=0):
        q = [(self.p(x), self.p(y)) for x, y in pts]
        self.d.polygon(q, fill=fill)
        if outline and w:
            self.d.line(q + [q[0]], fill=outline, width=self.p(w), joint="curve")

    def line(self, pts, fill, w=4):
        self.d.line([(self.p(x), self.p(y)) for x, y in pts], fill=fill, width=self.p(w), joint="curve")

    def arc(self, x, y, r, a0, a1, fill, w=4):
        self.d.arc((self.p(x - r), self.p(y - r), self.p(x + r), self.p(y + r)), a0, a1, fill=fill, width=self.p(w))

    def text(self, x, y, s, size, fill, stroke=0, stroke_fill=(0, 0, 0)):
        self.d.text((self.p(x), self.p(y)), s, font=find_font(self.p(size)), fill=fill, anchor="mm",
                    stroke_width=self.p(stroke), stroke_fill=stroke_fill)

    def paste(self, sprite, x, y):
        """Paste an RGBA sprite (already at 2x) centered at stage point (x, y)."""
        self.img.alpha_composite(sprite, (self.p(x) - sprite.width // 2, self.p(y) - sprite.height // 2))


def rot(points, cx, cy, a):
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in points]


def heart_pts(cx, cy, size, n=40):
    pts = []
    for i in range(n):
        a = TAU * i / n
        x = 16 * math.sin(a) ** 3
        y = 13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)
        pts.append((cx + x * size / 16, cy - y * size / 16))
    return pts


def ease_out_back(u):
    c = 1.70158
    return 1 + (c + 1) * (u - 1) ** 3 + c * (u - 1) ** 2


def ease_out_bounce(u):
    if u < 1 / 2.75:
        return 7.5625 * u * u
    if u < 2 / 2.75:
        u -= 1.5 / 2.75
        return 7.5625 * u * u + 0.75
    if u < 2.5 / 2.75:
        u -= 2.25 / 2.75
        return 7.5625 * u * u + 0.9375
    u -= 2.625 / 2.75
    return 7.5625 * u * u + 0.984375


GROUND = 470


# --------------------------------------------------------------------------- props (topic animations)

def p_pyramid(g, t, dur, ctx):
    bw, bh, rows, cx = 74, 44, 5, 620
    blocks = []
    for k in range(rows):
        n = rows - k
        for i in range(n):
            blocks.append((cx - n * bw / 2 + i * bw, GROUND - (k + 1) * bh))
    build = max(dur * 0.75, 2.5)
    done = min(len(blocks), int(t / build * len(blocks)))
    sand, edge = (226, 176, 100), (150, 105, 55)
    for x, y in blocks[:done]:
        g.rect(x + 2, y + 2, x + bw - 2, y + bh - 2, fill=sand, r=4, outline=edge, w=3)
    if done < len(blocks):
        frac = (t / build * len(blocks)) % 1
        tx, ty = blocks[done]
        x = 1000 + (tx - 1000) * min(1, frac * 1.6)
        y = GROUND - bh + (ty - GROUND + bh) * max(0, frac * 1.6 - 0.6) / 1.0
        g.rect(x + 2, y + 2, x + bw - 2, y + bh - 2, fill=(240, 195, 120), r=4, outline=edge, w=3)
        g.line([(x + bw, y + bh / 2), (x + bw + 60, y + bh / 2 + 10)], fill=(120, 85, 50), w=5)
    else:
        for i in range(6):
            a = t * 3 + i * TAU / 6
            g.text(cx + math.cos(a) * 190, 260 + math.sin(a) * 110, "*", 48, (255, 230, 90))


def _ball(g, x, y, r, a):
    g.circle(x, y, r, fill=(255, 255, 255), outline=INK, w=4)
    pent = [(x + r * 0.42 * math.cos(a + i * TAU / 5), y + r * 0.42 * math.sin(a + i * TAU / 5)) for i in range(5)]
    g.poly(pent, fill=(40, 40, 50))
    for i in range(5):
        ang = a + i * TAU / 5 + TAU / 10
        px, py = x + r * 0.82 * math.cos(ang), y + r * 0.82 * math.sin(ang)
        g.circle(px, py, r * 0.17, fill=(40, 40, 50))


def p_football(g, t, dur, ctx):
    gx0, gx1, gy = 740, 960, 250
    for i in range(9):
        x = gx0 + 20 + i * 24
        g.line([(x, gy + 10), (x + 10, GROUND)], fill=(230, 230, 240), w=2)
    for j in range(8):
        y = gy + 20 + j * 27
        g.line([(gx0 + 15, y), (gx1 - 5, y + 6)], fill=(230, 230, 240), w=2)
    g.line([(gx0, GROUND), (gx0, gy), (gx1, gy), (gx1, GROUND)], fill=(255, 255, 255), w=12)
    cycle = 3.0
    ph = (t % cycle) / cycle
    if ph < 0.5:
        u = ph / 0.5
        x = 330 + (870 - 330) * u
        y = GROUND - 30 - math.sin(u * math.pi) * 230 - u * 60
    else:
        u = (ph - 0.5) / 0.5
        x = 870 + 20 * min(1, u * 3)
        y = GROUND - 90 + abs(math.sin(u * 9)) * -30 * (1 - u)
    _ball(g, x, y, 34, t * 7)
    g.ellipse(x, GROUND + 6, 30, 7, fill=(0, 0, 0, 50))
    # kicker leg (Pip's foot)
    if ph < 0.12:
        g.ellipse(300, GROUND - 25, 34, 20, fill=(240, 140, 60), outline=INK, w=3)
    if ph > 0.52:
        k = min(1, (ph - 0.52) / 0.12)
        size = 40 + 50 * ease_out_back(k)
        g.text(560, 170, "GOAL!", size, (255, 225, 60), stroke=4, stroke_fill=INK)
        rng = random.Random(int(t / cycle))
        for _ in range(26):
            cx, cy = rng.uniform(360, 950), rng.uniform(40, 300) + (ph - 0.5) * 300
            col = rng.choice([(255, 90, 90), (90, 170, 255), (255, 210, 60), (110, 220, 130)])
            g.rect(cx, cy, cx + 12, cy + 18, fill=col, r=2)


def p_baby(g, t, dur, ctx):
    sway = math.sin(t * 2.2) * 26
    cx, cy = 620 + sway, 300
    skin, onesie = (255, 214, 180), (150, 200, 255)
    g.ellipse(cx, cy + 120, 105, 80, fill=onesie, outline=INK, w=4)
    g.ellipse(cx - 70, cy + 175, 30, 22, fill=skin, outline=INK, w=3)
    g.ellipse(cx + 70, cy + 175, 30, 22, fill=skin, outline=INK, w=3)
    g.circle(cx, cy, 98, fill=skin, outline=INK, w=4)
    g.arc(cx + 5, cy - 100, 22, 180, 360, fill=INK, w=5)
    blink = (t % 2.8) < 0.15
    for ex in (cx - 36, cx + 36):
        if blink:
            g.arc(ex, cy - 5, 14, 20, 160, fill=INK, w=4)
        else:
            g.circle(ex, cy - 8, 13, fill=(40, 30, 40))
            g.circle(ex - 4, cy - 13, 4, fill=(255, 255, 255))
    for chx in (cx - 62, cx + 62):
        g.ellipse(chx, cy + 25, 18, 11, fill=(255, 150, 150))
    g.arc(cx, cy + 22, 26, 20, 160, fill=(150, 60, 70), w=5)
    # rattle in hand
    a = math.sin(t * 13) * 0.5
    hx, hy = cx + 115, cy + 95
    g.circle(hx, hy, 20, fill=skin, outline=INK, w=3)
    tip = (hx + math.sin(a) * 95, hy - math.cos(a) * 95)
    g.line([(hx, hy), tip], fill=(255, 150, 60), w=9)
    g.circle(tip[0], tip[1], 30, fill=(255, 210, 70), outline=INK, w=4)
    g.circle(tip[0], tip[1], 10, fill=(255, 120, 150))
    for i in range(3):
        ph = (t * 0.6 + i / 3) % 1
        hxp, hyp = 420 + i * 40 + math.sin(ph * 6 + i) * 15, 300 - ph * 260
        g.poly(heart_pts(hxp, hyp, 22 * (1 - ph * 0.4)), fill=(255, 110, 140, int(255 * (1 - ph))))


def p_heart(g, t, dur, ctx):
    beat = max(0.0, math.sin(t * TAU * 1.1)) ** 6
    size = 120 * (1 + 0.16 * beat)
    g.poly(heart_pts(620, 230, size), fill=(235, 70, 90), outline=INK, w=5)
    g.ellipse(575, 175, 22, 14, fill=(255, 170, 180))
    pts = []
    for i in range(121):
        x = 330 + i * 5
        ph = ((x - t * 260) % 300) / 300
        y = 420
        if 0.4 < ph < 0.45:
            y -= 70 * math.sin((ph - 0.4) / 0.05 * math.pi)
        elif 0.45 < ph < 0.5:
            y += 35 * math.sin((ph - 0.45) / 0.05 * math.pi)
        pts.append((x, y))
    g.line(pts, fill=(80, 220, 140), w=6)


def p_water(g, t, dur, ctx):
    top, bot, cx = 120, 460, 620
    tw, bw = 120, 92
    level = 0.12 + 0.82 * min(1, t / max(dur * 0.8, 1))
    wy = bot - (bot - top) * level
    lw = bw + (tw - bw) * level
    wave = [(cx - lw + i * (2 * lw / 20), wy + math.sin(t * 5 + i * 0.8) * 5) for i in range(21)]
    g.poly(wave + [(cx + bw, bot), (cx - bw, bot)], fill=(90, 180, 255, 220))
    g.line([(cx - tw, top), (cx - bw, bot), (cx + bw, bot), (cx + tw, top)], fill=(255, 255, 255), w=8)
    g.line([(cx - tw + 25, top + 30), (cx - bw + 20, bot - 40)], fill=(255, 255, 255, 140), w=6)
    for i in range(3):
        ph = (t * 1.6 + i / 3) % 1
        y = 0 + ph * (wy - 10)
        g.ellipse(cx + (i - 1) * 30, y, 11, 16, fill=(110, 190, 255))
    for i in range(5):
        ph = (t * 0.7 + i / 5) % 1
        g.circle(cx - 60 + i * 30, bot - 10 - ph * (bot - wy - 10), 6, outline=(255, 255, 255), w=2)


def p_sleep(g, t, dur, ctx):
    g.rect(400, 330, 920, 450, fill=(170, 120, 90), r=18, outline=INK, w=4)
    g.rect(400, 250, 440, 470, fill=(150, 100, 75), r=10, outline=INK, w=4)
    g.ellipse(500, 320, 70, 35, fill=(255, 255, 255), outline=INK, w=4)
    g.circle(520, 285, 60, fill=ctx["mascot_color"], outline=INK, w=4)
    for ex in (500, 545):
        g.arc(ex, 285, 13, 20, 160, fill=INK, w=4)
    g.ellipse(525, 315, 9, 6, fill=(150, 60, 70))
    breathe = math.sin(t * 2) * 6
    g.rect(470, 310 - breathe, 910, 400, fill=(120, 170, 255), r=30, outline=INK, w=4)
    for i in range(4):
        x = 520 + i * 90
        g.line([(x, 330 - breathe), (x + 40, 395)], fill=(170, 205, 255), w=6)
    for i in range(3):
        ph = (t * 0.45 + i / 3) % 1
        g.text(600 + ph * 160 + i * 10, 220 - ph * 200, "Z", 40 + ph * 40, (255, 255, 255, int(255 * (1 - ph))),
               stroke=3, stroke_fill=(70, 70, 140))
    g.circle(860, 80, 40, fill=(255, 245, 190))
    g.circle(878, 70, 36, fill=ctx["sky"])


def p_sunlight(g, t, dur, ctx):
    sx, sy = 420, 200
    for i in range(12):
        a = t * 0.8 + i * TAU / 12
        r1, r2 = 95, 130 + 10 * math.sin(t * 4 + i)
        g.line([(sx + math.cos(a) * r1, sy + math.sin(a) * r1), (sx + math.cos(a) * r2, sy + math.sin(a) * r2)],
               fill=(255, 200, 60), w=10)
    g.circle(sx, sy, 80, fill=(255, 215, 70), outline=(240, 160, 40), w=5)
    for ex in (sx - 25, sx + 25):
        g.circle(ex, sy - 10, 8, fill=INK)
    g.arc(sx, sy + 15, 25, 20, 160, fill=INK, w=5)
    px, py = 700, 330
    g.poly([(px, py - 90), (px - 80, py + 60), (px + 80, py + 60)], fill=(220, 240, 255, 200), outline=(255, 255, 255), w=4)
    g.line([(sx + 80, sy + 40), (px - 30, py)], fill=(255, 255, 255), w=8)
    reveal = min(1, (t % 4) / 1.5)
    cols = [(255, 60, 60), (255, 150, 40), (255, 230, 50), (80, 200, 90), (60, 140, 255), (150, 80, 220)]
    for i, c in enumerate(cols):
        ex, ey = 700 + 260 * reveal, 250 + i * 34
        g.line([(px + 30, py), (ex, ey)], fill=c, w=10)


def p_space(g, t, dur, ctx):
    cx, cy = 620, 270
    for i, (rx, sp, col, pr) in enumerate([(120, 1.6, (120, 200, 255), 16), (210, 1.0, (255, 120, 90), 22),
                                          (300, 0.6, (240, 190, 110), 28)]):
        ry = rx * 0.38
        g.ellipse(cx, cy, rx, ry, outline=(255, 255, 255, 90), w=2)
        a = t * sp + i * 2
        g.circle(cx + math.cos(a) * rx, cy + math.sin(a) * ry, pr, fill=col, outline=INK, w=3)
    g.circle(cx, cy, 48, fill=(255, 210, 60), outline=(255, 160, 40), w=5)
    ph = (t * 0.25) % 1
    rx, ry = 300 + ph * 700, 470 - ph * 450
    body = rot([(rx - 20, ry + 30), (rx - 20, ry - 30), (rx, ry - 55), (rx + 20, ry - 30), (rx + 20, ry + 30)],
               rx, ry, math.radians(45))
    g.poly(body, fill=(240, 240, 250), outline=INK, w=3)
    fl = rot([(rx - 12, ry + 30), (rx, ry + 60 + 10 * math.sin(t * 30)), (rx + 12, ry + 30)], rx, ry, math.radians(45))
    g.poly(fl, fill=(255, 150, 40))


def p_plane(g, t, dur, ctx):
    for i in range(3):
        cx = (900 - (t * 60 + i * 380)) % 1300 - 150
        for dx, dy, r in ((0, 0, 30), (35, -15, 38), (75, 0, 30)):
            g.circle(cx + dx, 120 + i * 120 + dy, r, fill=(255, 255, 255, 230))
    ph = (t * 0.22) % 1
    x, y = 250 + ph * 800, 260 + math.sin(t * 2) * 25
    for k in range(8):
        tx = x - 150 - k * 40
        if tx > 200:
            g.line([(tx, y + 8), (tx + 20, y + 8)], fill=(255, 255, 255, 200), w=6)
    g.rect(x - 130, y - 22, x + 110, y + 26, fill=(240, 240, 250), r=24, outline=INK, w=4)
    g.poly([(x + 95, y - 20), (x + 145, y), (x + 95, y + 24)], fill=(240, 240, 250), outline=INK, w=4)
    g.poly([(x - 20, y), (x - 80, y + 90), (x - 40, y + 90), (x + 30, y)], fill=(90, 160, 255), outline=INK, w=4)
    g.poly([(x - 125, y - 18), (x - 150, y - 75), (x - 110, y - 75), (x - 85, y - 18)], fill=(255, 90, 90), outline=INK, w=4)
    for k in range(4):
        g.circle(x - 40 + k * 35, y - 2, 9, fill=(120, 190, 255))


def p_brain(g, t, dur, ctx):
    cx, cy = 620, 300
    pulse = 1 + 0.04 * math.sin(t * 4)
    for dx, dy, r in ((-90, 0, 70), (-40, -50, 70), (30, -55, 72), (95, -10, 68), (60, 45, 65), (-30, 50, 66)):
        g.circle(cx + dx * pulse, cy + dy * pulse, r * pulse, fill=(255, 160, 190), outline=INK, w=4)
    for dx, dy in ((-60, -10), (10, -30), (60, 10), (-10, 40)):
        g.arc(cx + dx, cy + dy, 28, 200, 340, fill=(220, 100, 140), w=5)
    on = (t % 1.2) < 0.8
    g.circle(cx, 95, 48, fill=(255, 235, 110) if on else (230, 230, 210), outline=INK, w=4)
    g.rect(cx - 22, 138, cx + 22, 165, fill=(170, 170, 180), r=5, outline=INK, w=3)
    if on:
        for i in range(8):
            a = i * TAU / 8 + t
            g.line([(cx + math.cos(a) * 62, 95 + math.sin(a) * 62), (cx + math.cos(a) * 85, 95 + math.sin(a) * 85)],
                   fill=(255, 220, 60), w=6)


def p_lightning(g, t, dur, ctx):
    for i in range(30):
        x = (i * 37 + 330) % 640 + 320
        y = ((t * 520 + i * 61) % 360) + 160
        g.line([(x, y), (x - 6, y + 22)], fill=(170, 200, 255), w=4)
    for dx, dy, r in ((0, 0, 80), (80, -30, 95), (170, 0, 80), (85, 30, 80)):
        g.circle(520 + dx, 140 + dy, r, fill=(110, 115, 140), outline=INK, w=4)
    if (t % 1.7) < 0.18:
        bolt = [(600, 200), (550, 320), (600, 320), (540, 460), (680, 290), (620, 290), (670, 200)]
        g.poly(bolt, fill=(255, 235, 80), outline=(255, 255, 255), w=4)


def _fish(g, x, y, s, col, t, flip=False):
    d = -1 if flip else 1
    wig = math.sin(t * 10) * 12 * s
    g.ellipse(x, y, 55 * s, 32 * s, fill=col, outline=INK, w=3)
    g.poly([(x - d * 50 * s, y), (x - d * 95 * s, y - 30 * s + wig), (x - d * 95 * s, y + 30 * s + wig)], fill=col, outline=INK, w=3)
    g.circle(x + d * 28 * s, y - 8 * s, 8 * s, fill=(255, 255, 255))
    g.circle(x + d * 30 * s, y - 8 * s, 4 * s, fill=INK)


def p_fish(g, t, dur, ctx):
    for i in range(5):
        x = 380 + i * 130
        sway = math.sin(t * 2 + i) * 20
        g.line([(x, GROUND + 20), (x + sway, GROUND - 60), (x - sway * 0.5, GROUND - 130)], fill=(60, 180, 120), w=12)
    cols = [(255, 160, 60), (255, 110, 120), (255, 215, 80)]
    for i in range(3):
        ph = ((t * 0.18 + i * 0.33) % 1)
        flip = i == 1
        x = 1050 - ph * 800 if flip else 250 + ph * 800
        _fish(g, x, 150 + i * 100 + math.sin(t * 2 + i) * 15, 1 - i * 0.15, cols[i], t + i, flip)
    for i in range(10):
        ph = (t * 0.35 + i / 10) % 1
        g.circle(360 + i * 60 + math.sin(t * 3 + i) * 10, GROUND - ph * 450, 7 + i % 3 * 3, outline=(255, 255, 255, 220), w=2)


def p_octopus(g, t, dur, ctx):
    cx, cy = 620, 200
    col = (190, 110, 220)
    for i in range(8):
        base = cx - 105 + i * 30
        pts = []
        for k in range(12):
            y = cy + 70 + k * 20
            x = base + (i - 3.5) * k * 4 + math.sin(t * 3 + i + k * 0.5) * (6 + k * 2)
            pts.append((x, y))
        g.line(pts, fill=col, w=22 - 0)
        g.line(pts, fill=INK, w=2)
    g.ellipse(cx, cy, 130, 115, fill=col, outline=INK, w=5)
    blink = (t % 3.1) < 0.15
    for ex in (cx - 45, cx + 45):
        if blink:
            g.arc(ex, cy + 5, 18, 20, 160, fill=INK, w=5)
        else:
            g.circle(ex, cy, 24, fill=(255, 255, 255), outline=INK, w=3)
            g.circle(ex + 5, cy + 3, 11, fill=INK)
    g.arc(cx, cy + 35, 30, 20, 160, fill=INK, w=5)
    for i in range(3):
        g.circle(cx - 70 + i * 50, cy - 60, 10, fill=(220, 160, 240))


def p_fruit(g, t, dur, ctx):
    for i in range(3):
        ph = (t * 1.6 + i * 0.33) % 1
        h = abs(math.sin(ph * math.pi)) * 160
        squash = 1 + (0.25 if ph < 0.08 or ph > 0.92 else 0)
        x, y = 400 + i * 220, GROUND - 60 - h
        g.ellipse(x, GROUND - 5, 50, 10, fill=(0, 0, 0, 50))
        if i == 0:
            pts = [(x - 70 + k * 14, y - 20 + math.sin(k / 10 * math.pi) * 45) for k in range(11)]
            g.line(pts, fill=(255, 220, 70), w=34)
            g.line(pts, fill=(200, 160, 40), w=3)
        elif i == 1:
            g.poly([(x - 55 * squash, y - 30), (x + 55 * squash, y - 30), (x, y + 60 / squash)], fill=(235, 50, 70), outline=INK, w=4)
            g.ellipse(x, y - 30, 55 * squash, 22, fill=(235, 50, 70), outline=INK, w=4)
            for sx, sy in ((-20, -10), (15, -5), (0, 20), (-10, 5), (22, 10)):
                g.ellipse(x + sx, y + sy, 3, 5, fill=(255, 230, 120))
            g.poly([(x - 35, y - 50), (x, y - 35), (x + 35, y - 50), (x, y - 65)], fill=(60, 170, 80))
        else:
            g.ellipse(x, y, 58 * squash, 55 / squash, fill=(230, 60, 60), outline=INK, w=4)
            g.line([(x, y - 55), (x + 5, y - 80)], fill=(110, 70, 40), w=6)
            g.ellipse(x + 25, y - 72, 20, 10, fill=(80, 180, 80))
            g.ellipse(x - 22, y - 20, 12, 18, fill=(255, 140, 140))


def p_clock(g, t, dur, ctx):
    cx, cy = 620, 270
    wob = math.sin(t * 6) * 4
    g.circle(cx, cy + wob, 165, fill=(255, 120, 100), outline=INK, w=5)
    g.circle(cx, cy + wob, 140, fill=(255, 255, 250), outline=INK, w=4)
    for i in range(12):
        a = i * TAU / 12
        g.line([(cx + math.cos(a) * 118, cy + wob + math.sin(a) * 118),
                (cx + math.cos(a) * 132, cy + wob + math.sin(a) * 132)], fill=INK, w=5)
    am = t * TAU / 2 - TAU / 4
    ah = t * TAU / 24 - TAU / 4
    g.line([(cx, cy + wob), (cx + math.cos(ah) * 70, cy + wob + math.sin(ah) * 70)], fill=INK, w=12)
    g.line([(cx, cy + wob), (cx + math.cos(am) * 115, cy + wob + math.sin(am) * 115)], fill=(220, 60, 60), w=7)
    g.circle(cx, cy + wob, 12, fill=INK)
    for bx in (cx - 120, cx + 120):
        g.circle(bx, cy - 150 + wob, 34, fill=(255, 200, 70), outline=INK, w=4)


def p_walk(g, t, dur, ctx):
    for i in range(4):
        x = (1100 - (t * 140 + i * 300) % 1300)
        g.rect(x - 8, GROUND - 120, x + 8, GROUND, fill=(130, 90, 55))
        g.circle(x, GROUND - 150, 50, fill=(70, 170, 95))
    hop = abs(math.sin(t * 6)) * 30
    sprite = ctx["mascot"]["open"]
    g.paste(sprite, 560, GROUND - 105 - hop)
    for i in range(3):
        ph = (t * 3 + i / 3) % 1
        g.circle(470 - ph * 120, GROUND - 5 - ph * 20, 12 * (1 - ph), fill=(220, 200, 170, int(200 * (1 - ph))))


def p_germs(g, t, dur, ctx):
    g.rect(540, 400, 700, 460, fill=(140, 220, 255), r=24, outline=INK, w=4)
    g.text(620, 430, "SOAP", 30, (40, 90, 140))
    for i in range(4):
        ph = (t * 0.5 + i / 4) % 1
        x, y = 380 + i * 160 + math.sin(t * 2 + i) * 20, 300 + math.sin(t * 3 + i) * 30
        if ph < 0.75:
            r = 40
            for k in range(8):
                a = k * TAU / 8 + t
                g.line([(x + math.cos(a) * r, y + math.sin(a) * r), (x + math.cos(a) * (r + 22), y + math.sin(a) * (r + 22))],
                       fill=(90, 160, 60), w=6)
            g.circle(x, y, r, fill=(130, 200, 80), outline=INK, w=4)
            g.circle(x - 12, y - 8, 7, fill=INK)
            g.circle(x + 12, y - 8, 7, fill=INK)
            g.arc(x, y + 18, 14, 200, 340, fill=INK, w=4)
        else:
            k = (ph - 0.75) / 0.25
            g.text(x, y, "POP!", 30 + 30 * k, (255, 255, 255, int(255 * (1 - k))), stroke=3, stroke_fill=(60, 120, 200))
    for i in range(12):
        ph = (t * 0.4 + i / 12) % 1
        x = 360 + (i * 53) % 560
        g.circle(x, 430 - ph * 420, 10 + (i % 4) * 6, outline=(255, 255, 255, 230), w=3)


def p_book(g, t, dur, ctx):
    cx, cy = 620, 320
    g.poly([(cx, cy - 120), (cx - 260, cy - 140), (cx - 260, cy + 110), (cx, cy + 130)], fill=(255, 250, 235), outline=INK, w=4)
    g.poly([(cx, cy - 120), (cx + 260, cy - 140), (cx + 260, cy + 110), (cx, cy + 130)], fill=(255, 250, 235), outline=INK, w=4)
    for k in range(6):
        y = cy - 90 + k * 34
        g.line([(cx - 225, y - 6), (cx - 30, y)], fill=(170, 170, 190), w=5)
        g.line([(cx + 30, y), (cx + 225, y - 6)], fill=(170, 170, 190), w=5)
    ph = (t * 0.5) % 1
    fx = math.cos(ph * math.pi)
    g.poly([(cx, cy - 120), (cx + 260 * fx, cy - 140 - 30 * math.sin(ph * math.pi)),
            (cx + 260 * fx, cy + 110 - 30 * math.sin(ph * math.pi)), (cx, cy + 130)],
           fill=(245, 240, 220), outline=INK, w=4)
    for i in range(5):
        a = t * 2 + i * TAU / 5
        g.text(cx + math.cos(a) * 300, cy - 200 + math.sin(a) * 40, "*", 40, (255, 220, 80))


def p_bee(g, t, dur, ctx):
    fx = 620
    g.line([(fx, GROUND), (fx, 380)], fill=(70, 160, 80), w=10)
    for i in range(6):
        a = i * TAU / 6 + math.sin(t) * 0.1
        g.circle(fx + math.cos(a) * 40, 360 + math.sin(a) * 40, 30, fill=(255, 130, 170), outline=INK, w=3)
    g.circle(fx, 360, 26, fill=(255, 210, 60), outline=INK, w=3)
    x, y = fx + 230 * math.sin(t * 1.3), 200 + 80 * math.sin(t * 2.6)
    d = 1 if math.cos(t * 1.3) > 0 else -1
    flap = abs(math.sin(t * 40)) * 25 + 10
    g.ellipse(x - 10, y - 40, 22, flap, fill=(220, 240, 255, 200), outline=INK, w=2)
    g.ellipse(x + 15, y - 40, 22, flap, fill=(220, 240, 255, 200), outline=INK, w=2)
    g.ellipse(x, y, 55, 38, fill=(255, 210, 50), outline=INK, w=4)
    for k in (-15, 10):
        g.rect(x + k - 7, y - 36, x + k + 7, y + 36, fill=INK)
    g.circle(x + d * 38, y - 8, 7, fill=INK)
    g.poly([(x - d * 55, y), (x - d * 75, y - 6), (x - d * 75, y + 6)], fill=INK)
    for k in range(6):
        ph = (t * 1.3 - k * 0.12)
        g.circle(fx + 230 * math.sin(ph), 200 + 80 * math.sin(ph * 2), 4, fill=(255, 255, 255, 160 - k * 25))


def p_phone(g, t, dur, ctx):
    cx, cy = 620, 270
    tilt = math.sin(t * 2) * 0.06
    body = rot([(cx - 110, cy - 200), (cx + 110, cy - 200), (cx + 110, cy + 200), (cx - 110, cy + 200)], cx, cy, tilt)
    g.poly(body, fill=(40, 40, 55), outline=INK, w=5)
    scr = rot([(cx - 92, cy - 170), (cx + 92, cy - 170), (cx + 92, cy + 170), (cx - 92, cy + 170)], cx, cy, tilt)
    g.poly(scr, fill=(120, 190, 255))
    for i in range(3):
        ph = (t * 0.7 - i * 0.25) % 1
        if ph < 0.8:
            y = cy - 120 + i * 85
            k = min(1, ph * 6)
            g.rect(cx - 80 * k, y - 28, cx + 80 * k, y + 28, fill=(255, 255, 255, 230), r=14)
            g.circle(cx - 55 * k, y, 14 * k, fill=(255, 120, 120))
    for i in range(3):
        a = -0.6 + i * 0.6
        r = 240 + 20 * math.sin(t * 6)
        g.arc(cx, cy, r, math.degrees(a) - 15 - 90 + 90, math.degrees(a) + 15, fill=(255, 255, 255, 140), w=6)


def p_cat(g, t, dur, ctx):
    cx, cy = 620, 330
    fur = (255, 170, 90)
    pts = []
    for k in range(14):
        a = k / 13
        pts.append((cx + 100 + a * 140 + math.sin(t * 3 + a * 3) * 30 * a, cy + 120 - a * 200 + math.cos(t * 3 + a * 3) * 20 * a))
    g.line(pts, fill=fur, w=26)
    g.ellipse(cx, cy + 70, 110, 95, fill=fur, outline=INK, w=4)
    g.circle(cx, cy - 60, 90, fill=fur, outline=INK, w=4)
    for d in (-1, 1):
        g.poly([(cx + d * 30, cy - 135), (cx + d * 85, cy - 175), (cx + d * 82, cy - 95)], fill=fur, outline=INK, w=4)
    blink = (t % 2.5) < 0.18
    for d in (-1, 1):
        ex = cx + d * 35
        if blink:
            g.arc(ex, cy - 65, 14, 20, 160, fill=INK, w=4)
        else:
            g.ellipse(ex, cy - 65, 14, 20, fill=(120, 200, 90), outline=INK, w=3)
            g.ellipse(ex, cy - 65, 4, 14, fill=INK)
    g.poly([(cx - 10, cy - 35), (cx + 10, cy - 35), (cx, cy - 25)], fill=(255, 120, 140))
    for d in (-1, 1):
        for k in (-8, 6):
            g.line([(cx + d * 25, cy - 25 + k / 2), (cx + d * 110, cy - 35 + k)], fill=INK, w=2)


def p_dog(g, t, dur, ctx):
    cx, cy = 620, 320
    fur, ear = (230, 190, 140), (150, 100, 70)
    wag = math.sin(t * 14) * 0.6
    tail = rot([(cx + 100, cy + 60), (cx + 200, cy - 10)], cx + 100, cy + 60, wag)
    g.line(tail, fill=fur, w=22)
    g.ellipse(cx + 20, cy + 80, 120, 80, fill=fur, outline=INK, w=4)
    g.circle(cx - 60, cy - 30, 85, fill=fur, outline=INK, w=4)
    flop = math.sin(t * 7) * 6
    g.ellipse(cx - 135, cy - 20 + flop, 30, 60, fill=ear, outline=INK, w=4)
    g.ellipse(cx + 15, cy - 20 - flop, 30, 60, fill=ear, outline=INK, w=4)
    g.circle(cx - 85, cy - 45, 10, fill=INK)
    g.circle(cx - 35, cy - 45, 10, fill=INK)
    g.ellipse(cx - 60, cy, 20, 14, fill=INK)
    tongue = 8 + 6 * abs(math.sin(t * 5))
    g.ellipse(cx - 60, cy + 30 + tongue / 2, 14, tongue, fill=(255, 120, 140), outline=INK, w=2)


def p_dumbbell(g, t, dur, ctx):
    lift = (math.sin(t * 3) + 1) / 2
    y = 330 - lift * 120
    g.paste(ctx["mascot"]["open"], 620, GROUND - 110)
    g.line([(540, y + 30), (500, y + 120)], fill=INK, w=6)
    g.line([(700, y + 30), (740, y + 120)], fill=INK, w=6)
    g.rect(460, y - 8, 780, y + 8, fill=(120, 120, 130), r=6)
    for x in (460, 780):
        g.rect(x - 30, y - 55, x + 30, y + 55, fill=(60, 60, 70), r=12, outline=INK, w=3)
    if lift > 0.8:
        for k, (dx, dy) in enumerate(((-110, -20), (115, -10))):
            g.ellipse(620 + dx, GROUND - 230 + dy + (t * 60 % 30), 8, 13, fill=(120, 200, 255))


def p_soda(g, t, dur, ctx):
    cx = 480
    g.rect(cx - 70, 170, cx + 70, GROUND, fill=(220, 50, 60), r=20, outline=INK, w=5)
    g.rect(cx - 70, 260, cx + 70, 330, fill=(255, 255, 255))
    g.text(cx, 295, "FIZZ", 34, (220, 50, 60))
    for i in range(12):
        ph = (t * 0.8 + i / 12) % 1
        g.circle(cx - 40 + (i * 23) % 80 + math.sin(t * 5 + i) * 6, 165 - ph * 160, 5 + i % 3 * 2, outline=(255, 255, 255), w=2)
    n = min(9, int(t / max(dur * 0.7 / 9, 0.3)) + 1)
    for k in range(n):
        row, col = divmod(k, 3)
        x, y = 680 + col * 62 + (row % 2) * 30, GROUND - 30 - row * 58
        if k == n - 1:
            ph = min(1, (t % max(dur * 0.7 / 9, 0.3)) * 4)
            y = 0 + (y - 0) * ease_out_bounce(ph)
        g.rect(x - 28, y - 28, x + 28, y + 28, fill=(255, 255, 255), r=6, outline=INK, w=3)
    g.text(780, 120, f"{n} sugar cubes", 32, (255, 255, 255), stroke=3, stroke_fill=INK)


def p_calendar(g, t, dur, ctx):
    cx, cy = 620, 280
    g.rect(cx - 160, cy - 170, cx + 160, cy + 170, fill=(255, 255, 255), r=20, outline=INK, w=5)
    g.rect(cx - 160, cy - 170, cx + 160, cy - 90, fill=(235, 70, 80), r=20)
    for k in (-80, 80):
        g.rect(cx + k - 10, cy - 195, cx + k + 10, cy - 145, fill=(120, 120, 130), r=8)
    day = 24 + int(t / 0.8) % 7
    g.text(cx, cy + 40, str(day), 150, INK)
    g.text(cx, cy - 130, "FEB", 50, (255, 255, 255))
    ph = (t / 0.8) % 1
    if ph < 0.4:
        k = ph / 0.4
        g.poly([(cx - 160, cy - 90), (cx + 160, cy - 90), (cx + 160 - 40 * k, cy + 170 - 260 * k), (cx - 160 + 20 * k, cy + 170 - 250 * k)],
               fill=(245, 245, 250, int(255 * (1 - k))), outline=INK, w=3)


def p_whale(g, t, dur, ctx):
    bob = math.sin(t * 1.5) * 12
    cx, cy = 600, 350 + bob
    for i in range(4):
        g.arc(330 + i * 200, GROUND + 10, 100, 200, 340, fill=(255, 255, 255, 180), w=6)
    g.ellipse(cx, cy, 230, 110, fill=(70, 130, 220), outline=INK, w=5)
    g.ellipse(cx + 20, cy + 50, 170, 55, fill=(170, 210, 255))
    tail = math.sin(t * 2) * 20
    g.poly([(cx - 210, cy - 10), (cx - 320, cy - 90 + tail), (cx - 290, cy), (cx - 320, cy + 70 + tail)], fill=(70, 130, 220), outline=INK, w=5)
    g.circle(cx + 140, cy - 30, 12, fill=INK)
    g.arc(cx + 150, cy + 10, 30, 20, 120, fill=INK, w=4)
    ph = (t % 3) / 3
    if ph < 0.6:
        h = math.sin(ph / 0.6 * math.pi) * 170
        for k in (-1, 0, 1):
            g.line([(cx + 60, cy - 105), (cx + 60 + k * 50, cy - 105 - h), (cx + 60 + k * 90, cy - 105 - h * 0.8)],
                   fill=(180, 225, 255), w=10)


def p_breath(g, t, dur, ctx):
    cyc = t % 16
    if cyc < 4:
        k, label = cyc / 4, "Breathe in"
    elif cyc < 8:
        k, label = 1, "Hold"
    elif cyc < 12:
        k, label = 1 - (cyc - 8) / 4, "Breathe out"
    else:
        k, label = 0, "Hold"
    r = 80 + 120 * (0.5 - 0.5 * math.cos(k * math.pi))
    g.circle(620, 270, r + 30, fill=(120, 220, 200, 70))
    g.circle(620, 270, r, fill=(120, 220, 200, 200), outline=(255, 255, 255), w=6)
    g.text(620, 270, label, 48, (255, 255, 255), stroke=4, stroke_fill=(40, 120, 110))
    count = 4 - int(cyc % 4)
    g.text(620, 470, str(count), 50, (255, 255, 255), stroke=4, stroke_fill=(40, 120, 110))


def p_globe(g, t, dur, ctx):
    cx, cy, r = 620, 270, 170
    g.circle(cx, cy, r, fill=(70, 150, 230), outline=INK, w=5)
    for k in range(6):
        ph = (t * 0.15 + k / 6) % 1
        x = math.cos(ph * math.pi)
        g.ellipse(cx, cy, abs(x) * r + 1, r, outline=(255, 255, 255, 110), w=2)
        if 0.15 < ph < 0.85:
            g.circle(cx + x * r * 0.6, cy - 60 + k * 25 - 60, 40 * math.sin(ph * math.pi), fill=(110, 200, 110))
    for k in (-80, 0, 80):
        g.line([(cx - r, cy + k), (cx + r, cy + k)], fill=(255, 255, 255, 90), w=2)
    a = t * 1.5
    sx, sy = cx + math.cos(a) * 240, cy + math.sin(a) * 90
    g.rect(sx - 18, sy - 12, sx + 18, sy + 12, fill=(200, 200, 210), outline=INK, w=3)
    g.rect(sx - 55, sy - 8, sx - 22, sy + 8, fill=(90, 140, 255))
    g.rect(sx + 22, sy - 8, sx + 55, sy + 8, fill=(90, 140, 255))


def p_tablet(g, t, dur, ctx):
    cx, cy = 620, 280
    g.poly([(cx - 180, cy - 190), (cx + 150, cy - 210), (cx + 190, cy + 190), (cx - 170, cy + 200)],
           fill=(150, 150, 165), outline=INK, w=5)
    rng = random.Random(7)
    shown = int(t * 9)
    k = 0
    for row in range(6):
        y = cy - 150 + row * 60
        for col in range(7):
            x = cx - 140 + col * 45
            if k < shown:
                kind = rng.randint(0, 4)
                c = (60, 60, 80)
                if kind == 0:
                    g.circle(x, y, 14, outline=c, w=4)
                elif kind == 1:
                    g.poly([(x, y - 16), (x - 14, y + 12), (x + 14, y + 12)], outline=c, w=4)
                elif kind == 2:
                    g.line([(x - 14, y + 12), (x, y - 14), (x + 14, y + 12)], fill=c, w=4)
                elif kind == 3:
                    g.ellipse(x, y, 16, 8, outline=c, w=4)
                else:
                    g.line([(x, y - 16), (x, y + 16)], fill=c, w=4)
                    g.line([(x - 10, y), (x + 10, y)], fill=c, w=4)
            k += 1
    g.circle(cx + 220, cy - 160, 30 + 5 * math.sin(t * 4), outline=(255, 230, 90), w=6)
    g.line([(cx + 242, cy - 138), (cx + 290, cy - 90)], fill=(255, 230, 90), w=10)


def p_bones(g, t, dur, ctx):
    def bone(x, y, a, s=1.0):
        p1 = (x - math.cos(a) * 60 * s, y - math.sin(a) * 60 * s)
        p2 = (x + math.cos(a) * 60 * s, y + math.sin(a) * 60 * s)
        g.line([p1, p2], fill=(250, 245, 230), w=26 * s)
        for px, py in (p1, p2):
            for d in (-1, 1):
                g.circle(px + math.cos(a + math.pi / 2) * 12 * d * s, py + math.sin(a + math.pi / 2) * 12 * d * s, 17 * s,
                         fill=(250, 245, 230), outline=INK, w=2)
    for i in range(5):
        ph = (t * 0.45 + i / 5) % 1
        y = 40 + ease_out_bounce(min(1, ph * 1.6)) * (GROUND - 80 - 40 - i % 2 * 50)
        bone(380 + i * 120, y, t * 2 * (1 - min(1, ph * 1.6)) + i, 0.9)
    count = 206 if (t % 6) > 3 else 300
    g.text(620, 90, f"{count} bones", 54, (255, 255, 255), stroke=4, stroke_fill=INK)


def p_umbrella(g, t, dur, ctx):
    sway = math.sin(t * 1.5) * 0.08
    cx, cy = 560, 200
    g.line(rot([(cx, cy), (cx, GROUND)], cx, GROUND, sway), fill=(200, 200, 210), w=10)
    top = rot([(cx - 220, cy + 10), (cx, cy - 110), (cx + 220, cy + 10)], cx, GROUND, sway)
    g.poly(top, fill=(255, 100, 100), outline=INK, w=5)
    stripe = rot([(cx - 70, cy + 10), (cx, cy - 110), (cx + 70, cy + 10)], cx, GROUND, sway)
    g.poly(stripe, fill=(255, 255, 255))
    for i in range(10):
        a = t * 0.8 + i * TAU / 10
        g.line([(880 + math.cos(a) * 60, 110 + math.sin(a) * 60), (880 + math.cos(a) * 85, 110 + math.sin(a) * 85)],
               fill=(255, 200, 60), w=8)
    g.circle(880, 110, 52, fill=(255, 215, 70), outline=(240, 160, 40), w=4)
    g.rect(760, GROUND - 130, 830, GROUND, fill=(255, 200, 80), r=16, outline=INK, w=4)
    g.rect(775, GROUND - 160, 815, GROUND - 130, fill=(70, 160, 230), r=6, outline=INK, w=3)
    g.text(795, GROUND - 65, "SPF", 24, INK)
    g.text(795, GROUND - 35, "30+", 24, INK)


def p_idea(g, t, dur, ctx):
    p_brain_light = (t % 1.0) < 0.7
    cx, cy = 620, 230
    glow = 20 * math.sin(t * 6)
    if p_brain_light:
        g.circle(cx, cy, 120 + glow, fill=(255, 240, 150, 90))
    g.circle(cx, cy, 95, fill=(255, 235, 110) if p_brain_light else (240, 240, 220), outline=INK, w=5)
    g.rect(cx - 45, cy + 85, cx + 45, cy + 145, fill=(170, 170, 185), r=10, outline=INK, w=4)
    g.line([(cx - 25, cy + 30), (cx - 10, cy - 20), (cx, cy + 20), (cx + 10, cy - 20), (cx + 25, cy + 30)], fill=(220, 150, 40), w=5)
    for i in range(3):
        ph = (t * 1.2 + i / 3) % 1
        g.text(400 + i * 210, 420 - abs(math.sin(ph * math.pi)) * 120, "?", 70, (255, 255, 255), stroke=4, stroke_fill=INK)


PROPS = {
    "pyramid": p_pyramid, "football": p_football, "baby": p_baby, "heart": p_heart, "water": p_water,
    "sleep": p_sleep, "sunlight": p_sunlight, "space": p_space, "plane": p_plane, "brain": p_brain,
    "lightning": p_lightning, "fish": p_fish, "octopus": p_octopus, "fruit": p_fruit, "clock": p_clock,
    "walk": p_walk, "germs": p_germs, "book": p_book, "bee": p_bee, "phone": p_phone, "cat": p_cat,
    "dog": p_dog, "dumbbell": p_dumbbell, "soda": p_soda, "calendar": p_calendar, "whale": p_whale,
    "breath": p_breath, "globe": p_globe, "tablet": p_tablet, "bones": p_bones, "umbrella": p_umbrella,
    "idea": p_idea,
}
ACTOR_PROPS = {"walk", "dumbbell", "sleep"}      # props where Pip is part of the animation

KEYWORDS = [
    ("football", ["football", "soccer", "stadium", "world cup", "penalty"]),
    ("baby", ["baby", "babies", "newborn", "infant", "toddler", "crib"]),
    ("pyramid", ["pyramid", "giza", "khufu", "pharaoh"]),
    ("tablet", ["hieroglyph", "rosetta", "decree", "script", "ancient writing", "stone slab", "champollion"]),
    ("octopus", ["octopus"]), ("whale", ["whale"]), ("bee", ["bee", "honey"]),
    ("fish", ["fish", "ocean", "sea", "reef", "dolphin", "underwater", "otter", "plankton", "jellyfish", "salt"]),
    ("heart", ["heart", "blood pressure", "pulse", "beat"]),
    ("breath", ["breath", "breathe", "breathing", "inhale", "exhale"]),
    ("water", ["water", "drink", "hydrat", "thirst", "urine", "bottle"]),
    ("sleep", ["sleep", "bed", "nap", "tired", "night", "pillow", "rest"]),
    ("germs", ["wash", "soap", "germ", "hand", "sanitizer", "bacteria"]),
    ("umbrella", ["sunscreen", "spf", "uv", "sunburn", "sun safety", "sunglasses"]),
    ("soda", ["sugar", "soda", "cola", "sweet", "syrup"]),
    ("fruit", ["fruit", "banana", "berry", "strawberr", "apple", "tomato", "avocado", "grape", "carrot", "food",
               "fiber", "vegetable", "beans", "nuts", "pineapple", "cashew", "ketchup", "chocolate", "cacao", "bread"]),
    ("dumbbell", ["exercise", "workout", "muscle", "strong", "gym", "lift"]),
    ("walk", ["walk", "steps", "stairs", "move", "sitting", "stretch", "run", "jog"]),
    ("bones", ["bone", "skeleton", "spine"]),
    ("brain", ["brain", "memory", "mind", "neuron", "think", "focus", "mood", "stress"]),
    ("lightning", ["lightning", "thunder", "storm", "rain", "electric"]),
    ("plane", ["airplane", "plane", "flight", "fly", "wing", "lift", "pilot"]),
    ("space", ["space", "planet", "star", "galaxy", "moon", "orbit", "black hole", "venus", "saturn", "astronaut",
               "universe", "rocket"]),
    ("sunlight", ["sun", "light", "rainbow", "color", "sky", "sunset", "wavelength", "scatter"]),
    ("globe", ["internet", "cable", "world", "earth", "global", "countries", "time zone", "longitude", "map"]),
    ("clock", ["clock", "time", "hour", "minute", "second", "caffeine"]),
    ("calendar", ["calendar", "year", "leap", "february", "date"]),
    ("phone", ["phone", "screen", "computer", "laptop", "digital", "notification"]),
    ("book", ["history", "book", "school", "learn", "study", "museum", "scholar", "read", "university"]),
    ("cat", ["cat", "kitten", "purr", "meow"]), ("dog", ["dog", "puppy"]),
]

SCENE_FOR_PROP = {
    "football": "stadium", "baby": "nursery", "pyramid": "desert", "tablet": "desert", "octopus": "ocean",
    "whale": "ocean", "fish": "ocean", "space": "space", "sleep": "night", "lightning": "night", "plane": "sky",
    "sunlight": "sky", "bee": "park", "walk": "park", "umbrella": "sky", "globe": "space", "cat": "nursery",
    "dog": "park", "phone": "city", "clock": "city", "calendar": "city", "book": "city",
}


def pick_prop(text, search, category, index, rng):
    explicit = None
    s = f"{search or ''} {text or ''}".lower()
    for prop, words in KEYWORDS:
        if any(w in s for w in words):
            explicit = prop
            break
    if explicit:
        return explicit
    pool = {"education": ["idea", "book", "globe", "brain"], "health": ["heart", "walk", "water", "breath"],
            "fun": ["idea", "fruit", "cat", "dog", "bee"]}.get(category, ["idea"])
    return pool[(index + rng.randint(0, 9)) % len(pool)]


# --------------------------------------------------------------------------- extra scenes

def scene_stadium(rng):
    img = cartoon._gradient((80, 160, 255), (190, 225, 255))
    d = ImageDraw.Draw(img)
    p = cartoon._s
    d.rectangle((0, p(1150), p(W), p(1330)), fill=(90, 90, 120))
    for row in range(5):
        for x in range(0, W, 26):
            col = rng.choice([(255, 90, 90), (255, 220, 70), (90, 160, 255), (255, 255, 255), (120, 220, 120)])
            cartoon._circle(d, x + 13 + (row % 2) * 13, 1170 + row * 32, 10, col)
    for k in range(10):
        shade = (90, 190, 90) if k % 2 == 0 else (80, 175, 82)
        d.rectangle((0, p(1330 + k * 60), p(W), p(1390 + k * 60)), fill=shade)
    d.line((0, p(1640), p(W), p(1640)), fill=(255, 255, 255), width=p(6))
    for x in (120, 960):
        d.rectangle((p(x - 8), p(700), p(x + 8), p(1150)), fill=(200, 200, 210))
        for i in range(3):
            cartoon._circle(d, x - 30 + i * 30, 690, 16, (255, 250, 200))
    return cartoon._done(img)


def scene_nursery(rng):
    wall = rng.choice([(255, 225, 235), (225, 240, 255), (235, 250, 225), (255, 240, 210)])
    img = cartoon._gradient(wall, tuple(max(c - 20, 0) for c in wall))
    d = ImageDraw.Draw(img)
    for _ in range(40):
        x, y = rng.randint(0, W), rng.randint(0, 1400)
        col = rng.choice([(255, 200, 120), (180, 200, 255), (255, 170, 190)])
        cartoon._circle(d, x, y, 10, col + (160,))
    p = cartoon._s
    d.rectangle((0, p(1520), p(W), p(H)), fill=(220, 180, 140))
    for x in range(0, W, 90):
        d.line((p(x), p(1520), p(x - 60), p(H)), fill=(200, 160, 120), width=p(3))
    d.rounded_rectangle((p(380), p(1590), p(900), p(1700)), radius=p(55), fill=(255, 255, 255, 200))
    return cartoon._done(img)


cartoon.SCENES.setdefault("stadium", scene_stadium)
cartoon.SCENES.setdefault("nursery", scene_nursery)


# --------------------------------------------------------------------------- mascot with outfits

def mascot_sprites(work, category, outfit, glasses, color):
    from pathlib import Path
    out = {}
    for name, kw in (("open", {}), ("blink", {"blink": True}), ("wave", {"wave": True})):
        path = Path(work) / f"pip_{name}.png"
        cartoon.draw_mascot(path, body=color, **kw)
        img = Image.open(path).convert("RGBA")
        d = ImageDraw.Draw(img)
        cx = 210
        if outfit == "grad":
            d.polygon([(cx - 110, 70), (cx, 30), (cx + 110, 70), (cx, 110)], fill=(40, 40, 60))
            d.rectangle((cx - 55, 85, cx + 55, 115), fill=(40, 40, 60))
            d.line((cx, 70, cx + 85, 85, cx + 90, 140), fill=(255, 210, 60), width=6)
            d.ellipse((cx + 80, 135, cx + 100, 155), fill=(255, 210, 60))
        elif outfit == "band":
            d.chord((cx - 140, 95, cx + 140, 375), 200, 340, fill=None, outline=(235, 60, 70), width=24)
        elif outfit == "party":
            d.polygon([(cx - 50, 105), (cx + 50, 105), (cx + 5, -5)], fill=(150, 90, 230))
            for k in range(3):
                y = 25 + k * 28
                d.line((cx - 12 - k * 13, y + 20, cx + 18 + k * 12, y + 20), fill=(255, 220, 70), width=8)
            d.ellipse((cx - 10, -12, cx + 20, 18), fill=(255, 120, 150))
        elif outfit == "crown":
            d.polygon([(cx - 70, 110), (cx - 70, 50), (cx - 35, 85), (cx, 35), (cx + 35, 85), (cx + 70, 50), (cx + 70, 110)],
                      fill=(255, 205, 50), outline=INK)
            d.ellipse((cx - 10, 75, cx + 10, 95), fill=(255, 90, 110))
        if glasses and name != "blink":
            for ex in (cx - 50, cx + 50):
                d.rounded_rectangle((ex - 36, 195, ex + 36, 245), radius=14, fill=(30, 30, 40))
                d.line((ex - 20, 205, ex - 5, 205), fill=(255, 255, 255), width=4)
            d.line((cx - 14, 210, cx + 14, 210), fill=(30, 30, 40), width=8)
        big = img.resize((int(img.width * S * 0.62), int(img.height * S * 0.62)), Image.LANCZOS)
        out[name] = big
    return out


# --------------------------------------------------------------------------- video look

class Look:
    """Per-video choices, so every video looks different."""

    def __init__(self, script_id, category):
        rng = random.Random(f"look-{script_id}")
        self.box_style = rng.choice(["dark", "light", "color"])
        self.entrance = rng.choice(["pop", "slide", "rise", "drop"])
        outfits = {"education": ["grad", "grad", "crown", "none"], "health": ["band", "band", "none"],
                   "fun": ["party", "crown", "party", "none"]}
        self.outfit = rng.choice(outfits.get(category, ["none"]))
        self.glasses = rng.random() < 0.3
        palette = {"education": [(120, 190, 255), (150, 160, 255), (110, 210, 230)],
                   "health": [(120, 220, 150), (150, 230, 120), (110, 210, 190)],
                   "fun": [(255, 196, 70), (255, 150, 120), (255, 170, 210)]}
        self.mascot_color = rng.choice(palette.get(category, [(255, 196, 70)]))
        self.mascot_side = rng.choice(["left", "right"])
        self.seed = rng.randint(0, 10 ** 6)


# --------------------------------------------------------------------------- segment rendering

def _transform_card(card, kind, u):
    """Return (image, offset) for the caption card during its entrance (u: 0..1)."""
    if u >= 1:
        return card, (0, 0)
    if kind == "slide":
        e = 1 - (1 - u) ** 3
        return card, (int(-W * (1 - e)), 0)
    if kind == "rise":
        e = 1 - (1 - u) ** 3
        img = card.copy()
        img.putalpha(img.getchannel("A").point(lambda a: int(a * u)))
        return img, (0, int(220 * (1 - e)))
    if kind == "drop":
        return card, (0, int(-500 * (1 - ease_out_bounce(u))))
    bbox = card.getbbox() or (0, 0, W, H)
    crop = card.crop(bbox)
    sc = max(0.05, ease_out_back(u))
    nw, nh = max(1, int(crop.width * sc)), max(1, int(crop.height * sc))
    small = crop.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
    canvas.alpha_composite(small, (max(0, cx - nw // 2), max(0, cy - nh // 2)))
    return canvas, (0, 0)


def render_segment(ff_bin, preset, scene_png, card_png, prop, seconds, look, sprites, wave, out_path, offset=0.0):
    bg = Image.open(scene_png).convert("RGBA")
    card = Image.open(card_png).convert("RGBA")
    static = bg.copy()
    static.alpha_composite(card)
    static_rgb = static.convert("RGB")
    stage_bg = bg.crop((0, STAGE_Y, SW, STAGE_Y + SH)).resize((SW * S, SH * S), Image.BICUBIC)
    card_stage = card.crop((0, STAGE_Y, SW, STAGE_Y + SH))
    card_in_stage = card_stage.getbbox() is not None
    sky = bg.getpixel((40, 40))[:3]
    ctx = {"mascot": sprites, "mascot_color": look.mascot_color, "sky": sky}
    actor = prop in ACTOR_PROPS
    mx = 150 if look.mascot_side == "left" else 930
    prop_fn = PROPS.get(prop, p_idea)
    shift = 0 if look.mascot_side == "left" else -200   # move props away from the mascot

    frames = int(round(seconds * FPS))
    proc = subprocess.Popen([ff_bin, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                             "-c:v", "libx264", "-preset", preset, "-crf", "21", "-pix_fmt", "yuv420p",
                             "-r", str(FPS), str(out_path)], stdin=subprocess.PIPE)
    entrance_frames = int(0.45 * FPS)
    try:
        for f in range(frames):
            t = f / FPS
            if f < entrance_frames:
                img, (ox, oy) = _transform_card(card, look.entrance, (f + 1) / entrance_frames)
                top = bg.copy()
                top.alpha_composite(img, (0, 0)) if (ox, oy) == (0, 0) else top.alpha_composite(
                    img.crop((max(0, -ox), max(0, -oy), min(W, W - ox), min(H, H - oy))), (max(0, ox), max(0, oy)))
                frame = top.convert("RGB")
            else:
                frame = static_rgb.copy()

            stage = stage_bg.copy()
            g = G(stage)
            layer = Image.new("RGBA", stage.size, (0, 0, 0, 0))
            gl = G(layer)
            prop_fn(gl, t + offset, seconds, ctx)
            if shift:
                layer = layer.transform(layer.size, Image.AFFINE, (1, 0, -shift * S, 0, 1, 0))
            stage.alpha_composite(layer)
            if not actor:
                bob = math.sin((t + offset) * TAU * 0.9) * 10
                if wave and ((t % 2.4) < 1.2):
                    sprite = sprites["wave"]
                elif (t + offset) % 3.4 < 0.16:
                    sprite = sprites["blink"]
                else:
                    sprite = sprites["open"]
                g.paste(sprite, mx, GROUND - 100 + bob)
            small = stage.resize((SW, SH), Image.BOX)
            if card_in_stage:
                small.alpha_composite(card_stage)
            frame.paste(small.convert("RGB"), (0, STAGE_Y))
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed while encoding {out_path}")
