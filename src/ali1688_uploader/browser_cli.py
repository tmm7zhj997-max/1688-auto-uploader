from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .browser_automation import (
    BrowserOptions,
    SelectorProfile,
    append_browser_result,
    browser_plan,
    inspect_page,
    manual_login,
    publish_one_browser,
)
from .io import load_products
from .sku_importer import import_husky_xlsx, save_normalized_json


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def cmd_login(url: str | None) -> int:
    manual_login(url, options=BrowserOptions.from_env())
    print("浏览器会话已保存到本地 profile。")
    return 0


def cmd_inspect(url: str) -> int:
    out = inspect_page(url, options=BrowserOptions.from_env())
    _print_json(
        {
            "output_dir": str(out),
            "screenshot": str(out / "page.png"),
            "controls": str(out / "controls.json"),
            "html": str(out / "page.html"),
        }
    )
    print("请保留这些文件。下一步用它们校准当前账号/类目的发布页选择器。")
    return 0


def cmd_plan(path: str, limit: int | None) -> int:
    products = load_products(path)
    if limit is not None:
        products = products[:limit]
    for product in products:
        _print_json(browser_plan(product, path))
    return 0


def cmd_sku_import(path: str, output: str | None, sheet: str | None) -> int:
    data = import_husky_xlsx(path, sheet_name=sheet)
    if output:
        target = save_normalized_json(data, output)
    else:
        source = Path(path)
        target = save_normalized_json(
            data,
            Path("runtime/sku-import") / f"{source.stem}.normalized.json",
        )
    summary = {
        "source": path,
        "output": str(target),
        "sku_count": data["sku_count"],
        "axes": data["axes"],
        "common_specs": data["common_specs"],
        "price_min": min(row["price"] for row in data["rows"]),
        "price_max": max(row["price"] for row in data["rows"]),
        "stock_total": sum(row["stock"] for row in data["rows"]),
    }
    _print_json(summary)
    return 0


def cmd_publish(
    path: str,
    profile_path: str,
    url: str | None,
    limit: int | None,
    commit: bool,
    fill_only: bool,
) -> int:
    products = load_products(path)
    if limit is not None:
        products = products[:limit]
    if fill_only and len(products) != 1:
        raise ValueError("--fill-only 为人工检查模式，一次只能处理 1 个商品；请加 --limit 1")

    profile = SelectorProfile.load(profile_path)
    if url:
        profile = SelectorProfile(
            publish_url=url.strip(),
            selectors=profile.selectors,
            wait_after_submit_ms=profile.wait_after_submit_ms,
        )
    failed = 0
    for product in products:
        try:
            result = publish_one_browser(
                product,
                profile,
                source_path=path,
                options=BrowserOptions.from_env(),
                commit=commit,
                fill_only=fill_only,
            )
        except Exception as exc:
            result = {
                "external_id": product.external_id,
                "status": "failed",
                "error": str(exc),
            }
            failed += 1
        append_browser_result(result)
        _print_json(result)
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="1688 Playwright 浏览器自动化（人工登录会话 + 可校准发布页）"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="打开浏览器，人工登录一次并保存会话")
    p_login.add_argument("--url", help="卖家工作台入口；默认使用 work.1688.com")

    p_inspect = sub.add_parser("inspect", help="抓取当前商品发布页截图/DOM/控件清单")
    p_inspect.add_argument("--url", required=True, help="你当前账号的真实商品发布页 URL")

    p_plan = sub.add_parser("plan", help="仅生成浏览器上架计划，不打开浏览器")
    p_plan.add_argument("path")
    p_plan.add_argument("--limit", type=int)

    p_sku = sub.add_parser("sku-import", help="导入哈士奇导出的 SKU Excel 并标准化")
    p_sku.add_argument("path", help="哈士奇导出的 .xlsx 文件")
    p_sku.add_argument("--sheet", help="工作表名称；默认第一个工作表")
    p_sku.add_argument("--output", help="标准化 JSON 输出路径")

    p_publish = sub.add_parser("publish", help="按 selector profile 填写/提交商品表单")
    p_publish.add_argument("path")
    p_publish.add_argument(
        "--profile",
        default="browser_profiles/1688-current.json",
        help="当前发布页 selector profile JSON",
    )
    p_publish.add_argument(
        "--url",
        help="覆盖 profile 中的发布页 URL；建议粘贴当前真实发布页完整 URL",
    )
    p_publish.add_argument("--limit", type=int)
    mode = p_publish.add_mutually_exclusive_group()
    mode.add_argument(
        "--fill-only",
        action="store_true",
        help="填写 1 个商品后停住让人工检查，不点击发布",
    )
    mode.add_argument(
        "--commit",
        action="store_true",
        help="真正点击 selector profile 中配置的提交按钮",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "login":
            return cmd_login(args.url)
        if args.command == "inspect":
            return cmd_inspect(args.url)
        if args.command == "plan":
            return cmd_plan(args.path, args.limit)
        if args.command == "sku-import":
            return cmd_sku_import(args.path, args.output, args.sheet)
        if args.command == "publish":
            return cmd_publish(
                args.path,
                args.profile,
                args.url,
                args.limit,
                args.commit,
                args.fill_only,
            )
        return 2
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
