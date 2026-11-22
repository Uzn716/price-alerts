"""Slickdeals public RSS feeds: shoppers post deals from every store as they find them."""
from __future__ import annotations

import feedparser

from ..http import SourceError
from .feeds import FeedItem, FeedSource, extract_price, extract_store, plain  # noqa: F401 (re-exported)


class SlickdealsSource(FeedSource):
    name = "slickdeals"
    store = "Slickdeals"

    @property
    def feeds_config(self):
        return self.config.slickdeals

    def parse(self, content: bytes) -> list[FeedItem]:
        parsed = feedparser.parse(content)
        if parsed.bozo and not parsed.entries:
            raise SourceError("feed could not be read")
        items = []
        for entry in parsed.entries:
            items.append(
                FeedItem(
                    item_id=str(entry.get("id") or entry.get("link") or entry.get("title") or ""),
                    title=plain(entry.get("title", "")),
                    url=str(entry.get("link") or ""),
                    body=plain(entry.get("summary", "")),
                )
            )
        return items
