from __future__ import annotations

from typing import Any

from . import sku_matrix_logistics as _base
from . import sku_matrix_logistics_weight_g as _weight_g  # noqa: F401 - installs the weight-only logistics patch

DETAIL_HTML = """<div class=\"product-detail-template\">
  <h2>产品说明</h2>
  <p>本产品为实木床类商品，支持多规格选择，具体颜色、尺寸、价格以页面规格表为准。</p>

  <h2>规格说明</h2>
  <p>可选规格包含不同颜色/组合与尺寸，购买前请根据实际需求选择对应规格。</p>

  <h2>发货与售后</h2>
  <p>支持 72 小时发货，支持七天无理由退货，支持 7 天包换。物流重量按商品设置。</p>

  <h2>温馨提示</h2>
  <p>家具类商品因拍摄光线、显示器差异、批次差异，颜色和细节可能略有不同，请以实物为准。</p>
</div>"""

_WEIGHT_ONLY_FILL = _base._fill_logistics_weight_only


def _fill_product_detail_template(page: Any, *, html: str = DETAIL_HTML) -> dict[str, Any]:
    """Fill a stable text-only product detail template.

    The current 1688 page exposes the old TinyMCE editor as textarea#tinyMCE-0
    in source-code mode. To make the value stick across Ali/Ant/TinyMCE layers,
    write the template to TinyMCE, its iframe body, the hidden textarea, and any
    visible contenteditable editor body we can safely identify.
    """
    result = page.evaluate(
        r"""
        async ({ html }) => {
          const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
          const visible = el => {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
          };
          const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
          const setTextAreaValue = (textarea, value) => {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
            if (setter) setter.call(textarea, value);
            else textarea.value = value;
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
            textarea.dispatchEvent(new Event('change', { bubbles: true }));
            textarea.dispatchEvent(new Event('blur', { bubbles: true }));
          };
          const clickElement = el => {
            el.scrollIntoView({ block: 'center', inline: 'nearest' });
            el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
            if (typeof el.click === 'function') el.click();
          };

          const operations = [];
          const errors = [];
          const block = document.querySelector('#guid-description, #guid-detail, [data-spm="description"], [data-module-name*="description"]')
            || [...document.querySelectorAll('.is-component, div')].find(el => visible(el) && textOf(el).includes('商品详情'))
            || null;
          if (block) block.scrollIntoView({ block: 'center', inline: 'nearest' });
          await sleep(500);

          // Prefer source-code mode when the old AliRTE/TinyMCE widget exposes it.
          const sourceBtn = document.querySelector('#tinyMCE-0-ali-code-status [title="源代码"], [id*="ali-code-status"] [title="源代码"], .aliRTE-btn-oncode[title="源代码"]');
          if (sourceBtn && visible(sourceBtn)) {
            clickElement(sourceBtn);
            operations.push('source_mode_clicked');
            await sleep(500);
          }

          const textarea = document.querySelector('textarea#tinyMCE-0')
            || [...document.querySelectorAll('textarea')].find(el => (el.id || '').includes('tinyMCE'))
            || null;
          if (textarea) {
            setTextAreaValue(textarea, html);
            operations.push('textarea#tinyMCE-0');
          }

          const tinymceApi = window.tinyMCE || window.tinymce || null;
          const editor = tinymceApi?.get?.('tinyMCE-0') || (tinymceApi?.activeEditor && String(tinymceApi.activeEditor.id || '').includes('tinyMCE') ? tinymceApi.activeEditor : null);
          if (editor) {
            try {
              editor.setContent(html);
              if (typeof editor.save === 'function') editor.save();
              if (typeof editor.fire === 'function') {
                editor.fire('input');
                editor.fire('change');
                editor.fire('blur');
                editor.fire('NodeChange');
              }
              if (typeof editor.execCommand === 'function') editor.execCommand('mceSetContent', false, html);
              const body = typeof editor.getBody === 'function' ? editor.getBody() : null;
              if (body) {
                body.innerHTML = html;
                body.dispatchEvent(new Event('input', { bubbles: true }));
                body.dispatchEvent(new Event('change', { bubbles: true }));
              }
              operations.push('tinymce_editor');
            } catch (err) {
              errors.push(`tinymce:${err?.message || err}`);
            }
          }

          const iframe = document.querySelector('iframe#tinyMCE-0_ifr, iframe[id*="tinyMCE-0"], iframe[id*="tinymce"], iframe[id*="mce"]');
          if (iframe?.contentDocument?.body) {
            try {
              iframe.contentDocument.body.innerHTML = html;
              iframe.contentDocument.body.dispatchEvent(new Event('input', { bubbles: true }));
              iframe.contentDocument.body.dispatchEvent(new Event('change', { bubbles: true }));
              operations.push('tinymce_iframe_body');
            } catch (err) {
              errors.push(`iframe:${err?.message || err}`);
            }
          }

          const editable = [...document.querySelectorAll('[contenteditable="true"]')]
            .find(el => visible(el) && (textOf(el).includes('产品详情') || (el.closest('#guid-description, #guid-detail, [data-spm="description"]') || block)));
          if (editable) {
            editable.innerHTML = html;
            editable.dispatchEvent(new Event('input', { bubbles: true }));
            editable.dispatchEvent(new Event('change', { bubbles: true }));
            operations.push('contenteditable');
          }

          await sleep(800);
          const readbackCandidates = [];
          if (textarea) readbackCandidates.push(textarea.value || '');
          if (editor && typeof editor.getContent === 'function') {
            try { readbackCandidates.push(editor.getContent() || ''); } catch (_) {}
          }
          if (iframe?.contentDocument?.body) readbackCandidates.push(iframe.contentDocument.body.innerHTML || '');
          if (editable) readbackCandidates.push(editable.innerHTML || '');

          const readback = readbackCandidates.join('\n');
          const ok = readback.includes('产品说明') && readback.includes('七天无理由退货') && readback.includes('72 小时发货');
          return {
            ok,
            operations,
            errors,
            textarea_found: !!textarea,
            tinymce_found: !!editor,
            iframe_found: !!iframe,
            contenteditable_found: !!editable,
            readback_preview: readback.replace(/\s+/g, ' ').slice(0, 500),
          };
        }
        """,
        {"html": html},
    )
    page.wait_for_timeout(1000)
    if not result.get("ok"):
        raise RuntimeError(f"商品详情模板未写入成功: {result!r}")
    return result


def _fill_logistics_then_detail(page: Any, *, weight_text: str = _weight_g.LOGISTICS_WEIGHT_TEXT) -> dict[str, Any]:
    logistics = _WEIGHT_ONLY_FILL(page, weight_text=weight_text)
    detail = _fill_product_detail_template(page)
    if isinstance(logistics, dict):
        return {**logistics, "detail": detail}
    return {"logistics": logistics, "detail": detail}


_base._fill_logistics_weight_only = _fill_logistics_then_detail
fill_sku_prices_and_stock = _base.fill_sku_prices_and_stock
