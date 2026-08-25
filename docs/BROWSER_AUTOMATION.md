# 1688 浏览器自动化模式

当当前账号无法满足 1688 开放平台“自研商家/主账号”入驻条件时，可以使用浏览器自动化作为主链路。

本模式的原则：

- 使用 Playwright 正常打开 1688 卖家工作台。
- 第一次由你本人手工完成登录、扫码、短信等正常验证。
- 登录会话保存在本机 `runtime/browser-profile/`，不会提交到 Git。
- 不做验证码绕过、指纹伪装、Cookie 窃取或风控规避。
- 默认 dry-run；只有显式 `--commit` 才点击发布按钮。
- 1688 发布页会按账号、类目和版本动态变化，所以先 `inspect` 当前真实页面，再校准 selector profile。

## 1. 安装

```bash
pip install -e .
python -m playwright install chromium
```

如果你希望 Playwright 使用本机 Chrome，可以设置：

```dotenv
ALI1688_BROWSER_CHANNEL=chrome
```

此时通常不需要额外下载 Chromium，但本机必须已安装 Google Chrome。

## 2. 第一次人工登录

```bash
python -m ali1688_uploader.browser_cli login
```

程序会打开浏览器。请在浏览器里正常登录 1688 卖家工作台。完成扫码/短信/验证码等人工验证后，确认已经进入工作台，再回到终端按 Enter。

登录状态会保存在：

```text
runtime/browser-profile/
```

不要把这个目录发送给别人。

如果默认入口不对，可以显式指定：

```bash
python -m ali1688_uploader.browser_cli login --url '你当前卖家工作台地址'
```

## 3. 打开“发布商品”页面并复制 URL

在刚刚登录的卖家工作台里，按你平时的操作进入：

```text
商品 / 商品管理 -> 发布商品 / 新发商品
```

如果页面要求先选择类目，就先手工选一个你真实准备发布的类目，直到进入最终商品编辑表单。

然后复制浏览器地址栏里的完整 URL。

## 4. 抓取当前发布页结构

把刚复制的 URL 放到：

```bash
python -m ali1688_uploader.browser_cli inspect --url '完整发布页URL'
```

程序会使用已经保存的登录会话打开该页面，并生成：

```text
runtime/browser-inspect/<时间>/page.png
runtime/browser-inspect/<时间>/page.html
runtime/browser-inspect/<时间>/controls.json
runtime/browser-inspect/<时间>/manifest.json
```

其中：

- `page.png`：当前发布页完整截图
- `controls.json`：输入框、按钮、文本域、上传控件等结构化信息
- `page.html`：页面 DOM 快照

这些信息用于校准 `browser_profiles/1688-current.json`。

## 5. selector profile

项目提供：

```text
browser_profiles/1688-current.json
```

初始模板为空：

```json
{
  "publish_url": "",
  "selectors": {
    "subject": "",
    "description": "",
    "image_input": "",
    "price": "",
    "stock": "",
    "unit": "",
    "min_order_quantity": "",
    "submit": ""
  }
}
```

在拿到当前页面的 `page.png / controls.json` 后，再把真实选择器填进去。

不要在没有校准页面的情况下直接使用 `--commit`。

## 6. 浏览器发布计划

这一步不打开浏览器，也不会修改 1688：

```bash
python -m ali1688_uploader.browser_cli plan data/example_products.jsonl --limit 1
```

浏览器模式中的 `images` 必须是本机图片文件路径，例如：

```json
"images": [
  "./data/images/product-001-1.jpg",
  "./data/images/product-001-2.jpg"
]
```

不能直接把 Open API 图片空间路径当本机上传文件。

## 7. 填表但不提交

selector profile 校准好之后，先执行：

```bash
python -m ali1688_uploader.browser_cli publish \
  data/example_products.jsonl \
  --profile browser_profiles/1688-current.json \
  --limit 1 \
  --fill-only
```

程序会：

1. 打开真实发布页
2. 填写已配置的字段
3. 上传本机图片
4. 保存提交前截图
5. 停住，不点击“发布”

你可以在浏览器里人工检查。

## 8. 真正发布

确认一个测试商品的页面填写完全正确后，才执行：

```bash
python -m ali1688_uploader.browser_cli publish \
  data/example_products.jsonl \
  --profile browser_profiles/1688-current.json \
  --limit 1 \
  --commit
```

程序会点击 profile 中的 `selectors.submit`。

每次发布前后都会保留截图证据，结果写入：

```text
runtime/browser-results.jsonl
runtime/browser-evidence/
```

## 9. 为什么先 inspect 而不是直接硬编码选择器

1688 卖家发布页可能因为以下原因出现不同 DOM：

- 店铺账号权限不同
- 类目不同
- 新旧发布器版本不同
- A/B 测试
- 页面改版
- SKU 规格组合不同

因此浏览器模式采用“真实页面校准 -> selector profile -> 小批量验证 -> 批量发布”的方式，而不是依赖一套永久不变的 CSS。

## 10. 当前自动化边界

第一版基础设施已覆盖：

- 持久登录会话
- 当前页面抓取/截图/DOM 控件报告
- 标题
- 详情
- 图片上传
- 第一价格
- 库存
- 单位
- 起订量
- 提交按钮
- dry-run / fill-only / commit
- 发布前后截图和结果日志

类目选择、动态商品属性和复杂多 SKU 矩阵需要根据你实际发布页的 `controls.json` 和截图继续校准。这是下一步，而不是通过验证码绕过或隐藏自动化来解决。
