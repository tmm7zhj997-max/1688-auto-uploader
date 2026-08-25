from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from .client import Alibaba1688Client
from .mapper import to_product_add_params
from .models import Product


class ResultStore:
    def __init__(self, path: str | Path = "runtime/publish-results.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def successful_external_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        success: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") == "success" and row.get("external_id"):
                success.add(row["external_id"])
        return success

    def append(self, row: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def publish_batch(
    products: list[Product],
    client: Alibaba1688Client,
    *,
    force: bool = False,
    max_attempts: int = 3,
    base_delay_seconds: float = 2.0,
) -> list[dict[str, Any]]:
    store = ResultStore()
    already_done = store.successful_external_ids()
    results: list[dict[str, Any]] = []

    for index, product in enumerate(products, start=1):
        if product.external_id in already_done and not force:
            row = {
                "external_id": product.external_id,
                "status": "skipped",
                "reason": "already_published",
            }
            results.append(row)
            print(f"[{index}/{len(products)}] SKIP {product.external_id}")
            continue

        params = to_product_add_params(product)
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = client.add_product(params)
                product_id = (
                    response.get("productID")
                    or response.get("productId")
                    or response.get("result", {}).get("productID")
                    if isinstance(response, dict)
                    else None
                )
                row = {
                    "external_id": product.external_id,
                    "status": "success",
                    "attempt": attempt,
                    "product_id": product_id,
                    "response": response,
                }
                store.append(row)
                results.append(row)
                print(f"[{index}/{len(products)}] OK   {product.external_id} -> {product_id}")
                break
            except Exception as exc:
                last_error = str(exc)
                print(
                    f"[{index}/{len(products)}] FAIL {product.external_id} "
                    f"attempt={attempt}/{max_attempts}: {last_error}"
                )
                if attempt < max_attempts:
                    time.sleep(base_delay_seconds * (2 ** (attempt - 1)))
        else:
            row = {
                "external_id": product.external_id,
                "status": "failed",
                "error": last_error,
            }
            store.append(row)
            results.append(row)

    return results
