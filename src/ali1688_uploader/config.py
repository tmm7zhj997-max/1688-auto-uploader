from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    app_key: str
    app_secret: str
    access_token: str
    product_add_api: str
    gateway: str = "https://gw.open.1688.com"
    api_version: str = "1"
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls, require_live: bool = False) -> "Settings":
        load_dotenv()

        settings = cls(
            app_key=os.getenv("ALI1688_APP_KEY", "").strip(),
            app_secret=os.getenv("ALI1688_APP_SECRET", "").strip(),
            access_token=os.getenv("ALI1688_ACCESS_TOKEN", "").strip(),
            product_add_api=os.getenv("ALI1688_PRODUCT_ADD_API", "").strip(),
            gateway=os.getenv("ALI1688_GATEWAY", "https://gw.open.1688.com").rstrip("/"),
            api_version=os.getenv("ALI1688_API_VERSION", "1").strip() or "1",
            timeout_seconds=int(os.getenv("ALI1688_TIMEOUT_SECONDS", "30")),
        )

        if require_live:
            missing = [
                name
                for name, value in [
                    ("ALI1688_APP_KEY", settings.app_key),
                    ("ALI1688_APP_SECRET", settings.app_secret),
                    ("ALI1688_ACCESS_TOKEN", settings.access_token),
                    ("ALI1688_PRODUCT_ADD_API", settings.product_add_api),
                ]
                if not value
            ]
            if missing:
                raise RuntimeError("缺少直播配置: " + ", ".join(missing))

        return settings
