from __future__ import annotations

from pathlib import Path
from typing import Any

from . import sku_matrix_logistics as _base
from . import sku_matrix_logistics_weight_g as _weight_g  # noqa: F401 - installs the weight-only logistics patch

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif"}
MAIN_DIR_NAMES = ("主图", "商品主图", "main", "main_images")
DETAIL_DIR_NAMES = ("详情图", "详情", "商品详情", "detail", "detail_images")

_WEIGHT_ONLY_FILL = _base._fill_logistics_weight_only
_ACTIVE_ASSET_DIR: Path | None = None
_ACTIVE_MAIN_IMAGE_DIR: Path | None = None
_ACTIVE_DETAIL_IMAGE_DIR: Path | None = None


def _natural_key(path: Path) -> list[object]:
    import re

    parts: list[object] = []
    for part in re.split(r"(\d+)", path.stem):
        if part.isdigit():
            parts.append(int(part))
        else:
            parts.append(part.lower())
    parts.append(path.suffix.lower())
    return parts


def _resolve_dir(root: Path | None, explicit: Path | None, names: tuple[str, ...]) -> Path | None:
    if explicit:
        return explicit
    if not root:
        return None
    for name in names:
        candidate = root / name
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _scan_images(folder: Path | None, *, limit: int | None = None) -> list[str]:
    if not folder:
        return []
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"图片文件夹不存在: {folder}")
    files = [
        item
        for item in folder.iterdir()
        if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS
    ]
    files.sort(key=_natural_key)
    if limit is not None:
        files = files[:limit]
    return [str(item.resolve()) for item in files]


def _visible_upload_points(page: Any, block_selector: str) -> list[Any]:
    block = page.locator(block_selector)
    if not block.count():
        return []
    block.first.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
    page.wait_for_timeout(500)

    selectors = [
        "text=添加图片",
        "text=上传图片",
        "button:has-text('添加图片')",
        "button:has-text('上传图片')",
        ".picture-cover-content:has-text('添加图片')",
        ".module-picture-cover-wrapper:has-text('添加图片')",
        "[role='button']:has-text('添加图片')",
    ]
    points: list[Any] = []
    for selector in selectors:
        locator = block.locator(selector)
        for index in range(locator.count()):
            item = locator.nth(index)
            try:
                if item.is_visible():
                    points.append(item)
            except Exception:
                continue
    return points


def _set_file_input_if_present(page: Any, block_selector: str, files: list[str]) -> bool:
    block = page.locator(block_selector)
    if not block.count():
        return False
    file_inputs = block.locator("input[type='file']")
    for index in range(file_inputs.count()):
        item = file_inputs.nth(index)
        try:
            item.set_input_files(files)
            return True
        except Exception:
            continue
    return False


def _wait_upload_settle(page: Any, *, seconds: float = 8.0) -> None:
    # 图片上传涉及本地文件、1688 图片空间、AI 审核入口；不要等网络完全 idle，给页面一段稳定时间即可。
    page.wait_for_timeout(int(seconds * 1000))


def _upload_files_to_block(
    page: Any,
    *,
    block_selector: str,
    files: list[str],
    label: str,
    limit: int | None = None,
    one_by_one: bool = False,
) -> dict[str, Any]:
    if limit is not None:
        files = files[:limit]
    result: dict[str, Any] = {
        "label": label,
        "block_selector": block_selector,
        "requested": len(files),
        "files": files,
        "uploaded_attempted": 0,
        "strategy": None,
        "errors": [],
    }
    if not files:
        result["strategy"] = "skipped-no-files"
        return result

    block = page.locator(block_selector)
    if not block.count():
        result["strategy"] = "block-not-found"
        result["errors"].append(f"未找到区块: {block_selector}")
        return result

    block.first.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
    page.wait_for_timeout(600)

    # 先尝试隐藏 file input。部分 1688 组件会把 input 放在图片区块内部。
    try:
        if _set_file_input_if_present(page, block_selector, files):
            result["strategy"] = "input[type=file]"
            result["uploaded_attempted"] = len(files)
            _wait_upload_settle(page)
            return result
    except Exception as exc:
        result["errors"].append(f"file_input:{exc}")

    points = _visible_upload_points(page, block_selector)
    if not points:
        result["strategy"] = "upload-point-not-found"
        result["errors"].append("未找到可见的添加图片/上传图片按钮")
        return result

    def upload_once(point: Any, selected_files: list[str]) -> bool:
        try:
            with page.expect_file_chooser(timeout=8000) as chooser_info:
                point.click(timeout=5000)
            chooser = chooser_info.value
            chooser.set_files(selected_files)
            return True
        except Exception as exc:
            result["errors"].append(f"file_chooser:{exc}")
            return False

    if one_by_one:
        result["strategy"] = "filechooser-one-by-one"
        for index, file_path in enumerate(files):
            point = points[min(index, len(points) - 1)]
            if upload_once(point, [file_path]):
                result["uploaded_attempted"] += 1
                _wait_upload_settle(page, seconds=3.5)
    else:
        result["strategy"] = "filechooser-batch"
        if upload_once(points[0], files):
            result["uploaded_attempted"] = len(files)
            _wait_upload_settle(page)

    return result


