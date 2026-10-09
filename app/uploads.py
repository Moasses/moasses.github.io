"""Safe handling of uploaded files.

Images are fully decoded and re-encoded with Pillow: this removes metadata
(GPS location in photos!), embedded payloads and malformed data that could
target image parsers. SVG is deliberately NOT accepted, because an SVG can
contain JavaScript. PDFs are accepted only for the CV and only if the file
really starts with a PDF header.
"""
from __future__ import annotations

import io
import secrets
from pathlib import Path

from PIL import Image, ImageOps

from .content import ValidationError

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_SIDE = 2400
Image.MAX_IMAGE_PIXELS = 40_000_000          # decompression-bomb guard

IMAGE_FORMATS = {"PNG", "JPEG", "WEBP"}
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}


def _read_limited(stream, limit: int) -> bytes:  # type: ignore[no-untyped-def]
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValidationError(f"File too large (max {limit // (1024 * 1024)} MB).")
    if not data:
        raise ValidationError("The file is empty.")
    return data


def save_upload(file_storage, uploads_dir: Path) -> str:  # type: ignore[no-untyped-def]
    """Validate + store an upload. Returns the new random file name."""
    original = (file_storage.filename or "").lower()
    ext = Path(original).suffix
    if ext not in ALLOWED_EXT:
        raise ValidationError("Only PNG, JPG, WEBP images and PDF files are allowed.")

    if ext == ".pdf":
        data = _read_limited(file_storage.stream, MAX_PDF_BYTES)
        if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
            raise ValidationError("This is not a valid PDF file.")
        name = secrets.token_hex(8) + ".pdf"
        (uploads_dir / name).write_bytes(data)
        return name

    data = _read_limited(file_storage.stream, MAX_IMAGE_BYTES)
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
        if fmt not in IMAGE_FORMATS:
            raise ValidationError("Unsupported image format.")
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "A" in img.getbands() or img.mode == "P" else "RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            out = io.BytesIO()
            if fmt == "JPEG":
                img.convert("RGB").save(out, "WEBP", quality=88, method=4)
            else:
                img.save(out, "WEBP", lossless=True, method=4)
    except ValidationError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError, SyntaxError):
        raise ValidationError("The image could not be read (corrupted or unsupported).") from None
    name = secrets.token_hex(8) + ".webp"
    (uploads_dir / name).write_bytes(out.getvalue())
    return name
