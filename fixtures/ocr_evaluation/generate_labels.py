"""Create deterministic, synthetic labels for live OCR evaluation.

Run from the repository root:
    uv run --project backend python fixtures/ocr_evaluation/generate_labels.py

The source texture is decorative only. Every word used for comparison is rendered
here so that fixtures remain reproducible and do not inherit text-generation errors.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WARNING = (
    "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT "
    "DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. "
    "(2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR "
    "OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
)

ROOT = Path(__file__).parent
TEXTURE = ROOT / "paper-texture.png"
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def centered(draw: ImageDraw.ImageDraw, text: str, y: int, text_font: ImageFont.FreeTypeFont) -> None:
    bounds = draw.textbbox((0, 0), text, font=text_font)
    draw.text(((1536 - (bounds[2] - bounds[0])) / 2, y), text, fill="#102a43", font=text_font)


def wrapped(draw: ImageDraw.ImageDraw, text: str, y: int, max_width: int, text_font: ImageFont.FreeTypeFont) -> None:
    words, lines, current = text.split(), [], []
    for word in words:
        candidate = " ".join([*current, word])
        if draw.textlength(candidate, font=text_font) <= max_width:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    for line in lines:
        centered(draw, line, y, text_font)
        y += text_font.size + 12


def label(
    name: str,
    *,
    brand: str,
    class_type: str,
    alcohol: str,
    business: str,
    city: str,
    warning: str = WARNING,
    blur_warning: bool = False,
) -> None:
    background = Image.open(TEXTURE).convert("RGB").resize((1536, 2048))
    draw = ImageDraw.Draw(background)
    draw.rounded_rectangle((56, 56, 1480, 1992), radius=28, outline="#102a43", width=14)
    draw.rounded_rectangle((82, 82, 1454, 1966), radius=18, outline="#b7791f", width=5)
    centered(draw, brand, 210, font(BOLD, 82))
    centered(draw, class_type, 440, font(BOLD, 46))
    centered(draw, alcohol, 590, font(SERIF, 42))
    centered(draw, "750 mL", 670, font(SERIF, 42))
    centered(draw, business, 850, font(BOLD, 38))
    centered(draw, city, 915, font(SERIF, 38))
    warning_layer = Image.new("RGBA", background.size, (0, 0, 0, 0))
    warning_draw = ImageDraw.Draw(warning_layer)
    wrapped(warning_draw, warning, 1230, 1240, font(BOLD, 27))
    if blur_warning:
        warning_layer = warning_layer.filter(ImageFilter.GaussianBlur(radius=5))
    background.paste(warning_layer, mask=warning_layer)
    background.save(ROOT / name, format="PNG", optimize=True)


def main() -> None:
    label(
        "01-clear-old-tom.png",
        brand="OLD TOM DISTILLERY",
        class_type="KENTUCKY STRAIGHT BOURBON WHISKEY",
        alcohol="45% ALC./VOL. (90 PROOF)",
        business="EXAMPLE DISTILLING COMPANY",
        city="FRANKFORT, KY, USA",
    )
    label(
        "02-clear-meadowlark.png",
        brand="MEADOWLARK RYE",
        class_type="STRAIGHT RYE WHISKEY",
        alcohol="47% ALC./VOL. (94 PROOF)",
        business="MEADOWLARK SPIRITS",
        city="LEXINGTON, KY, USA",
    )
    label(
        "03-brand-mismatch.png",
        brand="STONE THROW",
        class_type="KENTUCKY STRAIGHT BOURBON WHISKEY",
        alcohol="45% ALC./VOL. (90 PROOF)",
        business="EXAMPLE DISTILLING COMPANY",
        city="FRANKFORT, KY, USA",
    )
    label(
        "04-abv-mismatch.png",
        brand="RIVERBEND BOURBON",
        class_type="KENTUCKY STRAIGHT BOURBON WHISKEY",
        alcohol="44% ALC./VOL. (88 PROOF)",
        business="EXAMPLE DISTILLING COMPANY",
        city="FRANKFORT, KY, USA",
    )
    label(
        "05-warning-incomplete.png",
        brand="HARVEST MOON SPIRITS",
        class_type="KENTUCKY STRAIGHT BOURBON WHISKEY",
        alcohol="45% ALC./VOL. (90 PROOF)",
        business="EXAMPLE DISTILLING COMPANY",
        city="FRANKFORT, KY, USA",
        warning=WARNING[:156],
    )
    label(
        "06-warning-ambiguous.png",
        brand="CEDAR RIDGE WHISKEY",
        class_type="KENTUCKY STRAIGHT BOURBON WHISKEY",
        alcohol="45% ALC./VOL. (90 PROOF)",
        business="EXAMPLE DISTILLING COMPANY",
        city="FRANKFORT, KY, USA",
        blur_warning=True,
    )


if __name__ == "__main__":
    main()
