from .bestbuy import BestBuySource
from .keepa import KeepaSource
from .slickdeals import SlickdealsSource

ALL_SOURCES = (KeepaSource, BestBuySource, SlickdealsSource)

__all__ = ["ALL_SOURCES", "BestBuySource", "KeepaSource", "SlickdealsSource"]
