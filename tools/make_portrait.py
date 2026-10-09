#!/usr/bin/env python3
"""
Turn a portrait photo into the 0/1 "binary portrait" used on the home page.

Usage:
    pip install -r requirements-tools.txt
    python tools/make_portrait.py path/to/photo-cutout.png

Best input: a PNG with a TRANSPARENT background (e.g. made with remove.bg,
Photoshop, or Canva "background remover"). A normal JPG also works - the
script will then try to cut you out automatically (works best on a plain wall).

Output: content/portrait.json  (the site picks it up automatically)
"""
import sys, json, os
import cv2
import numpy as np

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "photo-cutout.png")
OUT = os.path.join(os.path.dirname(__file__), "..", "content", "portrait.json")

WIDTH_PX = 600          # rendered width of the portrait on the page
SML_COLS = 92           # fine grid (face)      -> cell 6.52px
MED_COLS = 46           # medium grid           -> cell 13.04px
BIG_COLS = 23           # big grid (dissolving) -> cell 26.09px
CROP_TOP = 0.0          # crop (fractions of the photo): tighter crop = bigger face
CROP_BOTTOM = None      # None = automatic: shoulders end up at SHOULDER_AT of the height
SHOULDER_AT = 0.68      # where the shoulder line sits in the portrait (0 = top, 1 = bottom)
CROP_LEFT = 0.10
CROP_RIGHT = 0.92
SEED = 7
GAMMA = 1.5            # contrast of the face (1.0 - 2.0)


def find_shoulders(alpha):
    """Relative height where the shoulders reach full width (below the neck).

    Everything above this line (the whole head) is drawn with fine, solid digits;
    the dissolving effect and the name start below it - on the shirt, not the face."""
    width = (alpha > 128).sum(axis=1).astype(float)
    h = len(width)
    rows = np.nonzero(width)[0]
    top = rows[0] if len(rows) else 0
    head = slice(top, top + int(h * 0.45))
    neck = top + int(np.argmin(np.where(width[head] > 0, width[head], 1e9)))
    full = width.max()
    for y in range(neck, h):
        if width[y] >= 0.92 * full:
            return y / h
    return 0.6


def load(path):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        sys.exit(f"Cannot read {path}")
    if img.ndim == 3 and img.shape[2] == 4:
        return img[:, :, :3], img[:, :, 3]
    # no alpha -> automatic cut-out with GrabCut
    bgr = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h, w = bgr.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    rect = (int(w * .03), int(h * .02), int(w * .94), int(h * .97))
    bg, fg = np.zeros((1, 65)), np.zeros((1, 65))
    cv2.grabCut(bgr, mask, rect, bg, fg, 8, cv2.GC_INIT_WITH_RECT)
    m = np.where((mask == 1) | (mask == 3), 255, 0).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    return bgr, m


def main():
    bgr, alpha = load(SRC)
    h, w = bgr.shape[:2]
    alpha_full_h = alpha.shape[0]
    shoulder = find_shoulders(alpha)
    bottom = CROP_BOTTOM if CROP_BOTTOM else min(1.0, (shoulder - CROP_TOP) / SHOULDER_AT + CROP_TOP)
    y0, y1 = int(h * CROP_TOP), int(h * bottom)
    x0, x1 = int(w * CROP_LEFT), int(w * CROP_RIGHT)
    bgr, alpha = bgr[y0:y1, x0:x1], alpha[y0:y1, x0:x1]
    h, w = bgr.shape[:2]

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    inside = alpha > 128
    # local contrast boost so facial features read well as digits
    blur = cv2.GaussianBlur(gray, (0, 0), 3)
    gray = np.clip(gray + 1.2 * (gray - blur), 0, 255)       # sharpen features
    lo, hi = np.percentile(gray[inside], [3, 97])
    dark = np.clip((hi - gray) / max(hi - lo, 1), 0, 1)   # 1 = darkest
    dark = dark ** GAMMA                                   # >1 = lighter skin, darker features

    rng = np.random.default_rng(SEED)
    height_px = WIDTH_PX * h / w

    def grid(cols, y0, y1, keep):
        """Sample the photo into a cols-wide grid between rel. heights y0..y1.
        keep(yrel) -> probability a filled cell is kept (for the dissolve)."""
        cell = WIDTH_PX / cols
        rows = int(round((y1 - y0) * height_px / cell))
        out = []
        for r in range(rows):
            yrel = y0 + (r + .5) * cell / height_px
            line = []
            for c in range(cols):
                xa, xb = int(c * w / cols), int((c + 1) * w / cols)
                ya = int((y0 * height_px + r * cell) / height_px * h)
                yb = int((y0 * height_px + (r + 1) * cell) / height_px * h)
                yb = max(yb, ya + 1); xb = max(xb, xa + 1)
                a = alpha[ya:yb, xa:xb].mean() / 255
                if a < .5 or rng.random() > keep(yrel):
                    line.append(".")
                    continue
                d = dark[ya:yb, xa:xb].mean()
                lvl = 2 + int(round(d * 7.4))
                line.append(str(min(9, max(2, lvl))))
            out.append("".join(line).rstrip("."))
        return {"cols": cols, "cell": round(cell, 4),
                "top": round(y0 * height_px, 2), "rows": out}

    def fade(a, b):          # 1 above a, 0 below b
        return lambda y: 1.0 if y < a else max(0.0, 1 - (y - a) / (b - a)) ** 1.4

    def band(a, b, c, d):    # fades in a..b, full b..c, fades out c..d
        def f(y):
            if y < a or y > d: return 0.0
            if y < b: return (y - a) / (b - a)
            if y <= c: return 1.0
            return max(0.0, 1 - (y - c) / (d - c)) ** 1.3
        return f

    S = (shoulder - y0 / alpha_full_h) / (bottom - CROP_TOP) if bottom > CROP_TOP else .68
    S = float(min(max(S, .45), .85))
    print(f"shoulders at {S:.2f} of the portrait height")
    data = {
        "width": WIDTH_PX,
        "height": round(height_px, 1),
        "layers": [
            # big digits: below the shoulders, dissolving to the bottom
            {"name": "big", **grid(BIG_COLS, S, 1.0, band(S + .03, S + .12, S + .20, 1.0))},
            # medium digits: the transition zone around the shoulders/chest
            {"name": "med", **grid(MED_COLS, S - .06, 1.0, band(S - .05, S + .03, S + .12, S + .30))},
            # fine digits: the whole head and neck stay solid down to the shoulders
            {"name": "sml", **grid(SML_COLS, 0.0, min(1.0, S + .22), fade(S + .02, S + .22))},
        ],
        "title_at": round(min(.9, S + .05), 3),   # the name sits on the shirt
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"wrote {os.path.normpath(OUT)}  ({int(height_px)}px tall)")


if __name__ == "__main__":
    main()
