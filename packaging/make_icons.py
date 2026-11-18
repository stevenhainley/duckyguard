"""Builds every DuckyGuard icon. Run it to regenerate all of them:

    .venv/bin/python packaging/make_icons.py

Menu bar  (src/duckyguard/ui/icons/menubar-<state>.png 18 px and @2x.png 36 px; black + alpha, macOS tints them)
    A side-profile duck head facing left, drawn here as a vector path on a 16 pt grid inside the 18 pt canvas.
    State is carried by shape and weight, never by colour:
      protected  the solid glyph            attention  the glyph with a "!" badge (installed, cannot block)
      alert      knocked out of a tile      paused     the glyph at 35 % opacity

App icon  (assets/AppIcon.icns, assets/AppIcon-1024.png; the iconset is left in build/AppIcon.iconset)
    One design at every size: the cyber duck head from assets/cyber-duck.png (red = engraving tone, alpha =
    silhouette), yellow on a navy macOS tile (1024 canvas, 824 tile), with the camera lens as the one red accent.
    Up to 128 px it is the flat silhouette with the eye, the lens and the bill's edge knocked out; from 256 px
    the same silhouette carries the engraving as a two-ink ordered dither.
"""
import math
import os
import shutil
import subprocess

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "cyber-duck.png")
MENUBAR_DIR = os.path.join(ROOT, "src", "duckyguard", "ui", "icons")
ICONSET = os.path.join(ROOT, "build", "AppIcon.iconset")
ICNS = os.path.join(ROOT, "assets", "AppIcon.icns")
PNG_1024 = os.path.join(ROOT, "assets", "AppIcon-1024.png")

YELLOW, RED = (249, 224, 21), (240, 53, 59)
NAVY_TOP, NAVY, NAVY_EDGE = (15, 19, 39), (8, 12, 28), (52, 60, 104)
BAYER = [[0, 48, 12, 60, 3, 51, 15, 63], [32, 16, 44, 28, 35, 19, 47, 31], [8, 56, 4, 52, 11, 59, 7, 55], [40, 24, 36, 20, 43, 27, 39, 23],
         [2, 50, 14, 62, 1, 49, 13, 61], [34, 18, 46, 30, 33, 17, 45, 29], [10, 58, 6, 54, 9, 57, 5, 53], [42, 26, 38, 22, 41, 25, 37, 21]]


# ---------------------------------------------------------------- menu bar glyph

MENUBAR_STATES = ("protected", "attention", "alert", "paused")
PT = 32                                   # master pixels per point; 18 pt canvas -> 576 px master
EYE = (9.0, 5.0, 1.15)                    # centre x, y and radius on the 16 pt grid (lands on whole pixels at 1x)
# Outline of the head on the 16 pt grid: a start point, then cubic Bezier segments (c1, c2, end). Straight
# runs are written as degenerate curves. The bill is a third of the width; its underside and the neck's
# base sit on whole points so they stay crisp at 1x.
DUCK = ((0.0, 8.5), [
    ((0.0, 7.6), (0.7, 7.0), (1.6, 7.0)),          # rounded tip of the bill
    ((2.7, 7.0), (3.6, 6.9), (4.4, 6.6)),          # top of the bill, flat like a duck's
    ((5.2, 6.3), (5.4, 5.6), (5.6, 4.8)),          # the stop, up to the forehead
    ((6.1, 2.2), (8.2, 0.5), (10.7, 0.5)),         # crown
    ((13.7, 0.5), (16.0, 2.8), (16.0, 5.7)),       # back of the head
    ((16.0, 8.0), (14.5, 9.3), (14.3, 11.2)),      # nape
    ((14.2, 12.9), (14.9, 14.6), (16.0, 16.0)),    # back of the neck, flaring into the body
    ((16.0, 16.0), (6.5, 16.0), (6.5, 16.0)),      # base
    ((8.0, 14.6), (8.9, 13.2), (8.8, 11.8)),       # chest
    ((8.7, 10.7), (7.4, 10.0), (5.8, 10.0)),       # throat, up under the bill
    ((5.8, 10.0), (1.5, 10.0), (1.5, 10.0)),       # underside of the bill
    ((0.6, 10.0), (0.0, 9.4), (0.0, 8.5)),         # back round the tip
])


