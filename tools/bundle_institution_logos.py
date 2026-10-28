"""Bundle the catalog's wallet, fintech and broker logos for account tiles (offline; nothing is fetched).

    python tools/bundle_institution_logos.py

For every row of lightning/accounts/institutions.csv that is not a bank and has an icon in
assets/institutions-logos/icons/<code>.png, it trims the white margin around the mark (a wordmark in a big white
square is unreadable at tile size), centres it on a square, shrinks it to 64 px and at most 8 KB, saves
lightning/ui/static/institutions/<code>.png and writes the file name into the CSV's `logo` column.
Banks keep the files made from their own 256 px icons. Needs Pillow.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
CSV_FILE = ROOT / "lightning" / "accounts" / "institutions.csv"
ICONS = ROOT / "assets" / "institutions-logos" / "icons"
OUT_DIR = ROOT / "lightning" / "ui" / "static" / "institutions"
SIZE, MAX_BYTES, MARGIN = 64, 8 * 1024, 0.08


def tile(path: Path) -> bytes | None:
    image = Image.open(path).convert("RGBA")
    flat = Image.new("RGBA", image.size, "white")
    flat.alpha_composite(image)
    flat = flat.convert("RGB")
    # what is not (near) white is the mark
    ink = ImageChops.difference(flat, Image.new("RGB", flat.size, "white")).convert("L").point(lambda v: 255 if v > 24 else 0)
    box = ink.getbbox() or (0, 0, *flat.size)
    mark = flat.crop(box)
    side = int(max(mark.size) * (1 + 2 * MARGIN))
    square = Image.new("RGB", (side, side), "white")
    square.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2))
    square = square.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    for colours in (256, 128, 64, 32):
        out = io.BytesIO()
        square.quantize(colours, method=Image.Quantize.MEDIANCUT).save(out, "PNG", optimize=True)
        if out.tell() <= MAX_BYTES:
            return out.getvalue()
    return None


def main() -> int:
    rows = list(csv.DictReader(CSV_FILE.open(encoding="utf-8", newline="")))
    done = 0
    for row in rows:
        icon = ICONS / f"{row['code']}.png"
        if row["kind"] == "bank" or not icon.exists():
            continue
        data = tile(icon)
        if data:
            (OUT_DIR / f"{row['code']}.png").write_bytes(data)
            row["logo"] = f"{row['code']}.png"
            done += 1
    with CSV_FILE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{done} logos bundled in {OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
