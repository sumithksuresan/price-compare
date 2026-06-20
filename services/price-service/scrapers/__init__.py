from .blinkit import BlinkitScraper
from .swiggy import SwiggyInstamartscraper
from .zepto import ZeptoScraper
from .bigbasket import BigBasketScraper

ALL_SCRAPERS = [
    BlinkitScraper(),
    SwiggyInstamartscraper(),
    ZeptoScraper(),
    BigBasketScraper(),
]
