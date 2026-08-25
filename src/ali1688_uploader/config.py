from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    app_key: str
    app_secret: str
    access_token: str

    gateway: str = "https://gw.open.1688.com"
    api_version: str = "1"
    timeout_seconds: int = 30

    category_attr_api: str = "category.level.attr.get"
    product_add_api: str = "alibaba.product.add"
    product_edit_api: str = "alibaba.product.edit"
    product_stock_api: str = "alibaba.product.modifyStock"
    product_get_api: str = "alibaba.product.get"
    product_list_api: str = "alibaba.product.list.get"
    photobank_photo_add_api: str = "alibaba.photobank.photo.add"

    @classmethod
    def from_env(cls, require_live: bool = False) -> "Settings":
        load_dotenv()

        settings = cls(
            app_key=os.getenv("ALI1688_APP_KEY", "").strip(),
            app_secret=os.getenv("ALI1688_APP_SECRET", "").strip(),
            access_token=os.getenv("ALI1688_ACCESS_TOKEN", "").strip(),
            gateway=os.getenv("ALI1688_GATEWAY", "https://gw.open.1688.com").rstrip("/"),
            api_version=os.getenv("ALI1688_API_VERSION", "1").strip() or "1",
            timeout_seconds=int(os.getenv("ALI1688_TIMEOUT_SECONDS", "30")),
            category_attr_api=os.getenv(
                "ALI1688_CATEGORY_ATTR_API", "category.level.attr.get"
            ).strip(),
            product_add_api=os.getenv(
                "ALI1688_PRODUCT_ADD_API", "alibaba.product.add"
            ).strip(),
            product_edit_api=os.getenv(
                "ALI1688_PRODUCT_EDIT_API", "alibaba.product.edit"
            ).strip(),
            product_stock_api=os.getenv(
                "ALI1688_PRODUCT_STOCK_API", "alibaba.product.modifyStock"
            ).strip(),
            product_get_api=os.getenv(
                "ALI1688_PRODUCT_GET_API", "alibaba.product.get"
            ).strip(),
            product_list_api=os.getenv(
                "ALI1688_PRODUCT_LIST_API", "alibaba.product.list.get"
            ).strip(),
            photobank_photo_add_api=os.getenv(
                "ALI1688_PHOTOBANK_PHOTO_ADD_API", "alibaba.photobank.photo.add"
            ).strip(),
        )

        if require_live:
            missing = [
                name
                for name, value in [
                    ("ALI1688_APP_KEY", settings.app_key),
                    ("ALI1688_APP_SECRET", settings.app_secret),
                    ("ALI1688_ACCESS_TOKEN", settings.access_token),
                ]
                if not value
            ]
            if missing:
                raise RuntimeError("缺少直播配置: " + ", ".join(missing))

        return settings
