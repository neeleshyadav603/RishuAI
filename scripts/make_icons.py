"""Draw the Rishu app icon (the orb) and write every icon file the platforms need.

Run from the repo root:  python scripts/make_icons.py
Needs Pillow and numpy (development machines only; nothing here ships in the app).
The icon is original artwork drawn by this script: no third-party assets.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ANDROID_RES = ROOT / "app" / "android" / "app" / "src" / "main" / "res"
WINDOWS_ICON = ROOT / "app" / "windows" / "runner" / "resources" / "app_icon.ico"
BRAND = ROOT / "docs" / "assets"

SIZE = 1024
BACKGROUND_TOP = (22, 20, 48)
BACKGROUND_BOTTOM = (8, 8, 18)
ANDROID_BACKGROUND = "#0D0C1D"


def _lerp(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
    return a + (b - a) * t[..., None]


def orb(size: int = SIZE, scale: float = 1.0) -> Image.Image:
    """The orb on a transparent canvas. ``scale`` shrinks it inside the canvas."""
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float64)
    cx = cy = size / 2
    radius = size * 0.27 * scale
    # Soft glow around the core.
    dist = np.hypot(xs - cx, ys - cy)
    glow_alpha = np.clip(1.0 - dist / (radius * 1.75), 0.0, 1.0) ** 2.2 * 0.75
    canvas = np.zeros((size, size, 4), dtype=np.float64)
    canvas[..., 0], canvas[..., 1], canvas[..., 2] = 124, 108, 240
    canvas[..., 3] = glow_alpha * 255
    image = Image.fromarray(canvas.astype(np.uint8), "RGBA")

    # Rings behind and in front of the core (drawn large, then smoothed).
    def ring_layer(angle: float, width_ratio: float, height_ratio: float, alpha: int) -> Image.Image:
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        w, h = radius * width_ratio, radius * height_ratio
        draw.ellipse(
            [cx - w, cy - h, cx + w, cy + h],
            outline=(200, 190, 255, alpha),
            width=max(2, int(size * 0.012 * scale)),
        )
        return layer.rotate(angle, resample=Image.BICUBIC, center=(cx, cy))

    for angle, alpha in ((-28, 150), (32, 110)):
        image = Image.alpha_composite(image, ring_layer(angle, 1.62, 0.62, alpha))

    # The core: a sphere lit from the upper left.
    light_x, light_y = cx - radius * 0.35, cy - radius * 0.42
    t = np.clip(np.hypot(xs - light_x, ys - light_y) / (radius * 1.45), 0.0, 1.0)
    inner = np.array([226.0, 220.0, 255.0])
    middle = np.array([124.0, 108.0, 240.0])
    outer = np.array([52.0, 36.0, 150.0])
    half = np.clip(t * 2, 0, 1)
    rest = np.clip(t * 2 - 1, 0, 1)
    colour = np.where((t < 0.5)[..., None], _lerp(inner, middle, half), _lerp(middle, outer, rest))
    edge = np.clip((radius - dist) / (size * 0.004), 0.0, 1.0)  # anti-aliased edge
    core = np.dstack([colour, edge * 255]).astype(np.uint8)
    image = Image.alpha_composite(image, Image.fromarray(core, "RGBA"))

    # The front half of one ring passes over the core.
    front = ring_layer(-28, 1.62, 0.62, 210)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rectangle([0, cy, size, size], fill=255)
    mask = mask.rotate(-28, resample=Image.BICUBIC, center=(cx, cy))
    front.putalpha(Image.composite(front.getchannel("A"), Image.new("L", (size, size), 0), mask))
    image = Image.alpha_composite(image, front)
    return image.filter(ImageFilter.GaussianBlur(size * 0.0012))


def tile(size: int = SIZE) -> Image.Image:
    """Full icon: the orb on a dark rounded square."""
    ys = np.linspace(0.0, 1.0, size)[:, None].repeat(size, axis=1)
    gradient = _lerp(np.array(BACKGROUND_TOP, float), np.array(BACKGROUND_BOTTOM, float), ys)
    background = Image.fromarray(gradient.astype(np.uint8), "RGB").convert("RGBA")
    mask = Image.new("L", (size * 2, size * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size * 2 - 1, size * 2 - 1], radius=int(size * 2 * 0.225), fill=255
    )
    background.putalpha(mask.resize((size, size), Image.LANCZOS))
    return Image.alpha_composite(background, orb(size, scale=1.04))


def main() -> None:
    icon = tile()
    foreground = orb(SIZE, scale=0.86)  # stays inside the adaptive-icon safe zone

    BRAND.mkdir(parents=True, exist_ok=True)
    icon.resize((512, 512), Image.LANCZOS).save(BRAND / "rishu_icon.png", optimize=True)

    WINDOWS_ICON.parent.mkdir(parents=True, exist_ok=True)
    icon.save(WINDOWS_ICON, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])

    legacy = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for density, px in legacy.items():
        folder = ANDROID_RES / f"mipmap-{density}"
        folder.mkdir(parents=True, exist_ok=True)
        icon.resize((px, px), Image.LANCZOS).save(folder / "ic_launcher.png", optimize=True)
        adaptive = px * 108 // 48
        foreground.resize((adaptive, adaptive), Image.LANCZOS).save(
            folder / "ic_launcher_foreground.png", optimize=True
        )

    anydpi = ANDROID_RES / "mipmap-anydpi-v26"
    anydpi.mkdir(parents=True, exist_ok=True)
    (anydpi / "ic_launcher.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@color/ic_launcher_background"/>\n'
        '    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>\n'
        "</adaptive-icon>\n",
        encoding="utf-8",
    )
    (ANDROID_RES / "values" / "colors.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n"
        f'    <color name="ic_launcher_background">{ANDROID_BACKGROUND}</color>\n'
        f'    <color name="launch_background">{ANDROID_BACKGROUND}</color>\n'
        "</resources>\n",
        encoding="utf-8",
    )
    print("icons written")


if __name__ == "__main__":
    main()
