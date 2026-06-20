import random
from .base import BaseScraper, PriceResult, MOCK_CATALOG, find_catalog_key


class BigBasketScraper(BaseScraper):
    platform = "bigbasket"
    platform_display = "BigBasket"
    BASE_URL = "https://www.bigbasket.com"

    def search(self, query: str) -> list[PriceResult]:
        return self._mock_search(query)

    def _mock_search(self, query: str) -> list[PriceResult]:
        key = find_catalog_key(query)
        if not key:
            return []
        item = MOCK_CATALOG[key]
        base = item["base_price"]
        # BigBasket tends to have bulk pricing advantages
        discount = random.choice([0, 0, 3, 5, 7, 10])
        price = round(base * (1 - discount / 100))
        original = base if discount else None
        in_stock = random.random() > 0.05

        return [
            PriceResult(
                platform=self.platform,
                platform_display=self.platform_display,
                product_name=item["name"],
                price=price,
                original_price=original,
                unit=item["unit"],
                image_url=item["image"],
                product_url=f"{self.BASE_URL}/pd/search/?q={query.replace(' ', '+')}",
                in_stock=in_stock,
                delivery_time="30-60 mins",
                discount_pct=discount,
            )
        ]
