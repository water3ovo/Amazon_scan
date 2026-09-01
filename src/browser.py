from __future__ import annotations

import os
import random
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .utils import clean_text, safe_filename


class BrowserSession:
    def __init__(self, country: str, settings: dict, country_config: dict, base_dir: Path, headless: bool | None = None):
        self.country = country
        self.settings = settings
        self.country_config = country_config
        self.base_dir = Path(base_dir)
        self.profile_dir = self.base_dir / "profiles" / country
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.debug_dir = self.base_dir / "debug" / country
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        configured_headless = bool(settings.get("browser", {}).get("headless", False))
        self.headless = configured_headless if headless is None else bool(headless)
        self.driver = None
        self.navigation_count = 0

    def start(self):
        options = Options()
        options.page_load_strategy = "eager"
        options.add_argument(f"--user-data-dir={self.profile_dir.resolve()}")
        options.add_argument("--profile-directory=Default")
        options.add_argument("--lang=en-US")
        options.add_argument("--window-size=1365,900")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option(
            "prefs",
            {
                "intl.accept_languages": "en-US,en",
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False,
            },
        )
        if self.headless:
            options.add_argument("--headless=new")

        chrome_binary = os.environ.get("CHROME_BINARY", "").strip()
        if chrome_binary:
            options.binary_location = chrome_binary

        # Selenium Manager automatically resolves a compatible ChromeDriver.
        self.driver = webdriver.Chrome(options=options)
        timeout = int(self.settings.get("browser", {}).get("page_load_timeout_seconds", 25))
        self.driver.set_page_load_timeout(timeout)
        try:
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
            )
        except Exception:
            pass
        return self

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def _wait_body(self):
        wait_seconds = int(self.settings.get("browser", {}).get("element_wait_seconds", 5))
        WebDriverWait(self.driver, wait_seconds).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    def polite_delay(self):
        browser = self.settings.get("browser", {})
        low = float(browser.get("min_delay_seconds", 2.0))
        high = float(browser.get("max_delay_seconds", 4.0))
        if high < low:
            high = low
        time.sleep(random.uniform(low, high))

    def navigate(self, url: str):
        if not self.driver:
            raise RuntimeError("Browser is not started")
        try:
            if self.navigation_count == 0:
                self.driver.get(url)
            else:
                # Preserve a same-session referrer path; this was more stable than repeated address-bar navigation in V1.
                self.driver.execute_script("window.location.href = arguments[0];", url)
            self.navigation_count += 1
            self._wait_body()
        except TimeoutException:
            # Amazon can finish rendering useful product content after Selenium's page timeout.
            try:
                self.driver.execute_script("window.stop();")
            except Exception:
                pass
        self._handle_continue_shopping(url)
        self.polite_delay()

    def body_text(self) -> str:
        try:
            return clean_text(self.driver.find_element(By.TAG_NAME, "body").text)
        except Exception:
            return ""

    def detect_gate(self) -> str:
        text = self.body_text().lower()
        title = clean_text(getattr(self.driver, "title", "")).lower()
        source = f"{title} {text[:8000]}"
        captcha_terms = [
            "enter the characters you see below",
            "type the characters you see in this image",
            "sorry, we just need to make sure you're not a robot",
            "captcha",
        ]
        if any(term in source for term in captcha_terms):
            return "CAPTCHA"
        if "continue shopping" in source and "click the button" in source:
            return "CONTINUE_SHOPPING"
        return "OK"

    def _handle_continue_shopping(self, original_url: str) -> bool:
        if self.detect_gate() != "CONTINUE_SHOPPING":
            return False
        selectors = [
            "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
            "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
            "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
        ]
        for selector in selectors:
            try:
                element = self.driver.find_element(By.XPATH, selector)
                self.driver.execute_script("arguments[0].click();", element)
                time.sleep(random.uniform(1.5, 2.5))
                self.driver.execute_script("window.location.href = arguments[0];", original_url)
                self._wait_body()
                time.sleep(random.uniform(1.0, 2.0))
                return True
            except Exception:
                continue
        return True

    def save_screenshot(self, label: str) -> str:
        if not self.driver:
            return ""
        path = self.debug_dir / f"{safe_filename(label)}.png"
        try:
            self.driver.save_screenshot(str(path))
            return str(path)
        except Exception:
            return ""

    def setup_location(self):
        if self.headless:
            raise RuntimeError("配送地址配置必须使用可见浏览器，请不要使用 --headless。")
        domain = self.country_config["domain"]
        self.driver.get(f"https://www.{domain}/")
        self._wait_body()
        print("\n" + "=" * 72)
        print(f"正在配置 {self.country} ({domain}) 的独立扫查浏览器 Profile。")
        print("请在打开的 Chrome 中：")
        print("1) 切换到 English（如页面不是英文）")
        print("2) 设置实际用于扫查的配送地址/城市")
        print("3) 确认页面显示的国家、货币与配送地正确")
        input("完成后回到此窗口，按 Enter 保存配置并关闭浏览器...")
        marker = self.profile_dir / ".location_ready"
        marker.write_text("configured\n", encoding="utf-8")
        print(f"已记录 {self.country} 配送地址配置。")

    @property
    def location_is_ready(self) -> bool:
        return (self.profile_dir / ".location_ready").exists()
