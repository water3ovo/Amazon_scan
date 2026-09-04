from __future__ import annotations

import re

from selenium.webdriver.common.by import By

from .utils import clean_text


SCRIPT_JUNK_MARKERS = (
    "p.when(",
    "aod-assets-loaded",
    "assetsnotloaded",
    "uelogerror",
    "function(",
    "settimeout(",
    "window.ue",
    "a.state(",
)

PRICE_HIGH_MARKERS = (
    "price higher than typical",
    "price is higher than typical",
    "higher than typical",
    "low price standards not met",
)

NO_FEATURED_OFFER_MARKERS = (
    "no featured offers available",
    "no featured offer available",
    "no featured offer",
    "see all buying options",
    "see all buying choices",
    "عرض جميع خيارات الشراء",
)


def _strict_stock_status(value: str) -> str:
    """Classify only explicit stock/availability wording.

    This intentionally avoids the historical broad ``only `` rule, which could
    turn ordinary product copy such as ``USA MARKET ONLY`` into LOW_STOCK.
    """
    text = clean_text(value)
    if not text:
        return "UNKNOWN"
    lower = text.lower()

    unavailable = (
        "currently unavailable",
        "temporarily out of stock",
        "unavailable",
        "not available",
        "غير متوفر",
        "غير متاح",
    )
    out_of_stock = (
        "out of stock",
        "sold out",
        "no longer available",
        "نفد من المخزون",
    )
    low_stock = (
        "left in stock",
        "few left",
        "limited stock",
        "تبقى فقط",
        "متبقي",
    )
    in_stock = (
        "in stock",
        "available to ship",
        "متوفر في المخزون",
        "متوفر",
    )

    if any(x in lower for x in unavailable):
        return "UNAVAILABLE"
    if any(x in lower for x in out_of_stock):
        return "OUT_OF_STOCK"
    if any(x in lower for x in low_stock):
        return "LOW_STOCK"
    if re.search(r"\bonly\s+\d+\s+.*?left\s+in\s+stock\b", lower):
        return "LOW_STOCK"
    if any(x in lower for x in in_stock):
        return "IN_STOCK"
    return "UNKNOWN"


def _is_valid_stock_text(value: str) -> bool:
    text = clean_text(value)
    if not text:
        return False
    lower = text.lower()
    if len(text) > 500:
        return False
    if any(marker in lower for marker in SCRIPT_JUNK_MARKERS):
        return False
    return _strict_stock_status(text) != "UNKNOWN"


def _visible_text(element) -> str:
    """Read visible text only; never fall back to textContent for stock blocks."""
    try:
        return clean_text(element.text)
    except Exception:
        return ""


def fixed_stock(self) -> tuple[str, str]:
    """Read stock only from the main product / purchase-box availability area.

    Do not scan the whole page. On a suppressed/no-Featured-Offer page Amazon
    can preload AOD/other-offer inventory such as ``Only 1 left in stock``.
    That is not the main Featured Offer inventory and must not be reported as
    the product's stock warning.
    """
    selectors = [
        (By.CSS_SELECTOR, "#availability .a-color-success"),
        (By.CSS_SELECTOR, "#availability .a-color-price"),
        (By.CSS_SELECTOR, "#availability span.a-size-medium"),
        (By.ID, "availability"),
        (By.CSS_SELECTOR, "#availabilityInsideBuyBox_feature_div .a-color-success"),
        (By.CSS_SELECTOR, "#availabilityInsideBuyBox_feature_div .a-color-price"),
        (By.CSS_SELECTOR, "#availabilityInsideBuyBox_feature_div span.a-size-medium"),
        (By.ID, "availabilityInsideBuyBox_feature_div"),
    ]
    for by, selector in selectors:
        try:
            for element in self.driver.find_elements(by, selector):
                raw = _visible_text(element)
                status = _strict_stock_status(raw)
                if _is_valid_stock_text(raw):
                    return raw, status
        except Exception:
            continue

    return "", "UNKNOWN"


def classify_purchase_box_reason(
    seller: str,
    stock_status: str,
    price_value: float | None,
    has_checkout_controls: bool,
    body_text: str,
) -> tuple[str, str]:
    """Return (purchase_box_status, reason) without conflating parser misses."""
    if clean_text(seller):
        return "FOUND", ""

    body = clean_text(body_text).lower()

    # Explicit price-suppression wording is more specific than generic
    # "See all buying options", so it must win when both appear.
    if any(marker in body for marker in PRICE_HIGH_MARKERS):
        return "NO_BUYBOX", "PRICE_HIGHER_THAN_TYPICAL"

    if any(marker in body for marker in NO_FEATURED_OFFER_MARKERS):
        return "NO_BUYBOX", "NO_FEATURED_OFFER"

    if stock_status in {"OUT_OF_STOCK", "UNAVAILABLE"}:
        return "NO_BUYBOX", "OUT_OF_STOCK"

    if has_checkout_controls or price_value is not None or stock_status in {"IN_STOCK", "LOW_STOCK"}:
        return "PARSE_FAILED", "PARSER_MISS"

    return "PARSE_FAILED", "INSUFFICIENT_SIGNAL"


def fixed_purchase_box_status(self, seller: str, stock_status: str, price_value: float | None) -> str:
    checkout_selectors = [
        (By.ID, "add-to-cart-button"),
        (By.ID, "buy-now-button"),
        (By.CSS_SELECTOR, "input[name='submit.add-to-cart']"),
        (By.CSS_SELECTOR, "input[name='submit.buy-now']"),
    ]
    has_checkout_controls = False
    for by, selector in checkout_selectors:
        try:
            if self.driver.find_elements(by, selector):
                has_checkout_controls = True
                break
        except Exception:
            continue

    status, reason = classify_purchase_box_reason(
        seller=seller,
        stock_status=stock_status,
        price_value=price_value,
        has_checkout_controls=has_checkout_controls,
        body_text=self._body_text(),
    )
    self._last_purchase_box_reason = reason
    return status


def apply_parser_fixes(parser_cls):
    """Apply parser hotfixes without changing the public output schema."""
    if getattr(parser_cls, "_v52_parser_fixes_applied", False):
        return parser_cls

    original_extract = parser_cls.extract

    def fixed_extract(self):
        self._last_purchase_box_reason = ""
        snapshot = original_extract(self)
        snapshot.purchase_box_reason = getattr(self, "_last_purchase_box_reason", "")
        return snapshot

    parser_cls.stock = fixed_stock
    parser_cls.purchase_box_status = fixed_purchase_box_status
    parser_cls.extract = fixed_extract
    parser_cls._v52_parser_fixes_applied = True
    return parser_cls
