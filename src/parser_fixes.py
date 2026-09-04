from __future__ import annotations

from selenium.webdriver.common.by import By

from .utils import clean_text, normalize_stock


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

STOCK_TEXT_MARKERS = (
    "in stock",
    "left in stock",
    "out of stock",
    "currently unavailable",
    "temporarily out of stock",
    "unavailable",
    "available to ship",
    "usually ships within",
    "ships within",
    "more on the way",
    "order soon",
    "متوفر",
    "غير متوفر",
    "نفد من المخزون",
    "متبقي",
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


def _is_valid_stock_text(value: str) -> bool:
    text = clean_text(value)
    if not text:
        return False
    lower = text.lower()
    if len(text) > 500:
        return False
    if any(marker in lower for marker in SCRIPT_JUNK_MARKERS):
        return False
    return normalize_stock(text) != "UNKNOWN" or any(marker in lower for marker in STOCK_TEXT_MARKERS)


def _visible_text(element) -> str:
    """Read visible text only; never fall back to textContent for stock blocks.

    Amazon AOD containers may contain large inline scripts in textContent even
    when those scripts are not visible on the product page.
    """
    try:
        return clean_text(element.text)
    except Exception:
        return ""


def fixed_stock(self) -> tuple[str, str]:
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
                if _is_valid_stock_text(raw):
                    return raw, normalize_stock(raw)
        except Exception:
            continue

    # Conservative fallback: inspect visible body lines, but only accept a line
    # that itself looks like a stock/availability message.
    try:
        body = self.driver.find_element(By.TAG_NAME, "body").text or ""
        for line in str(body).splitlines():
            raw = clean_text(line)
            if _is_valid_stock_text(raw):
                return raw, normalize_stock(raw)
    except Exception:
        pass
    return "", "UNKNOWN"


def classify_purchase_box_reason(
    seller: str,
    stock_status: str,
    price_value: float | None,
    has_checkout_controls: bool,
    body_text: str,
) -> tuple[str, str]:
    """Return (purchase_box_status, reason) without conflating parser misses.

    reason values are intentionally technical/stable; business-facing Chinese
    labels are produced in anomaly.py.
    """
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

    # A visible checkout control, price, or positive stock state means the page
    # looks sellable; missing Seller is therefore a parser issue, not business
    # proof that the Featured Offer is gone.
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
    """Apply V5.2 parser hotfixes without changing the public output schema."""
    if getattr(parser_cls, "_v52_parser_fixes_applied", False):
        return parser_cls

    original_extract = parser_cls.extract

    def fixed_extract(self):
        self._last_purchase_box_reason = ""
        snapshot = original_extract(self)
        # ProductSnapshot is not slotted; keeping this dynamic avoids a schema
        # migration while still allowing anomaly.py to use the reason.
        snapshot.purchase_box_reason = getattr(self, "_last_purchase_box_reason", "")
        return snapshot

    parser_cls.stock = fixed_stock
    parser_cls.purchase_box_status = fixed_purchase_box_status
    parser_cls.extract = fixed_extract
    parser_cls._v52_parser_fixes_applied = True
    return parser_cls
