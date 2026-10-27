#!/usr/bin/env python3
"""Generate menu bar icon states from assets/menubar_icon@2x.png (pixel duck + shield).

protected : original colours (yellow duck, matte orange shield)
paused    : duck in grey, 55% opacity
alert     : shield recoloured to alert red (#DC2626), duck unchanged
"""
import os
import sys
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "assets", "menubar_icon@2x.png")
OUT = os.path.join(ROOT, "src", "duckyguard", "ui", "icons")
RED = (220, 38, 38)
GREY = (120, 113, 108)


def is_orange(p):
    r, g, b, a = p
    return a > 0 and r > 200 and 70 < g < 150 and b < 60


def variant(name, fn):
    im = Image.open(SRC).convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            px[x, y] = fn(px[x, y])
    im.save(os.path.join(OUT, f"menubar-{name}@2x.png"))
    im.resize((im.width // 2, im.height // 2), Image.NEAREST).save(os.path.join(OUT, f"menubar-{name}.png"))


def main():
    os.makedirs(OUT, exist_ok=True)
    variant("protected", lambda p: p)
    variant("alert", lambda p: (RED[0], RED[1], RED[2], p[3]) if is_orange(p) else p)

    def grey(p):
        r, g, b, a = p
        if a == 0:
            return p
        l = int(0.299 * r + 0.587 * g + 0.114 * b)
        l = int(l * 0.6 + 70)
        return (l, l, l, int(a * 0.55))
    variant("paused", grey)
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
