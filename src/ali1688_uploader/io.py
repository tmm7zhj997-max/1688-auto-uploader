from __future__ import annotations

from pathlib import Path
import json

from .models import Product


def load_products(path: str | Path) -> list[Product]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    products: list[Product] = []

    if path.suffix.lower() == ".jsonl":
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                products.append(Product.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"{path}:{lineno} 商品数据无效: {exc}") from exc
        return products

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = [data]
        return [Product.model_validate(item) for item in data]

    raise ValueError("当前仅支持 .json 或 .jsonl")
