# 1688 OAuth 授权

本项目不要求把 AppSecret、access token 或 refresh token 提交到 Git。

推荐在本地或部署环境使用 `.env`；仓库已忽略 `.env`。

## 1. 创建 / 确认 1688 开放平台应用

在 1688 开放平台应用中准备：

- AppKey
- AppSecret
- Redirect URI（必须与应用后台登记的回调域名/地址规则一致）
- 商品、库存、图片银行等所需 API 权限

先创建本地配置：

```bash
cp .env.example .env
```

填写：

```dotenv
ALI1688_APP_KEY=你的AppKey
ALI1688_APP_SECRET=你的AppSecret
ALI1688_REDIRECT_URI=https://你的回调地址
```

不要把 `.env` 提交到 GitHub，也不要把 AppSecret 或 token 粘贴到 issue / PR / 聊天记录。

## 2. 生成授权地址

```bash
python -m ali1688_uploader.cli auth-url
```

命令会生成：

- `authorization_url`
- 随机 `state`
- 当前 `redirect_uri`

在浏览器中打开 `authorization_url`，登录并授权店铺。

授权完成后 1688 会跳回 Redirect URI，并附带 `code` 和 `state`。
请核对返回的 `state` 与 CLI 生成的值一致。

## 3. 用 code 换 token

推荐直接写入本地 `.env`，这样 token 不会显示在终端：

```bash
python -m ali1688_uploader.cli token-exchange '回调中的code' --write-env .env
```

成功后 `.env` 会被更新：

```dotenv
ALI1688_ACCESS_TOKEN=...
ALI1688_REFRESH_TOKEN=...
```

如果不使用 `--write-env`，命令会把 token 响应打印到终端；只适合受控的本地终端。

## 4. 刷新 access token

只要 `.env` 已保存 refresh token：

```bash
python -m ali1688_uploader.cli token-refresh --write-env .env
```

也可以显式传入 refresh token：

```bash
python -m ali1688_uploader.cli token-refresh --refresh-token '...' --write-env .env
```

## 5. 先做只读联调

Token 配置完成后，不要马上批量上架。先验证账号权限和 API 路径：

```bash
python -m ali1688_uploader.cli list-products --page-size 5
```

若已知一个自己店铺的商品 ID：

```bash
python -m ali1688_uploader.cli get-product <product_id>
```

若已知一个叶子类目 ID：

```bash
python -m ali1688_uploader.cli category-attrs <category_id>
```

只读调用全部成功后，再测试图片上传和一个测试商品。

## 6. 写操作仍有安全开关

商品发布、商品编辑、库存修改、图片上传等写操作仍要求显式 `--commit`。

例如：

```bash
python -m ali1688_uploader.cli photo-add ./demo.jpg
# 仅预检，不上传

python -m ali1688_uploader.cli photo-add ./demo.jpg --commit
# 真正上传
```

发布商品同理：

```bash
python -m ali1688_uploader.cli publish data/example_products.jsonl
# dry-run

python -m ali1688_uploader.cli publish data/example_products.jsonl --commit
# 真正发布
```
