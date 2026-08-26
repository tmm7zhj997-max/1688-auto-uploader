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


def _axis_state(page: Any, selector: str) -> list[dict[str, Any]]:
    return page.locator(selector).evaluate_all(
        """
        (inputs) => inputs.map((input) => {
          const item = input.closest('.value-select-item');
          const rect = input.getBoundingClientRect();
          return {
            value: input.value || '',
            resident: !!(item && item.classList.contains('resident')),
            visible: !!(rect.width || rect.height) && getComputedStyle(input).visibility !== 'hidden'
          };
        })
        """
    )


def _committed_values(page: Any, selector: str) -> list[str]:
    return [
        str(item["value"])
        for item in _axis_state(page, selector)
        if item.get("visible") and not item.get("resident") and str(item.get("value") or "").strip()
    ]


def _resident_input(page: Any, selector: str) -> Any:
    candidates = page.locator(selector)
    count = candidates.count()
    for index in range(count - 1, -1, -1):
        locator = candidates.nth(index)
        if not locator.is_visible():
            continue
        value = locator.input_value().strip()
        resident = locator.evaluate(
            "el => !!(el.closest('.value-select-item') && el.closest('.value-select-item').classList.contains('resident'))"
        )
        if resident and not value:
            return locator
    raise RuntimeError(f"找不到可写入的空白 resident 规格输入框: {selector}")


def _commit_spec_value(page: Any, selector: str, value: str) -> None:
    before = set(_committed_values(page, selector))
    locator = _resident_input(page, selector)
    locator.scroll_into_view_if_needed()
    locator.click()
    locator.fill(value)
    locator.dispatch_event("input")
    locator.dispatch_event("change")
    locator.press("Enter")
    page.wait_for_timeout(350)

    # Some 1688 spec controls (notably size) only finalize a custom value on blur.
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(550)

    after = set(_committed_values(page, selector))
    if value not in after:
        state = _axis_state(page, selector)
        raise RuntimeError(
            f"规格值没有完成提交: {value!r}; before={sorted(before)!r}; state={state!r}"
        )


def _fill_axis(page: Any, selector: str, values: list[str]) -> list[str]:
    wanted = [str(raw).strip() for raw in values if str(raw).strip()]
    for value in wanted:
        if value in _committed_values(page, selector):
            continue
        _commit_spec_value(page, selector, value)

    committed = _committed_values(page, selector)
    missing = [value for value in wanted if value not in committed]
    if missing:
        raise RuntimeError(f"规格轴提交不完整，缺少: {missing!r}; 已提交: {committed!r}")
    return committed


def _switch_to_spec_quotation(page: Any) -> None:
    container = page.locator("#guid-quotationType")
    if not container.count():
        raise RuntimeError("找不到报价方式组件 #guid-quotationType")

    spec_radio = container.locator("input.ant-radio-input[value='1']")
    if not spec_radio.count():
        raise RuntimeError("找不到‘按产品规格报价’ radio(value=1)")

    radio = spec_radio.first
    if not radio.is_checked():
        # Ant Design hides the real radio input and, on some 1688 layouts, the
        # label may also be outside Playwright's visible/actionable box. Do not
        # use scroll_into_view_if_needed() here; dispatch a DOM click instead.
        container.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
        page.wait_for_timeout(300)
        radio.evaluate(
            """
            el => {
              const label = el.closest('label');
              const target = label || el;
              target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
              target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
              target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
            }
            """
        )
        page.wait_for_timeout(1200)

    if not radio.is_checked():
        raise RuntimeError("切换到‘按产品规格报价’失败")


def _sku_row_count(page: Any) -> int:
    table = page.locator("#guid-skuTable")
    if not table.count() or not table.first.is_visible():
        return 0
    rows = table.locator(".next-table-body tbody tr.next-table-row")
    return rows.count()


def _sku_headers(page: Any) -> list[str]:
    table = page.locator("#guid-skuTable")
    if not table.count() or not table.first.is_visible():
        return []
    headers = table.locator(".next-table-header th .sku-header-label > span:first-child")
    values: list[str] = []
    for i in range(headers.count()):
        text = headers.nth(i).inner_text().strip()
        if text:
            values.append(text)
    return values


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

        _switch_to_spec_quotation(page)

        axis1_values = [str(v) for v in axes[0].get("values", [])]
        axis2_values = [str(v) for v in axes[1].get("values", [])] if len(axes) > 1 else []

        axis1_committed = _fill_axis(page, color_selector, axis1_values)
        axis2_committed = _fill_axis(page, size_selector, axis2_values) if axis2_values else []

        page.wait_for_timeout(1800)
        sku_table = page.locator("#guid-skuTable")
        matrix_visible = bool(sku_table.count() and sku_table.first.is_visible())
        matrix_rows = _sku_row_count(page)
        expected_rows = len(axis1_values) * max(1, len(axis2_values))
        headers = _sku_headers(page)
        spec_price_visible = any("单价" in h or "价格" in h for h in headers)

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
            "quotation_mode": "specification",
            "axis1": axis1_committed,
            "axis2": axis2_committed,
            "common_specs": normalized.get("common_specs", []),
            "matrix_visible": matrix_visible,
            "matrix_rows": matrix_rows,
            "expected_rows": expected_rows,
            "matrix_complete": matrix_visible and matrix_rows == expected_rows,
            "sku_headers": headers,
            "spec_price_visible": spec_price_visible,
            "output_dir": str(out),
            "screenshot": str(out / "page.png"),
            "controls": str(out / "controls.json"),
            "html": str(out / "page.html"),
            "status": "sku-spec-quotation-captured-not-submitted",
        }
        (out / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if not result["matrix_complete"]:
            raise RuntimeError(
                f"SKU 矩阵未完整生成：实际 {matrix_rows} 行，预期 {expected_rows} 行。证据已保存到 {out}"
            )
        if not result["spec_price_visible"]:
            raise RuntimeError(
                f"已切换按产品规格报价，但 SKU 表未出现单价/价格列；headers={headers!r}。证据已保存到 {out}"
            )

        print("已切换按产品规格报价并生成完整 SKU 矩阵，未提交商品。请检查单价列，完成后回终端按 Enter。")
        input()
        return result
