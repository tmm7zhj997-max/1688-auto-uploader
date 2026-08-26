from __future__ import annotations

from typing import Any

from . import sku_matrix_logistics as _base

LOGISTICS_WEIGHT_TEXT = "1000"


def _fill_logistics_weight_only(page: Any, *, weight_text: str = LOGISTICS_WEIGHT_TEXT) -> dict[str, Any]:
    """Fill logistics using product-level weight only.

    1688 shows a confirmation modal when switching from SKU weight/size to
    product-level settings. The business rule for this workflow is to confirm
    that switch, then fill only weight=1000 and leave length/width/height blank.
    """
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
          const confirmLogisticsSwitch = () => {
            const modalRoots = [
              ...document.querySelectorAll('.ant-modal, .next-dialog, .next-overlay-wrapper, [role="dialog"]')
            ].filter(visible);
            const modal = modalRoots.find(el => {
              const text = (el.innerText || '').replace(/\s+/g, ' ');
              return text.includes('切换后将清除') || text.includes('件重尺信息') || text.includes('是否切换');
            });
            if (!modal) return { found: false, clicked: false };
            const buttons = [...modal.querySelectorAll('button')].filter(visible);
            const confirmButton = buttons.find(btn => (btn.innerText || '').includes('确认'))
              || buttons.find(btn => (btn.innerText || '').includes('确定'));
            if (!confirmButton) return { found: true, clicked: false, reason: 'confirm_button_not_found', text: modal.innerText || '' };
            clickElement(confirmButton);
            return { found: true, clicked: true, text: (modal.innerText || '').replace(/\s+/g, ' ').trim() };
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
          let confirm = { found: false, clicked: false };
          if (modeLabel) {
            const input = modeLabel.querySelector('input');
            if (!input || (!input.disabled && !input.checked)) {
              clickElement(modeLabel);
              confirm = confirmLogisticsSwitch();
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
            confirm,
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


_base._fill_logistics_weight_only = _fill_logistics_weight_only
fill_sku_prices_and_stock = _base.fill_sku_prices_and_stock
