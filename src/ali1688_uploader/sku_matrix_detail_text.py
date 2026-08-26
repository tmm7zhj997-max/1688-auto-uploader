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

DETAIL_TEXT = """产品说明
本产品为实木床类商品，支持多规格选择，具体颜色、尺寸、价格以页面规格表为准。

规格说明
可选规格包含不同颜色/组合与尺寸，购买前请根据实际需求选择对应规格。

发货与售后
支持 72 小时发货，支持七天无理由退货，支持 7 天包换。物流重量按商品设置。

温馨提示
家具类商品因拍摄光线、显示器差异、批次差异，颜色和细节可能略有不同，请以实物为准。"""

_WEIGHT_ONLY_FILL = _base._fill_logistics_weight_only


def _fill_product_detail_template(page: Any, *, html: str = DETAIL_HTML, text: str = DETAIL_TEXT) -> dict[str, Any]:
    """Fill the 1688 product detail editor with a stable text template.

    The current page has both a modern “快捷编辑/插文本” editor and a hidden old
    TinyMCE editor. Writing directly to the hidden textarea can pass local
    readback but does not update the real product-detail state. The reliable
    path is to switch the detail component to the visible legacy editor first;
    only if that fails do we try the modern quick-text editor.
    """
    result = page.evaluate(
        r"""
        async ({ html, text }) => {
          const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
          const visible = el => {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
          };
          const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
          const compactTextOf = el => textOf(el).replace(/\s+/g, '');
          const fireInputEvents = el => {
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: '0' }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
          };
          const setTextAreaValue = (textarea, value) => {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
            if (setter) setter.call(textarea, value);
            else textarea.value = value;
            fireInputEvents(textarea);
          };
          const clickElement = el => {
            el.scrollIntoView({ block: 'center', inline: 'nearest' });
            el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
            if (typeof el.click === 'function') el.click();
          };
          const wait = async (predicate, timeout = 8000, interval = 250) => {
            const end = Date.now() + timeout;
            let last = null;
            while (Date.now() < end) {
              try {
                last = predicate();
                if (last) return last;
              } catch (_) {}
              await sleep(interval);
            }
            return last;
          };

          const operations = [];
          const errors = [];
          const descBlock = document.querySelector('#guid-description')
            || [...document.querySelectorAll('div')].find(el => visible(el) && compactTextOf(el).includes('商品详情') && compactTextOf(el).includes('图文详情'))
            || null;
          if (!descBlock) return { ok: false, reason: 'description_block_not_found', operations, errors };
          descBlock.scrollIntoView({ block: 'center', inline: 'nearest' });
          await sleep(800);

          const acknowledgeDialog = async () => {
            for (let i = 0; i < 12; i++) {
              const buttons = [...document.querySelectorAll('button, [role="button"], .ant-btn, .next-btn')].filter(visible);
              const confirm = buttons.find(btn => {
                const t = compactTextOf(btn);
                return (t === '确认' || t === '确定' || t.includes('确认') || t.includes('确定')) && !t.includes('取消');
              });
              const bodyText = compactTextOf(document.body);
              if (confirm && (bodyText.includes('旧版') || bodyText.includes('切换') || bodyText.includes('确认'))) {
                clickElement(confirm);
                operations.push('dialog_confirmed');
                await sleep(900);
                return true;
              }
              await sleep(250);
            }
            return false;
          };

          const tryLegacyEditor = async () => {
            const legacyButton = [...descBlock.querySelectorAll('button, [role="button"]')]
              .filter(visible)
              .find(btn => compactTextOf(btn).includes('返回到旧版'));
            if (legacyButton) {
              clickElement(legacyButton);
              operations.push('return_to_legacy_clicked');
              await acknowledgeDialog();
              await sleep(2500);
            }

            const editorParent = await wait(() => {
              const parent = document.querySelector('#tinyMCE-0_parent');
              return parent && visible(parent) ? parent : null;
            }, 7000);
            const textarea = document.querySelector('textarea#tinyMCE-0')
              || [...document.querySelectorAll('textarea')].find(el => (el.id || '').includes('tinyMCE'))
              || null;

            const tinymceApi = window.tinyMCE || window.tinymce || null;
            const editor = tinymceApi?.get?.('tinyMCE-0') || (tinymceApi?.activeEditor && String(tinymceApi.activeEditor.id || '').includes('tinyMCE') ? tinymceApi.activeEditor : null);

            if (!editorParent && !editor && !textarea) {
              return { ok: false, reason: 'legacy_editor_not_available' };
            }

            if (textarea) {
              setTextAreaValue(textarea, html);
              operations.push('legacy_textarea_written');
            }
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
                const body = typeof editor.getBody === 'function' ? editor.getBody() : null;
                if (body) {
                  body.innerHTML = html;
                  fireInputEvents(body);
                }
                operations.push('legacy_tinymce_written');
              } catch (err) {
                errors.push(`legacy_tinymce:${err?.message || err}`);
              }
            }

            const iframe = document.querySelector('iframe#tinyMCE-0_ifr, iframe[id*="tinyMCE-0"], iframe[id*="tinymce"], iframe[id*="mce"]');
            if (iframe?.contentDocument?.body) {
              try {
                iframe.contentDocument.body.innerHTML = html;
                fireInputEvents(iframe.contentDocument.body);
                operations.push('legacy_iframe_written');
              } catch (err) {
                errors.push(`legacy_iframe:${err?.message || err}`);
              }
            }

            await sleep(1200);
            let readback = '';
            if (textarea) readback += textarea.value || '';
            if (editor && typeof editor.getContent === 'function') {
              try { readback += '\n' + (editor.getContent() || ''); } catch (_) {}
            }
            if (iframe?.contentDocument?.body) readback += '\n' + (iframe.contentDocument.body.innerHTML || '');
            const visibleText = editorParent ? textOf(editorParent) : '';
            const ok = (readback + '\n' + visibleText).includes('产品说明') && (readback + '\n' + visibleText).includes('七天无理由退货');
            return { ok, readback_preview: (readback + '\n' + visibleText).replace(/\s+/g, ' ').slice(0, 600) };
          };

          const tryModernQuickText = async () => {
            const insertText = [...descBlock.querySelectorAll('button, [role="button"]')]
              .filter(visible)
              .find(btn => compactTextOf(btn).includes('插文本'));
            if (!insertText) return { ok: false, reason: 'insert_text_button_not_found' };
            clickElement(insertText);
            operations.push('modern_insert_text_clicked');
            await sleep(1800);

            const candidates = [...document.querySelectorAll('textarea, input:not([type="hidden"]), [contenteditable="true"]')]
              .filter(el => visible(el) && !el.disabled && !el.readOnly);
            const textTarget = candidates.find(el => {
              const local = compactTextOf(el.closest('[role="dialog"], .ant-modal, .next-dialog, .description-editor, .module-cbu-description') || el.parentElement || el);
              return local.includes('文本') || local.includes('内容') || local.includes('编辑') || local.includes('商品详情');
            }) || candidates[0] || null;

            if (textTarget) {
              if (textTarget.tagName === 'TEXTAREA') setTextAreaValue(textTarget, text);
              else if (textTarget.getAttribute('contenteditable') === 'true') {
                textTarget.innerHTML = html;
                fireInputEvents(textTarget);
              } else {
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                if (setter) setter.call(textTarget, text);
                else textTarget.value = text;
                fireInputEvents(textTarget);
              }
              operations.push('modern_text_target_written');
            }

            // Some versions open a same-origin iframe editor in a fullscreen overlay.
            const visibleIframes = [...document.querySelectorAll('iframe')].filter(visible);
            for (const iframe of visibleIframes) {
              try {
                const doc = iframe.contentDocument;
                if (!doc?.body) continue;
                const editable = [...doc.querySelectorAll('textarea, [contenteditable="true"], body')]
                  .find(el => visible(el) || el === doc.body);
                if (editable) {
                  if (editable.tagName === 'TEXTAREA') setTextAreaValue(editable, text);
                  else editable.innerHTML = html;
                  fireInputEvents(editable);
                  operations.push('modern_iframe_written');
                  break;
                }
              } catch (err) {
                errors.push(`modern_iframe:${err?.message || err}`);
              }
            }

            await sleep(800);
            const buttons = [...document.querySelectorAll('button, [role="button"], .ant-btn, .next-btn')].filter(visible);
            const done = buttons.find(btn => {
              const t = compactTextOf(btn);
              return ['确定', '确认', '完成', '保存', '插入'].some(label => t.includes(label)) && !t.includes('清空') && !t.includes('取消');
            });
            if (done) {
              clickElement(done);
              operations.push(`modern_done_clicked:${textOf(done)}`);
              await sleep(1500);
            }

            const previewText = textOf(descBlock);
            let iframeText = '';
            for (const iframe of [...descBlock.querySelectorAll('iframe')]) {
              try { iframeText += ' ' + textOf(iframe.contentDocument?.body); } catch (_) {}
            }
            const ok = (previewText + ' ' + iframeText).includes('产品说明') && (previewText + ' ' + iframeText).includes('七天无理由退货');
            return { ok, preview: (previewText + ' ' + iframeText).replace(/\s+/g, ' ').slice(0, 600) };
          };

          const legacy = await tryLegacyEditor();
          let modern = null;
          if (!legacy.ok) {
            modern = await tryModernQuickText();
          }

          const bodyText = textOf(descBlock);
          const finalOk = (legacy.ok || modern?.ok || bodyText.includes('产品说明')) && bodyText.includes('商品详情');
          return {
            ok: finalOk,
            strategy: legacy.ok ? 'legacy' : (modern?.ok ? 'modern_quick_text' : 'failed'),
            legacy,
            modern,
            operations,
            errors,
            desc_preview: bodyText.slice(0, 800),
          };
        }
        """,
        {"html": html, "text": text},
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
