from __future__ import annotations

from math import comb
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SCALE = 4
SIZE = 256


def bezier(points: tuple[tuple[float, float], ...], steps: int = 180):
    degree = len(points) - 1
    for index in range(steps + 1):
        t = index / steps
        x = sum(comb(degree, i) * (1 - t) ** (degree - i) * t**i * point[0] for i, point in enumerate(points))
        y = sum(comb(degree, i) * (1 - t) ** (degree - i) * t**i * point[1] for i, point in enumerate(points))
        yield round(x * SCALE), round(y * SCALE)


def color_at(t: float) -> tuple[int, int, int, int]:
    stops = ((0.0, (113, 226, 220)), (0.53, (166, 200, 255)), (1.0, (192, 164, 255)))
    for (lo, a), (hi, b) in zip(stops, stops[1:]):
        if lo <= t <= hi:
            f = (t - lo) / (hi - lo)
            return tuple(round(x + (y - x) * f) for x, y in zip(a, b)) + (255,)
    return (*stops[-1][1], 255)


def gradient_line(draw: ImageDraw.ImageDraw, points, width: int, opacity: int = 255) -> None:
    for index, (start, end) in enumerate(zip(points, points[1:])):
        color = color_at(index / max(1, len(points) - 2))
        if opacity != 255:
            color = (*color[:3], opacity)
        draw.line((start, end), fill=color, width=width, joint="curve")


def render() -> Image.Image:
    side = SIZE * SCALE
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, side - 1, side - 1), radius=58 * SCALE, fill="#0b1220")

    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((42 * SCALE, 42 * SCALE, 214 * SCALE, 214 * SCALE), fill=(113, 226, 220, 52))
    glow = glow.filter(ImageFilter.GaussianBlur(34 * SCALE))
    image.alpha_composite(glow)
    draw = ImageDraw.Draw(image)

    paths = (
        ((59, 66), (89, 68), (99, 96), (128, 128), (157, 160), (169, 186), (200, 190)),
        ((197, 62), (165, 67), (154, 95), (128, 128), (102, 161), (89, 187), (59, 194)),
    )
    for index, path in enumerate(paths):
        pts = list(bezier(path))
        draw.line(
            pts,
            fill=(113, 226, 220, 255) if index == 0 else (192, 164, 255, 230),
            width=8 * SCALE,
            joint="curve",
        )

    spurs = (
        ((59, 66), (42, 52)), ((59, 66), (57, 89)),
        ((197, 62), (214, 49)), ((197, 62), (200, 85)),
        ((59, 194), (42, 207)), ((59, 194), (57, 171)),
        ((200, 190), (217, 204)), ((200, 190), (203, 167)),
    )
    for start, end in spurs:
        draw.line((start[0] * SCALE, start[1] * SCALE, end[0] * SCALE, end[1] * SCALE), fill=(166, 200, 255, 166), width=5 * SCALE)

    for x, y in ((59, 66), (197, 62), (59, 194), (200, 190)):
        radius = 10 * SCALE
        draw.ellipse((x * SCALE - radius, y * SCALE - radius, x * SCALE + radius, y * SCALE + radius), fill="#0b1220", outline="#e9f3ff", width=5 * SCALE)
    draw.ellipse((112 * SCALE, 112 * SCALE, 144 * SCALE, 144 * SCALE), fill="#0b1220", outline="#f4fbff", width=6 * SCALE)
    draw.ellipse((122 * SCALE, 122 * SCALE, 134 * SCALE, 134 * SCALE), fill="#71e2dc")
    return image.resize((512, 512), Image.Resampling.LANCZOS)


if __name__ == "__main__":
    mark = render()
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "desktop/melodex/assets").mkdir(exist_ok=True)
    mark.save(ROOT / "assets/icon.png")
    mark.resize((256, 256), Image.Resampling.LANCZOS).save(ROOT / "assets/icon.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
    mark.save(ROOT / "desktop/melodex/assets/chiasm-mark.png")
    for density, edge in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
        target = ROOT / f"android/app/src/main/res/mipmap-{density}/ic_launcher.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        mark.resize((edge, edge), Image.Resampling.LANCZOS).save(target)
