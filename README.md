# BiliCookie
采用HTTP服务端定期刷新BiliBili已登入账号的Cookie，避免使用第三方程序调用API时出现SESSDATA失效问题；
Cookie采用对称加密算法可以安全地通过HTTP传输

## 特性
1. 定期刷新登入账号的Cookie(默认3天), 保证客户端每次获取的Cookie中的SESSDATA字段都是有效的(疑似7天有效期？)。
2. 使用Fernet AES 128 位对称加密，确保Cookies可以安全地通过HTTP传输 (SSL证书并非总是必要选项)。

## 依赖
1. `Chrome for Testing` 与 `ChromeDriver` 版本需要对应
2. [Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/#stable)
3. [ChromeDriver](https://googlechromelabs.github.io/chrome-for-testing/#stable)

## 使用方法
1. 下载适用版本的[Chrome for Testing](https://storage.googleapis.com/chrome-for-testing-public/141.0.7390.54/win64/chrome-win64.zip) 与 对应的[ChromeDriver](https://storage.googleapis.com/chrome-for-testing-public/141.0.7390.54/win64/chromedriver-win64.zip)
2. 下载 [Release](https://github.com/Rurityan/BiliCookie/releases) 中的 `BiliCookieServer.zip` 与 `gen_key.exe
`
3. 解压 `BiliCookieServer.zip` 修改 `chromeLocation.json`中
    `chrome_location`的值 为 `Chrome for Testing`的 `chrome.exe`的所在路径；
    `driver_path`的值 为 `chromedriver.exe` 的所在路径。
4. 打开 `gen_key.exe` 获得生成的随机密钥填入`bili_config.json`中的`key`的值。
5. (首次启动或者长时间闲置后账号过期) 修改 `bili_config.json`中的`headless`为`false`
6. 启动 `main.exe`
7. 扫码登录完成后即可关闭，修改 `bili_config.json`中的`headless`为`true`启用无头模式(节省资源)

## 环境
Python 3.10

## 获取Cookie
`pip install requests`
`pip install cryptography`
```
# bili_cookie_url 为 服务端配置的地址
# bili_cookie_key 为 服务端配置的密钥

import requests
import cryptography.fernet

# bili_cookie_url = "http://{server_ip}:{server_port}/getbilibilicookie"
# bili_cookie_key = "bili_config 中 key 的值"

x = requests.get(url=bili_cookie_url, timeout=5.0).json()
encrypted_str: str = x['encrypted_cookie']
cipher_suite = cryptography.fernet.Fernet(bili_cookie_key)
decrypted_data = cipher_suite.decrypt(encrypted_str).decode('utf-8')
```

## 开发
```bash
# 克隆仓库
git clone https://github.com/Rurityan/BiliCookie.git

# 进入目录
cd BiliCookie

# 安装依赖
pip install -r requirements.txt
