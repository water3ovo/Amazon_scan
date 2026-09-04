from datetime import date

from src.amazon_parser import AmazonParser
from src.anomaly import build_anomaly
from src.models import ProductSnapshot, ScanTarget
from src.parser_fixes import _is_valid_stock_text, _strict_stock_status, classify_purchase_box_reason
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


def test_stock_javascript_is_rejected():
    junk = 'P.when("A", "load").execute("aod-assets-loaded", function(A){ window.ue.count("x", 1); });'
    assert not _is_valid_stock_text(junk)
    assert _is_valid_stock_text("Only 1 left in stock (more on the way).")
    assert _is_valid_stock_text("Temporarily out of stock. Order now and we'll deliver when available.")


def test_strict_stock_does_not_treat_generic_only_as_low_stock():
    copy = "USA MARKET ONLY WORK ON TMOBILE MINT TELLO OR ANY UNDER TMOBILE NETWORK"
    assert _strict_stock_status(copy) == "UNKNOWN"
    assert not _is_valid_stock_text(copy)
    assert _strict_stock_status("Only 1 left in stock - order soon.") == "LOW_STOCK"
    assert _strict_stock_status("Only 3 left in stock (more on the way).") == "LOW_STOCK"


def test_delivery():
    today = date(2026, 9, 1)
    assert delivery_over_10_days("FREE delivery September 5", today) == "No"
    assert delivery_over_10_days("FREE delivery September 15", today) == "Yes"
    assert delivery_over_10_days("Delivery September 10 - 14", today) == "Yes"


def test_anomaly():
    target = ScanTarget("AE", "本品", "P", "Phone", "B0GGQP6FQ3")
    snap = ProductSnapshot(
        buybox_seller="Other Seller",
        purchase_box_status="FOUND",
        stock_status="LOW_STOCK",
        delivery_over_10_days="Yes",
    )
    result = build_anomaly(target, snap, ["Amazon.ae"])
    assert "库存紧张" in result
    assert "配送时间大于10天" in result
    assert "buy box被第三方抢占（Other Seller）" in result


def test_purchase_box_label_variants():
    seller, fulfiller = AmazonParser._parse_labeled_lines(
        "Shipper / Seller\nAmazon.ae\nGift options\nAvailable at checkout"
    )
    assert seller == "Amazon.ae"
    assert fulfiller == ""

    seller, fulfiller = AmazonParser._parse_labeled_lines(
        "Delivered by\nAmazon.ae\nSold by\nTell Tech Trading FZ-LLC\nPayment\nSecure transaction"
    )
    assert seller == "Tell Tech Trading FZ-LLC"
    assert fulfiller == "Amazon.ae"

    seller, fulfiller = AmazonParser._parse_labeled_lines(
        "Delivered by Amazon.ae Sold by Tell Tech Trading FZ-LLC"
    )
    assert seller == "Tell Tech Trading FZ-LLC"
    assert fulfiller == "Amazon.ae"


def test_missing_purchase_box_is_not_business_anomaly():
    target = ScanTarget("AE", "本品", "P", "Phone", "B0GGQP6FQ3")
    snap = ProductSnapshot(
        buybox_seller="", purchase_box_status="PARSE_FAILED", stock_status="IN_STOCK"
    )
    assert "buy box丢失" not in build_anomaly(target, snap, ["Amazon.ae"])


def test_purchase_box_status_signals():
    assert AmazonParser._classify_purchase_box(
        seller="Amazon.ae", stock_status="IN_STOCK", price_value=2699.0,
        has_checkout_controls=True, body_text="In Stock"
    ) == "FOUND"

    assert AmazonParser._classify_purchase_box(
        seller="", stock_status="UNAVAILABLE", price_value=None,
        has_checkout_controls=False, body_text="Currently unavailable"
    ) == "NO_BUYBOX"

    assert AmazonParser._classify_purchase_box(
        seller="", stock_status="IN_STOCK", price_value=2699.0,
        has_checkout_controls=True, body_text="In Stock"
    ) == "PARSE_FAILED"

    assert AmazonParser._classify_purchase_box(
        seller="", stock_status="UNKNOWN", price_value=None,
        has_checkout_controls=False, body_text="Product detail page"
    ) == "PARSE_FAILED"


def test_specific_no_buybox_reasons():
    status, reason = classify_purchase_box_reason(
        seller="", stock_status="UNKNOWN", price_value=None,
        has_checkout_controls=False,
        body_text="Price higher than typical See all buying options",
    )
    assert status == "NO_BUYBOX"
    assert reason == "PRICE_HIGHER_THAN_TYPICAL"

    status, reason = classify_purchase_box_reason(
        seller="", stock_status="UNKNOWN", price_value=None,
        has_checkout_controls=False,
        body_text="No featured offers available See all buying options",
    )
    assert status == "NO_BUYBOX"
    assert reason == "NO_FEATURED_OFFER"


def test_specific_no_buybox_anomaly_labels():
    target = ScanTarget("AE", "本品", "P", "Phone", "B0GGQP6FQ3")

    price_high = ProductSnapshot(purchase_box_status="NO_BUYBOX", stock_status="UNKNOWN")
    price_high.purchase_box_reason = "PRICE_HIGHER_THAN_TYPICAL"
    assert build_anomaly(target, price_high, ["Amazon.ae"]) == "buy box丢失（价格高于典型价格）"

    no_featured = ProductSnapshot(purchase_box_status="NO_BUYBOX", stock_status="UNKNOWN")
    no_featured.purchase_box_reason = "NO_FEATURED_OFFER"
    assert build_anomaly(target, no_featured, ["Amazon.ae"]) == "buy box丢失（无Featured Offer）"


def test_purchase_box_loss_and_specific_seller_anomaly():
    target = ScanTarget("AE", "本品", "P", "Phone", "B0GGQP6FQ3")
    lost = ProductSnapshot(purchase_box_status="NO_BUYBOX", stock_status="UNAVAILABLE")
    assert "buy box丢失" in build_anomaly(target, lost, ["Amazon.ae"])

    third_party = ProductSnapshot(
        buybox_seller="Tell Tech Trading FZ-LLC",
        purchase_box_status="FOUND",
        stock_status="IN_STOCK",
    )
    assert "buy box被第三方抢占（Tell Tech Trading FZ-LLC）" in build_anomaly(
        target, third_party, ["Amazon.ae"]
    )
