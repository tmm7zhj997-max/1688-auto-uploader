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
from .sku_matrix import (
    PRICE_HEADERS,
    STOCK_HEADERS,
    _fill_service_commitments,
    _find_header_index,
    _format_price,
    _input_value,
    _row_cell_texts,
    _set_input_value,
    _spec_column_indices,
)

LOGISTICS_WEIGHT_TEXT = "1000"


def _fill_logistics_weight_only(page: Any, *, weight_text: str = LOGISTICS_WEIGHT_TEXT) -> dict[str, Any]:
    block = page.locator("#guid-blockLogistics")
    if not block.count():
        raise RuntimeError("未找到物流信息区块 #guid-blockLogistics")

    block.first.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
    page.wait_for_timeout(500)

    result = page.evaluate(
        r"""
        ({ weightText }) => {
          const visible = el => {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
          };
          const setNativeValue = (input, value) => {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, value);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
          };
          const clickElement = el => {
            el.scrollIntoView({ block: 'center', inline: 'nearest' });
            el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
          };

          const block = document.querySelector('#guid-blockLogistics');
          if (!block) return { ok: false, error: 'block_not_found' };

          const okButton = [...document.querySelectorAll('button')]
            .find(btn => visible(btn) && (btn.innerText || '').includes('我知道了'));
          if (okButton) clickElement(okButton);

          const labels = [...block.querySelectorAll('label')];
          const modeLabel = labels.find(label => {
            const text = (label.innerText || '').replace(/\s+/g, '');
            return text.includes('按照商品设置') || text.includes('按商品设置') || /按.*商品.*设置/.test(text);
          });
          let mode = { selected: false, text: null, reason: null };
          if (modeLabel) {
            const input = modeLabel.querySelector('input');
            if (!input || (!input.disabled && !input.checked)) {
              clickElement(modeLabel);
            }
            mode = { selected: true, text: (modeLabel.innerText || '').replace(/\s+/g, ' ').trim(), reason: null };
          } else {
            mode = { selected: false, text: null, reason: 'product_level_mode_label_not_found' };
          }

          const filled = [];
          const skipped = [];
          const tables = [...block.querySelectorAll('table')]
            .filter(table => visible(table) && (table.innerText || '').includes('重量'));

          for (const table of tables) {
            const headers = [...table.querySelectorAll('thead th, thead td')]
              .map(cell => (cell.innerText || '').replace(/\s+/g, ' ').trim());
            let weightIndex = headers.findIndex(text => text.includes('重量'));
            const rows = [...table.querySelectorAll('tbody tr')].filter(visible);

            for (let rowIndex = 0; rowIndex < rows.length; rowIndex++) {
              const row = rows[rowIndex];
              const cells = [...row.querySelectorAll('td')];
              let targetCell = null;
              if (weightIndex >= 0 && weightIndex < cells.length) {
                targetCell = cells[weightIndex];
              }
              if (!targetCell) {
                targetCell = cells.find(cell => {
                  const text = (cell.innerText || '').replace(/\s+/g, ' ').trim();
                  if (text.includes('长宽高')) return false;
                  return !![...cell.querySelectorAll('input')].find(input => visible(input) && !input.disabled && !input.readOnly && !['hidden', 'radio', 'checkbox', 'search'].includes((input.type || '').toLowerCase()));
                }) || null;
              }
              if (!targetCell) {
                skipped.push({ row: rowIndex + 1, reason: 'target_cell_not_found' });
                continue;
              }
              const input = [...targetCell.querySelectorAll('input')]
                .find(el => visible(el) && !el.disabled && !el.readOnly && !['hidden', 'radio', 'checkbox', 'search'].includes((el.type || '').toLowerCase()));
              if (!input) {
                skipped.push({ row: rowIndex + 1, reason: 'weight_input_not_found' });
                continue;
              }
              setNativeValue(input, weightText);
              filled.push({ row: rowIndex + 1, value: input.value, headers, cellText: (targetCell.innerText || '').replace(/\s+/g, ' ').trim() });
            }
          }

          if (!filled.length) {
            const fallbackInput = [...block.querySelectorAll('input')]
              .find(el => visible(el) && !el.disabled && !el.readOnly && !['hidden', 'radio', 'checkbox', 'search'].includes((el.type || '').toLowerCase()));
            if (fallbackInput) {
              setNativeValue(fallbackInput, weightText);
              filled.push({ row: 1, value: fallbackInput.value, fallback: true });
            }
          }

          return {
            ok: filled.length > 0,
            target: '按照商品设置，仅填写重量',
            weight_expected: weightText,
            mode,
            filled,
            skipped,
            block_text: (block.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 1000),
          };
        }
        """,
        {"weightText": weight_text},
    )
    page.wait_for_timeout(1200)
    if not result.get("ok"):
        raise RuntimeError(f"物流重量未填写成功: {result!r}")
    bad = [item for item in result.get("filled", []) if str(item.get("value", "")).strip() != weight_text]
    if bad:
        raise RuntimeError(f"物流重量写入后读回不一致: {bad!r}")
    return result


def fill_sku_prices_and_stock(
    normalized_path: str | Path,
    *,
    url: str,
    profile_path: str | Path = "browser_profiles/1688-current.json",
    fixed_stock: int = 1000,
    logistics_weight: int = 1000,
    options: BrowserOptions | None = None,
    output_root: str | Path = DEFAULT_SKU_EVIDENCE_DIR,
) -> dict[str, Any]:
    if not url.strip():
        raise ValueError("必须提供真实 1688 发布页 URL")
    if fixed_stock <= 0:
        raise ValueError("fixed_stock 必须大于 0")
    if logistics_weight <= 0:
        raise ValueError("logistics_weight 必须大于 0")

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

        bad_readback = [
            item
            for item in filled
            if item["price_actual"] != item["price_expected"] or item["stock_actual"] != item["stock_expected"]
        ]
        if missing:
            raise RuntimeError(f"有 SKU 行没有匹配到哈士奇数据：{missing!r}。证据已保存到 {out}")
        if bad_readback:
            raise RuntimeError(f"有 SKU 行写入后读回不一致：{bad_readback!r}。证据已保存到 {out}")
        if len(filled) != expected_rows:
            raise RuntimeError(f"SKU 填写数量不完整：实际 {len(filled)}，预期 {expected_rows}。证据已保存到 {out}")

        services = _fill_service_commitments(page)
        logistics = _fill_logistics_weight_only(page, weight_text=str(logistics_weight))

        controls = page.locator(
            "input, textarea, select, button, [role='button'], [contenteditable='true']"
        ).evaluate_all(_control_snapshot_script())
        (out / "controls.json").write_text(json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "page.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(out / "page.png"), full_page=True)

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
            "services": services,
            "logistics": logistics,
            "readback": filled,
            "output_dir": str(out),
            "screenshot": str(out / "page.png"),
            "controls": str(out / "controls.json"),
            "html": str(out / "page.html"),
            "status": "sku-price-stock-services-logistics-filled-not-submitted",
        }
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        print("SKU 批发价、可售数量、服务与承诺和物流重量已填写，未提交商品。请在浏览器检查后回终端按 Enter。")
        input()
        return result
