"""Bilibili web QR login and cookie renewal without a browser."""
import copy
import json
import os
import re
import threading
import time
from pathlib import Path

import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


PASSPORT = "https://passport.bilibili.com"
# Bilibili's web correspond-path public key (not a secret).
REFRESH_KEY = b"""-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDLgd2OAkcGVtoE3ThUREbio0Eg
Uc/prcajMKXvkCKFCWhJYJcLkcM2DKKcSeFpD/j6Boy538YXnR6VhcuUJOhH2x71
nzPjfdTcqMz7djHum0qSZA0AyCBDABUqCrfNgCiJ00Ra7GmRj+YCK1NJEuewlb40
JNrRuoEUXpabUzGB8QIDAQAB
-----END PUBLIC KEY-----"""


class ProtocolError(RuntimeError):
    pass


class LoginRequired(ProtocolError):
    pass


def cookie_list(jar):
    """Keep the Selenium cookie format consumed by existing clients."""
    result = []
    for c in jar:
        item = dict(name=c.name, value=c.value, domain=c.domain, path=c.path,
                    secure=c.secure, httpOnly=any(k.lower() == "httponly" for k in c._rest))
        if c.expires is not None:
            item["expiry"] = c.expires
        result.append(item)
    return result


class BiliClient:
    def __init__(self, state_file, key):
        self.lock = threading.RLock()
        self.path = Path(state_file)
        self.cipher = Fernet(key)
        self.session = self._session()
        self.refresh_token = ""
        self.pending_confirmation = ""
        self.valid = False
        self.last_error = ""
        self.last_check = None
        self.qr_session = None
        self.qr_key = None
        self.qr_deadline = 0
        if self.path.exists():
            state = json.loads(self.cipher.decrypt(self.path.read_bytes()))
            for c in state["cookies"]:
                self.session.cookies.set_cookie(requests.cookies.create_cookie(**c))
            self.refresh_token = state["refresh_token"]
            self.pending_confirmation = state.get("pending_confirmation", "")

    @staticmethod
    def _session():
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                                "Referer": "https://www.bilibili.com/"})
        return session

    @staticmethod
    def _json(session, method, url, required_cookies=(), **kwargs):
        response = session.request(method, url, timeout=20, **kwargs)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ProtocolError("接口返回了未知格式")
        if body.get("code") != 0:
            if body.get("code") == -101:
                raise LoginRequired("登录凭据已失效，请重新扫码")
            raise ProtocolError(f"B站接口返回错误码 {body.get('code')}")
        if not all(any(c.name == name for c in response.cookies) for name in required_cookies):
            raise ProtocolError("刷新响应缺少新的登录 Cookie")
        data = body.get("data")
        if data is not None and not isinstance(data, dict):
            raise ProtocolError("接口 data 格式异常")
        return data or {}

    def _cookie(self, name):
        values = {c.value for c in self.session.cookies if c.name == name and
                  (c.domain == "bilibili.com" or c.domain.endswith(".bilibili.com"))}
        if len(values) != 1:
            raise LoginRequired(f"缺少或存在冲突的 {name} Cookie，请重新扫码")
        return values.pop()

    def _save(self):
        cookies = [dict(name=c.name, value=c.value, domain=c.domain, path=c.path,
                        secure=c.secure, expires=c.expires, rest=c._rest) for c in self.session.cookies]
        state = dict(cookies=cookies, refresh_token=self.refresh_token,
                     pending_confirmation=self.pending_confirmation)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(temporary, "wb") as output:
            os.chmod(temporary, 0o600)
            output.write(self.cipher.encrypt(json.dumps(state).encode()))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, self.path)

    def new_qr(self):
        with self.lock:
            session = self._session()
            try:
                data = self._json(session, "GET", PASSPORT + "/x/passport-login/web/qrcode/generate")
            except Exception:
                session.close()
                raise
            if self.qr_session:
                self.qr_session.close()
            self.qr_session = session
            self.qr_key = data["qrcode_key"]
            self.qr_deadline = time.monotonic() + 180
            return data["url"]

    def poll_qr(self):
        with self.lock:
            if not self.qr_key or time.monotonic() >= self.qr_deadline:
                return {"code": 86038, "message": "二维码已过期，请重新生成"}
            data = self._json(self.qr_session, "GET", PASSPORT + "/x/passport-login/web/qrcode/poll",
                              params={"qrcode_key": self.qr_key})
            code = data["code"]
            if code == 0:
                if not data.get("refresh_token") or not any(c.name == "SESSDATA" for c in self.qr_session.cookies):
                    raise ProtocolError("扫码结果未包含完整登录凭据")
                previous = (self.session, self.refresh_token, self.pending_confirmation)
                self.session = self.qr_session
                self.refresh_token, self.pending_confirmation = data["refresh_token"], ""
                try:
                    self._cookie("SESSDATA")
                    self._cookie("bili_jct")
                    self._save()
                except Exception:
                    self.session, self.refresh_token, self.pending_confirmation = previous
                    raise
                previous[0].close()
                self.qr_session, self.qr_key = None, None
                self.valid = True
                self.last_error = ""
            elif code == 86038:
                self.qr_key = None
            return {"code": code, "message": {0: "登录成功", 86101: "等待扫码", 86090: "已扫码，请在手机确认", 86038: "二维码已过期"}.get(code, "未知扫码状态")}

    def _confirm(self):
        # Also retry a previous failed disk write before invalidating old tokens.
        self._save()
        self._json(self.session, "POST", PASSPORT + "/x/passport-login/web/confirm/refresh",
                   data={"csrf": self._cookie("bili_jct"), "refresh_token": self.pending_confirmation})
        self.pending_confirmation = ""
        self._save()

    def _refresh(self, timestamp):
        public_key = serialization.load_pem_public_key(REFRESH_KEY)
        correspond = public_key.encrypt(f"refresh_{timestamp}".encode(), padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)).hex()
        response = self.session.get("https://www.bilibili.com/correspond/1/" + correspond, timeout=20)
        response.raise_for_status()
        match = re.search(r'<div\s+id=[\"\']1-name[\"\']\s*>([^<]+)</div>', response.text)
        if not match:
            raise ProtocolError("未能解析 refresh_csrf，刷新协议可能已变更")
        old_token = self.refresh_token
        old_cookies = copy.deepcopy(self.session.cookies)
        try:
            data = self._json(self.session, "POST", PASSPORT + "/x/passport-login/web/cookie/refresh",
                              required_cookies=("SESSDATA", "bili_jct"),
                              data={"csrf": self._cookie("bili_jct"), "refresh_csrf": match[1].strip(),
                                    "source": "main_web", "refresh_token": old_token})
            new_token = data["refresh_token"]
            if not new_token:
                raise ProtocolError("刷新响应缺少 refresh_token")
            self._cookie("SESSDATA")
            self._cookie("bili_jct")
        except Exception:
            self.session.cookies = old_cookies
            raise
        self.refresh_token = new_token
        self.pending_confirmation = old_token
        # Persist rotated credentials before invalidating the previous token.
        self._save()
        self._confirm()

    def check(self):
        with self.lock:
            try:
                if not self.refresh_token:
                    raise LoginRequired("尚未登录，请扫码登录")
                nav = self._json(self.session, "GET", "https://api.bilibili.com/x/web-interface/nav")
                if not nav.get("isLogin"):
                    raise LoginRequired("登录已失效，请重新扫码")
                self.valid = True
                if self.pending_confirmation:
                    self._confirm()
                info = self._json(self.session, "GET", PASSPORT + "/x/passport-login/web/cookie/info",
                                  params={"csrf": self._cookie("bili_jct")})
                if info["refresh"]:
                    self._refresh(info["timestamp"])
                self.last_error = ""
            except LoginRequired as exc:
                self.valid = False
                self.last_error = str(exc)
            except (requests.RequestException, ValueError, KeyError, OSError, ProtocolError):
                self.last_error = "检查或续期失败，将在下次检查时重试；请检查网络及协议"
            finally:
                self.last_check = int(time.time())
            return self.status()

    def status(self):
        with self.lock:
            return {"logged_in": self.valid, "last_check": self.last_check,
                    "message": self.last_error, "pending_confirmation": bool(self.pending_confirmation)}

    def get_all_cookies(self):
        with self.lock:
            if not self.valid:
                raise LoginRequired("尚未确认有效登录，请打开 /login 扫码或查看状态")
            return cookie_list(self.session.cookies)

    def close(self):
        with self.lock:
            self.session.close()
            if self.qr_session:
                self.qr_session.close()
