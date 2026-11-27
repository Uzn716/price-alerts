"""New, Buy-It-Now eBay listings via eBay's free Browse API.

For each part in config.yaml the bot searches the newest US listings in
"New" condition and works out the typical eBay price from all of them
(the median). A listing alerts when it's far below that, or under your
alert_below price, AND the seller has a solid feedback record.

Free developer accounts get 5,000 searches a day, so eBay is only checked
every `every_minutes` (default 15), which keeps usage around 2,000 a day.
"""
from __future__ import annotations

import base64
import statistics
from datetime import datetime, timedelta

import requests

from ..config import Config
from ..http import TIMEOUT, SourceError
from ..matching import any_phrase_in, match_part, tokenize
from ..models import Listing, Part
from ..state import State, _parse_time

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"
NEW_CONDITION = "1000"

# Common eBay listing tricks that aren't the actual product at a real price.
EBAY_EXCLUDES = [
    "box only", "empty box", "read description", "see description", "picture of",
    "photo of", "image of", "not working", "broken", "parts only", "for parts",
    "as is", "untested", "no gpu", "no card", "proof of purchase", "receipt",
]


def _money(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


class EbaySource:
    name = "ebay"
    store = "eBay"

    def __init__(self, config: Config, state: State, session: requests.Session, now: datetime):
        self.config = config
        self.cfg = config.ebay
        self.state = state
        self.session = session
        self.now = now
        self.token: str | None = None

    @property
    def available(self) -> bool:
        return self.cfg.enabled and bool(self.config.ebay_client_id and self.config.ebay_client_secret)

    # ---- HTTP -------------------------------------------------------------
    def _get_token(self) -> str:
        creds = f"{self.config.ebay_client_id}:{self.config.ebay_client_secret}".encode()
        try:
            resp = self.session.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials", "scope": SCOPE},
                headers={
                    "Authorization": "Basic " + base64.b64encode(creds).decode(),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise SourceError(f"eBay unreachable: {exc.__class__.__name__}") from None
        if resp.status_code != 200:
            raise SourceError(
                f"eBay rejected the Client ID / Client Secret (HTTP {resp.status_code}). "
                "Use the PRODUCTION keyset (not Sandbox) and check both secrets."
            )
        try:
            return resp.json()["access_token"]
        except (ValueError, KeyError):
            raise SourceError("eBay sign-in returned an unexpected response") from None

    def _search(self, query: str, min_price: float | None) -> list[dict]:
        filters = [
            "buyingOptions:{FIXED_PRICE}",
            f"conditionIds:{{{NEW_CONDITION}}}",
            "itemLocationCountry:US",
            "deliveryCountry:US",
            "priceCurrency:USD",
        ]
        if min_price:
            filters.append(f"price:[{int(min_price)}..]")
        try:
            resp = self.session.get(
                SEARCH_URL,
                params={"q": query, "filter": ",".join(filters), "sort": "newlyListed", "limit": 50},
                headers={"Authorization": f"Bearer {self.token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise SourceError(f"eBay unreachable: {exc.__class__.__name__}") from None
        if resp.status_code == 429:
            raise SourceError("eBay daily search limit reached; it resets at midnight Pacific")
        if resp.status_code != 200:
            raise SourceError(f"eBay search HTTP {resp.status_code}")
        try:
            return resp.json().get("itemSummaries") or []
        except ValueError:
            raise SourceError("eBay returned non-JSON") from None

    # ---- main ---------------------------------------------------------------
    def _due(self) -> bool:
        last = (self.state.meta.get("ebay") or {}).get("last_at")
        return not last or self.now - _parse_time(last) >= timedelta(minutes=self.cfg.every_minutes - 2)

    def fetch(self) -> list[Listing]:
        if not self._due():
            print(f"  ebay: next check within {self.cfg.every_minutes} minutes")
            return []
        searches: dict[str, Part] = {}
        for part in self.config.parts:
            if not part.prebuilt:  # used/refurb prebuilts on eBay are too risky to compare
                searches.setdefault(part.match[0], part)
        if not searches:
            return []

        meta = self.state.meta.setdefault("ebay", {})
        queries = list(searches)
        count = min(len(queries), max(1, self.cfg.max_searches_per_run))
        start = int(meta.get("rotate", 0)) % len(queries)
        batch = [queries[(start + i) % len(queries)] for i in range(count)]

        self.token = self._get_token()
        listings: list[Listing] = []
        for query in batch:
            part = searches[query]
            listings.extend(self._listings_for(part, self._search(query, part.min_price)))

        meta["rotate"] = (start + count) % len(queries)
        meta["last_at"] = self.now.isoformat()
        return listings

    def _listings_for(self, part: Part, items: list[dict]) -> list[Listing]:
        matched = []
        for item in items:
            title = str(item.get("title") or "")
            price = _money((item.get("price") or {}).get("value"))
            if not title or price is None or (item.get("price") or {}).get("currency", "USD") != "USD":
                continue
            tokens = tokenize(title)
            if match_part(title, [part]) is None or self.config.settings.title_is_prebuilt(tokens):
                continue
            if any_phrase_in(tokens, EBAY_EXCLUDES) or any_phrase_in(tokens, self.config.settings.exclude):
                continue
            matched.append((item, title, price))
        if not matched:
            return []

        # Typical price = median of all matching new listings right now, and
        # (once we have a few days) the lower of that and the usual daily median.
        history_key = f"ebay-part:{part.name}"
        prices = [p for _, _, p in matched]
        current_median = statistics.median(prices) if len(prices) >= self.cfg.min_listings_for_typical else None
        usual = self.state.typical_price(history_key, self.now, min_days=3)
        if current_median:
            self.state.record_price(history_key, current_median, self.now)
        typical_candidates = [v for v in (current_median, usual) if v]
        typical = min(typical_candidates) if typical_candidates else None

        listings = []
        for item, title, price in matched:
            seller = item.get("seller") or {}
            pct = _money(seller.get("feedbackPercentage")) or 0
            score = int(seller.get("feedbackScore") or 0)
            if pct < self.cfg.min_seller_feedback_percent or score < self.cfg.min_seller_feedback_score:
                continue
            listings.append(
                Listing(
                    source=self.name,
                    store=self.store,
                    item_id=str(item.get("itemId") or item.get("itemWebUrl")),
                    title=title,
                    url=str(item.get("itemWebUrl") or ""),
                    price=price,
                    reference_price=typical,
                    reference_label="the typical new price on eBay",
                    image_url=(item.get("image") or {}).get("imageUrl"),
                    part_hint=part,
                    note=(
                        f"🛒 eBay seller **{seller.get('username', '?')}** "
                        f"({pct:g}% positive, {score:,} ratings). Read the full listing before buying."
                    ),
                )
            )
        return listings
