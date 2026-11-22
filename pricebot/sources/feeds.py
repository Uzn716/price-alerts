"""Shared logic for deal-site RSS feeds (Slickdeals, DealNews).

These sites list deals as people/editors find them, across every store.
There's no "normal price" in a feed, so a post alerts when it matches a
tracked part AND (it's under your alert_below price OR it's called a
price error) — or on every match if the feed has alert_all_matches: true.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime

import requests

from ..config import Config, FeedsConfig
from ..http import TIMEOUT, SourceError
from ..models import Listing
from ..state import State

_PRICE_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(\.\d{1,2})?")
ERROR_RE = re.compile(
    r"\b(price\s*(?:error|mistake|glitch)|pricing\s*(?:error|mistake)|mis-?priced|glitch(?:ed)?)\b",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")

KNOWN_STORES = [
    "Amazon", "Newegg", "Best Buy", "Micro Center", "B&H", "Walmart", "Adorama",
    "Antonline", "Costco", "Target", "eBay", "Dell", "Lenovo", "HP", "Office Depot",
    "Staples", "Sam's Club", "Monoprice", "Corsair", "AMD", "Nvidia", "Woot",
]
_STORE_RES = [(s, re.compile(r"(?<![\w])" + re.escape(s) + r"(?![\w])", re.IGNORECASE)) for s in KNOWN_STORES]


def extract_price(title: str) -> float | None:
    """First dollar amount in the title that isn't '$X off', 'save $X', etc."""
    for m in _PRICE_RE.finditer(title):
        before = title[max(0, m.start() - 12) : m.start()].lower()
        after = title[m.end() : m.end() + 12].lower()
        if re.match(r"\s*(off|gift|credit|back|promo|reward|instant)", after):
            continue
        if re.search(r"(save|extra|get|earn|\+)\s*$", before):
            continue
        try:
            return float(m.group(1).replace(",", "") + (m.group(2) or ""))
        except ValueError:
            continue
    return None


def extract_store(title: str, default: str) -> str:
    for name, pattern in _STORE_RES:
        if pattern.search(title):
            return name
    return default


def plain(text: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", text or "")).split())


@dataclass
class FeedItem:
    item_id: str
    title: str
    url: str
    body: str = ""
    price: float | None = None
    store: str | None = None
    image_url: str | None = None


class FeedSource:
    name = "feed"
    store = "Deal site"

    def __init__(self, config: Config, state: State, session: requests.Session, now: datetime):
        self.config = config
        self.state = state
        self.session = session
        self.now = now

    # subclasses provide these
    @property
    def feeds_config(self) -> FeedsConfig:
        raise NotImplementedError

    def parse(self, content: bytes) -> list[FeedItem]:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        return self.feeds_config.enabled and bool(self.feeds_config.feeds)

    def fetch(self) -> list[Listing]:
        listings: list[Listing] = []
        failures = []
        feeds = self.feeds_config.feeds
        for feed in feeds:
            try:
                listings.extend(self._fetch_feed(feed))
            except SourceError as exc:
                failures.append(f"{feed.get('name', feed['url'])}: {exc}")
        if failures and len(failures) == len(feeds):
            raise SourceError("; ".join(failures))
        for f in failures:
            print(f"  {self.name} warning: {f}")
        return listings

    def _fetch_feed(self, feed: dict) -> list[Listing]:
        url = str(feed["url"])
        label = feed.get("name") or url
        feed_id = f"{self.name}:{label}"
        try:
            resp = self.session.get(url, timeout=TIMEOUT, headers={"Accept": "application/rss+xml, application/xml"})
        except requests.RequestException as exc:
            raise SourceError(f"unreachable ({exc.__class__.__name__})") from None
        if resp.status_code != 200:
            raise SourceError(f"HTTP {resp.status_code}")
        items = self.parse(resp.content)

        first_time = not self.state.feed_initialized(feed_id)
        self.state.seen.setdefault(feed_id, [])
        listings = []
        for item in items:
            if not item.item_id or self.state.is_seen(feed_id, item.item_id):
                continue
            self.state.mark_seen(feed_id, item.item_id)
            if first_time:
                continue  # don't flood you with old posts on the very first run
            listings.append(
                Listing(
                    source=self.name,
                    store=item.store or extract_store(item.title, self.store),
                    item_id=item.item_id,
                    title=item.title,
                    url=item.url,
                    price=item.price if item.price is not None else extract_price(item.title),
                    image_url=item.image_url,
                    error_words=bool(ERROR_RE.search(item.title) or ERROR_RE.search(item.body[:600])),
                    alert_all_matches=bool(feed.get("alert_all_matches", False)),
                )
            )
        if first_time:
            print(f"  {self.name}: first run for '{label}', remembered {len(items)} existing posts")
        return listings
