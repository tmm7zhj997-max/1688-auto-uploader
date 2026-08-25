from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .models import Product


DEFAULT_SELLER_URL = "https://work.1688.com/"
DEFAULT_PROFILE_DIR = Path("runtime/browser-profile")
DEFAULT_INSPECT_DIR = Path("runtime/browser-inspect")
DEFAULT_RESULTS_PATH = Path("runtime/browser-results.jsonl")


@dataclass(frozen=True)
class BrowserOptions:
    profile_dir: Path = DEFAULT_PROFILE_DIR
    headless: bool = False
    channel: str | None = None
    timeout_ms: int = 30_000

    @classmethod
    def from_env(cls) -> "BrowserOptions":
        channel = os.getenv("ALI1688_BROWSER_CHANNEL", "").strip() or None
        return cls(
            profile_dir=Path(
                os.getenv("ALI1688_BROWSER_PROFILE_DIR", str(DEFAULT_PROFILE_DIR))
            ),
            headless=os.getenv("ALI1688_BROWSER_HEADLESS", "0").strip() in {"1", "true", "TRUE"},
            channel=channel,
            timeout_ms=int(os.getenv("ALI1688_BROWSER_TIMEOUT_MS", "30000")),
        )


@dataclass(frozen=True)
class SelectorProfile:
    publish_url: str
    selectors: dict[str, str]
    wait_after_submit_ms: int = 3_000

    @classmethod
    def load(cls, path: str | Path) -> "SelectorProfile":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("浏览器 selector profile 必须是 JSON object")
        publish_url = str(payload.get("publish_url") or "").strip()
        selectors = payload.get("selectors") or {}
        if not isinstance(selectors, dict):
            raise ValueError("selectors 必须是 JSON object")
        return cls(
            publish_url=publish_url,
            selectors={str(k): str(v) for k, v in selectors.items() if str(v).strip()},
            wait_after_submit_ms=int(payload.get("wait_after_submit_ms", 3000)),
        )


@contextmanager
def persistent_context(options: BrowserOptions) -> Iterator[Any]:
    """Launch a persistent Playwright browser context."""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "缺少 Playwright。请执行 `pip install -e .`，然后执行 "
            "`python -m playwright install chromium`。"
        ) from exc

    options.profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        launch_kwargs: dict[str, Any] = {
            "user_data_dir": str(options.profile_dir),
            "headless": options.headless,
            "viewport": {"width": 1440, "height": 960},
        }
        if options.channel:
            launch_kwargs["channel"] = options.channel
        context = playwright.chromium.launch_persistent_context(**launch_kwargs)
        context.set_default_timeout(options.timeout_ms)
        try:
            yield context
        finally:
            context.close()


def manual_login(url: str | None = None, *, options: BrowserOptions | None = None) -> None:
    options = options or BrowserOptions.from_env()
    target = (url or os.getenv("ALI1688_BROWSER_HOME_URL") or DEFAULT_SELLER_URL).strip()
    with persistent_context(options) as context:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(target, wait_until="domcontentloaded")
        print("浏览器已打开。请在浏览器里手工完成 1688 登录/短信/扫码等正常验证。")
        print("不要关闭终端。确认已进入卖家工作台后，回到终端按 Enter 保存会话并退出。")
        input()


def _control_snapshot_script() -> str:
    return r"""
(elements) => elements.map((el, index) => {
  const rect = el.getBoundingClientRect();
  const visible = !!(rect.width || rect.height) && getComputedStyle(el).visibility !== 'hidden';
  const text = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 240);
  return {
    index,
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type'),
    id: el.id || null,
    name: el.getAttribute('name'),
    placeholder: el.getAttribute('placeholder'),
    ariaLabel: el.getAttribute('aria-label'),
    role: el.getAttribute('role'),
    contentEditable: el.getAttribute('contenteditable'),
    text,
    visible,
    disabled: !!el.disabled,
    valuePreview: typeof el.value === 'string' ? el.value.slice(0, 120) : null,
    html: el.outerHTML.slice(0, 700)
  };
})
"""


