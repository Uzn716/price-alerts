from .bestbuy import BestBuySource
from .dealnews import DealNewsSource
from .ebay import EbaySource
from .keepa import KeepaSource
from .slickdeals import SlickdealsSource

ALL_SOURCES = (KeepaSource, BestBuySource, EbaySource, SlickdealsSource, DealNewsSource)

__all__ = ["ALL_SOURCES", "BestBuySource", "DealNewsSource", "EbaySource", "KeepaSource", "SlickdealsSource"]
