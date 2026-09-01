from __future__ import annotations

from .models import ProductSnapshot, ScanTarget


def build_anomaly(
    target: ScanTarget,
    snapshot: ProductSnapshot,
    expected_seller_keywords: list[str] | None = None,
) -> str:
    """Return business anomalies only; technical crawler failures stay in error_reason."""
    issues: list[str] = []

    if snapshot.page_state == "PRODUCT_NOT_FOUND":
        issues.append("页面异常")

    if snapshot.stock_status in {"OUT_OF_STOCK", "UNAVAILABLE"}:
        issues.append("缺货/不可售")
    elif snapshot.stock_status == "LOW_STOCK":
        issues.append("库存紧张")

    if snapshot.delivery_over_10_days == "Yes":
        issues.append("配送>10天")

    if target.product_type == "本品" and snapshot.buybox_seller and expected_seller_keywords:
        seller = snapshot.buybox_seller.lower()
        expected = [x.lower() for x in expected_seller_keywords if x]
        if expected and not any(keyword in seller for keyword in expected):
            issues.append("BuyBox异常")

    return "；".join(dict.fromkeys(issues))