def inspect_page(
    url: str,
    *,
    options: BrowserOptions | None = None,
    output_root: str | Path = DEFAULT_INSPECT_DIR,
    pause_seconds: float = 2.0,
) -> Path:
    if not url.strip():
        raise ValueError("browser-inspect 必须提供商品发布页 URL")

    options = options or BrowserOptions.from_env()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(output_root) / stamp
    out.mkdir(parents=True, exist_ok=True)

    with persistent_context(options) as context:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(int(pause_seconds * 1000))

        controls = page.locator(
            "input, textarea, select, button, [role='button'], [contenteditable='true']"
        ).evaluate_all(_control_snapshot_script())
        manifest = {
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "url": page.url,
            "title": page.title(),
            "control_count": len(controls),
            "profile_dir": str(options.profile_dir),
        }

        (out / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out / "controls.json").write_text(
            json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out / "page.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(out / "page.png"), full_page=True)

    return out


def browser_plan(product: Product, source_path: str | Path | None = None) -> dict[str, Any]:
    base = Path(source_path).resolve().parent if source_path else Path.cwd()
    resolved_images: list[str] = []
    missing_images: list[str] = []
    for value in product.images:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = base / candidate
        if candidate.exists() and candidate.is_file():
            resolved_images.append(str(candidate.resolve()))
        else:
            missing_images.append(value)

    first_sku = product.skus[0] if product.skus else None
    price = None
    if first_sku is not None:
        price = first_sku.price
        if price is None and first_sku.priceRange:
            price = first_sku.priceRange[0].price

    return {
        "external_id": product.external_id,
        "subject": product.subject,
        "category_id": product.category_id,
        "description_length": len(product.description),
        "local_images": resolved_images,
        "missing_or_remote_images": missing_images,
        "sku_count": len(product.skus),
        "first_sku_price": price,
        "amount_on_sale": product.sale_info.amountOnSale,
        "unit": product.sale_info.unit,
        "min_order_quantity": product.sale_info.minOrderQuantity,
        "note": (
            "浏览器模式要求 images 是本机图片路径。类目/SKU 动态控件需要先运行 "
            "browser-inspect 校准当前账号的发布页。"
        ),
    }


def _fill_if_configured(
    page: Any,
    selectors: dict[str, str],
    key: str,
    value: Any,
    *,
    commit_events: bool = False,
) -> str | None:
    selector = selectors.get(key)
    if not selector or value is None:
        return None
    locator = page.locator(selector).first
    locator.wait_for(state="visible")
    locator.scroll_into_view_if_needed()
    locator.click()
    locator.fill(str(value))
    if commit_events:
        locator.dispatch_event("input")
        locator.dispatch_event("change")
        locator.press("Tab")
        page.wait_for_timeout(500)
    return locator.input_value()


def _first_sku_price(product: Product) -> float | None:
    if not product.skus:
        return None
    sku = product.skus[0]
    if sku.price is not None:
        return sku.price
    if sku.priceRange:
        return sku.priceRange[0].price
    return None


def fill_product_form(
    page: Any,
    product: Product,
    profile: SelectorProfile,
    *,
    source_path: str | Path,
) -> dict[str, Any]:
    selectors = profile.selectors
    actions: list[str] = []
    readback: dict[str, str] = {}

    subject_value = _fill_if_configured(page, selectors, "subject", product.subject)
    if subject_value is not None:
        actions.append("subject")
        readback["subject"] = subject_value

    description_value = _fill_if_configured(
        page, selectors, "description", product.description, commit_events=True
    )
    if description_value is not None:
        actions.append("description")
        readback["description"] = description_value

    price_value = _fill_if_configured(
        page, selectors, "price", _first_sku_price(product), commit_events=True
    )
    if price_value is not None:
        actions.append("price")
        readback["price"] = price_value

    stock_value = _fill_if_configured(
        page, selectors, "stock", product.sale_info.amountOnSale, commit_events=True
    )
    if stock_value is not None:
        actions.append("stock")
        readback["stock"] = stock_value

    unit_value = _fill_if_configured(
        page, selectors, "unit", product.sale_info.unit, commit_events=True
    )
    if unit_value is not None:
        actions.append("unit")
        readback["unit"] = unit_value

    min_order_value = _fill_if_configured(
        page,
        selectors,
        "min_order_quantity",
        product.sale_info.minOrderQuantity,
        commit_events=True,
    )
    if min_order_value is not None:
        actions.append("min_order_quantity")
        readback["min_order_quantity"] = min_order_value

    image_selector = selectors.get("image_input")
    if image_selector:
        base = Path(source_path).resolve().parent
        image_paths: list[str] = []
        for value in product.images:
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = base / candidate
            if not candidate.exists():
                raise FileNotFoundError(f"浏览器上传图片不存在: {candidate}")
            image_paths.append(str(candidate.resolve()))
        page.locator(image_selector).first.set_input_files(image_paths)
        actions.append(f"images:{len(image_paths)}")

    page.wait_for_timeout(1000)
    return {
        "external_id": product.external_id,
        "actions": actions,
        "readback": readback,
        "unhandled": [
            "category" if "category" not in selectors else None,
            "attributes" if "attributes" not in selectors else None,
            "sku_matrix" if "sku_matrix" not in selectors else None,
            "shipping" if "shipping" not in selectors else None,
        ],
    }


def publish_one_browser(
    product: Product,
    profile: SelectorProfile,
    *,
    source_path: str | Path,
    options: BrowserOptions | None = None,
    commit: bool = False,
    fill_only: bool = False,
) -> dict[str, Any]:
    if commit and fill_only:
        raise ValueError("--commit 与 --fill-only 不能同时使用")
    if not profile.publish_url:
        raise ValueError("selector profile 缺少 publish_url")

    if not commit and not fill_only:
        return {
            "status": "dry-run",
            "plan": browser_plan(product, source_path),
            "publish_url": profile.publish_url,
            "configured_selectors": sorted(profile.selectors),
        }

    options = options or BrowserOptions.from_env()
    with persistent_context(options) as context:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(profile.publish_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        result = fill_product_form(page, product, profile, source_path=source_path)

        evidence_dir = Path("runtime/browser-evidence")
        evidence_dir.mkdir(parents=True, exist_ok=True)
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in product.external_id)
        before_path = evidence_dir / f"{safe_id}-before-submit.png"
        page.screenshot(path=str(before_path), full_page=True)
        result["before_submit_screenshot"] = str(before_path)

        if fill_only:
            result["status"] = "filled-not-submitted"
            print("表单已填充但未提交。请在浏览器人工检查，完成后回终端按 Enter。")
            input()
            return result

        submit_selector = profile.selectors.get("submit")
        if not submit_selector:
            raise RuntimeError("--commit 需要 selector profile 配置 selectors.submit")

        page.locator(submit_selector).first.click()
        page.wait_for_timeout(profile.wait_after_submit_ms)
        after_path = evidence_dir / f"{safe_id}-after-submit.png"
        page.screenshot(path=str(after_path), full_page=True)
        result.update(
            {
                "status": "submitted",
                "after_submit_screenshot": str(after_path),
                "final_url": page.url,
                "page_title": page.title(),
            }
        )
        return result


def append_browser_result(result: dict[str, Any], path: str | Path = DEFAULT_RESULTS_PATH) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"time": datetime.now().isoformat(timespec="seconds"), **result}
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
