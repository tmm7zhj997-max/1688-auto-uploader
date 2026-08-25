from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ali1688_uploader.client import compute_signature

sig = compute_signature(
    "param2/1/com.example/alibaba.product.add/123456",
    {
        "access_token": "token",
        "_aop_timestamp": 1700000000000,
        "subject": "测试商品",
        "categoryID": 123,
    },
    "secret",
)
assert len(sig) == 40
assert sig.upper() == sig
print("signature smoke test OK:", sig)
