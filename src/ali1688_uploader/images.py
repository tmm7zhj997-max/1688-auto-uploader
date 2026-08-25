from __future__ import annotations

from pathlib import Path
import mimetypes


MAX_IMAGE_BYTES = 2 * 1024 * 1024
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".gif", ".bmp", ".png"}


def validate_image_file(path: str | Path) -> dict[str, object]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"不支持的图片格式 {suffix or '<none>'}；支持 JPG/JPEG/GIF/BMP/PNG"
        )

    size = path.stat().st_size
    if size <= 0:
        raise ValueError("图片文件为空")
    if size >= MAX_IMAGE_BYTES:
        raise ValueError("图片必须小于 2 MB")

    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return {
        "path": str(path),
        "name": path.name,
        "size_bytes": size,
        "mime_type": mime_type,
    }
