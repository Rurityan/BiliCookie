import base64
import hmac
import io
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import qrcode
import qrcode.image.svg
import requests
from cryptography.fernet import Fernet

from bili_http_client import BiliClient, LoginRequired, ProtocolError

ROOT = Path(__file__).resolve().parent


def read_file_option():
    with (ROOT / "bili_config.json").open(encoding="utf-8") as source:
        config = json.load(source)
    Fernet(config["key"])
    config.setdefault("state_file", str(Path(config.get("dir", "data")) / "login_state.enc"))
    config.setdefault("check_interval", 3600)
    if not isinstance(config["check_interval"], (int, float)) or config["check_interval"] < 60:
        raise ValueError("check_interval 必须至少为 60 秒")
    config["admin_token"] = os.environ.get("BILI_ADMIN_TOKEN") or config.get("admin_token") or config["key"]
    return config


def get_encrypted_cookie_bytes(_instance, _key):
    return Fernet(_key).encrypt(json.dumps(_instance.get_all_cookies(), ensure_ascii=False).encode())


def make_handler(client, config):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, code, body, content_type="application/json; charset=utf-8", authenticate=False):
            if isinstance(body, dict):
                body = json.dumps(body, ensure_ascii=False).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            if authenticate:
                self.send_header("WWW-Authenticate", 'Basic realm="BiliCookie admin", charset="UTF-8"')
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            header = self.headers.get("Authorization", "")
            token = ""
            if header.startswith("Basic "):
                try:
                    user, token = base64.b64decode(header[6:], validate=True).decode().split(":", 1)
                    if user != "admin":
                        token = ""
                except (ValueError, UnicodeError):
                    pass
            elif header.startswith("Bearer "):
                token = header[7:]
            if hmac.compare_digest(token.encode(), config["admin_token"].encode()):
                return True
            self.respond(401, {"error": "需要管理员认证"}, authenticate=True)
            return False

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/getbilibilicookie":
                try:
                    self.respond(200, {"encrypted_cookie": get_encrypted_cookie_bytes(client, config["key"]).decode()})
                except LoginRequired as exc:
                    self.respond(503, {"error": str(exc)})
                return
            if path not in ("/", "/login", "/login.js", "/api/status"):
                self.respond(404, {"error": "接口不存在"})
                return
            if not self.authorized():
                return
            if path == "/api/status":
                self.respond(200, client.status())
            elif path == "/login.js":
                self.respond(200, (ROOT / "static" / "login.js").read_bytes(), "text/javascript; charset=utf-8")
            else:
                self.respond(200, (ROOT / "static" / "login.html").read_bytes(), "text/html; charset=utf-8")

        def do_POST(self):
            path = urlsplit(self.path).path
            if not self.authorized():
                return
            # Cross-origin HTML forms cannot set this header; no CORS is enabled.
            if self.headers.get("X-Requested-With") != "BiliCookie":
                self.respond(403, {"error": "缺少管理请求标识"})
                return
            try:
                if path == "/api/login/qr":
                    output = io.BytesIO()
                    qrcode.make(client.new_qr(), image_factory=qrcode.image.svg.SvgPathImage).save(output)
                    self.respond(200, {"image": "data:image/svg+xml;base64," + base64.b64encode(output.getvalue()).decode()})
                elif path == "/api/login/poll":
                    self.respond(200, client.poll_qr())
                elif path == "/api/check":
                    self.respond(200, client.check())
                else:
                    self.respond(404, {"error": "接口不存在"})
            except (requests.RequestException, ProtocolError, ValueError, KeyError, OSError):
                self.respond(502, {"error": "B站请求或状态保存失败，请检查网络、数据目录权限或稍后重试"})

        def log_message(self, format, *args):
            logging.info("HTTP request completed from %s", self.client_address[0])

    return Handler


def maintain(client, stop, interval):
    while not stop.is_set():
        status = client.check()
        if status["message"]:
            logging.warning("登录状态：%s", status["message"])
        if stop.wait(interval):
            break


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = read_file_option()
    client = BiliClient(ROOT / config["state_file"], config["key"])
    stop = threading.Event()
    with ThreadingHTTPServer((config["ipAddr"], int(config["port"])), make_handler(client, config)) as server:
        worker = threading.Thread(target=maintain, args=(client, stop, config["check_interval"]), daemon=True)
        worker.start()
        logging.info("服务已启动，端口 %s；访问 /login 扫码，管理用户名为 admin", config["port"])
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            worker.join()
            client.close()


if __name__ == "__main__":
    main()
