"""Deals from every other store (Newegg, Micro Center, B&H, Walmart, ...)
via Slickdeals' public RSS feeds, where shoppers post deals as they find them.

There's no "normal price" here, so a post alerts when it matches a tracked
part AND (it's under your alert_below price OR it's called a price error).
"""
from __future__ import annotations

import html
import re
from datetime import datetime

import feedparser
import requests

from ..config import Config
from ..http import TIMEOUT, SourceError
from ..models import Listing
from ..state import State

_PRICE_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(\.\d{1,2})?")
_ERROR_RE = re.compile(
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
        whole = m.group(1).replace(",", "")
        cents = m.group(2) or ""
        try:
            return float(whole + cents)
        except ValueError:
            continue
    return None


def extract_store(title: str) -> str:
    for name, pattern in _STORE_RES:
        if pattern.search(title):
            return name
    return "Slickdeals"


def _plain(text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", text or ""))


class SlickdealsSource:
    name = "slickdeals"
    store = "Slickdeals"

    def __init__(self, config: Config, state: State, session: requests.Session, now: datetime):
        self.config = config
        self.state = state
        self.session = session
        self.now = now

    @property
    def available(self) -> bool:
        return self.config.slickdeals.enabled and bool(self.config.slickdeals.feeds)

    def fetch(self) -> list[Listing]:
        listings: list[Listing] = []
        failures = []
        for feed in self.config.slickdeals.feeds:
            try:
                listings.extend(self._fetch_feed(feed))
            except SourceError as exc:
                failures.append(f"{feed.get('name', feed['url'])}: {exc}")
        if failures and len(failures) == len(self.config.slickdeals.feeds):
            raise SourceError("; ".join(failures))
        for f in failures:
            print(f"  slickdeals warning: {f}")
        return listings

    def _fetch_feed(self, feed: dict) -> list[Listing]:
        url = str(feed["url"])
        feed_id = f"slickdeals:{feed.get('name') or url}"
        try:
            resp = self.session.get(url, timeout=TIMEOUT, headers={"Accept": "application/rss+xml, application/xml"})
        except requests.RequestException as exc:
            raise SourceError(f"unreachable ({exc.__class__.__name__})") from None
        if resp.status_code != 200:
            raise SourceError(f"HTTP {resp.status_code}")
        parsed = feedparser.parse(resp.content)
        if parsed.bozo and not parsed.entries:
            raise SourceError("feed could not be read")

        first_time = not self.state.feed_initialized(feed_id)
        self.state.seen.setdefault(feed_id, [])
        listings = []
        for entry in parsed.entries:
            item_id = str(entry.get("id") or entry.get("link") or entry.get("title") or "")
            if not item_id or self.state.is_seen(feed_id, item_id):
                continue
            self.state.mark_seen(feed_id, item_id)
            if first_time:
                continue  # don't flood you with old posts on the very first run
            title = _plain(entry.get("title", "")).strip()
            body = _plain(entry.get("summary", ""))[:600]
            listings.append(
                Listing(
                    source=self.name,
                    store=extract_store(title),
                    item_id=item_id,
                    title=title,
                    url=str(entry.get("link") or ""),
                    price=extract_price(title),
                    error_words=bool(_ERROR_RE.search(title) or _ERROR_RE.search(body)),
                    alert_all_matches=bool(feed.get("alert_all_matches", False)),
                )
            )
        if first_time:
            print(f"  slickdeals: first run for '{feed.get('name', url)}', remembered {len(parsed.entries)} existing posts")
        return listings
