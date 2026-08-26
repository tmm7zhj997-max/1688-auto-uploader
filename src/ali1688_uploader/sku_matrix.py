from __future__ import annotations

import json
import re
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


DELIVERY_PATTERNS = ("72小时", "72 小时", "三天发货", "3天发货", "三天", "3天", "72")
EXCHANGE_TEXT = "7天包换"
RETURN_TEXT = "7天无理由退货"
SERVICE_PACKAGE_TEXT = "不支持"


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
        r"""
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


def _click_visible_option_by_text(page: Any, patterns: tuple[str, ...]) -> str | None:
    pattern = re.compile("|".join(re.escape(text) for text in patterns))
    options = page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option")
    count = options.count()
    for index in range(count):
        option = options.nth(index)
        try:
            text = (option.inner_text() or "").strip()
        except Exception:
            text = ""
        if text and pattern.search(text):
            option.click()
            page.wait_for_timeout(700)
            return text
    clicked = page.evaluate(
        """
        patterns => {
          const dropdowns = [...document.querySelectorAll('.ant-select-dropdown')]
            .filter(el => !el.classList.contains('ant-select-dropdown-hidden'));
          for (const dropdown of dropdowns) {
            const options = [...dropdown.querySelectorAll('.ant-select-item-option')];
            for (const option of options) {
              const text = (option.innerText || '').trim();
              if (patterns.some(pattern => text.includes(pattern))) {
                option.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                option.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                option.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                return text;
              }
            }
          }
          return null;
        }
        """,
        list(patterns),
    )
    if clicked:
        page.wait_for_timeout(700)
    return clicked


def _select_delivery_time(page: Any) -> dict[str, Any]:
    block = page.locator("#guid-buyerProtection")
    if not block.count():
        raise RuntimeError("未找到买家保障/服务与承诺区块 #guid-buyerProtection")

    block.first.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
    page.wait_for_timeout(300)

    trigger = page.locator("#guid-buyerProtection .ant-select-selector").filter(has_text="请选择发货时间")
    if not trigger.count():
        trigger = page.locator("#guid-buyerProtection input[aria-controls^='rc_select_']").locator(
            "xpath=ancestor::div[contains(@class, 'ant-select-selector')][1]"
        )
    if not trigger.count():
        raise RuntimeError("未找到服务与承诺里的发货时间下拉框")

    trigger.first.click()
    page.wait_for_timeout(700)
    selected = _click_visible_option_by_text(page, DELIVERY_PATTERNS)
    if not selected:
        raise RuntimeError("发货时间下拉框已打开，但没有找到 72小时/三天发货 选项")

    current = page.locator("#guid-buyerProtection").evaluate(
        r"""
        el => {
          const table = [...el.querySelectorAll('table')].find(t => (t.innerText || '').includes('发货时间'));
          return table ? (table.innerText || '').replace(/\s+/g, ' ').trim() : '';
        }
        """
    )
    return {"target": "72小时", "selected": selected, "table_text": current}


def _click_radio_in_service(page: Any, *, section_label: str, option_text: str) -> dict[str, Any]:
    result = page.evaluate(
        """
        ({ sectionLabel, optionText }) => {
          const wrappers = [...document.querySelectorAll('#guid-buyerProtection .service-wrapper')];
          const wrapper = wrappers.find(el => (el.innerText || '').includes(sectionLabel));
          if (!wrapper) {
            return { ok: false, section: sectionLabel, option: optionText, error: 'section_not_found' };
          }
          const labels = [...wrapper.querySelectorAll('label')];
          const label = labels.find(el => (el.innerText || '').includes(optionText));
          if (!label) {
            return { ok: false, section: sectionLabel, option: optionText, error: 'option_not_found', text: wrapper.innerText || '' };
          }
          const input = label.querySelector('input[type="radio"]');
          if (!input) {
            return { ok: false, section: sectionLabel, option: optionText, error: 'radio_missing' };
          }
          if (input.disabled) {
            return { ok: false, section: sectionLabel, option: optionText, error: 'radio_disabled' };
          }
          if (!input.checked) {
            label.scrollIntoView({ block: 'center', inline: 'nearest' });
            label.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
            label.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
            label.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
          }
          return { ok: true, section: sectionLabel, option: optionText, checked: input.checked || true };
        }
        """,
        {"sectionLabel": section_label, "optionText": option_text},
    )
    page.wait_for_timeout(500)
    if not result.get("ok"):
        raise RuntimeError(f"无法选择 {section_label} -> {option_text}: {result!r}")
    return result


def _check_all_available_quality_services(page: Any) -> dict[str, Any]:
    result = page.evaluate(
        """
        () => {
          const wrappers = [...document.querySelectorAll('#guid-buyerProtection .service-wrapper')];
          const wrapper = wrappers.find(el => (el.innerText || '').includes('品质服务'));
          if (!wrapper) {
            return { ok: false, error: 'quality_section_not_found' };
          }
          const checked = [];
          const skipped = [];
          const labels = [...wrapper.querySelectorAll('label.ant-checkbox-wrapper')];
          for (const label of labels) {
            const input = label.querySelector('input[type="checkbox"]');
            const text = (label.innerText || '').replace(/\\s+/g, ' ').trim();
            if (!input) {
              skipped.push({ text, reason: 'checkbox_missing' });
              continue;
            }
            if (input.disabled || label.classList.contains('ant-checkbox-wrapper-disabled')) {
              skipped.push({ text, value: input.value || '', reason: 'disabled_or_not_opened' });
              continue;
            }
            if (!input.checked) {
              label.scrollIntoView({ block: 'center', inline: 'nearest' });
              label.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
              label.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
              label.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
            }
            checked.push({ text, value: input.value || '', checked: true });
          }
          return { ok: true, checked, skipped };
        }
        """
    )
    page.wait_for_timeout(700)
    if not result.get("ok"):
        raise RuntimeError(f"无法勾选品质服务: {result!r}")
    if not result.get("checked"):
        raise RuntimeError(f"品质服务没有可勾选项: {result!r}")
    return result


def _fill_service_commitments(page: Any) -> dict[str, Any]:
    block = page.locator("#guid-buyerProtection")
    if not block.count():
        raise RuntimeError("未找到买家保障/服务与承诺区块 #guid-buyerProtection")
    block.first.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
    page.wait_for_timeout(500)

    delivery = _select_delivery_time(page)
    exchange = _click_radio_in_service(page, section_label="包换服务", option_text=EXCHANGE_TEXT)
    returns = _click_radio_in_service(page, section_label="退货服务", option_text=RETURN_TEXT)
    quality = _check_all_available_quality_services(page)
    package = _click_radio_in_service(page, section_label="服务包", option_text=SERVICE_PACKAGE_TEXT)

    page.wait_for_timeout(1000)
    return {
        "delivery_time": delivery,
        "exchange_service": exchange,
        "return_service": returns,
        "quality_services": quality,
        "service_package": package,
    }


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
            "readback": filled,
            "output_dir": str(out),
            "screenshot": str(out / "page.png"),
            "controls": str(out / "controls.json"),
            "html": str(out / "page.html"),
            "status": "sku-price-stock-services-filled-not-submitted",
        }
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        print("SKU 批发价、可售数量和服务与承诺已填写，未提交商品。请在浏览器检查后回终端按 Enter。")
        input()
        return result
