from __future__ import annotations

from .models import ProductSnapshot, ScanTarget


def build_anomaly(
    target: ScanTarget,
    snapshot: ProductSnapshot,
    expected_seller_keywords: list[str] | None = None,
) -> str:
    """Return business anomalies only; parser failures stay in error_reason."""
    issues: list[str] = []

    if snapshot.page_state == "PRODUCT_NOT_FOUND":
        issues.append("页面异常")

    if target.product_type == "本品":
        if snapshot.purchase_box_status == "NO_BUYBOX":
            reason = getattr(snapshot, "purchase_box_reason", "")
            if reason == "PRICE_HIGHER_THAN_TYPICAL":
                issues.append("buy box丢失（价格高于典型价格）")
            elif reason == "NO_FEATURED_OFFER":
                issues.append("buy box丢失（无Featured Offer）")
            else:
                issues.append("buy box丢失")
        elif (
            snapshot.purchase_box_status == "FOUND"
            and snapshot.buybox_seller
            and expected_seller_keywords
        ):
            seller_lower = snapshot.buybox_seller.lower()
            expected = [x.lower() for x in expected_seller_keywords if x]
            if expected and not any(keyword in seller_lower for keyword in expected):
                issues.append(f"buy box被第三方抢占（{snapshot.buybox_seller}）")

    if snapshot.stock_status in {"OUT_OF_STOCK", "UNAVAILABLE"}:
        issues.append("缺货")
    elif snapshot.stock_status == "LOW_STOCK":
        issues.append("库存紧张")

    if snapshot.delivery_over_10_days == "Yes":
        issues.append("配送时间大于10天")

    return "；".join(dict.fromkeys(issues))
