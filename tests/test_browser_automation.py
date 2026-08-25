from __future__ import annotations

import json

from ali1688_uploader.browser_automation import SelectorProfile, browser_plan
from ali1688_uploader.models import Product


def _product(image_path: str) -> Product:
    return Product.model_validate(
        {
            "external_id": "BROWSER-001",
            "category_id": 123,
            "subject": "浏览器测试商品",
            "description": "详情",
            "attributes": [],
            "images": [image_path],
            "skus": [
                {
                    "cargoNumber": "SKU-1",
                    "amountOnSale": 8,
                    "price": 19.9,
                    "retailPrice": 29.9,
                    "consignPrice": 19.9,
                    "attributes": [],
                }
            ],
            "sale_info": {
                "supportOnlineTrade": True,
                "mixWholeSale": False,
                "saleType": "normal",
                "priceAuth": False,
                "priceRanges": [{"startQuantity": 1, "price": 19.9}],
                "amountOnSale": 8,
                "unit": "件",
                "minOrderQuantity": 1,
                "quoteType": 1,
            },
            "shipping_info": {
                "freightTemplateID": 1,
                "unitWeight": 0.5,
                "sendGoodsAddressId": 1,
                "sendGoodsAddressText": "测试地址",
            },
        }
    )


def test_browser_plan_resolves_local_image(tmp_path):
    data_dir = tmp_path / "data"
    image_dir = data_dir / "images"
    image_dir.mkdir(parents=True)
    image = image_dir / "one.jpg"
    image.write_bytes(b"fake-image-for-path-test")
    source = data_dir / "products.jsonl"
    source.write_text("", encoding="utf-8")

    plan = browser_plan(_product("images/one.jpg"), source)

    assert plan["external_id"] == "BROWSER-001"
    assert plan["local_images"] == [str(image.resolve())]
    assert plan["missing_or_remote_images"] == []
    assert plan["first_sku_price"] == 19.9


def test_selector_profile_loads_only_nonempty_selectors(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(
        json.dumps(
            {
                "publish_url": "https://example.invalid/publish",
                "wait_after_submit_ms": 1234,
                "selectors": {
                    "subject": "input[name=title]",
                    "submit": "",
                },
            }
        ),
        encoding="utf-8",
    )

    profile = SelectorProfile.load(path)

    assert profile.publish_url == "https://example.invalid/publish"
    assert profile.wait_after_submit_ms == 1234
    assert profile.selectors == {"subject": "input[name=title]"}
