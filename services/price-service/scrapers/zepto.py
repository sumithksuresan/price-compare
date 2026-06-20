import random
from .base import BaseScraper, PriceResult, MOCK_CATALOG, find_catalog_key


class ZeptoScraper(BaseScraper):
    platform = "zepto"
    platform_display = "Zepto"
    BASE_URL = "https://www.zeptonow.com"

    def search(self, query: str) -> list[PriceResult]:
        return self._mock_search(query)

    def _mock_search(self, query: str) -> list[PriceResult]:
        key = find_catalog_key(query)
        if not key:
            return []
        item = MOCK_CATALOG[key]
        base = item["base_price"]
        # Zepto often has aggressive discounts
        discount = random.choice([0, 5, 10, 15, 18, 20])
        price = round(base * (1 - discount / 100))
        original = base if discount else None
        in_stock = random.random() > 0.12

        return [
            PriceResult(
                platform=self.platform,
                platform_display=self.platform_display,
                product_name=item["name"],
                price=price,
                original_price=original,
                unit=item["unit"],
                image_url=item["image"],
                product_url=f"{self.BASE_URL}/search?q={query.replace(' ', '+')}",
                in_stock=in_stock,
                delivery_time="8-12 mins",
                discount_pct=discount,
            )
        ]
