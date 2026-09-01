from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScanTarget:
    country: str
    product_type: str
    portfolio_brand: str
    product: str
    asin: str
    configuration: str = ""
    color: str = ""
    url: str = ""
    active_status: str = ""
    remark: str = ""


@dataclass
class ProductSnapshot:
    product_name: str = ""
    price_raw: str = ""
    price_value: Optional[float] = None
    list_price: str = ""
    buybox_seller: str = ""
    ships_from: str = ""
    stock_text: str = ""
    stock_status: str = "UNKNOWN"
    delivery_text: str = ""
    delivery_over_10_days: str = "No"
    rating: str = ""
    reviews: str = ""
    bsr_primary: str = ""
    bsr_secondary: str = ""
    deal_tag: str = "No"
    amazon_choice: str = "No"
    page_title: str = ""
    page_state: str = "OK"
    warnings: list[str] = field(default_factory=list)


@dataclass
class ScanResult:
    target: ScanTarget
    snapshot: ProductSnapshot
    scan_status: str = "OK"
    error_reason: str = ""
    attempts: int = 1
    debug_screenshot: str = ""
    anomaly: str = ""
