from __future__ import annotations

import argparse
import json
import sys

from .client import Alibaba1688Client
from .config import Settings
from .io import load_products
from .mapper import to_product_add_params
from .publisher import publish_batch


def cmd_validate(path: str) -> int:
    products = load_products(path)
    print(f"校验通过：{len(products)} 个商品")
    for p in products:
        print(f"- {p.external_id}: {p.subject}")
    return 0


def cmd_plan(path: str) -> int:
    products = load_products(path)
    for product in products:
        print("=" * 80)
        print(f"external_id: {product.external_id}")
        print(json.dumps(to_product_add_params(product), ensure_ascii=False, indent=2))
    return 0


def cmd_publish(path: str, commit: bool, force: bool) -> int:
    products = load_products(path)

    if not commit:
        print("未指定 --commit，执行 dry-run。")
        return cmd_plan(path)

    settings = Settings.from_env(require_live=True)
    client = Alibaba1688Client(settings)
    results = publish_batch(products, client, force=force)

    failed = sum(1 for item in results if item["status"] == "failed")
    success = sum(1 for item in results if item["status"] == "success")
    skipped = sum(1 for item in results if item["status"] == "skipped")

    print(f"\n完成：success={success}, skipped={skipped}, failed={failed}")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="1688 自动上架商品")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="校验商品数据")
    p_validate.add_argument("path")

    p_plan = sub.add_parser("plan", help="输出 1688 发布参数，不发请求")
    p_plan.add_argument("path")

    p_publish = sub.add_parser("publish", help="批量发布商品")
    p_publish.add_argument("path")
    p_publish.add_argument("--commit", action="store_true", help="真正调用 1688")
    p_publish.add_argument("--force", action="store_true", help="忽略本地成功记录，强制重发")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "validate":
            return cmd_validate(args.path)
        if args.command == "plan":
            return cmd_plan(args.path)
        if args.command == "publish":
            return cmd_publish(args.path, args.commit, args.force)
        parser.error("unknown command")
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
