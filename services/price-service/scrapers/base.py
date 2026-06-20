from dataclasses import dataclass, field
from typing import Optional
import random


@dataclass
class PriceResult:
    platform: str
    platform_display: str
    product_name: str
    price: float
    original_price: Optional[float]
    unit: str
    image_url: str
    product_url: str
    in_stock: bool
    delivery_time: str
    discount_pct: int = 0

    def to_dict(self):
        return {
            "platform": self.platform,
            "platform_display": self.platform_display,
            "product_name": self.product_name,
            "price": self.price,
            "original_price": self.original_price,
            "unit": self.unit,
            "image_url": self.image_url,
            "product_url": self.product_url,
            "in_stock": self.in_stock,
            "delivery_time": self.delivery_time,
            "discount_pct": self.discount_pct,
        }


class BaseScraper:
    platform = "base"
    platform_display = "Base"

    def search(self, query: str) -> list[PriceResult]:
        raise NotImplementedError


# Shared mock catalog for consistent cross-platform data
MOCK_CATALOG = {
    "milk": {
        "name": "Amul Full Cream Milk",
        "unit": "1 L",
        "base_price": 68,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/13076a.jpg",
    },
    "bread": {
        "name": "Britannia 100% Whole Wheat Bread",
        "unit": "400 g",
        "base_price": 45,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10003a.jpg",
    },
    "eggs": {
        "name": "Farm Fresh Eggs",
        "unit": "12 pcs",
        "base_price": 95,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/16888a.jpg",
    },
    "rice": {
        "name": "India Gate Basmati Rice",
        "unit": "5 kg",
        "base_price": 449,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10000a.jpg",
    },
    "sugar": {
        "name": "Madhur Sugar",
        "unit": "1 kg",
        "base_price": 52,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10001a.jpg",
    },
    "butter": {
        "name": "Amul Butter",
        "unit": "500 g",
        "base_price": 275,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10002a.jpg",
    },
    "paneer": {
        "name": "Amul Paneer",
        "unit": "200 g",
        "base_price": 90,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10004a.jpg",
    },
    "atta": {
        "name": "Aashirvaad Atta",
        "unit": "5 kg",
        "base_price": 280,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10005a.jpg",
    },
    "oil": {
        "name": "Fortune Sunflower Oil",
        "unit": "1 L",
        "base_price": 138,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10006a.jpg",
    },
    "tea": {
        "name": "Tata Tea Gold",
        "unit": "250 g",
        "base_price": 135,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10007a.jpg",
    },
    "coffee": {
        "name": "Nescafe Classic",
        "unit": "100 g",
        "base_price": 260,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10008a.jpg",
    },
    "salt": {
        "name": "Tata Salt Iodised",
        "unit": "1 kg",
        "base_price": 24,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10009a.jpg",
    },
    "banana": {
        "name": "Banana",
        "unit": "6 pcs (~500 g)",
        "base_price": 49,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10010a.jpg",
    },
    "tomato": {
        "name": "Tomato",
        "unit": "500 g",
        "base_price": 35,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10011a.jpg",
    },
    "onion": {
        "name": "Onion",
        "unit": "1 kg",
        "base_price": 40,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10012a.jpg",
    },
    "potato": {
        "name": "Potato",
        "unit": "1 kg",
        "base_price": 35,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10013a.jpg",
    },
    "shampoo": {
        "name": "Head & Shoulders Anti-Dandruff Shampoo",
        "unit": "340 ml",
        "base_price": 349,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10014a.jpg",
    },
    "soap": {
        "name": "Dove Cream Beauty Bar",
        "unit": "4×100 g",
        "base_price": 199,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10015a.jpg",
    },
    "chips": {
        "name": "Lay's Classic Salted Chips",
        "unit": "73 g",
        "base_price": 30,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10016a.jpg",
    },
    "biscuit": {
        "name": "Parle-G Original Glucose Biscuits",
        "unit": "799 g",
        "base_price": 70,
        "image": "https://cdn.grofers.com/cdn-cgi/image/f=auto,fit=scale-down,q=70,metadata=none,w=270/app/images/products/sliding_image/10017a.jpg",
    },
}


def find_catalog_key(query: str) -> str | None:
    q = query.lower().strip()
    for key in MOCK_CATALOG:
        if key in q or q in key:
            return key
    # fuzzy: match first word of product name
    for key, val in MOCK_CATALOG.items():
        name_words = val["name"].lower().split()
        for word in name_words:
            if word in q or q in word:
                return key
    return None
