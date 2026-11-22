"""Amazon prices via the Keepa API (https://keepa.com/#!api).

Keepa charges in "tokens" that refill every minute:
  * product lookup with stats: 1 token per ASIN
  * deal search: 5 tokens per request (up to 150 deals)
The bot checks your balance first and only spends what you have, rotating
through your watched ASINs if it can't afford all of them in one run.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import requests

from ..config import Config
from ..http import TIMEOUT, SourceError
from ..models import Listing, Part
from ..state import State, _parse_time

API = "https://api.keepa.com"
PRICE_TYPE_INDEX = {"amazon": 0, "new": 1}
DEAL_COST = 5
DATE_RANGES = {"day": 0, "week": 1, "month": 2, "90days": 3}
# Deal interval indexes inside a deal's avg array
MONTH, NINETY_DAYS = 2, 3
AMAZON_DOMAIN_US = 1


def _price(cents) -> float | None:
    if isinstance(cents, (int, float)) and cents > 0:
        return round(cents / 100, 2)
    return None


def _image_url(name: str | None) -> str | None:
    return f"https://m.media-amazon.com/images/I/{name}" if name else None


def _decode_deal_image(chars) -> str | None:
    if isinstance(chars, list) and chars:
        try:
            return "".join(chr(c) for c in chars if isinstance(c, int))
        except ValueError:
            return None
    return None


def _deal_avg(avg, price_type: int, interval: int) -> float | None:
    """Keepa's deal avg is a 2D array; handle either axis order defensively."""
    if not isinstance(avg, list) or not avg:
        return None
    try:
        if len(avg) == 4 and isinstance(avg[0], list) and len(avg[0]) > 4:
            value = avg[interval][price_type]  # [interval][priceType]
        else:
            value = avg[price_type][interval]  # [priceType][interval]
    except (IndexError, TypeError):
        return None
    return _price(value)


def _conservative_reference(*values: float | None) -> float | None:
    """Use the lower of the available averages so short sales don't cause false alarms."""
    valid = [v for v in values if v]
    return min(valid) if valid else None


