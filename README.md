# AEL Render 匿名网络测试

该程序只访问 3 个固定的公开端点，不接收账号、授权码、密码或令牌，也不提供转发代理。

## 部署

1. 在 GitHub 新建仓库 `ael-render-probe`，将本目录的文件放到仓库根目录。
2. Render 控制台选择 New → Web Service，连接该仓库。
3. Language：Python 3；Build Command：`python -V`；Start Command：`python server.py`。
4. Instance Type：Free。Advanced 中 Health Check Path：`/health`。
5. 不需要数据库、磁盘、环境密钥或支付信息。若账户流程要求支付验证，可暂停。
6. 部署 Live 后打开生成的网址，点击“开始测试”。

## 结果说明

- `/health` 返回正常，只说明测试程序启动了。
- 匿名请求的 401 或 405、无地区拒绝且没有挑战页，是端点可达的初步证据。
- `region_denial: true` 是地区拒绝。
- `cloudflare_challenge: true` 表示挑战页，不能当作正常连通。
- `http_status: null` 表示请求未取得 HTTP 响应；需继续查看网络原因。
- GET 测试不会交换授权码。未看到地区错误也不能证明真实 OAuth POST、账号权限、刷新和推理可用。
- Render 网址不能直接填到 Sub2API 的 HTTP/SOCKS5 代理字段。后续架构需另行配置和验证。

Free 服务闲置会休眠，文件系统不持久。此测试程序不存数据、不需要保活。

参考：https://render.com/docs/web-services 和 https://render.com/docs/free
