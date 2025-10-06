import json
import socket
import time
import threading
import typing

from selenium import webdriver
from selenium.webdriver.chrome.service import Service


class Browser:
    main_page = ""
    def __init__(self, port_number: int, user_data_dir, target_url: str, headless=False):
        # 账户配置
        self.targetPage = target_url
        # Google浏览器配置
        self.dev_port = port_number
        self.started = False
        self.options = webdriver.ChromeOptions()
        if headless is True:
            # 添加无头配置
            self.options.add_argument('--headless')
            # 可选：解决部分环境下无头模式下可能出现的显卡加速问题
            self.options.add_argument('--disable-gpu')
            # 可选：设置浏览器窗口大小，避免无头时窗口大小为0导致部分问题
            self.options.add_argument('window-size=640,480')

        self.options.add_experimental_option('excludeSwitches', ['enable-logging'])
        self.options.add_argument(fr"--user-data-dir={user_data_dir}")
        self.options.add_argument(f"--remote-debugging-port={port_number}")
        self.options.binary_location = ''
        self.driverPath = ''
        self.browser: typing.Optional[webdriver.Chrome] = None
        try:
            with open('chromeLocation.json', 'r', encoding='utf-8') as clf:
                cl = json.load(clf)
                self.options.binary_location = cl['chrome_location']
                self.driverPath = cl['driver_path']
        except Exception as nofile:
            print(f"本目录下不存在谷歌路径文件:{nofile}，自动读取上一级目录...:")
            try:
                with open('../chromeLocation.json', 'r', encoding='utf-8') as clf:
                    cl = json.load(clf)
                    self.options.binary_location = cl['chrome_location']
                    self.driverPath = cl['driver_path']
            except Exception as nofile:
                print(f"未检查到谷歌位置及其驱动路径文件，请检查并重启...{nofile}")
                time.sleep(3600)


    def browser_init(self):
        service = Service(self.driverPath)
        self.browser = webdriver.Chrome(options=self.options, service=service)
        self.browser.get(self.targetPage)
        self.started = True
        while True:
            time.sleep(10)


    def browser_start(self):
        # 应该让子线程执行
        BrowserKeepAlive = threading.Thread(target=self.browser_init)
        BrowserKeepAlive.start()
        print(f"Browser:{self.dev_port} started...")


    def refresh_page(self):
        self.browser.refresh()

    def get_all_cookies(self):
        return self.browser.get_cookies()


def is_port_in_use(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # 设置一个超时，避免长时间等待
    sock.settimeout(1)
    try:
        # 尝试连接指定的地址和端口
        sock.connect((ip, port))
    except socket.error:
        # 连接失败，端口未被占用
        return False
    else:
        return True
    finally:
        sock.close()


def auto_port_select() -> int:
    start_at = 12345
    current_port = start_at
    while True:
        if is_port_in_use("127.0.0.1", current_port):
            current_port += 1
        else:
            return current_port