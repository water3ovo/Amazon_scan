from __future__ import annotations

import re
from datetime import date

from selenium.webdriver.common.by import By

from .models import ProductSnapshot
from .utils import clean_text, delivery_over_10_days, normalize_stock, parse_price_value


class AmazonParser:
    def __init__(self, driver):
        self.driver = driver

    def _first_text(self, selectors: list[tuple[str, str]], attr: str | None = None) -> str:
        for by, selector in selectors:
            try:
                elements = self.driver.find_elements(by, selector)
                for element in elements:
                    if attr:
                        value = element.get_attribute(attr)
                    else:
                        value = element.text or element.get_attribute("textContent")
                    value = clean_text(value)
                    if value:
                        return value
            except Exception:
                continue
        return ""

    def _body_text(self) -> str:
        try:
            return clean_text(self.driver.find_element(By.TAG_NAME, "body").text)
        except Exception:
            return ""

    def detect_page_state(self) -> str:
        body = self._body_text().lower()
        title = clean_text(getattr(self.driver, "title", "")).lower()
        source = f"{title} {body[:10000]}"
        captcha = [
            "enter the characters you see below",
            "type the characters you see in this image",
            "sorry, we just need to make sure you're not a robot",
            "captcha",
        ]
        if any(x in source for x in captcha):
            return "CAPTCHA"
        not_found = [
            "sorry! we couldn't find that page",
            "looking for something?",
            "the web address you entered is not a functioning page on our site",
        ]
        if any(x in source for x in not_found):
            return "PRODUCT_NOT_FOUND"
        return "OK"

    def product_name(self) -> str:
        return self._first_text([(By.ID, "productTitle")])

    def price(self) -> tuple[str, float | None]:
        selectors = [
            (By.CSS_SELECTOR, "#apex-pricetopay-accessibility-label"),
            (By.CSS_SELECTOR, "#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen"),
            (By.CSS_SELECTOR, "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen"),
            (By.CSS_SELECTOR, "#corePrice_feature_div .a-price .a-offscreen"),
            (By.CSS_SELECTOR, ".priceToPay .a-offscreen"),
            (By.ID, "priceblock_dealprice"),
            (By.ID, "priceblock_ourprice"),
        ]
        raw = self._first_text(selectors, attr="textContent")
        return raw, parse_price_value(raw)

    def list_price(self) -> str:
        selectors = [
            (By.CSS_SELECTOR, "#corePriceDisplay_desktop_feature_div .a-text-price .a-offscreen"),
            (By.CSS_SELECTOR, "#corePrice_feature_div .a-text-price .a-offscreen"),
            (By.CSS_SELECTOR, ".basisPrice .a-offscreen"),
            (By.CSS_SELECTOR, "span.a-price.a-text-price .a-offscreen"),
        ]
        return self._first_text(selectors, attr="textContent")

    @staticmethod
    def _parse_labeled_lines(text: str) -> tuple[str, str]:
        """Parse Amazon Buy Box labels into purchase-box owner and fulfiller.

        AE/SA currently use several layouts, including ``Shipper / Seller``,
        ``Sold by``, ``Delivered by`` and ``Ships from``. A label/value pair may
        be split across two lines or rendered inline on the same line.
        """
        lines = [clean_text(x) for x in str(text).splitlines() if clean_text(x)]
        seller_labels = [
            "shipper / seller", "shipper/seller", "sold by", "seller",
            "يُباع بواسطة", "يباع بواسطة", "البائع",
        ]
        ship_labels = [
            "delivered by", "ships from", "dispatches from", "shipped from",
            "الشحن من",
        ]
        all_labels = sorted(set(seller_labels + ship_labels), key=len, reverse=True)

        def extract_value(labels: list[str]) -> str:
            # Common two-line layout: label on one line and value on the next.
            for i, line in enumerate(lines):
                normalized = line.lower().rstrip(":：").strip()
                for label in sorted(labels, key=len, reverse=True):
                    if normalized == label.lower() and i + 1 < len(lines):
                        return clean_text(lines[i + 1])

            # Inline layouts, including two labeled fields on the same line.
            for line in lines:
                for label in sorted(labels, key=len, reverse=True):
                    match = re.search(
                        rf"(?:^|\s){re.escape(label)}\s*(?:[:：\-]\s*)?(.+)$",
                        line,
                        flags=re.I,
                    )
                    if not match:
                        continue
                    value = clean_text(match.group(1))
                    cut_positions: list[int] = []
                    for other in all_labels:
                        marker = re.search(
                            rf"\s+{re.escape(other)}(?:\s|[:：\-]|$)",
                            value,
                            flags=re.I,
                        )
                        if marker:
                            cut_positions.append(marker.start())
                    if cut_positions:
                        value = clean_text(value[: min(cut_positions)])
                    if value:
                        return value
            return ""

        return extract_value(seller_labels), extract_value(ship_labels)

    def merchant(self) -> tuple[str, str]:
        # The old script used merchantInfoFeature_feature_div. Keep that proven
        # selector, but read the semantic value rather than a fixed array index.
        seller = self._first_text([
            (By.CSS_SELECTOR, "#merchantInfoFeature_feature_div .offer-display-feature-text-message"),
            (By.ID, "sellerProfileTriggerId"),
            (By.CSS_SELECTOR, "#merchantInfoFeature_feature_div a[href*='seller']"),
        ])
        ships_from = self._first_text([
            (By.CSS_SELECTOR, "#fulfillerInfoFeature_feature_div .offer-display-feature-text-message"),
            (By.CSS_SELECTOR, "#fulfillerInfoFeature_feature_div a"),
        ])

        # Amazon may render label/value pairs as plain text rather than links.
        for block_id in ("merchantInfoFeature_feature_div", "fulfillerInfoFeature_feature_div"):
            try:
                block = self.driver.find_element(By.ID, block_id)
                block_text = block.text or block.get_attribute("innerText") or ""
                parsed_seller, parsed_ship = self._parse_labeled_lines(block_text)
                seller = seller or parsed_seller
                ships_from = ships_from or parsed_ship
            except Exception:
                pass

        # Older layouts expose one merchant-info sentence.
        merchant_info = self._first_text([(By.ID, "merchant-info")])
        if merchant_info:
            if not seller:
                match = re.search(
                    r"(?:shipper\s*/\s*seller|sold by)\s*:?[ \t]+(.+?)(?=\s+(?:delivered by|ships from|dispatches from)\b|\.|$)",
                    merchant_info,
                    re.I,
                )
                if match:
                    seller = clean_text(match.group(1))
            if not ships_from:
                match = re.search(
                    r"(?:delivered by|ships from|dispatches from|shipped from)\s*:?[ \t]+(.+?)(?=\s+(?:sold by|shipper\s*/\s*seller)\b|\.|$)",
                    merchant_info,
                    re.I,
                )
                if match:
                    ships_from = clean_text(match.group(1))
        return seller, ships_from

    def stock(self) -> tuple[str, str]:
        selectors = [
            (By.ID, "availability"),
            (By.CSS_SELECTOR, "span.a-size-medium.a-color-success.primary-availability-message"),
            (By.CSS_SELECTOR, "#availabilityInsideBuyBox_feature_div"),
        ]
        raw = self._first_text(selectors)
        return raw, normalize_stock(raw)

    def delivery(self) -> tuple[str, str]:
        selectors = [
            (By.ID, "mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE"),
            (By.ID, "mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE-container"),
            (By.CSS_SELECTOR, "#deliveryBlockMessage"),
            (By.CSS_SELECTOR, "#deliveryBlock_feature_div"),
        ]
        raw = self._first_text(selectors)
        if len(raw) > 300:
            raw = raw[:300]
        return raw, delivery_over_10_days(raw, today=date.today())

    def rating_reviews(self) -> tuple[str, str]:
        rating_text = self._first_text([
            (By.ID, "acrPopover"),
            (By.CSS_SELECTOR, "span[data-hook='rating-out-of-text']"),
            (By.CSS_SELECTOR, "#averageCustomerReviews .a-icon-alt"),
        ], attr="title")
        if not rating_text:
            rating_text = self._first_text([
                (By.CSS_SELECTOR, "span[data-hook='rating-out-of-text']"),
                (By.CSS_SELECTOR, "#averageCustomerReviews .a-icon-alt"),
            ])
        rating = ""
        match = re.search(r"([0-5](?:[.,]\d+)?)", rating_text)
        if match:
            rating = match.group(1).replace(",", ".")

        reviews_text = self._first_text([
            (By.ID, "acrCustomerReviewText"),
            (By.CSS_SELECTOR, "span[data-hook='total-review-count']"),
        ])
        reviews = ""
        match = re.search(r"([\d,\.]+)", reviews_text)
        if match:
            reviews = match.group(1).replace(",", "")
        return rating, reviews

    def bsr(self) -> tuple[str, str]:
        text = ""
        selectors = [
            (By.ID, "detailBulletsWrapper_feature_div"),
            (By.ID, "detailBullets_feature_div"),
            (By.ID, "productDetails_detailBullets_sections1"),
            (By.ID, "productDetails_techSpec_section_1"),
        ]
        for by, selector in selectors:
            try:
                elements = self.driver.find_elements(by, selector)
                for element in elements:
                    candidate = clean_text(element.text or element.get_attribute("innerText"))
                    if "best sellers rank" in candidate.lower():
                        text = candidate
                        break
            except Exception:
                continue
            if text:
                break
        if not text:
            return "", ""

        ranks = re.findall(r"#\s*([\d,]+)\s+in\s+([^#|]+?)(?=\s+#\s*[\d,]+\s+in\s+|$)", text, re.I)
        cleaned = []
        for rank, category in ranks[:2]:
            category = clean_text(re.sub(r"\(.*?\)", "", category))
            cleaned.append(f"#{rank} in {category}".strip())
        primary = cleaned[0] if cleaned else ""
        secondary = cleaned[1] if len(cleaned) > 1 else ""
        return primary, secondary

    def badges(self) -> tuple[str, str]:
        deal = "No"
        choice = "No"
        deal_selectors = [
            ".a-badge-label",
            "#dealBadgeSupportingText",
            ".dealBadgeTextColor",
            "[data-a-badge-type='deal']",
            ".s-limited-time-deal",
        ]
        deal_keywords = [
            "limited time deal", "deal", "discount", "prime exclusive deal",
            "lowest price in", "offer", "خصم", "عرض",
        ]
        for selector in deal_selectors:
            try:
                for element in self.driver.find_elements(By.CSS_SELECTOR, selector):
                    text = clean_text(element.text or element.get_attribute("textContent")).lower()
                    if text and any(k in text for k in deal_keywords):
                        deal = "Yes"
                        break
            except Exception:
                continue
            if deal == "Yes":
                break

        choice_selectors = [
            ".mvt-ac-badge-wrapper", ".ac-badge-wrapper", ".s-amazons-choice", ".ac-badge",
            "[data-csa-c-slot-id='AC-badge']",
        ]
        for selector in choice_selectors:
            try:
                if self.driver.find_elements(By.CSS_SELECTOR, selector):
                    choice = "Yes"
                    break
            except Exception:
                continue
        return deal, choice

    def extract(self) -> ProductSnapshot:
        snapshot = ProductSnapshot()
        snapshot.page_title = clean_text(getattr(self.driver, "title", ""))
        snapshot.page_state = self.detect_page_state()
        if snapshot.page_state == "CAPTCHA":
            snapshot.warnings.append("captcha_detected")
            return snapshot
        if snapshot.page_state == "PRODUCT_NOT_FOUND":
            return snapshot

        snapshot.product_name = self.product_name()
        snapshot.price_raw, snapshot.price_value = self.price()
        snapshot.list_price = self.list_price()
        snapshot.buybox_seller, snapshot.ships_from = self.merchant()
        snapshot.stock_text, snapshot.stock_status = self.stock()
        snapshot.delivery_text, snapshot.delivery_over_10_days = self.delivery()
        snapshot.rating, snapshot.reviews = self.rating_reviews()
        snapshot.bsr_primary, snapshot.bsr_secondary = self.bsr()
        snapshot.deal_tag, snapshot.amazon_choice = self.badges()

        if not snapshot.product_name:
            snapshot.warnings.append("product_title_missing")
        if snapshot.price_value is None and snapshot.stock_status not in {"OUT_OF_STOCK", "UNAVAILABLE"}:
            snapshot.warnings.append("price_missing")
        if not snapshot.stock_text:
            snapshot.warnings.append("stock_text_missing")
        if snapshot.stock_status in {"IN_STOCK", "LOW_STOCK"} and not snapshot.buybox_seller:
            snapshot.warnings.append("purchase_box_owner_missing")
        return snapshot
