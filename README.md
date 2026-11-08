# BiliCookie

纯 HTTP 的 B 站扫码登录及 Cookie 续期服务，不需要 Chrome、ChromeDriver 或 Linux 桌面环境。Python 3.10+。

## 启动

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python gen_key.py
```

将生成的 Fernet 密钥填入 `bili_config.json` 的 `key`，然后运行：

```bash
python main.py
```

访问 `http://服务器地址:13678/login`，浏览器认证用户名是 `admin`，密码是环境变量 `BILI_ADMIN_TOKEN` 的值；未设置时依次使用配置中的 `admin_token`、`key`。

点击“生成登录二维码”，用 B 站手机客户端扫码并确认。页面每 2.5 秒查询一次状态，二维码约三分钟有效，过期后可重新生成。网页登录管理使用 HTTPS 反向代理或 SSH 隧道；HTTP Basic 本身不会加密管理密码。

登录成功后 Cookie 和 refresh_token 以 Fernet 加密保存，重启后自动检查恢复。旧版 Chrome 用户目录不能自动转换，需要重新扫码。旧配置中的 headless、target_url、dir 无需用于浏览器启动；未配置 state_file 时会使用 dir/login_state.enc（dir 缺省为 data）。

## 配置

| 字段 | 用途 |
| --- | --- |
| key | Fernet 密钥，用于响应和本地登录状态加密 |
| ipAddr / port | 监听地址和端口，默认示例为 0.0.0.0:13678 |
| state_file | 登录状态文件，默认示例为 data/login_state.enc，相对项目目录解析 |
| check_interval | 状态检查间隔（秒），默认 3600，最小 60 |
| admin_token | 可选的管理密码，建议与 key 分开设置；BILI_ADMIN_TOKEN 环境变量优先 |

配置文件相对程序目录读取，不依赖启动时的工作目录。请保留相同的 key 和状态文件以便恢复登录；更换 key 前需迁移或移走旧状态文件并重新扫码。无法解密的文件会导致启动报错，不会覆盖原凭据。

网络请求使用 20 秒超时，并支持 requests 的 HTTP_PROXY / HTTPS_PROXY 环境变量。

## 自动检查和续期

服务启动时及每个检查周期验证登录状态，查询 cookie/info；只有返回需要刷新时才执行完整协议：

1. 使用 RSA-OAEP / SHA-256 生成 correspondPath，取得 refresh_csrf。
2. 使用当前 csrf、refresh_csrf 和 refresh_token 请求 cookie/refresh。
3. 将新 Cookie、新 refresh_token 和待确认的旧 token 原子加密保存。
4. 使用新 Cookie 与旧 refresh_token 请求 confirm/refresh，确认成功后清除待确认信息。

确认失败后保留待确认信息，下次检查或重启后重试。网络错误不会主动删除凭据；明确检测到登录失效时停止提供 Cookie，并在管理页面显示重新扫码提示。页面可以手动触发检查。状态是最近一次检查结果，不能保证两次检查之间账号不会被退出或失效；续期也不能绕过账号风控或保证永久登录。

## 获取 Cookie（兼容旧客户端）

`GET /getbilibilicookie` 返回 `{"encrypted_cookie": "..."}`，解密后仍是 Selenium 风格的 Cookie 对象列表。该接口保留原来的访问方式；Cookie 内容需持有 key 才能解密。尚未登录或已检测到失效时返回 HTTP 503 和 error，不会返回空的成功结果。

```python
import json
import requests
from cryptography.fernet import Fernet

response = requests.get("http://服务器地址:13678/getbilibilicookie", timeout=20)
response.raise_for_status()
cookies = json.loads(Fernet(b"你的Fernet密钥").decrypt(
    response.json()["encrypted_cookie"].encode()
))
```

## 管理接口

全部要求 HTTP Basic（用户名 admin）或 `Authorization: Bearer <管理密码>`。POST 还必须携带 `X-Requested-With: BiliCookie`，不启用跨域访问。响应不包含原始 Cookie 或刷新凭据。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /login | 扫码管理页面 |
| GET | /api/status | 最近一次登录检查状态 |
| POST | /api/login/qr | 生成二维码，返回 SVG data URL |
| POST | /api/login/poll | 查询扫码结果，成功时保存登录状态 |
| POST | /api/check | 立即检查并按需续期 |

二维码生成和轮询在打开的管理页面中执行；关闭页面后如尚未完成登录，需要重新打开并生成二维码。

## Linux Docker 部署

```bash
docker build -t bilicookie .
docker volume create bilicookie-data
docker run -d --name bilicookie --restart unless-stopped \
  -p 127.0.0.1:13678:13678 \
  -e BILI_ADMIN_TOKEN='替换为管理密码' \
  --mount type=bind,src="$(pwd)/bili_config.json",dst=/app/bili_config.json,readonly \
  --mount type=volume,src=bilicookie-data,dst=/app/data \
  bilicookie
```

将配置中的 state_file 设置为 data/login_state.enc。容器使用 UID 10001 的非 root 用户，挂载已有目录时需确保其有写权限。配置和凭据不打包进镜像；通过反向代理或 SSH 隧道访问绑定到服务器回环地址的端口。

## 验证及协议来源

```bash
python -m unittest discover -s tests -v
```

测试模拟 B 站响应，覆盖扫码状态、加密恢复、续期及确认恢复、网络失败和旧 Cookie 输出格式。真实账号首次扫码及真实续期需要实际账号验证。

协议实现参考 B 站 web passport 接口及 bilibili-api-python 17.4.2 的 QRCodeLogin、Cookie 刷新流程（仅核对协议，运行时不依赖该库）。接口属于网站协议，后续变化可能需要更新实现。
