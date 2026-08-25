from __future__ import annotations

import argparse
import json
import sys

from .client import Alibaba1688Client
from .config import Settings
from .images import validate_image_file
from .io import load_products
from .mapper import to_product_add_params, to_product_edit_patch
from .publisher import publish_batch
from .stock import parse_sku_changes, product_stock_change, sku_stock_change


def _live_client() -> Alibaba1688Client:
    return Alibaba1688Client(Settings.from_env(require_live=True))


def _print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


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
        _print_json(to_product_add_params(product))
    return 0


def cmd_publish(path: str, commit: bool, force: bool) -> int:
    products = load_products(path)

    if not commit:
        print("未指定 --commit，执行 dry-run。")
        return cmd_plan(path)

    client = _live_client()
    results = publish_batch(products, client, force=force)

    failed = sum(1 for item in results if item["status"] == "failed")
    success = sum(1 for item in results if item["status"] == "success")
    skipped = sum(1 for item in results if item["status"] == "skipped")

    print(f"\n完成：success={success}, skipped={skipped}, failed={failed}")
    return 1 if failed else 0


def cmd_category_attrs(category_id: int) -> int:
    _print_json(_live_client().category_attributes(category_id))
    return 0


def cmd_get_product(product_id: int) -> int:
    _print_json(_live_client().get_product(product_id))
    return 0


def cmd_list_products(
    page_no: int,
    page_size: int,
    statuses: list[str] | None,
    category_id: int | None,
    subject_key: str | None,
) -> int:
    _print_json(
        _live_client().list_products(
            page_no=page_no,
            page_size=page_size,
            status_list=statuses,
            category_id=category_id,
            subject_key=subject_key,
        )
    )
    return 0


def cmd_edit(product_id: int, path: str, commit: bool) -> int:
    products = load_products(path)
    if len(products) != 1:
        raise ValueError("edit 命令要求输入文件中恰好 1 个商品")

    patch = to_product_edit_patch(products[0])

    if not commit:
        _print_json(
            {
                "productID": product_id,
                "productInfoPatch": patch,
                "webSite": "1688",
                "note": "commit 时会先 get-product，再覆盖这些字段后调用 edit",
            }
        )
        print("\n未指定 --commit，只输出编辑补丁。")
        return 0

    client = _live_client()
    current = client.get_product(product_id)
    product_info = current.get("productInfo") or current.get("product")
    if not isinstance(product_info, dict):
        raise RuntimeError(f"无法从 alibaba.product.get 响应提取 productInfo: {current}")

    merged = dict(product_info)
    merged.update(patch)
    merged["productID"] = product_id

    _print_json(client.edit_product(product_id, merged))
    return 0


def cmd_stock(
    product_id: int,
    amount_change: int | None,
    sku_values: list[str],
    incremental: bool,
    commit: bool,
) -> int:
    if amount_change is not None and sku_values:
        raise ValueError("--amount-change 与 --sku 不能同时使用")
    if amount_change is None and not sku_values:
        raise ValueError("必须提供 --amount-change 或至少一个 --sku")

    if sku_values:
        change = sku_stock_change(product_id, parse_sku_changes(sku_values))
    else:
        change = product_stock_change(product_id, int(amount_change))

    request = {
        "productStockChange": [change],
        "increaseModify": incremental,
        "webSite": "1688",
    }

    if not commit:
        _print_json(request)
        print("\n未指定 --commit，只输出库存请求。")
        return 0

    _print_json(_live_client().modify_stock([change], incremental=incremental))
    return 0


def cmd_image_check(path: str) -> int:
    _print_json(validate_image_file(path))
    return 0


def cmd_photo_add(
    path: str,
    name: str | None,
    album_id: int | None,
    description: str | None,
    draw_text: bool,
    commit: bool,
) -> int:
    info = validate_image_file(path)
    plan = {
        **info,
        "api": "alibaba.photobank.photo.add",
        "name": name,
        "albumID": album_id,
        "description": description,
        "drawTxt": draw_text,
        "webSite": "1688",
    }

    if not commit:
        _print_json(plan)
        print("\n未指定 --commit，只做图片上传预检。")
        return 0

    _print_json(
        _live_client().add_photo(
            path,
            name=name,
            album_id=album_id,
            description=description,
            draw_text=draw_text,
        )
    )
    return 0


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

    p_cat = sub.add_parser("category-attrs", help="查询叶子类目及父类目的发布属性")
    p_cat.add_argument("category_id", type=int)

    p_get = sub.add_parser("get-product", help="查询自己店铺中的一个商品")
    p_get.add_argument("product_id", type=int)

    p_list = sub.add_parser("list-products", help="分页查询自己店铺的商品")
    p_list.add_argument("--page-no", type=int, default=1)
    p_list.add_argument("--page-size", type=int, default=20)
    p_list.add_argument("--status", action="append", dest="statuses")
    p_list.add_argument("--category-id", type=int)
    p_list.add_argument("--subject-key")

    p_edit = sub.add_parser("edit", help="编辑已有商品")
    p_edit.add_argument("product_id", type=int)
    p_edit.add_argument("path")
    p_edit.add_argument("--commit", action="store_true")

    p_stock = sub.add_parser("stock", help="修改商品或 SKU 库存")
    p_stock.add_argument("product_id", type=int)
    p_stock.add_argument("--amount-change", type=int)
    p_stock.add_argument(
        "--sku",
        action="append",
        default=[],
        help="SKU库存变化，格式 <skuId>:<change>，可重复",
    )
    p_stock.add_argument(
        "--incremental",
        action="store_true",
        help="将 increaseModify 设置为 true",
    )
    p_stock.add_argument("--commit", action="store_true")

    p_image = sub.add_parser("image-check", help="检查图片格式和 2MB 限制")
    p_image.add_argument("path")

    p_photo = sub.add_parser("photo-add", help="上传图片到 1688 图片银行")
    p_photo.add_argument("path")
    p_photo.add_argument("--name")
    p_photo.add_argument("--album-id", type=int)
    p_photo.add_argument("--description")
    p_photo.add_argument("--draw-text", action="store_true")
    p_photo.add_argument("--commit", action="store_true")

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
        if args.command == "category-attrs":
            return cmd_category_attrs(args.category_id)
        if args.command == "get-product":
            return cmd_get_product(args.product_id)
        if args.command == "list-products":
            return cmd_list_products(
                args.page_no,
                args.page_size,
                args.statuses,
                args.category_id,
                args.subject_key,
            )
        if args.command == "edit":
            return cmd_edit(args.product_id, args.path, args.commit)
        if args.command == "stock":
            return cmd_stock(
                args.product_id,
                args.amount_change,
                args.sku,
                args.incremental,
                args.commit,
            )
        if args.command == "image-check":
            return cmd_image_check(args.path)
        if args.command == "photo-add":
            return cmd_photo_add(
                args.path,
                args.name,
                args.album_id,
                args.description,
                args.draw_text,
                args.commit,
            )
        parser.error("unknown command")
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
