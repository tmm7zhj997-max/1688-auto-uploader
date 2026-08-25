# 1688 自动上架商品（官方开放平台优先）

一个面向 **阿里巴巴国内站 / 1688** 的批量商品发布骨架。

设计目标：

- 官方开放平台 API 优先，不依赖易失效的后台页面 DOM。
- 商品数据先标准化，再映射到 `alibaba.product.add`。
- 默认 `dry-run`，只有显式 `--commit` 才真正发请求。
- 支持 JSONL 批量导入、字段校验、重试、结果日志。
- API 路径可配置，避免把不同应用/市场下的接口命名硬编码死。
- AppKey、AppSecret、AccessToken 只从环境变量读取，不写入仓库。

## 已确认的 1688 商品发布字段

官方 1688 Cloud Hub API Reference 中，`alibaba.product.add` 用于发布商品，核心参数包含：

- `productType`：如 `wholesale`
- `categoryID`
- `webSite`：固定 `1688`
- `subject`：商品标题
- `description`
- `language`：固定 `CHINESE`
- `attributes`
- `image`
- `skuInfos`
- `saleInfo`
- `shippingInfo`

其中 `saleInfo` 可表达阶梯价、起订量、销售单位等；`shippingInfo` 可表达运费模板、单位重量、发货地址。

> 注意：不同 1688 开放平台应用可能拿到不同 API 权限和调用路径。
> 因此本项目不强行假设发布接口的 namespace，而是要求在 `.env` 中配置
> `ALI1688_PRODUCT_ADD_API`。例如你的开放平台控制台若显示完整路径，就原样填写。

## 1. 安装

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

## 2. 配置

编辑 `.env`：

```dotenv
ALI1688_APP_KEY=
ALI1688_APP_SECRET=
ALI1688_ACCESS_TOKEN=

# 必须以你的 1688 开放平台控制台中显示的完整 API 路径为准。
# 常见形式类似：业务命名空间/接口名
ALI1688_PRODUCT_ADD_API=

ALI1688_GATEWAY=https://gw.open.1688.com
ALI1688_API_VERSION=1
ALI1688_TIMEOUT_SECONDS=30
```

## 3. 准备商品

参考 `data/example_products.jsonl`，每行一个 JSON 对象。

字段结构：

```json
{
  "external_id": "SKU-GROUP-001",
  "category_id": 1035589,
  "subject": "示例商品标题",
  "description": "商品详情",
  "attributes": [
    {
      "attributeID": 346,
      "attributeName": "产地",
      "value": "广东"
    }
  ],
  "images": [
    "img/ibank/xxxx/example.jpg"
  ],
  "skus": [
    {
      "cargoNumber": "RED-L",
      "amountOnSale": 100,
      "price": 19.9,
      "retailPrice": 29.9,
      "consignPrice": 19.9,
      "attributes": []
    }
  ],
  "sale_info": {
    "supportOnlineTrade": true,
    "mixWholeSale": false,
    "saleType": "normal",
    "priceAuth": false,
    "priceRanges": [
      {"startQuantity": 3, "price": 19.9},
      {"startQuantity": 20, "price": 18.5}
    ],
    "amountOnSale": 100,
    "unit": "件",
    "minOrderQuantity": 3,
    "quoteType": 1
  },
  "shipping_info": {
    "freightTemplateID": 11754104,
    "unitWeight": 0.5,
    "sendGoodsAddressId": 31973275,
    "sendGoodsAddressText": "广东省 深圳市"
  }
}
```

## 4. 校验

```bash
python -m ali1688_uploader.cli validate data/example_products.jsonl
```

## 5. 预演发布计划

不会调用 1688：

```bash
python -m ali1688_uploader.cli plan data/example_products.jsonl
```

## 6. 真正发布

确保 `.env` 已填写 AppKey、AppSecret、AccessToken 和 API 路径：

```bash
python -m ali1688_uploader.cli publish data/example_products.jsonl --commit
```

默认行为：

- 单商品最多重试 3 次
- 指数退避
- 每次请求前重新生成时间戳和签名
- 结果写入 `runtime/publish-results.jsonl`
- 同一 `external_id` 已成功发布时默认跳过，降低重复铺货风险

要强制重新发布：

```bash
python -m ali1688_uploader.cli publish data/example_products.jsonl --commit --force
```

## 7. API 调用模型

本项目按 1688 开放平台常见 `param2` 风格实现：

```text
POST
{gateway}/openapi/param2/{version}/{api}/{app_key}
```

请求参数自动加入：

- `access_token`
- `_aop_timestamp`
- `_aop_signature`

签名算法：

```text
HMAC-SHA1(
  key = AppSecret,
  message = API路径 + 按 key 排序后的 key/value 串
)
```

输出大写十六进制。

## 8. 生产化建议

### 第一阶段
先跑 5~20 个测试商品，确保：

- 类目 ID 正确
- 类目必填属性齐全
- 图片已进入 1688 可接受的图片空间/路径
- SKU 规格和价格合法
- 运费模板、发货地址 ID 可用
- 应用确实拥有商品发布权限

### 第二阶段
再接你的商品源：

```text
ERP / Excel / PIM / 数据库
        ↓
标准商品模型
        ↓
类目与属性映射
        ↓
图片上传/图片空间
        ↓
1688 Publisher
        ↓
结果库 + 失败队列
```

### 第三阶段
增加：

- 类目属性自动拉取
- 图片上传
- 商品编辑
- 库存同步
- 审核状态回查
- 定时任务
- 企业微信/钉钉失败告警

## 安全

不要把以下信息提交到 Git：

- AppSecret
- AccessToken / RefreshToken
- Cookie
- 店铺后台登录信息

项目已经在 `.gitignore` 中忽略 `.env` 与 `runtime/`。

## 为什么不默认用浏览器自动化

后台页面自动化容易受：

- DOM 改版
- 登录态过期
- 验证码
- 风控
- 批量操作失败难以回滚

影响。

因此项目主链路只做开放平台 API。页面自动化如确有必要，应作为“人工辅助兜底”，而不是核心发布系统。