def _outline(start, curves, steps=40):
    pts, p0 = [start], start
    for c1, c2, p3 in curves:
        for i in range(1, steps + 1):
            t = i / steps
            u = 1 - t
            pts.append(tuple(u ** 3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t ** 3 * d for a, b, c, d in zip(p0, c1, c2, p3)))
        p0 = p3
    return pts


def duck_glyph(scale=1.0, origin=(1.0, 1.0)):
    """The duck as a white-on-black master mask (18 pt * PT square); grid points map to origin + scale * p."""
    m = Image.new("L", (18 * PT, 18 * PT), 0)
    d = ImageDraw.Draw(m)
    to_px = lambda x, y: ((origin[0] + scale * x) * PT, (origin[1] + scale * y) * PT)
    d.polygon([to_px(*p) for p in _outline(*DUCK)], fill=255)
    ex, ey, er = EYE
    d.ellipse(to_px(ex - er, ey - er) + to_px(ex + er, ey + er), fill=0)
    return m


def _bang(grow=0.0):
    """A bold "!" at the right edge of the canvas (canvas points), optionally grown to make its clear halo."""
    m = Image.new("L", (18 * PT, 18 * PT), 0)
    d = ImageDraw.Draw(m)
    for x0, y0, x1, y1, r in ((15, 7, 17, 13, .7), (15, 15, 17, 17, 1.0)):       # stem, dot
        d.rounded_rectangle([(x0 - grow) * PT, (y0 - grow) * PT, (x1 + grow) * PT, (y1 + grow) * PT], radius=(r + grow) * PT, fill=255)
    return m


