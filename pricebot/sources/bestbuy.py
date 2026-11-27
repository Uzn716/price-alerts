"""Best Buy prices via the official Products API (https://developer.bestbuy.com).

For each part in config.yaml the bot runs a keyword search, then compares
each result's price against Best Buy's own "regular price" and the bot's
own price history for that SKU (whichever is lower, to avoid fake
"was $X" markdowns).
"""
from __future__ import annotations

import re
import time
from datetime import datetime

import requests

from ..config import Config
from ..http import TIMEOUT, SourceError
from ..matching import match_part, tokenize
from ..models import Listing
from ..state import State

API = "https://api.bestbuy.com/v1"
FIELDS = "sku,name,salePrice,regularPrice,url,image,condition,onlineAvailability"
PAUSE_SECONDS = 0.35  # Best Buy allows ~5 requests/second


def _search_terms(phrase: str) -> list[str]:
    terms = [re.sub(r"[^a-z0-9]", "", w.lower()) for w in phrase.split()]
    return [t for t in terms if t]


def _money(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


class BestBuySource:
    name = "bestbuy"
    store = "Best Buy"

    def __init__(self, config: Config, state: State, session: requests.Session, now: datetime):
        self.config = config
        self.state = state
        self.session = session
        self.now = now
        self.key = config.bestbuy_api_key

    @property
    def available(self) -> bool:
        return self.config.bestbuy.enabled and bool(self.key)

    def _search(self, terms: list[str]) -> list[dict]:
        filters = "&".join(f"search={t}" for t in terms)
        params = {
            "apiKey": self.key,
            "format": "json",
            "show": FIELDS,
            "pageSize": 50,
            "sort": "salePrice.asc",
        }
        try:
            resp = self.session.get(f"{API}/products({filters})", params=params, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise SourceError(f"Best Buy unreachable: {exc.__class__.__name__}") from None
        if resp.status_code in (401, 403):
            raise SourceError(
                f"Best Buy rejected the API key or the daily limit was hit (HTTP {resp.status_code})."
            )
        if resp.status_code == 429:
            return []
        if resp.status_code != 200:
            raise SourceError(f"Best Buy HTTP {resp.status_code}")
        try:
            return resp.json().get("products") or []
        except ValueError:
            raise SourceError("Best Buy returned non-JSON") from None

    def fetch(self) -> list[Listing]:
        listings: dict[str, Listing] = {}
        searched: set[tuple[str, ...]] = set()
        for part in self.config.parts:
            terms = tuple(_search_terms(part.match[0]))
            if not terms or terms in searched:
                continue
            searched.add(terms)
            for product in self._search(list(terms)):
                listing = self._to_listing(product)
                if listing and listing.item_id not in listings:
                    listings[listing.item_id] = listing
            time.sleep(PAUSE_SECONDS)
        return list(listings.values())

    def _to_listing(self, product: dict) -> Listing | None:
        sku = product.get("sku")
        name = str(product.get("name") or "")
        price = _money(product.get("salePrice"))
        if not sku or not name or price is None:
            return None
        if product.get("onlineAvailability") is False:
            return None
        condition = str(product.get("condition") or "New").lower()
        if condition != "new" and not self.config.bestbuy.include_open_box:
            return None
        # Only keep history for things we actually track, so the state file stays small.
        prebuilt = self.config.settings.title_is_prebuilt(tokenize(name))
        if match_part(name, self.config.parts, prebuilt=prebuilt) is None:
            return None

        key = f"{self.name}:{sku}"
        regular = _money(product.get("regularPrice"))
        typical = self.state.typical_price(key, self.now)
        self.state.record_price(key, price, self.now)

        candidates = [(regular, "Best Buy's regular price"), (typical, "its usual Best Buy price")]
        candidates = [(v, label) for v, label in candidates if v]
        ref, label = min(candidates) if candidates else (None, "")

        return Listing(
            source=self.name,
            store=self.store,
            item_id=str(sku),
            title=name,
            url=str(product.get("url") or f"https://www.bestbuy.com/site/{sku}.p"),
            price=price,
            reference_price=ref,
            reference_label=label,
            image_url=product.get("image"),
        )
