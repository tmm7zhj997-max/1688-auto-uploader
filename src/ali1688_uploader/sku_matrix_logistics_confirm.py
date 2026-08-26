from __future__ import annotations

from typing import Any

from . import sku_matrix_logistics as _base

LOGISTICS_WEIGHT_TEXT = "1000"


def _confirm_logistics_switch_modal(page: Any, *, attempts: int = 16) -> dict[str, Any]:
    """Poll and confirm the modal shown after switching logistics mode."""
    last: dict[str, Any] = {"clicked": False, "seen": False}
    for _ in range(attempts):
        last = page.evaluate(
            """
            () => {
              const visible = el => {
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
              };
              const clickElement = el => {
                el.scrollIntoView({ block: 'center', inline: 'nearest' });
                el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
              };
              const modals = [...document.querySelectorAll('.ant-modal, .next-dialog, [role="dialog"]')]
                .filter(visible);
              for (const modal of modals) {
                const text = (modal.innerText || '').replace(/\s+/g, ' ').trim();
                const isSwitchModal = text.includes('切换后') || text.includes('件重尺') || text.includes('确认是否切换');
                if (!isSwitchModal) continue;
                const buttons = [...modal.querySelectorAll('button')].filter(visible);
                const confirm = buttons.find(btn => ['确认', '确定'].some(t => (btn.innerText || '').includes(t)));
                if (confirm) {
                  clickElement(confirm);
                  return { clicked: true, seen: true, text };
                }
                return { clicked: false, seen: true, text, reason: 'confirm_button_not_found' };
              }
              return { clicked: false, seen: false };
            }
            """
        )
        if last.get("clicked"):
            page.wait_for_timeout(900)
            return last
        page.wait_for_timeout(250)
    return last


def _fill_logistics_weight_only(page: Any, *, weight_text: str = LOGISTICS_WEIGHT_TEXT) -> dict[str, Any]:
    """Select product-level logistics and fill only weight=1000.

    1688 may show the switch confirmation modal asynchronously. This function
    repeatedly polls that modal and confirms it before filling row-level weights.
    Length, width, height and volume are intentionally not filled.
    """
    block = page.locator("#guid-blockLogistics")
    if not block.count():
        raise RuntimeError("未找到物流信息区块 #guid-blockLogistics")

    block.first.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
    page.wait_for_timeout(500)

    # Close the guidance bubble if it is present.
    page.evaluate(
        """
        () => {
          const visible = el => {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
          };
          const btn = [...document.querySelectorAll('button')]
            .find(el => visible(el) && (el.innerText || '').includes('我知道了'));
          if (btn) btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
        }
        """
    )

    mode_click = page.evaluate(
        """
        () => {
          const clickElement = el => {
            el.scrollIntoView({ block: 'center', inline: 'nearest' });
            el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
          };
          const block = document.querySelector('#guid-blockLogistics');
          if (!block) return { ok: false, error: 'block_not_found' };
          const modeLabel = [...block.querySelectorAll('label')].find(label => {
            const text = (label.innerText || '').replace(/\s+/g, '');
            return text.includes('按照商品设置') || text.includes('按商品设置') || /按.*商品.*设置/.test(text);
          });
          if (!modeLabel) return { ok: false, error: 'product_level_mode_label_not_found' };
          const input = modeLabel.querySelector('input');
          const checkedBefore = !!(input && input.checked);
          if (!checkedBefore) clickElement(modeLabel);
          return { ok: true, text: (modeLabel.innerText || '').replace(/\s+/g, ' ').trim(), checked_before: checkedBefore };
        }
        """
    )
    if not mode_click.get("ok"):
        raise RuntimeError(f"无法选择按商品设置物流模式: {mode_click!r}")

    first_modal_confirm = _confirm_logistics_switch_modal(page, attempts=20)
    page.wait_for_timeout(1000)

    # Some accounts require clicking the product-level mode again after confirming.
    page.evaluate(
        """
        () => {
          const clickElement = el => {
            el.scrollIntoView({ block: 'center', inline: 'nearest' });
            el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
          };
          const block = document.querySelector('#guid-blockLogistics');
          if (!block) return;
          const modeLabel = [...block.querySelectorAll('label')].find(label => {
            const text = (label.innerText || '').replace(/\s+/g, '');
            return text.includes('按照商品设置') || text.includes('按商品设置') || /按.*商品.*设置/.test(text);
          });
          const input = modeLabel && modeLabel.querySelector('input');
          if (modeLabel && (!input || !input.checked)) clickElement(modeLabel);
        }
        """
    )
    second_modal_confirm = _confirm_logistics_switch_modal(page, attempts=10)
    page.wait_for_timeout(1000)

    result = page.evaluate(
        r"""
        ({ weightText }) => {
          const setNativeValue = (input, value) => {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, value);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
          };
          const block = document.querySelector('#guid-blockLogistics');
          if (!block) return { ok: false, error: 'block_not_found' };

          const filled = [];
          const skipped = [];
          const tables = [...block.querySelectorAll('table')]
            .filter(table => (table.innerText || '').includes('重量'));

          for (const table of tables) {
            const headers = [...table.querySelectorAll('thead th, thead td')]
              .map(cell => (cell.innerText || '').replace(/\s+/g, ' ').trim());
            const weightIndex = headers.findIndex(text => text.includes('重量'));
            if (weightIndex < 0) continue;
            const rows = [...table.querySelectorAll('tbody tr')];
            for (let rowIndex = 0; rowIndex < rows.length; rowIndex++) {
              const cells = [...rows[rowIndex].querySelectorAll('td')];
              const targetCell = cells[weightIndex];
              if (!targetCell) {
                skipped.push({ row: rowIndex + 1, reason: 'weight_cell_not_found' });
                continue;
              }
              const input = [...targetCell.querySelectorAll('input')]
                .find(el => !el.disabled && !el.readOnly && !['hidden', 'radio', 'checkbox', 'search'].includes((el.type || '').toLowerCase()));
              if (!input) {
                skipped.push({ row: rowIndex + 1, reason: 'weight_input_not_found' });
                continue;
              }
              setNativeValue(input, weightText);
              filled.push({ row: rowIndex + 1, value: input.value, headers });
            }
          }

          const mode_options = [...block.querySelectorAll('label')]
            .filter(label => (label.innerText || '').replace(/\s+/g, '').match(/按.*商品.*设置/))
            .map(label => {
              const input = label.querySelector('input');
              return { text: (label.innerText || '').replace(/\s+/g, ' ').trim(), checked: !!(input && input.checked) };
            });

          return {
            ok: filled.length > 0,
            target: '按照商品设置，仅填写重量',
            weight_expected: weightText,
            mode_options,
            filled,
            skipped,
            block_text: (block.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 1200),
          };
        }
        """,
        {"weightText": weight_text},
    )
    page.wait_for_timeout(1200)

    if not result.get("ok"):
        raise RuntimeError(
            f"物流重量未填写成功: mode_click={mode_click!r}, modal1={first_modal_confirm!r}, "
            f"modal2={second_modal_confirm!r}, result={result!r}"
        )
    bad = [item for item in result.get("filled", []) if str(item.get("value", "")).strip() != weight_text]
    if bad:
        raise RuntimeError(f"物流重量写入后读回不一致: {bad!r}")
    result["mode_click"] = mode_click
    result["first_modal_confirm"] = first_modal_confirm
    result["second_modal_confirm"] = second_modal_confirm
    return result


_base._fill_logistics_weight_only = _fill_logistics_weight_only
fill_sku_prices_and_stock = _base.fill_sku_prices_and_stock
