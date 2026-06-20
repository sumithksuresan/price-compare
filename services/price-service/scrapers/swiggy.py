import random
from .base import BaseScraper, PriceResult, MOCK_CATALOG, find_catalog_key


class SwiggyInstamartscraper(BaseScraper):
    platform = "swiggy_instamart"
    platform_display = "Swiggy Instamart"
    BASE_URL = "https://www.swiggy.com/instamart"

    def search(self, query: str) -> list[PriceResult]:
        return self._mock_search(query)

    def _mock_search(self, query: str) -> list[PriceResult]:
        key = find_catalog_key(query)
        if not key:
            return []
        item = MOCK_CATALOG[key]
        base = item["base_price"]
        # Swiggy Instamart sometimes has higher MRP offset by coupons
        markup = random.choice([0, 2, 5])
        discount = random.choice([0, 0, 5, 10])
        price = round(base * (1 + markup / 100) * (1 - discount / 100))
        original = round(base * (1 + markup / 100)) if discount else None
        in_stock = random.random() > 0.15

        return [
            PriceResult(
                platform=self.platform,
                platform_display=self.platform_display,
                product_name=item["name"],
                price=price,
                original_price=original,
                unit=item["unit"],
                image_url=item["image"],
                product_url=f"{self.BASE_URL}/search?query={query.replace(' ', '%20')}",
                in_stock=in_stock,
                delivery_time="15-20 mins",
                discount_pct=discount,
            )
        ]
