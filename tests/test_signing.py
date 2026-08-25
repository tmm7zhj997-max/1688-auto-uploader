from ali1688_uploader.client import compute_signature


def test_signature_is_stable():
    api = "param2/1/com.example/alibaba.product.add/123456"
    params = {
        "access_token": "token",
        "_aop_timestamp": 1700000000000,
        "subject": "测试商品",
        "categoryID": 123,
    }
    sig = compute_signature(api, params, "secret")
    assert sig == "E36FCE9255F3342C5644055759AE31A51A53F472"
