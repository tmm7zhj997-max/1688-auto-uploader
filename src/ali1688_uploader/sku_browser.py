from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .browser_automation import (
    BrowserOptions,
    SelectorProfile,
    _control_snapshot_script,
    persistent_context,
)


DEFAULT_SKU_EVIDENCE_DIR = Path("runtime/browser-sku-evidence")


def _load_normalized(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("标准化 SKU 文件必须是 JSON object")
    axes = payload.get("axes")
    rows = payload.get("rows")
    if not isinstance(axes, list) or not axes:
        raise ValueError("标准化 SKU 文件缺少 axes")
    if not isinstance(rows, list) or not rows:
        raise ValueError("标准化 SKU 文件缺少 rows")
    return payload


def _commit_spec_value(page: Any, selector: str, value: str) -> None:
    # 1688 spec inputs re-render after each committed value, so reacquire every time.
    locator = page.locator(selector).first
    locator.wait_for(state="visible")
    locator.scroll_into_view_if_needed()
    locator.click()
    locator.fill(value)
    locator.dispatch_event("input")
    locator.dispatch_event("change")
    locator.press("Enter")
    page.wait_for_timeout(450)


def _fill_axis(page: Any, selector: str, values: list[str]) -> list[str]:
    committed: list[str] = []
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        _commit_spec_value(page, selector, value)
        committed.append(value)
    return committed


def fill_sku_axes_and_capture(
    normalized_path: str | Path,
    *,
    url: str,
    profile_path: str | Path = "browser_profiles/1688-current.json",
    options: BrowserOptions | None = None,
    output_root: str | Path = DEFAULT_SKU_EVIDENCE_DIR,
) -> dict[str, Any]:
    if not url.strip():
        raise ValueError("必须提供真实 1688 发布页 URL")

    normalized = _load_normalized(normalized_path)
    axes = normalized["axes"]
    if len(axes) > 2:
        raise ValueError("当前 1688 页面使用旧版二维规格，本阶段最多支持 2 个变化规格轴")

    profile = SelectorProfile.load(profile_path)
    color_selector = profile.selectors.get("sku_color")
    size_selector = profile.selectors.get("sku_size")
    if not color_selector or not size_selector:
        raise ValueError("selector profile 必须配置 sku_color 和 sku_size")

    options = options or BrowserOptions.from_env()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(output_root) / stamp
    out.mkdir(parents=True, exist_ok=True)

    with persistent_context(options) as context:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(1800)

        axis1_values = [str(v) for v in axes[0].get("values", [])]
        axis2_values = [str(v) for v in axes[1].get("values", [])] if len(axes) > 1 else []

        axis1_committed = _fill_axis(page, color_selector, axis1_values)
        axis2_committed = _fill_axis(page, size_selector, axis2_values) if axis2_values else []

        page.wait_for_timeout(1800)
        sku_table = page.locator("#guid-skuTable")
        matrix_visible = False
        if sku_table.count():
            matrix_visible = sku_table.first.is_visible()

        controls = page.locator(
            "input, textarea, select, button, [role='button'], [contenteditable='true']"
        ).evaluate_all(_control_snapshot_script())
        (out / "controls.json").write_text(
            json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out / "page.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(out / "page.png"), full_page=True)

        result = {
            "source": str(normalized_path),
            "sku_count": normalized.get("sku_count", len(normalized.get("rows", []))),
            "axis1": axis1_committed,
            "axis2": axis2_committed,
            "common_specs": normalized.get("common_specs", []),
            "matrix_visible": matrix_visible,
            "output_dir": str(out),
            "screenshot": str(out / "page.png"),
            "controls": str(out / "controls.json"),
            "html": str(out / "page.html"),
            "status": "sku-axes-filled-not-submitted",
        }
        (out / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print("SKU 规格轴已填写，未提交商品。请在浏览器检查生成的 SKU 矩阵，完成后回终端按 Enter。")
        input()
        return result
