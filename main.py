import datetime
import json
import os
import sys
import threading
import time
import typing

import bili_browser_module
import cryptography.fernet
import http.server



def read_file_option() -> dict[str, int|str|bool]:
    try:
        with open('bili_config.json', 'r', encoding='utf-8') as rb:
            rbj = json.load(rb)
            _name = rbj['name']
            _location = os.path.join(os.getcwd(), rbj['dir'])
            _target_url = rbj['target_url']
            _headless = rbj['headless']
            _key = rbj['key']
            _ipAddr = rbj['ipAddr']
            _port = rbj['port']
        return {"name": _name, "location": _location, "target_url": _target_url,
                "headless": _headless, "key": _key, "ipAddr": _ipAddr, "port": _port}

    except Exception as no_file:
        print(f"未找到：bili_config.json:{no_file}, 将自动退出")
        time.sleep(300)
        sys.exit(-1)


def refresh_page_every3day(_instance:bili_browser_module.Browser):
    while True:
        print(f"{datetime.datetime.now()}: 执行了页面刷新")
        _instance.refresh_page()
        time.sleep(259200) # 86400 * 3

def refresh_page_threading(_instance:bili_browser_module.Browser):
    threading.Thread(target=refresh_page_every3day, kwargs={"_instance": _instance}).start()


def get_encrypted_cookie_bytes(_instance:bili_browser_module.Browser, _key:str):
    cookie_dict = _instance.get_all_cookies()
    cookie_json = json.dumps(cookie_dict, ensure_ascii=False, indent=2)
    cipher_suite = cryptography.fernet.Fernet(key=_key)
    encrypted_data = cipher_suite.encrypt(cookie_json.encode('utf-8'))
    return encrypted_data



class MyHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, request: typing.Any, client_address: typing.Any, server: http.server.ThreadingHTTPServer) -> None:
        super().__init__(request, client_address, server)

    def do_GET(self):
        global instance
        global cookie_key
        if "/getbilibilicookie" in self.path:
            bili_cookie = get_encrypted_cookie_bytes(_instance=instance, _key=cookie_key)
            bili_cookie_json = {
                "encrypted_cookie": bili_cookie.decode()
            }
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(bili_cookie_json).encode('utf-8'))
        else:
            self.send_response(200)
            self.send_header('Content-type', "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Invalid Options".encode('utf-8'))



if __name__ == "__main__":
    instance_cfg = read_file_option()
    cookie_key = instance_cfg['key']
    instance = bili_browser_module.Browser(port_number=bili_browser_module.auto_port_select(), user_data_dir=instance_cfg['location'],
                                           target_url=instance_cfg['target_url'], headless=instance_cfg["headless"])
    instance.browser_start()
    print("Initializing...")
    time.sleep(15)
    refresh_page_threading(instance)

    IPAddr = str(instance_cfg['ipAddr'])
    server_port = int(instance_cfg['port'])

    with http.server.ThreadingHTTPServer((IPAddr, server_port), MyHandler) as httpd:
        print(f"Serving BiliBili Cookie Service on http://{IPAddr}:{server_port}/getbilibilicookie")
        httpd.timeout = 5.0
        httpd.serve_forever()
    
