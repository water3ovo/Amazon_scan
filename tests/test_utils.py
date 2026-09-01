from datetime import date

from src.anomaly import build_anomaly
from src.models import ProductSnapshot, ScanTarget
from src.utils import delivery_over_10_days, extract_asin, normalize_stock, parse_price_value


def test_extract_asin():
    assert extract_asin("https://www.amazon.ae/dp/B0GGQP6FQ3?ref=x") == "B0GGQP6FQ3"


def test_price():
    assert parse_price_value("AED 1,299.00") == 1299.0
    assert parse_price_value("SAR 899") == 899.0


def test_stock():
    assert normalize_stock("In Stock") == "IN_STOCK"
    assert normalize_stock("Only 2 left in stock") == "LOW_STOCK"
    assert normalize_stock("Currently unavailable") == "UNAVAILABLE"


def test_delivery():
    today = date(2026, 9, 1)
    assert delivery_over_10_days("FREE delivery September 5", today) == "No"
    assert delivery_over_10_days("FREE delivery September 15", today) == "Yes"
    assert delivery_over_10_days("Delivery September 10 - 14", today) == "Yes"


def test_anomaly():
    target = ScanTarget("AE", "本品", "P", "Phone", "B0GGQP6FQ3")
    snap = ProductSnapshot(
        buybox_seller="Other Seller",
        stock_status="LOW_STOCK",
        delivery_over_10_days="Yes",
    )
    result = build_anomaly(target, snap, ["Amazon.ae"])
    assert "库存紧张" in result
    assert "配送>10天" in result
    assert "BuyBox异常" in result
