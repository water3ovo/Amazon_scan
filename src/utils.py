from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urlparse

ASIN_RE = re.compile(r"\b([A-Z0-9]{10})\b", re.I)
MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def extract_asin(value: str) -> str:
    text = clean_text(value).upper()
    if not text:
        return ""
    patterns = [
        r"/dp/([A-Z0-9]{10})(?:[/?]|$)",
        r"/gp/product/([A-Z0-9]{10})(?:[/?]|$)",
        r"/product/([A-Z0-9]{10})(?:[/?]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).upper()
    match = ASIN_RE.search(text)
    return match.group(1).upper() if match else ""


def canonical_product_url(domain: str, asin: str) -> str:
    return f"https://www.{domain}/dp/{asin.upper()}"


def url_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def parse_price_value(raw: str):
    text = clean_text(raw)
    if not text:
        return None
    # Keep the first plausible decimal number. Amazon AE/SA normally uses comma as thousands separator.
    match = re.search(r"(?<!\d)(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def normalize_stock(text: str) -> str:
    value = clean_text(text).lower()
    if not value:
        return "UNKNOWN"

    unavailable = [
        "currently unavailable", "temporarily out of stock", "unavailable",
        "not available", "غير متوفر", "غير متاح",
    ]
    out_of_stock = [
        "out of stock", "sold out", "no longer available", "نفد من المخزون",
    ]
    low_stock = [
        "only ", "left in stock", "few left", "limited stock",
        "تبقى فقط", "متبقي",
    ]
    in_stock = [
        "in stock", "available to ship", "متوفر", "متوفر في المخزون",
    ]

    if any(k in value for k in unavailable):
        return "UNAVAILABLE"
    if any(k in value for k in out_of_stock):
        return "OUT_OF_STOCK"
    if any(k in value for k in low_stock):
        return "LOW_STOCK"
    if any(k in value for k in in_stock):
        return "IN_STOCK"
    return "UNKNOWN"


def _future_date(month: int, day: int, today: date) -> date | None:
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate >= today:
            return candidate
    return None


def extract_delivery_dates(text: str, today: date | None = None) -> list[date]:
    today = today or date.today()
    value = clean_text(text)
    if not value:
        return []

    found: list[date] = []
    month_words = "|".join(sorted(MONTHS.keys(), key=len, reverse=True))

    # September 14 - 18 / Sep 14–18
    range_re = re.compile(
        rf"\b({month_words})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*[-–—]\s*(\d{{1,2}})(?:st|nd|rd|th)?\b",
        re.I,
    )
    for m in range_re.finditer(value):
        month = MONTHS[m.group(1).lower()]
        for day_num in (int(m.group(2)), int(m.group(3))):
            candidate = _future_date(month, day_num, today)
            if candidate:
                found.append(candidate)

    # September 14 / 14 September
    month_day_re = re.compile(
        rf"\b({month_words})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.I
    )
    day_month_re = re.compile(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_words})\b", re.I
    )
    for m in month_day_re.finditer(value):
        candidate = _future_date(MONTHS[m.group(1).lower()], int(m.group(2)), today)
        if candidate:
            found.append(candidate)
    for m in day_month_re.finditer(value):
        candidate = _future_date(MONTHS[m.group(2).lower()], int(m.group(1)), today)
        if candidate:
            found.append(candidate)

    # De-duplicate while keeping sort order.
    return sorted(set(found))


def delivery_over_10_days(text: str, today: date | None = None) -> str:
    today = today or date.today()
    value = clean_text(text).lower()
    if not value:
        return "No"
    if any(word in value for word in ("today", "tomorrow", "اليوم", "غد")):
        return "No"

    dates = extract_delivery_dates(text, today=today)
    if dates:
        latest = max(dates)
        return "Yes" if (latest - today).days > 10 else "No"

    # Fallback for phrases such as "delivery in 12 - 15 days".
    day_ranges = re.findall(r"(\d{1,3})\s*(?:-|–|to)\s*(\d{1,3})\s*days?", value)
    if day_ranges:
        max_days = max(max(int(a), int(b)) for a, b in day_ranges)
        return "Yes" if max_days > 10 else "No"
    single_days = re.findall(r"(?:in|within)\s+(\d{1,3})\s*days?", value)
    if single_days:
        return "Yes" if max(map(int, single_days)) > 10 else "No"
    return "No"


def safe_filename(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", clean_text(text))
    return cleaned.strip("._") or "item"


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