class KeepaSource:
    name = "keepa"
    store = "Amazon"

    def __init__(self, config: Config, state: State, session: requests.Session, now: datetime):
        self.config = config
        self.cfg = config.keepa
        self.state = state
        self.session = session
        self.now = now
        self.key = config.keepa_api_key
        self.price_type = PRICE_TYPE_INDEX[self.cfg.price_type]
        self.tokens = 0

    @property
    def available(self) -> bool:
        return self.cfg.enabled and bool(self.key)

    # ---- HTTP ------------------------------------------------------------
    def _get(self, endpoint: str, params: dict) -> dict:
        params = {"key": self.key, **params}
        try:
            resp = self.session.get(f"{API}/{endpoint}", params=params, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise SourceError(f"Keepa unreachable: {exc.__class__.__name__}") from None
        try:
            data = resp.json()
        except ValueError:
            raise SourceError(f"Keepa returned non-JSON (HTTP {resp.status_code})") from None
        if isinstance(data.get("tokensLeft"), int):
            self.tokens = data["tokensLeft"]
        if resp.status_code == 429:
            return {}  # out of tokens; just skip until next run
        if resp.status_code in (401, 402, 403):
            raise SourceError(
                f"Keepa rejected the API key (HTTP {resp.status_code}). "
                "Check KEEPA_API_KEY and that your Keepa plan includes API access."
            )
        if resp.status_code != 200:
            raise SourceError(f"Keepa HTTP {resp.status_code}: {str(data.get('error', ''))[:200]}")
        return data

    def _spendable(self) -> int:
        return self.tokens - self.cfg.keep_tokens

    # ---- main --------------------------------------------------------------
    def fetch(self) -> list[Listing]:
        self._get("token", {})  # free; tells us our balance
        listings: list[Listing] = []
        if self._deals_due():
            listings.extend(self._fetch_deals())
        listings.extend(self._fetch_watched())
        return listings

    def _deals_due(self) -> bool:
        if not self.cfg.deal_searches:
            return False
        last = self.state.keepa.get("last_deals_at")
        if not last:
            return True
        return self.now - _parse_time(last) >= timedelta(minutes=self.cfg.deals_every_minutes - 2)

    def _fetch_deals(self) -> list[Listing]:
        listings: list[Listing] = []
        ran_any = False
        for search in self.cfg.deal_searches:
            if self._spendable() < DEAL_COST:
                print(f"  keepa: not enough tokens for deal search ({self.tokens} left)")
                break
            selection = self._deal_selection(search)
            data = self._get("deal", {"selection": json.dumps(selection)})
            ran_any = True
            for deal in (data.get("deals") or {}).get("dr") or []:
                listing = self._deal_to_listing(deal)
                if listing:
                    listings.append(listing)
        if ran_any:
            self.state.keepa["last_deals_at"] = self.now.isoformat()
        return listings

    def _deal_selection(self, search: dict) -> dict:
        min_drop = int(search.get("min_drop_percent", 30))
        selection = {
            "page": 0,
            "domainId": AMAZON_DOMAIN_US,
            "priceTypes": [self.price_type],
            "dateRange": DATE_RANGES.get(str(search.get("date_range", "day")), 0),
            "deltaPercentRange": [max(10, min_drop), 100],
            "currentRange": [
                int(float(search.get("min_price", 25)) * 100),
                int(float(search.get("max_price", 5000)) * 100),
            ],
            "isRangeEnabled": True,
            "isFilterEnabled": False,
            "filterErotic": True,
            "hasReviews": False,
            "sortType": 4,  # biggest percentage drop first
        }
        if search.get("category"):
            selection["includeCategories"] = [int(search["category"])]
        if search.get("title_search"):
            selection["titleSearch"] = str(search["title_search"])
        return selection

    def _deal_to_listing(self, deal: dict) -> Listing | None:
        asin = deal.get("asin")
        current = deal.get("current") or []
        price = _price(current[self.price_type]) if len(current) > self.price_type else None
        if not asin or price is None:
            return None
        avg = deal.get("avg")
        ref = _conservative_reference(
            _deal_avg(avg, self.price_type, MONTH), _deal_avg(avg, self.price_type, NINETY_DAYS)
        )
        return Listing(
            source=self.name,
            store=self.store,
            item_id=asin,
            title=str(deal.get("title") or asin),
            url=f"https://www.amazon.com/dp/{asin}",
            price=price,
            reference_price=ref,
            reference_label="Amazon's 30/90-day average",
            image_url=_image_url(_decode_deal_image(deal.get("image"))),
        )

    def _fetch_watched(self) -> list[Listing]:
        by_asin: dict[str, Part] = {}
        for part in self.config.parts:
            for asin in part.amazon:
                by_asin.setdefault(asin, part)
        if not by_asin:
            return []
        asins = sorted(by_asin)
        budget = min(self._spendable(), 100, len(asins))
        if budget <= 0:
            print(f"  keepa: no tokens left for watched products ({self.tokens} left)")
            return []
        start = int(self.state.keepa.get("rotate", 0)) % len(asins)
        batch = [asins[(start + i) % len(asins)] for i in range(budget)]
        self.state.keepa["rotate"] = (start + budget) % len(asins)

        data = self._get(
            "product",
            {"domain": AMAZON_DOMAIN_US, "asin": ",".join(batch), "stats": 90, "history": 0},
        )
        listings = []
        for product in data.get("products") or []:
            listing = self._product_to_listing(product, by_asin.get(product.get("asin")))
            if listing:
                listings.append(listing)
        return listings

    def _product_to_listing(self, product: dict, part: Part | None) -> Listing | None:
        asin = product.get("asin")
        stats = product.get("stats") or {}

        def stat(name: str) -> float | None:
            values = stats.get(name) or []
            return _price(values[self.price_type]) if len(values) > self.price_type else None

        price = stat("current")
        if not asin or price is None:
            return None
        images = str(product.get("imagesCSV") or "").split(",")
        return Listing(
            source=self.name,
            store=self.store,
            item_id=asin,
            title=str(product.get("title") or (part.name if part else asin)),
            url=f"https://www.amazon.com/dp/{asin}",
            price=price,
            reference_price=_conservative_reference(stat("avg30"), stat("avg90")),
            reference_label="Amazon's 30/90-day average",
            image_url=_image_url(images[0] if images[0] else None),
            part_hint=part,
        )
