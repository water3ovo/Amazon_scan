from __future__ import annotations

import json
import random
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .amazon_parser import AmazonParser
from .anomaly import build_anomaly
from .browser import BrowserSession
from .io_excel import write_results
from .models import ProductSnapshot, ScanResult, ScanTarget
from .utils import canonical_product_url, timestamp_slug


class Scanner:
    def __init__(self, base_dir: Path, settings: dict, countries: dict, headless: bool | None = None):
        self.base_dir = Path(base_dir)
        self.settings = settings
        self.countries = countries
        self.headless = headless

    def _scan_one(self, browser: BrowserSession, target: ScanTarget, country_cfg: dict) -> ScanResult:
        max_retries = int(self.settings.get("browser", {}).get("max_retries", 2))
        url = canonical_product_url(country_cfg["domain"], target.asin)
        target.url = url
        last_reason = ""
        screenshot = ""
        snapshot = ProductSnapshot()

        for attempt in range(1, max_retries + 2):
            try:
                browser.navigate(url)
                gate = browser.detect_gate()
                if gate == "CAPTCHA":
                    last_reason = "amazon_captcha"
                    screenshot = browser.save_screenshot(f"{target.asin}_captcha_{timestamp_slug()}")
                    if attempt <= max_retries:
                        time.sleep(random.uniform(6, 10) * attempt)
                        continue
                    return ScanResult(target, snapshot, "FAILED", last_reason, attempt, screenshot, "")

                parser = AmazonParser(browser.driver)
                snapshot = parser.extract()
                if snapshot.page_state == "CAPTCHA":
                    last_reason = "amazon_captcha"
                    screenshot = browser.save_screenshot(f"{target.asin}_captcha_{timestamp_slug()}")
                    if attempt <= max_retries:
                        time.sleep(random.uniform(6, 10) * attempt)
                        continue
                    return ScanResult(target, snapshot, "FAILED", last_reason, attempt, screenshot, "")

                if snapshot.page_state == "PRODUCT_NOT_FOUND":
                    anomaly = build_anomaly(target, snapshot, country_cfg.get("expected_seller_keywords", []))
                    screenshot = browser.save_screenshot(f"{target.asin}_not_found_{timestamp_slug()}")
                    return ScanResult(target, snapshot, "OK", "", attempt, screenshot, anomaly)

                core_missing = not snapshot.product_name or (snapshot.price_value is None and not snapshot.stock_text)
                purchase_box_missing = (
                    target.product_type == "本品"
                    and "purchase_box_owner_missing" in snapshot.warnings
                )
                status = "PARTIAL" if (core_missing or purchase_box_missing) else "OK"
                reason = ",".join(snapshot.warnings) if status == "PARTIAL" else ""
                anomaly = build_anomaly(target, snapshot, country_cfg.get("expected_seller_keywords", []))

                browser_cfg = self.settings.get("browser", {})
                if status != "OK" and browser_cfg.get("save_screenshot_on_failure", True):
                    screenshot = browser.save_screenshot(f"{target.asin}_{status.lower()}_{timestamp_slug()}")
                elif anomaly and browser_cfg.get("save_screenshot_on_anomaly", False):
                    screenshot = browser.save_screenshot(f"{target.asin}_anomaly_{timestamp_slug()}")
                return ScanResult(target, snapshot, status, reason, attempt, screenshot, anomaly)

            except Exception as exc:
                last_reason = f"{type(exc).__name__}: {str(exc)[:180]}"
                if attempt <= max_retries:
                    time.sleep(random.uniform(4, 7) * attempt)
                    continue
                screenshot = browser.save_screenshot(f"{target.asin}_failed_{timestamp_slug()}")
                return ScanResult(target, snapshot, "FAILED", last_reason, attempt, screenshot, "")

        return ScanResult(target, snapshot, "FAILED", last_reason or "unknown_error", max_retries + 1, screenshot, "")

    def run(self, targets: list[ScanTarget], output_path: Path) -> list[ScanResult]:
        started_at = datetime.now()
        grouped: dict[str, list[ScanTarget]] = defaultdict(list)
        for target in targets:
            grouped[target.country].append(target)

        results: list[ScanResult] = []
        checkpoint_every = max(1, int(self.settings.get("scan", {}).get("checkpoint_every", 10)))

        for country in sorted(grouped):
            if country not in self.countries:
                for target in grouped[country]:
                    results.append(ScanResult(target, ProductSnapshot(), "FAILED", f"unsupported_country:{country}"))
                continue

            cfg = self.countries[country]
            print(f"\n=== {country} 开始，共 {len(grouped[country])} 个ASIN ===")
            browser = BrowserSession(country, self.settings, cfg, self.base_dir, headless=self.headless)
            try:
                try:
                    browser.start()
                except Exception as exc:
                    reason = f"browser_start_failed:{type(exc).__name__}:{str(exc)[:180]}"
                    print(f"[错误] {country} 浏览器启动失败: {reason}")
                    for target in grouped[country]:
                        results.append(ScanResult(target, ProductSnapshot(), "FAILED", reason))
                    write_results(output_path, results, started_at=started_at)
                    continue

                if not browser.location_is_ready:
                    print(f"[提醒] {country} 尚未运行配送地址配置。价格/库存一般可扫，但配送时间可能使用默认地址。")
                for index, target in enumerate(grouped[country], start=1):
                    print(f"[{country} {index}/{len(grouped[country])}] {target.asin} {target.product}")
                    result = self._scan_one(browser, target, cfg)
                    results.append(result)
                    print(f"  -> {result.scan_status} | 异常: {result.anomaly or '-'} | {result.error_reason or 'OK'}")
                    if len(results) % checkpoint_every == 0:
                        write_results(output_path, results, started_at=started_at)
                        print(f"  已保存检查点: {output_path.name}")
            finally:
                browser.close()

        write_results(output_path, results, started_at=started_at)
        return results
