from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Iterable

from .models import ScanResult, ScanTarget
from .utils import clean_text, extract_asin

ACTIVE_VALUES = {"在投", "投放中", "active", "yes", "y", "true", "1"}


class GoogleSheetsError(RuntimeError):
    pass


def _quote_sheet(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _note_for_result(result: ScanResult) -> str:
    note = result.target.remark
    if result.scan_status != "OK":
        tech = f"{result.scan_status}: {result.error_reason}".strip(": ")
        note = f"{note}；{tech}".strip("；") if note else tech
    return note


def _own_values(result: ScanResult) -> list:
    t, s = result.target, result.snapshot
    return [
        date.today().isoformat(), t.country, t.portfolio_brand, t.product, t.asin, t.url,
        s.product_name, t.configuration, t.color, s.price_raw,
        "" if s.price_value is None else s.price_value, s.list_price, s.buybox_seller,
        s.stock_text, s.delivery_text, s.delivery_over_10_days, s.rating, s.reviews,
        s.bsr_primary, s.bsr_secondary, result.anomaly, s.deal_tag, s.amazon_choice,
        _note_for_result(result), s.purchase_box_status,
    ]


def _comp_values(result: ScanResult) -> list:
    t, s = result.target, result.snapshot
    return [
        date.today().isoformat(), t.country, t.portfolio_brand, t.product, t.asin, t.url,
        s.product_name, t.configuration, t.color, s.price_raw,
        "" if s.price_value is None else s.price_value, s.list_price, s.buybox_seller,
        s.stock_text, s.delivery_text, s.delivery_over_10_days, s.rating, s.reviews,
        s.bsr_primary, s.bsr_secondary,
    ]


def _normalize_date(value) -> str:
    text = clean_text(value)
    if not text:
        return ""
    text = text.replace("/", "-")
    parts = text.split("-")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        y, m, d = (int(x) for x in parts)
        if y >= 2000:
            return f"{y:04d}-{m:02d}-{d:02d}"
    return text


class GoogleSheetsClient:
    def __init__(self, base_dir: Path, config_path: Path):
        self.base_dir = Path(base_dir)
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.http_timeout = max(30, int(self.config.get("http_timeout_seconds", 120)))
        self.api_retries = max(0, int(self.config.get("api_retries", 4)))
        self.credentials = None
        self.service = self._build_service()

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            raise GoogleSheetsError(f"Google Sheet 配置文件不存在: {self.config_path}")
        with self.config_path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not cfg.get("spreadsheet_id"):
            raise GoogleSheetsError("config/google_sheets.json 缺少 spreadsheet_id。")
        return cfg

    def _build_service(self):
        try:
            import httplib2
            from google.oauth2.service_account import Credentials
            from google_auth_httplib2 import AuthorizedHttp
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise GoogleSheetsError(
                "缺少 Google API 依赖。请先运行‘升级V5依赖.bat’，或执行 pip install -r requirements.txt。"
            ) from exc

        credentials_file = self.config.get("credentials_file", "config/google_service_account.json")
        credentials_path = Path(credentials_file)
        if not credentials_path.is_absolute():
            credentials_path = self.base_dir / credentials_path
        if not credentials_path.exists():
            raise GoogleSheetsError(
                f"未找到 Google 服务账号密钥: {credentials_path}\n"
                "请把刚下载的 JSON 密钥复制到 config/google_service_account.json。"
            )

        self.credentials = Credentials.from_service_account_file(
            str(credentials_path),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        http = httplib2.Http(timeout=self.http_timeout)
        authorized_http = AuthorizedHttp(self.credentials, http=http)
        return build(
            "sheets",
            "v4",
            http=authorized_http,
            cache_discovery=False,
        )

    @property
    def spreadsheet_id(self) -> str:
        return self.config["spreadsheet_id"]

    def test_connection(self) -> dict:
        try:
            from google.auth.transport.requests import Request
            print("[Google 1/2] 正在获取服务账号访问令牌...")
            self.credentials.refresh(Request())
            print("[Google 1/2] 访问令牌获取成功。")
        except Exception as exc:
            raise GoogleSheetsError(
                "获取 Google 访问令牌失败（oauth2.googleapis.com）。"
                f" 原始错误: {type(exc).__name__}: {exc}"
            ) from exc

        try:
            print("[Google 2/2] 正在读取目标 Google Sheet...")
            meta = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id,
                fields="properties.title,sheets.properties.title",
            ).execute(num_retries=self.api_retries)
            print("[Google 2/2] Google Sheet 读取成功。")
        except Exception as exc:
            raise GoogleSheetsError(
                "读取 Google Sheet 失败（sheets.googleapis.com）。"
                f" 原始错误: {type(exc).__name__}: {exc}"
            ) from exc

        return {
            "title": meta.get("properties", {}).get("title", ""),
            "sheets": [x.get("properties", {}).get("title", "") for x in meta.get("sheets", [])],
        }

    def load_targets(self, filter_active_products: bool = True) -> list[ScanTarget]:
        sheet = self.config.get("mapping_sheet", "Mapping")
        mapping_range = self.config.get("mapping_range", "A:J")
        range_name = f"{_quote_sheet(sheet)}!{mapping_range}"
        response = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueRenderOption="FORMATTED_VALUE",
        ).execute(num_retries=self.api_retries)
        values = response.get("values", [])
        if not values:
            raise GoogleSheetsError(f"Google Sheet 的 {sheet} 没有数据。")

        headers = [clean_text(x) for x in values[0]]
        index = {name: i for i, name in enumerate(headers)}
        required = {"国家", "类型", "ASIN"}
        missing = [x for x in required if x not in index]
        if missing:
            raise GoogleSheetsError(f"Mapping 缺少列: {', '.join(missing)}")

        def val(row, name: str) -> str:
            i = index.get(name)
            return clean_text(row[i]) if i is not None and i < len(row) else ""

        merged: dict[tuple[str, str], ScanTarget] = {}
        for row in values[1:]:
            country = val(row, "国家").upper()
            url = val(row, "URL")
            asin = val(row, "ASIN").upper() or extract_asin(url)
            if not country or not asin:
                continue
            product_type = val(row, "类型") or "本品"
            active_status = val(row, "在投状态")
            if filter_active_products and product_type == "本品":
                if active_status.strip().lower() not in {x.lower() for x in ACTIVE_VALUES}:
                    continue
            target = ScanTarget(
                country=country,
                product_type=product_type,
                portfolio_brand=val(row, "Portfolio/品牌"),
                product=val(row, "产品"),
                asin=asin,
                configuration=val(row, "配置"),
                color=val(row, "颜色"),
                url=url,
                active_status=active_status,
                remark=val(row, "备注"),
            )
            key = (country, asin)
            if key not in merged:
                merged[key] = target
        return list(merged.values())

    def _existing_rows(self, sheet: str, last_col: str, max_rows: int) -> tuple[dict[tuple[str, str, str], int], list[int]]:
        range_name = f"{_quote_sheet(sheet)}!A2:{last_col}{max_rows}"
        response = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueRenderOption="FORMATTED_VALUE",
        ).execute(num_retries=self.api_retries)
        values = response.get("values", [])
        keys: dict[tuple[str, str, str], int] = {}
        free_rows: list[int] = []
        for offset in range(max_rows - 1):
            row_num = offset + 2
            row = values[offset] if offset < len(values) else []
            scan_date = _normalize_date(row[0] if len(row) > 0 else "")
            country = clean_text(row[1] if len(row) > 1 else "").upper()
            asin = clean_text(row[4] if len(row) > 4 else "").upper()
            if scan_date and country and asin:
                keys[(scan_date, country, asin)] = row_num
            elif not scan_date and not country and not asin:
                free_rows.append(row_num)
        return keys, free_rows

    def _upsert_sheet(self, sheet: str, last_col: str, rows: Iterable[list], max_rows: int) -> dict:
        rows = list(rows)
        if not rows:
            return {"updated": 0, "inserted": 0}
        existing, free_rows = self._existing_rows(sheet, last_col, max_rows)
        updates = []
        updated = inserted = 0
        next_row = max_rows + 1

        for row in rows:
            key = (_normalize_date(row[0]), clean_text(row[1]).upper(), clean_text(row[4]).upper())
            row_num = existing.get(key)
            if row_num is not None:
                updated += 1
            else:
                if free_rows:
                    row_num = free_rows.pop(0)
                else:
                    row_num = next_row
                    next_row += 1
                existing[key] = row_num
                inserted += 1
            updates.append({
                "range": f"{_quote_sheet(sheet)}!A{row_num}:{last_col}{row_num}",
                "values": [row],
            })

        for start in range(0, len(updates), 200):
            chunk = updates[start:start + 200]
            self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": chunk},
            ).execute(num_retries=self.api_retries)
        return {"updated": updated, "inserted": inserted}

    def upsert_results(self, results: list[ScanResult]) -> dict:
        own_sheet = self.config.get("own_detail_sheet", "本品扫查明细")
        comp_sheet = self.config.get("competitor_detail_sheet", "竞品扫查明细")
        writable = [r for r in results if r.scan_status != "FAILED"]
        skipped_failed = len(results) - len(writable)
        own_rows = [_own_values(r) for r in writable if r.target.product_type != "竞品"]
        comp_rows = [_comp_values(r) for r in writable if r.target.product_type == "竞品"]
        own_stats = self._upsert_sheet(
            own_sheet, "Y", own_rows, int(self.config.get("own_max_rows", 5000))
        )
        comp_stats = self._upsert_sheet(
            comp_sheet, "T", comp_rows, int(self.config.get("competitor_max_rows", 3000))
        )
        return {"own": own_stats, "competitor": comp_stats, "skipped_failed": skipped_failed}
