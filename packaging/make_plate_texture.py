"""Packs the plate's texture for the dashboard and writes src/duckyguard/ui/duck-texture.js.

Inputs (both in assets/):
  cyber-duck.png        red = engraving, alpha = silhouette
  cyber-duck-depth.png  monocular depth of the same picture (Depth Anything V2 Small, Apache-2.0), near = white

Output channels: red = engraving, green = depth (0 far .. 1 near, inside the silhouette),
blue = distance from the silhouette edge (0 at the edge .. 1 at 40 px in), alpha = silhouette.
Needs Pillow only.  Run:  python packaging/make_plate_texture.py
"""
import base64
import io
import os

from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZE, EDGE_PX = 512, 40.0


def edge_distance(mask):
    """Two-pass chamfer distance (3-4 weights) from every inside pixel to the silhouette edge, in pixels."""
    w, h = mask.size
    inside = [v > 127 for v in mask.tobytes()]
    big = 10 ** 6
    d = [big if v else 0 for v in inside]
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if not d[i]:
                continue
            best = d[i]
            if x: best = min(best, d[i - 1] + 3)
            if y:
                best = min(best, d[i - w] + 3)
                if x: best = min(best, d[i - w - 1] + 4)
                if x < w - 1: best = min(best, d[i - w + 1] + 4)
            d[i] = best
    for y in range(h - 1, -1, -1):
        for x in range(w - 1, -1, -1):
            i = y * w + x
            if not d[i]:
                continue
            best = d[i]
            if x < w - 1: best = min(best, d[i + 1] + 3)
            if y < h - 1:
                best = min(best, d[i + w] + 3)
                if x < w - 1: best = min(best, d[i + w + 1] + 4)
                if x: best = min(best, d[i + w - 1] + 4)
            d[i] = best
    return [v / 3.0 for v in d]


def main():
    art = Image.open(os.path.join(ROOT, "assets", "cyber-duck.png")).convert("RGBA").resize((SIZE, SIZE))
    depth = Image.open(os.path.join(ROOT, "assets", "cyber-duck-depth.png")).convert("L").resize((SIZE, SIZE), Image.LANCZOS)
    depth = depth.filter(ImageFilter.GaussianBlur(1.2))
    red, _, _, alpha = art.split()
    dist = edge_distance(alpha)
    dvals, avals = list(depth.tobytes()), list(alpha.tobytes())
    inside = sorted(v for v, a in zip(dvals, avals) if a > 127)
    lo, hi = inside[len(inside) // 100], inside[-1]                       # ignore the darkest 1% so the range is not set by a stray pixel
    green = Image.new("L", (SIZE, SIZE)); green.putdata([max(0, min(255, round((v - lo) * 255 / (hi - lo)))) if a > 127 else 0 for v, a in zip(dvals, avals)])
    blue = Image.new("L", (SIZE, SIZE)); blue.putdata([min(255, round(v * 255 / EDGE_PX)) for v in dist])
    out = Image.merge("RGBA", (red, green, blue, alpha))
    buf = io.BytesIO(); out.save(buf, "PNG", optimize=True)
    path = os.path.join(ROOT, "src", "duckyguard", "ui", "duck-texture.js")
    with open(path, "w") as f:
        f.write("// The plate's source image: red = engraving, green = depth, blue = distance from the edge, alpha = silhouette.\n")
        f.write("// Built by packaging/make_plate_texture.py. Depth estimated with Depth Anything V2 Small (Apache-2.0).\n")
        f.write('const DUCK_TEXTURE = "data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode() + '";\n')
    out.save(os.path.join(ROOT, "assets", "cyber-duck-plate.png"))
    print(f"wrote {path} ({len(buf.getvalue()) // 1024} KB png), depth range {lo}..{hi}")
    for name, (x, y) in {"eye": (.328, .336), "lens": (.617, .346), "bill tip": (.2, .68), "crest": (.52, .08)}.items():
        px = out.getpixel((int(x * SIZE), int(y * SIZE)))
        print(f"  {name:9s} depth {px[1] / 255:.2f} edge {px[2] / 255:.2f} alpha {px[3]}")


if __name__ == "__main__":
    main()
