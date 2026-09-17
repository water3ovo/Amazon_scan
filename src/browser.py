from __future__ import annotations

import io
import os
import random
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .utils import clean_text, safe_filename


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)\.(\d+)")


def _version_tuple(text: str) -> tuple[int, int, int, int] | None:
    match = _VERSION_RE.search(text or "")
    if not match:
        return None
    return tuple(int(x) for x in match.groups())


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

    def _find_chrome_binary(self) -> Path | None:
        configured = os.environ.get("CHROME_BINARY", "").strip()
        if configured:
            path = Path(configured)
            if path.exists():
                return path

        which = shutil.which("chrome") or shutil.which("chrome.exe")
        if which:
            return Path(which)

        candidates = []
        for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(env_name, "").strip()
            if root:
                candidates.append(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _detect_chrome_version(self, chrome_binary: Path) -> tuple[int, int, int, int] | None:
        try:
            versions = []
            for child in chrome_binary.parent.iterdir():
                if child.is_dir():
                    parsed = _version_tuple(child.name)
                    if parsed:
                        versions.append(parsed)
            if versions:
                return max(versions)
        except Exception:
            pass

        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            escaped = str(chrome_binary).replace("'", "''")
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"(Get-Item '{escaped}').VersionInfo.ProductVersion",
            ]
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=creationflags,
            )
            parsed = _version_tuple(f"{completed.stdout} {completed.stderr}")
            if parsed:
                return parsed
        except Exception:
            pass
        return None

    def _cache_root(self) -> Path:
        userprofile = os.environ.get("USERPROFILE", "").strip()
        if not userprofile:
            raise RuntimeError("无法读取 USERPROFILE，无法定位 Selenium ChromeDriver 缓存。")
        return Path(userprofile) / ".cache" / "selenium" / "chromedriver" / "win64"

    def _find_cached_driver(self, chrome_version: tuple[int, int, int, int] | None) -> Path | None:
        cache_root = self._cache_root()
        if not cache_root.exists():
            return None

        candidates: list[tuple[tuple[int, int, int, int], Path]] = []
        for driver in cache_root.glob("*/chromedriver.exe"):
            version = _version_tuple(driver.parent.name)
            if version:
                candidates.append((version, driver))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        if chrome_version:
            same_major = [item for item in candidates if item[0][0] == chrome_version[0]]
            if same_major:
                return same_major[0][1]
            return None

        return candidates[0][1]

    def _download_driver(self, chrome_version: tuple[int, int, int, int]) -> Path:
        version_text = ".".join(str(x) for x in chrome_version)
        cache_dir = self._cache_root() / version_text
        driver_path = cache_dir / "chromedriver.exe"
        if driver_path.exists():
            return driver_path

        url = (
            "https://storage.googleapis.com/chrome-for-testing-public/"
            f"{version_text}/win64/chromedriver-win64.zip"
        )

        print(f"[Browser] 本机没有 Chrome {chrome_version[0]} driver，正在下载 {version_text}...")
        try:
            response = requests.get(url, timeout=(15, 120))
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(
                f"自动下载 ChromeDriver {version_text} 失败: {type(exc).__name__}: {exc}"
            ) from exc

        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                member = next(
                    name for name in zf.namelist()
                    if name.lower().endswith("/chromedriver.exe")
                )
                with zf.open(member) as src, driver_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        except Exception as exc:
            raise RuntimeError(
                f"ChromeDriver 压缩包解压失败: {type(exc).__name__}: {exc}"
            ) from exc

        print(f"[Browser] ChromeDriver 已缓存: {driver_path}")
        return driver_path

    def _build_service(self, chrome_binary: Path | None) -> Service:
        chrome_version = self._detect_chrome_version(chrome_binary) if chrome_binary else None
        version_text = ".".join(str(x) for x in chrome_version) if chrome_version else "未知"
        print(f"[Browser] Chrome: {chrome_binary or '未识别到路径'} | 版本: {version_text}")

        if not chrome_version:
            raise RuntimeError("无法识别本机 Chrome 版本，已停止，避免使用错误的 ChromeDriver。")

        driver = self._find_cached_driver(chrome_version)
        if driver:
            print(f"[Browser] 使用本地缓存 ChromeDriver: {driver}")
        else:
            driver = self._download_driver(chrome_version)

        return Service(executable_path=str(driver))

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

        print(f"[Browser] 正在准备 {self.country} Chrome Profile...")
        chrome_binary = self._find_chrome_binary()
        if chrome_binary:
            options.binary_location = str(chrome_binary)

        service = self._build_service(chrome_binary)

        print(f"[Browser] 正在启动 {self.country} Chrome...")
        self.driver = webdriver.Chrome(service=service, options=options)
        print(f"[Browser] {self.country} Chrome 启动成功。")

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
        WebDriverWait(self.driver, wait_seconds).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

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
                self.driver.execute_script("window.location.href = arguments[0];", url)
            self.navigation_count += 1
            self._wait_body()
        except TimeoutException:
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