def menubar(state, px):
    if state == "alert":                                                          # a 13 pt duck knocked out of a filled tile
        tile = Image.new("L", (18 * PT, 18 * PT), 0)
        ImageDraw.Draw(tile).rounded_rectangle([0, 0, 18 * PT - 1, 18 * PT - 1], radius=4.5 * PT, fill=255)
        m = ImageChops.subtract(tile, duck_glyph(scale=13 / 16, origin=(2.5, 3.0)))
    else:
        m = duck_glyph()
        if state == "attention":
            m = ImageChops.lighter(ImageChops.subtract(m, _bang(grow=1.0)), _bang())
        elif state == "paused":
            m = m.point(lambda v: round(v * .35))
    im = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    im.putalpha(m.reduce(18 * PT // px))
    return im


# ---------------------------------------------------------------- app icon

HEAD_BOX = (72, 0, 426, 396)              # the head in the source art, with a little air around it
HEAD_ROWS = (7, 386)                      # top of the crest .. where the neck is cut (the cables below are dropped)
EYE_SRC = (168, 172, 21)                  # the living eye: centre x, y and radius in source pixels
LENS_SRC = (316, 177, 37)                 # the camera lens
BILL_SRC = [(108, 312), (122, 296), (146, 275), (170, 254), (188, 230), (197, 206), (208, 193), (228, 190), (250, 197), (260, 212),
            (264, 236), (272, 258), (290, 276), (308, 291), (303, 307), (286, 326), (268, 344), (250, 372)]   # where the bill meets the face
BILL_LEAD = 5                             # BILL_SRC[:BILL_LEAD] is the bill's leading edge, from the cheek up towards the eye
HEAD_FILL = {16: .80, 32: .74}            # head height as a share of the tile (a touch larger when tiny) ...
HEAD_FILL_DEFAULT = .70                   # ... and everywhere else
DITHER_CELL = {256: 1, 512: 2, 1024: 4}   # screen pixels per dither dot, so the three big sizes are one drawing
_art = None


def _source():
    """(engraving tone, silhouette alpha) cropped to HEAD_BOX."""
    global _art
    if _art is None:
        art = Image.open(SRC)
        alpha = art.getchannel("A")
        ImageDraw.Draw(alpha).rectangle([0, HEAD_ROWS[1], art.width, art.height], fill=0)
        _art = art.getchannel("R").crop(HEAD_BOX), alpha.crop(HEAD_BOX)
    return _art


def head_silhouette(size, ss=4, reduce=True):
    """Clean-edged head mask of `size` = (w, h) pixels (the source alpha is soft); reduce=False keeps the ss-times master."""
    big = _source()[1].resize((size[0] * ss, size[1] * ss), Image.BICUBIC).filter(ImageFilter.GaussianBlur(size[1] * ss / 260))
    big = big.point(lambda v: 255 if v > 120 else 0)
    return big.resize(size, Image.LANCZOS) if reduce else big


def _disc(draw, src, k, fill, grow=1.0, min_r=0.0):
    """Fill a source-space circle (x, y, r) on a head-crop image scaled by k."""
    cx, cy, r = (src[0] - HEAD_BOX[0]) * k, (src[1] - HEAD_BOX[1]) * k, max(src[2] * k * grow, min_r)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)


def flat_head(size, ss=8):
    """Small sizes: (yellow mask, red mask). The silhouette with the eye, the lens and the bill's edge knocked out."""
    yellow = head_silhouette(size, ss, reduce=False)
    red = Image.new("L", yellow.size, 0)
    d, k, px = ImageDraw.Draw(yellow), size[1] * ss / (HEAD_BOX[3] - HEAD_BOX[1]), ss       # px = one device pixel
    if size[1] >= 16:                                                             # 16 px icon: only the lens survives
        bill = BILL_SRC if size[1] >= 32 else BILL_SRC[:BILL_LEAD]                # 32 px icon: just the bill's leading edge
        d.line([((x - HEAD_BOX[0]) * k, (y - HEAD_BOX[1]) * k) for x, y in bill], fill=0, width=round(max(8.5 * k, 1.1 * px)), joint="curve")
        _disc(d, EYE_SRC, k, 0, min_r=1.2 * px)
    tiny = size[1] < 16
    _disc(d, LENS_SRC, k, 0, min_r=(1.35 if tiny else 1.8) * px)
    _disc(ImageDraw.Draw(red), LENS_SRC, k, 255, grow=.52, min_r=(.75 if tiny else .9) * px)
    return yellow.resize(size, Image.LANCZOS), red.resize(size, Image.LANCZOS)


def engraved_head(size, cell):
    """Large sizes: (yellow mask, red mask). The engraving as an ordered dither with dots `cell` pixels wide."""
    wl, hl = size[0] // cell, size[1] // cell
    t = _source()[0].filter(ImageFilter.UnsharpMask(radius=12, percent=250, threshold=0)).resize((wl, hl), Image.LANCZOS).load()
    k = hl / (HEAD_BOX[3] - HEAD_BOX[1])
    lx, ly, lr = (LENS_SRC[0] - HEAD_BOX[0]) * k, (LENS_SRC[1] - HEAD_BOX[1]) * k, LENS_SRC[2] * k
    yellow, red = Image.new("L", (wl, hl), 0), Image.new("L", (wl, hl), 0)
    yp, rp = yellow.load(), red.load()
    for y in range(hl):
        for x in range(wl):
            thresh = (BAYER[y % 8][x % 8] + .5) / 64
            d = ((x + .5 - lx) ** 2 + (y + .5 - ly) ** 2) ** .5 / lr
            if d < 1.0:                                                           # the lens: red core, red glow, yellow rim
                if d > .86:
                    yp[x, y] = 255
                elif d < .44 or (1 - (d - .44) / .42) ** 1.5 * .85 > thresh:
                    rp[x, y] = 255
            elif min(1.0, max(0.0, ((t[x, y] / 255) ** 1.2 - .20) / .70)) > thresh:    # highlights solid, shadows empty
                yp[x, y] = 255
    sil = head_silhouette(size)
    yellow, red = yellow.resize(size, Image.NEAREST), red.resize(size, Image.NEAREST)
    contour = ImageChops.subtract(sil, sil.filter(ImageFilter.MinFilter(2 * max(1, round(size[1] / 150)) + 1)))   # keeps the shape whole
    return ImageChops.multiply(ImageChops.lighter(yellow, contour), sil), ImageChops.multiply(red, sil)


def squircle(size, box, ss=4, n=5.0):
    """Superellipse mask (close to the macOS continuous-corner tile) filling box = (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = (v * ss + (.5 if i < 2 else -.5) for i, v in enumerate(box))  # mid-pixel, so the flat sides rasterise evenly
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    arc = lambda v: math.copysign(abs(v) ** (2 / n), v)
    pts = [(cx + rx * arc(math.cos(math.tau * i / 720)), cy + ry * arc(math.sin(math.tau * i / 720))) for i in range(720)]
    m = Image.new("L", (size * ss, size * ss), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m.resize((size, size), Image.LANCZOS)


def _centroid(mask):
    """Centre of mass of a mask, from its row and column projections."""
    cols, rows = mask.resize((mask.width, 1), Image.BOX).tobytes(), mask.resize((1, mask.height), Image.BOX).tobytes()
    return sum(i * v for i, v in enumerate(cols)) / sum(cols) + .5, sum(i * v for i, v in enumerate(rows)) / sum(rows) + .5


def app_icon(size):
    margin = max(1, int(size * 100 / 1024))                                       # 824 px tile on the 1024 canvas, pixel-snapped
    tile = size - 2 * margin
    mask = squircle(size, (margin, margin, size - margin, size - margin))
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if size >= 64:                                                                # soft drop shadow, kept inside the margin
        shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        shadow.putalpha(ImageChops.offset(mask, 0, round(size * .010)).filter(ImageFilter.GaussianBlur(size * .012)).point(lambda v: v * 3 // 10))
        icon.alpha_composite(shadow)
    grad = Image.linear_gradient("L").resize((size, size))
    paper = Image.composite(Image.new("RGB", (size, size), NAVY), Image.new("RGB", (size, size), NAVY_TOP), grad).convert("RGBA")
    paper.putalpha(mask)
    icon.alpha_composite(paper)
    if size >= 32:                                                                # hairline rim so the tile holds on dark backgrounds
        inset = margin + max(1, size / 512)
        ring = ImageChops.subtract(mask, squircle(size, (inset, inset, size - inset, size - inset)))
        rim = Image.new("RGBA", (size, size), NAVY_EDGE + (0,))
        rim.putalpha(ring.point(lambda v: v * (6 if size < 128 else 10) // 10))   # quieter on the small sizes
        icon.alpha_composite(rim)

    cell = DITHER_CELL.get(size, 1)
    k = tile * HEAD_FILL.get(size, HEAD_FILL_DEFAULT) / (HEAD_ROWS[1] - HEAD_ROWS[0]) / cell
    head = (round((HEAD_BOX[2] - HEAD_BOX[0]) * k) * cell, round((HEAD_BOX[3] - HEAD_BOX[1]) * k) * cell)
    yellow, red = engraved_head(head, cell) if size in DITHER_CELL else flat_head(head)
    sil = head_silhouette(head)
    box, (mx, my) = sil.getbbox(), _centroid(sil)
    cx, cy = .5 * (box[0] + box[2]) / 2 + .5 * mx, .7 * (box[1] + box[3]) / 2 + .3 * my   # optical centre: between the box and the mass
    at = (round(size / 2 - cx), round(size / 2 - cy))
    for m, colour in ((yellow, YELLOW), (red, RED)):
        layer = Image.new("RGBA", (size, size), colour + (0,))
        layer.paste(Image.new("RGBA", m.size, colour + (255,)), at, m)
        icon.alpha_composite(layer)
    return icon


# ---------------------------------------------------------------- build

def main():
    os.makedirs(MENUBAR_DIR, exist_ok=True)
    for state in MENUBAR_STATES:
        menubar(state, 18).save(os.path.join(MENUBAR_DIR, f"menubar-{state}.png"))
        menubar(state, 36).save(os.path.join(MENUBAR_DIR, f"menubar-{state}@2x.png"))
    shutil.rmtree(ICONSET, ignore_errors=True)
    os.makedirs(ICONSET)
    icons = {px: app_icon(px) for px in (16, 32, 64, 128, 256, 512, 1024)}
    for pts in (16, 32, 128, 256, 512):
        icons[pts].save(os.path.join(ICONSET, f"icon_{pts}x{pts}.png"))
        icons[pts * 2].save(os.path.join(ICONSET, f"icon_{pts}x{pts}@2x.png"))
    subprocess.run(["iconutil", "-c", "icns", ICONSET, "-o", ICNS], check=True)
    icons[1024].save(PNG_1024)
    print(f"menu bar icons: {MENUBAR_DIR}\napp icon: {ICNS}, {PNG_1024}")


if __name__ == "__main__":
    main()
