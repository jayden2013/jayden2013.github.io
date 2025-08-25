#!/usr/bin/env python3
"""
watermark_repeat_hq.py — Repeated diagonal watermark with minimal quality loss.

- Preserves original format by default (auto)
- JPEG: quality (default 95), subsampling=0 (4:4:4), optional progressive
- PNG: lossless (set compress-level), preserves RGBA
- WebP: lossy Q or --lossless
- Preserves EXIF + ICC profile when available
"""

import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}

def load_font(font_path, fontsize):
    try:
        if font_path:
            return ImageFont.truetype(font_path, fontsize)
        return ImageFont.truetype("arial.ttf", fontsize)
    except Exception:
        return ImageFont.load_default()

def text_size(draw, text, font):
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    return r - l, b - t

def make_repeated_watermark(size, text, font, color_rgba, angle=35,
                            spacing_mult=1.3, stagger=True, shadow=True):
    w, h = size
    diag = int((w**2 + h**2) ** 0.5) + max(w, h)
    canvas = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    tw, th = text_size(draw, text, font)
    step_x = max(1, int(tw * spacing_mult))
    step_y = max(1, int(th * spacing_mult))

    y = 0
    row = 0
    while y < diag:
        x_offset = (step_x // 2) if (stagger and row % 2 == 1) else 0
        x = x_offset
        while x < diag:
            if shadow:
                draw.text((x + 2, y + 2), text, font=font,
                          fill=(0, 0, 0, max(0, color_rgba[3] - 30)))
            draw.text((x, y), text, font=font, fill=color_rgba)
            x += step_x
        y += step_y
        row += 1

    rotated = canvas.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    rw, rh = rotated.size
    left, top = (rw - w) // 2, (rh - h) // 2
    return rotated.crop((left, top, left + w, top + h))  # exact original size

def add_repeated_watermark(im, *, text="carsandcollectibles.com", angle=35,
                           opacity=80, font_path=None, color=(255, 255, 255),
                           size_ratio=0.08, spacing=1.3, stagger=True, shadow=True):
    w, h = im.size
    fontsize = max(12, int(min(w, h) * size_ratio))
    font = load_font(font_path, fontsize)
    layer = make_repeated_watermark((w, h), text, font,
                                    (*color, int(max(0, min(255, opacity)))),
                                    angle=angle, spacing_mult=spacing,
                                    stagger=stagger, shadow=shadow)
    base = im.convert("RGBA") if im.mode != "RGBA" else im
    return Image.alpha_composite(base, layer)

def save_with_quality(img_rgba, src_img, out_path, fmt, *, quality, progressive, lossless, compress_level):
    """Save in chosen format with high-quality settings; preserve EXIF/ICC when possible."""
    exif = src_img.info.get("exif")
    icc = src_img.info.get("icc_profile")

    if fmt == "JPEG":
        # JPEG requires RGB
        img = img_rgba.convert("RGB")
        img.save(
            out_path,
            "JPEG",
            quality=quality,              # high quality
            subsampling=0,                # 4:4:4 (no chroma subsampling)
            progressive=progressive,      # off by default unless enabled
            optimize=False,               # avoid extra recompress heuristics
            exif=exif if exif else None,
            icc_profile=icc if icc else None,
        )
    elif fmt == "PNG":
        # PNG is lossless
        img = img_rgba  # keep RGBA if present
        img.save(
            out_path,
            "PNG",
            compress_level=compress_level,  # 0 (bigger/faster) .. 9 (smaller/slower)
            optimize=False,
        )
    elif fmt == "WEBP":
        img = img_rgba
        if lossless:
            img.save(out_path, "WEBP", lossless=True, quality=100, method=6)
        else:
            img.save(out_path, "WEBP", quality=quality, method=6)  # high quality
    else:
        # Fallback: keep original mode/format best-effort
        img = img_rgba
        img.save(out_path, fmt)

def decide_output_format(input_suffix, mode, requested):
    if requested != "auto":
        return requested.upper()
    # Keep original if supported; if TIFF/BMP, prefer PNG to avoid JPEG re-encode
    s = input_suffix.lower()
    if s in (".jpg", ".jpeg"):
        return "JPEG"
    if s == ".png":
        return "PNG"
    if s == ".webp":
        return "WEBP"
    # If image has alpha, prefer PNG
    if mode in ("RGBA", "LA", "P"):
        return "PNG"
    return "JPEG"

def process_one(in_path: Path, out_path: Path, args):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(in_path) as im:
        im = ImageOps.exif_transpose(im)
        result = add_repeated_watermark(
            im,
            text=args.text,
            angle=args.angle,
            opacity=args.opacity,
            font_path=args.font,
            color=tuple(args.color),
            size_ratio=args.size_ratio,
            spacing=args.spacing,
            stagger=not args.no_stagger,
            shadow=not args.no_shadow
        )
        fmt = decide_output_format(in_path.suffix, result.mode, args.format)
        out_file = out_path.with_suffix({
            "JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"
        }.get(fmt, in_path.suffix))
        save_with_quality(
            result, im, out_file, fmt,
            quality=args.quality,
            progressive=args.progressive,
            lossless=args.lossless,
            compress_level=args.png_compress
        )
        print(f"[OK] {in_path} -> {out_file}")

def iter_files(root: Path, recursive=True):
    it = root.rglob("*") if recursive else root.glob("*")
    for p in it:
        if p.is_file() and p.suffix.lower() in SUPPORTED:
            yield p

def main():
    ap = argparse.ArgumentParser(description="Repeated diagonal watermark with minimal quality loss.")
    ap.add_argument("input", type=Path, help="Input file or folder")
    ap.add_argument("output", type=Path, help="Output file or folder")
    ap.add_argument("--text", default="carsandcollectibles.com")
    ap.add_argument("--angle", type=float, default=35.0)
    ap.add_argument("--opacity", type=int, default=80)
    ap.add_argument("--color", type=int, nargs=3, default=(255, 255, 255))
    ap.add_argument("--font", type=str, default=None)
    ap.add_argument("--size-ratio", type=float, default=0.08, help="Font size as fraction of min(image side)")
    ap.add_argument("--spacing", type=float, default=1.3, help="Spacing in multiples of text size (>=1.0 avoids overlap)")
    ap.add_argument("--format", choices=["auto", "jpeg", "png", "webp"], default="auto",
                    help="Output format. 'auto' keeps original or best choice.")
    ap.add_argument("--quality", type=int, default=95, help="JPEG/WebP quality (ignored for lossless PNG/WebP)")
    ap.add_argument("--progressive", action="store_true", help="Progressive JPEG")
    ap.add_argument("--lossless", action="store_true", help="Lossless WebP when --format webp or auto->webp")
    ap.add_argument("--png-compress", type=int, default=6, help="PNG compress level 0..9 (lossless)")
    ap.add_argument("--no-stagger", action="store_true")
    ap.add_argument("--no-shadow", action="store_true")
    ap.add_argument("--no-recursive", action="store_true")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()

    in_path, out_path = args.input.resolve(), args.output.resolve()

    if args.preview:
        process_one(in_path, out_path, args)
        return

    out_path.mkdir(parents=True, exist_ok=True)
    for f in iter_files(in_path, recursive=not args.no_recursive):
        rel = f.relative_to(in_path) if in_path.is_dir() else Path(f.name)
        out_f = out_path / rel
        if args.skip_existing and (out_f.with_suffix(".jpg").exists()
                                   or out_f.with_suffix(".png").exists()
                                   or out_f.with_suffix(".webp").exists()):
            print(f"[SKIP] {rel}")
            continue
        try:
            process_one(f, out_f, args)
        except Exception as e:
            print(f"[ERR] {f} — {e}")

if __name__ == "__main__":
    main()
