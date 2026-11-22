"""Draw the ZENE Bot logo with Pillow — no paid image service needed."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SCALE = 4
SIZE = 512 * SCALE
OUT = Path(__file__).resolve().parent.parent / "docs" / "logo.png"


def font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in ("arialbd.ttf", "segoeuib.ttf", "calibrib.ttf"):
        path = Path("C:/Windows/Fonts") / candidate
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def main() -> None:
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # Vertical navy -> blurple gradient.
    gradient = Image.new("RGB", (SIZE, SIZE))
    gd = ImageDraw.Draw(gradient)
    for y in range(SIZE):
        t = y / SIZE
        gd.line(
            [(0, y), (SIZE, y)],
            fill=(int(15 + 30 * t), int(23 + 40 * t), int(42 + 110 * t)),
        )

    rounded = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(rounded).rounded_rectangle(
        (0, 0, SIZE - 1, SIZE - 1), radius=112 * SCALE, fill=255
    )
    canvas.paste(gradient, (0, 0), rounded)

    # Soft blurple glow ring.
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.rounded_rectangle(
        (26 * SCALE, 26 * SCALE, SIZE - 26 * SCALE, SIZE - 26 * SCALE),
        radius=94 * SCALE,
        outline=(88, 101, 242, 210),
        width=10 * SCALE,
    )
    glow = glow.filter(ImageFilter.GaussianBlur(18 * SCALE))
    canvas = Image.alpha_composite(glow, canvas)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (26 * SCALE, 26 * SCALE, SIZE - 26 * SCALE, SIZE - 26 * SCALE),
        radius=94 * SCALE,
        outline=(88, 101, 242, 255),
        width=5 * SCALE,
    )

    # Fox ears peeking over the badge.
    white = (226, 232, 240, 255)
    draw.polygon(
        [
            (146 * SCALE, 168 * SCALE),
            (176 * SCALE, 78 * SCALE),
            (236 * SCALE, 154 * SCALE),
        ],
        fill=white,
    )
    draw.polygon(
        [
            (366 * SCALE, 168 * SCALE),
            (336 * SCALE, 78 * SCALE),
            (276 * SCALE, 154 * SCALE),
        ],
        fill=white,
    )

    # Big stylized Z with a blurple shadow.
    face_font = font(300 * SCALE)
    text = "Z"
    box = draw.textbbox((0, 0), text, font=face_font)
    tw, th = box[2] - box[0], box[3] - box[1]
    x = (SIZE - tw) / 2 - box[0]
    y = (SIZE - th) / 2 - box[1] - 12 * SCALE
    draw.text((x + 8 * SCALE, y + 8 * SCALE), text, font=face_font, fill=(88, 101, 242, 255))
    draw.text((x, y), text, font=face_font, fill=white)

    # Three small status dots at the bottom.
    for index, color in enumerate(((34, 197, 94, 255), (96, 165, 250, 255), (245, 158, 11, 255))):
        cx = (208 + index * 48) * SCALE
        cy = 408 * SCALE
        r = 9 * SCALE
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)

    final = canvas.resize((512, 512), Image.Resampling.LANCZOS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    final.save(OUT, optimize=True)
    print("saved", OUT)


if __name__ == "__main__":
    main()
