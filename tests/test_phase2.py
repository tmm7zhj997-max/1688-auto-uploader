from pathlib import Path

import pytest

from ali1688_uploader.client import Alibaba1688Client
from ali1688_uploader.config import Settings
from ali1688_uploader.images import validate_image_file
from ali1688_uploader.io import load_products
from ali1688_uploader.mapper import to_product_edit_patch
from ali1688_uploader.stock import (
    parse_sku_changes,
    product_stock_change,
    sku_stock_change,
)


def test_product_stock_change():
    assert product_stock_change(123, 5) == {
        "productId": 123,
        "productAmountChange": 5,
        "skuStocks": [],
    }


def test_sku_stock_change():
    assert sku_stock_change(123, [("abc", 5), ("def", -2)]) == {
        "productId": 123,
        "skuStocks": [
            {"skuId": "abc", "stockChange": 5},
            {"skuId": "def", "stockChange": -2},
        ],
    }


def test_parse_sku_changes():
    assert parse_sku_changes(["abc:5", "def:-2"]) == [("abc", 5), ("def", -2)]


def test_rejects_wrong_extension(tmp_path: Path):
    file = tmp_path / "a.txt"
    file.write_bytes(b"x")
    with pytest.raises(ValueError):
        validate_image_file(file)


def test_accepts_small_jpg(tmp_path: Path):
    file = tmp_path / "a.jpg"
    file.write_bytes(b"preflight-only")
    info = validate_image_file(file)
    assert info["size_bytes"] > 0
    assert info["mime_type"] == "image/jpeg"


def test_edit_patch_excludes_website():
    product = load_products("data/example_products.jsonl")[0]
    patch = to_product_edit_patch(product)
    assert "webSite" not in patch
    assert patch["subject"] == product.subject
    assert patch["categoryID"] == product.category_id


def test_list_page_size_is_capped_before_network():
    client = Alibaba1688Client(Settings(app_key="", app_secret="", access_token=""))
    with pytest.raises(ValueError):
        client.list_products(page_size=21)