def _upload_asset_images(page: Any) -> dict[str, Any]:
    asset_root = _ACTIVE_ASSET_DIR
    main_dir = _resolve_dir(asset_root, _ACTIVE_MAIN_IMAGE_DIR, MAIN_DIR_NAMES)
    detail_dir = _resolve_dir(asset_root, _ACTIVE_DETAIL_IMAGE_DIR, DETAIL_DIR_NAMES)

    main_files = _scan_images(main_dir, limit=5)
    detail_files = _scan_images(detail_dir)

    result: dict[str, Any] = {
        "asset_dir": str(asset_root) if asset_root else None,
        "main_dir": str(main_dir) if main_dir else None,
        "detail_dir": str(detail_dir) if detail_dir else None,
        "main_count": len(main_files),
        "detail_count": len(detail_files),
        "main": None,
        "detail": None,
    }

    if not asset_root and not main_dir and not detail_dir:
        result["status"] = "skipped-no-asset-dir"
        return result

    if main_files:
        result["main"] = _upload_files_to_block(
            page,
            block_selector="#guid-primaryPicture",
            files=main_files,
            label="商品主图",
            limit=5,
            one_by_one=False,
        )
    else:
        result["main"] = {"label": "商品主图", "strategy": "skipped-no-files", "files": []}

    if detail_files:
        # 新版详情区通常是 guid-description；保留 blockDescription 作为兜底。
        detail_result = _upload_files_to_block(
            page,
            block_selector="#guid-description",
            files=detail_files,
            label="详情图",
            one_by_one=False,
        )
        if detail_result.get("strategy") == "block-not-found":
            detail_result = _upload_files_to_block(
                page,
                block_selector="#guid-blockDescription",
                files=detail_files,
                label="详情图",
                one_by_one=False,
            )
        result["detail"] = detail_result
    else:
        result["detail"] = {"label": "详情图", "strategy": "skipped-no-files", "files": []}

    result["status"] = "asset-image-upload-attempted-not-submitted"
    return result


def _fill_logistics_then_assets(page: Any, *, weight_text: str = _weight_g.LOGISTICS_WEIGHT_TEXT) -> dict[str, Any]:
    logistics = _WEIGHT_ONLY_FILL(page, weight_text=weight_text)
    assets = _upload_asset_images(page)
    if isinstance(logistics, dict):
        return {**logistics, "assets": assets}
    return {"logistics": logistics, "assets": assets}


_base._fill_logistics_weight_only = _fill_logistics_then_assets


def fill_sku_prices_and_stock(
    normalized_path: str | Path,
    *,
    url: str,
    profile_path: str | Path = "browser_profiles/1688-current.json",
    fixed_stock: int = 1000,
    logistics_weight: int = 1000,
    asset_dir: str | Path | None = None,
    main_image_dir: str | Path | None = None,
    detail_image_dir: str | Path | None = None,
    options: Any | None = None,
    output_root: str | Path = _base.DEFAULT_SKU_EVIDENCE_DIR,
) -> dict[str, Any]:
    global _ACTIVE_ASSET_DIR, _ACTIVE_MAIN_IMAGE_DIR, _ACTIVE_DETAIL_IMAGE_DIR

    _ACTIVE_ASSET_DIR = Path(asset_dir) if asset_dir else None
    _ACTIVE_MAIN_IMAGE_DIR = Path(main_image_dir) if main_image_dir else None
    _ACTIVE_DETAIL_IMAGE_DIR = Path(detail_image_dir) if detail_image_dir else None
    try:
        return _base.fill_sku_prices_and_stock(
            normalized_path,
            url=url,
            profile_path=profile_path,
            fixed_stock=fixed_stock,
            logistics_weight=logistics_weight,
            options=options,
            output_root=output_root,
        )
    finally:
        _ACTIVE_ASSET_DIR = None
        _ACTIVE_MAIN_IMAGE_DIR = None
        _ACTIVE_DETAIL_IMAGE_DIR = None
