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
from .sku_browser import (
    DEFAULT_SKU_EVIDENCE_DIR,
    _fill_axis,
    _has_sku_price_header,
    _load_normalized,
    _sku_headers,
    _sku_row_count,
    _switch_to_spec_quotation,
)


PRICE_HEADERS = ("批发价", "单价", "价格", "报价")
STOCK_HEADERS = ("可售数量", "库存")
IGNORED_SPEC_HEADERS = (
    "序号",
    "图片",
    "SKU分类",
    "批发价",
    "单价",
    "价格",
    "报价",
    "可售数量",
    "库存",
    "单品货号",
    "货号",
    "是否上架",
)


def _format_price(value: Any) -> str:
    number = float(value)
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _find_header_index(headers: list[str], keywords: tuple[str, ...], *, label: str) -> int:
    for index, header in enumerate(headers):
        if any(keyword in header for keyword in keywords):
            return index
    raise RuntimeError(f"SKU 表头中找不到 {label} 列: headers={headers!r}")


def _spec_column_indices(headers: list[str]) -> list[int]:
    indices: list[int] = []
    for index, header in enumerate(headers):
        if not header:
            continue
        if any(keyword in header for keyword in IGNORED_SPEC_HEADERS):
            continue
        indices.append(index)
    if not indices:
        raise RuntimeError(f"SKU 表头中找不到规格列: headers={headers!r}")
    return indices


def _row_cell_texts(row: Any) -> list[str]:
    return row.locator("td").evaluate_all(
        """
        cells => cells.map(cell => (cell.innerText || '').replace(/\s+/g, ' ').trim())
        """
    )


def _set_input_value(locator: Any, value: str) -> None:
    locator.scroll_into_view_if_needed()
    locator.click()
    locator.fill("")
    locator.fill(value)
    locator.evaluate(
        """
        (el, value) => {
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(el, value);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """,
        value,
    )


def _input_value(locator: Any) -> str:
    try:
        return locator.input_value().strip()
    except Exception:
        return ""


def fill_sku_prices_and_stock(
    normalized_path: str | Path,
    *,
    url: str,
    profile_path: str | Path = "browser_profiles/1688-current.json",
    fixed_stock: int = 1000,
    options: BrowserOptions | None = None,
    output_root: str | Path = DEFAULT_SKU_EVIDENCE_DIR,
) -> dict[str, Any]:
    if not url.strip():
        raise ValueError("必须提供真实 1688 发布页 URL")
    if fixed_stock <= 0:
        raise ValueError("fixed_stock 必须大于 0")

    normalized = _load_normalized(normalized_path)
    axes = normalized["axes"]
    rows_data = normalized["rows"]
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

    lookup: dict[tuple[str, ...], dict[str, Any]] = {}
    for item in rows_data:
        key = tuple(str(value).strip() for value in item.get("spec_values", []))
        lookup[key] = item

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
        spec_price_visible = _has_sku_price_header(headers)
        if not matrix_visible or matrix_rows != expected_rows:
            raise RuntimeError(f"SKU 矩阵未完整生成：实际 {matrix_rows} 行，预期 {expected_rows} 行")
        if not spec_price_visible:
            raise RuntimeError(f"SKU 表未出现价格列；headers={headers!r}")

        price_index = _find_header_index(headers, PRICE_HEADERS, label="批发价/价格")
        stock_index = _find_header_index(headers, STOCK_HEADERS, label="可售数量/库存")
        spec_indices = _spec_column_indices(headers)

        table_rows = sku_table.locator(".next-table-body tbody tr.next-table-row")
        filled: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        stock_text = str(fixed_stock)

        for index in range(table_rows.count()):
            row = table_rows.nth(index)
            cells = row.locator("td")
            cell_texts = _row_cell_texts(row)
            spec_values = tuple(cell_texts[i].strip() for i in spec_indices if i < len(cell_texts))
            data = lookup.get(spec_values)
            if data is None:
                missing.append({"row_index": index + 1, "spec_values": list(spec_values), "cell_texts": cell_texts})
                continue

            price_text = _format_price(data["price"])
            price_input = cells.nth(price_index).locator("input").first
            stock_input = cells.nth(stock_index).locator("input").first
            if not price_input.count() or not stock_input.count():
                missing.append({"row_index": index + 1, "spec_values": list(spec_values), "reason": "price_or_stock_input_missing"})
                continue

            _set_input_value(price_input, price_text)
            _set_input_value(stock_input, stock_text)
            page.wait_for_timeout(80)

            price_actual = _input_value(price_input)
            stock_actual = _input_value(stock_input)
            filled.append(
                {
                    "row_index": index + 1,
                    "spec_values": list(spec_values),
                    "price_expected": price_text,
                    "price_actual": price_actual,
                    "stock_expected": stock_text,
                    "stock_actual": stock_actual,
                }
            )

        controls = page.locator(
            "input, textarea, select, button, [role='button'], [contenteditable='true']"
        ).evaluate_all(_control_snapshot_script())
        (out / "controls.json").write_text(json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "page.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(out / "page.png"), full_page=True)

        bad_readback = [
            item
            for item in filled
            if item["price_actual"] != item["price_expected"] or item["stock_actual"] != item["stock_expected"]
        ]
        result = {
            "source": str(normalized_path),
            "sku_count": normalized.get("sku_count", len(rows_data)),
            "quotation_mode": "specification",
            "axis1": axis1_committed,
            "axis2": axis2_committed,
            "common_specs": normalized.get("common_specs", []),
            "matrix_visible": matrix_visible,
            "matrix_rows": matrix_rows,
            "expected_rows": expected_rows,
            "matrix_complete": matrix_visible and matrix_rows == expected_rows,
            "sku_headers": headers,
            "price_column": headers[price_index],
            "stock_column": headers[stock_index],
            "spec_columns": [headers[i] for i in spec_indices],
            "fixed_stock": fixed_stock,
            "filled_count": len(filled),
            "missing_rows": missing,
            "bad_readback": bad_readback,
            "readback": filled,
            "output_dir": str(out),
            "screenshot": str(out / "page.png"),
            "controls": str(out / "controls.json"),
            "html": str(out / "page.html"),
            "status": "sku-price-stock-filled-not-submitted",
        }
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        if missing:
            raise RuntimeError(f"有 SKU 行没有匹配到哈士奇数据：{missing!r}。证据已保存到 {out}")
        if bad_readback:
            raise RuntimeError(f"有 SKU 行写入后读回不一致：{bad_readback!r}。证据已保存到 {out}")
        if len(filled) != expected_rows:
            raise RuntimeError(f"SKU 填写数量不完整：实际 {len(filled)}，预期 {expected_rows}。证据已保存到 {out}")

        print("SKU 批发价和可售数量已填写，未提交商品。请在浏览器检查后回终端按 Enter。")
        input()
        return result
