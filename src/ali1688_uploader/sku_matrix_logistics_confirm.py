from __future__ import annotations

from typing import Any

from . import sku_matrix_logistics as _base

LOGISTICS_WEIGHT_TEXT = "1000"


def _fill_logistics_weight_only(page: Any, *, weight_text: str = LOGISTICS_WEIGHT_TEXT) -> dict[str, Any]:
    """Fill logistics using product-level weight only.

    Business rule for this workflow:
    - switch to product-level logistics settings and confirm the warning modal;
    - fill only weight=1000;
    - do not fill length/width/height/volume;
    - do not submit the product.
    """
    block = page.locator("#guid-blockLogistics")
    if not block.count():
        raise RuntimeError("未找到物流信息区块 #guid-blockLogistics")

    block.first.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
    page.wait_for_timeout(500)

    result = page.evaluate(
        r"""
        async ({ weightText }) => {
          const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
          const visible = el => {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
          };
          const isEditableTextInput = input => {
            const type = (input.type || '').toLowerCase();
            return visible(input) && !input.disabled && !input.readOnly && !['hidden', 'radio', 'checkbox', 'search'].includes(type);
          };
          const setNativeValue = (input, value) => {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
            if (setter) setter.call(input, value);
            else input.value = value;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: '0' }));
            input.dispatchEvent(new Event('blur', { bubbles: true }));
          };
          const clickElement = el => {
            el.scrollIntoView({ block: 'center', inline: 'nearest' });
            el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
            if (typeof el.click === 'function') el.click();
          };
          const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
          const compactTextOf = el => textOf(el).replace(/\s+/g, '');
          const modalTextMatches = text => {
            const compact = (text || '').replace(/\s+/g, '');
            return compact.includes('切换后将清除')
              || compact.includes('件重尺信息')
              || compact.includes('确认是否切换')
              || compact.includes('是否切换');
          };
          const findSwitchModal = () => {
            const candidates = [
              ...document.querySelectorAll('.ant-modal, .ant-modal-content, .next-dialog, .next-dialog-body, .next-overlay-wrapper, [role="dialog"]')
            ].filter(visible);
            let modal = candidates.find(el => modalTextMatches(textOf(el))) || null;
            if (!modal && modalTextMatches(document.body.innerText || '')) {
              const bodies = [...document.querySelectorAll('div')].filter(el => visible(el) && modalTextMatches(textOf(el)));
              modal = bodies.sort((a, b) => textOf(a).length - textOf(b).length)[0] || null;
            }
            return modal;
          };
          const findConfirmButton = () => {
            const buttons = [...document.querySelectorAll('button, [role="button"], .ant-btn, .next-btn')].filter(visible);
            return buttons.find(btn => {
              const text = compactTextOf(btn);
              return (text === '确认' || text === '确定' || text.includes('确认') || text.includes('确定')) && !text.includes('取消');
            }) || null;
          };
          const confirmLogisticsSwitch = async () => {
            let seen = false;
            let clicked = false;
            let lastText = '';
            for (let i = 0; i < 40; i++) {
              const modal = findSwitchModal();
              if (modal) {
                seen = true;
                lastText = textOf(modal);
                const button = findConfirmButton();
                if (button) {
                  clickElement(button);
                  clicked = true;
                  await sleep(900);
                  if (!findSwitchModal()) {
                    return { seen, clicked, gone: true, text: lastText };
                  }
                }
              } else if (clicked || seen) {
                return { seen, clicked, gone: true, text: lastText };
              }
              await sleep(250);
            }
            return { seen, clicked, gone: !findSwitchModal(), text: lastText };
          };

          const block = document.querySelector('#guid-blockLogistics');
          if (!block) return { ok: false, error: 'block_not_found' };

          const okButton = [...document.querySelectorAll('button')]
            .find(btn => visible(btn) && textOf(btn).includes('我知道了'));
          if (okButton) clickElement(okButton);

          const labels = [...block.querySelectorAll('label')];
          const modeLabel = labels.find(label => {
            const text = compactTextOf(label);
            return text.includes('按照商品设置') || text.includes('按商品设置') || /按.*商品.*设置/.test(text);
          });
          let mode = { selected: false, text: null, checked_before: null, checked_after: null, reason: null };
          let modal = { seen: false, clicked: false, gone: true };
          if (modeLabel) {
            const input = modeLabel.querySelector('input');
            const checkedBefore = input ? !!input.checked : null;
            if (!input || (!input.disabled && !input.checked)) {
              clickElement(modeLabel);
              modal = await confirmLogisticsSwitch();
              await sleep(1200);
              if (input && !input.checked) {
                clickElement(modeLabel);
                const modalAgain = await confirmLogisticsSwitch();
                modal = { first: modal, second: modalAgain };
                await sleep(1200);
              }
            }
            mode = {
              selected: true,
              text: textOf(modeLabel),
              checked_before: checkedBefore,
              checked_after: input ? !!input.checked : null,
              reason: null,
            };
          } else {
            mode = { selected: false, text: null, checked_before: null, checked_after: null, reason: 'product_level_mode_label_not_found' };
          }

          await confirmLogisticsSwitch();
          await sleep(1200);

          const filled = [];
          const skipped = [];
          const markFilled = (input, source, extra = {}) => {
            setNativeValue(input, weightText);
            filled.push({ source, value: input.value, ...extra });
          };

          // 1) Prefer the product-level / batch row: it usually contains a “批量填写” button.
          const batchButtons = [...block.querySelectorAll('button, [role="button"], .next-btn, .ant-btn')]
            .filter(el => visible(el) && textOf(el).includes('批量填写'));
          for (const button of batchButtons) {
            const area = button.closest('tr, .next-row, .ant-row, div') || block;
            const inputs = [...area.querySelectorAll('input')].filter(isEditableTextInput);
            if (!inputs.length) continue;
            // In the batch row the order is normally 长、宽、高、重量; choose the input nearest to unit “g” or the last numeric input.
            const weightInput = inputs.find(input => {
              const local = textOf(input.parentElement || area).replace(/\s+/g, '');
              return local.includes('重量') || /(^|[^a-zA-Z])g($|[^a-zA-Z])/.test(local);
            }) || inputs[inputs.length - 1];
            markFilled(weightInput, 'batch_weight_input', { button_text: textOf(button), input_count: inputs.length });
            clickElement(button);
            await sleep(1000);
            break;
          }

          // 2) If the SKU 件重尺 table is still present, fill only the 重量(g) column; never touch 长/宽/高/体积.
          const tables = [...block.querySelectorAll('table')]
            .filter(table => visible(table) && textOf(table).includes('重量'));
          for (const table of tables) {
            const headers = [...table.querySelectorAll('thead th, thead td')]
              .map(cell => textOf(cell));
            const weightIndex = headers.findIndex(text => text.includes('重量'));
            if (weightIndex < 0) continue;
            const rows = [...table.querySelectorAll('tbody tr')].filter(visible);
            for (let rowIndex = 0; rowIndex < rows.length; rowIndex++) {
              const cells = [...rows[rowIndex].querySelectorAll('td')];
              const cell = cells[weightIndex];
              if (!cell) {
                skipped.push({ source: 'table_weight_column', row: rowIndex + 1, reason: 'weight_cell_missing', headers });
                continue;
              }
              const input = [...cell.querySelectorAll('input')].find(isEditableTextInput);
              if (!input) {
                skipped.push({ source: 'table_weight_column', row: rowIndex + 1, reason: 'weight_input_missing', headers });
                continue;
              }
              markFilled(input, 'table_weight_column', { row: rowIndex + 1, headers });
            }
          }

          // 3) Last fallback: a standalone form item whose text contains 重量 and g, but not 长/宽/高/体积.
          if (!filled.length) {
            const inputs = [...block.querySelectorAll('input')].filter(isEditableTextInput);
            for (const input of inputs) {
              const local = textOf(input.closest('td, .ant-form-item, .next-form-item, .ant-input-group, div') || input.parentElement || block).replace(/\s+/g, '');
              if ((local.includes('重量') || /(^|[^a-zA-Z])g($|[^a-zA-Z])/.test(local))
                  && !local.includes('长宽高') && !local.includes('长(cm)') && !local.includes('宽(cm)') && !local.includes('高(cm)') && !local.includes('体积')) {
                markFilled(input, 'standalone_weight_input', { local_text: local.slice(0, 120) });
                break;
              }
            }
          }

          await sleep(600);
          const bad = filled.filter(item => String(item.value || '').trim() !== String(weightText));
          return {
            ok: filled.length > 0 && bad.length === 0,
            target: '按照商品设置，仅填写重量',
            weight_expected: weightText,
            mode,
            modal,
            filled,
            bad,
            skipped,
            block_text: textOf(block).slice(0, 1400),
          };
        }
        """,
        {"weightText": weight_text},
    )
    page.wait_for_timeout(1200)
    if not result.get("ok"):
        raise RuntimeError(f"物流重量未填写成功: {result!r}")
    return result


_base._fill_logistics_weight_only = _fill_logistics_weight_only
fill_sku_prices_and_stock = _base.fill_sku_prices_and_stock
