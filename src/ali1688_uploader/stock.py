from __future__ import annotations

from typing import Any


def product_stock_change(product_id: int, amount_change: int) -> dict[str, Any]:
    if amount_change == 0:
        raise ValueError("库存变化量不能为 0")
    return {
        "productId": product_id,
        "productAmountChange": amount_change,
        "skuStocks": [],
    }


def sku_stock_change(
    product_id: int,
    changes: list[tuple[str, int]],
) -> dict[str, Any]:
    if not changes:
        raise ValueError("至少需要一个 SKU 库存变化")

    sku_stocks = []
    for sku_id, change in changes:
        if not sku_id:
            raise ValueError("skuId 不能为空")
        if change == 0:
            raise ValueError(f"SKU {sku_id} 的库存变化量不能为 0")
        sku_stocks.append({"skuId": sku_id, "stockChange": change})

    return {
        "productId": product_id,
        "skuStocks": sku_stocks,
    }


def parse_sku_changes(values: list[str]) -> list[tuple[str, int]]:
    changes: list[tuple[str, int]] = []
    for value in values:
        try:
            sku_id, raw_change = value.rsplit(":", 1)
            change = int(raw_change)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"SKU 库存格式错误: {value!r}，应为 <skuId>:<change>"
            ) from exc
        changes.append((sku_id, change))
    return changes
