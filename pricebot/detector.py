"""Decides whether a listing is a big enough deal to alert on.

One rule: the price must be at least `min_drop_percent` (default 30%) below
the part's normal price. "Normal" is the lowest of whatever we know:
  * the store's own reference (Keepa 30/90-day average, Best Buy regular
    price, the typical eBay price right now)
  * the typical price the bot has learned for that part over the last
    `learn_window_days` days, from every source
Using the lowest keeps inflated "was" prices from causing false alarms.
An optional per-part `alert_below` price also alerts, if you set one.
"""
from __future__ import annotations

from dataclasses import replace

from .config import Settings
from .matching import any_phrase_in, match_part, tokenize
from .models import Alert, Listing, Part

UNSET = object()


def drop_percent(price: float | None, reference: float | None) -> float | None:
    if not price or not reference or reference <= 0 or price >= reference:
        return None
    return (reference - price) / reference * 100


def resolve_part(listing: Listing, parts: list[Part], settings: Settings) -> Part | None:
    """Which tracked part this listing is (None if excluded or not tracked)."""
    if listing.part_hint is not None:
        return listing.part_hint
    if any_phrase_in(tokenize(listing.title), settings.exclude):
        return None
    return match_part(listing.title, parts)


def price_floor(part: Part | None, settings: Settings) -> float:
    return part.min_price if (part and part.min_price is not None) else settings.min_price


def evaluate(
    listing: Listing,
    parts: list[Part],
    settings: Settings,
    learned_typical: float | None = None,
    part=UNSET,
) -> Alert | None:
    tokens = tokenize(listing.title)
    if part is UNSET:
        part = resolve_part(listing, parts, settings)
    if part is None and listing.part_hint is None and any_phrase_in(tokens, settings.exclude):
        return None
    is_general = part is None and any_phrase_in(tokens, settings.general_keywords)
    if part is None and not is_general:
        return None

    price = listing.price
    if price is None or price < price_floor(part, settings):
        return None

    # Pick the lowest known "normal" price as the reference (on a copy, so the
    # original listing is left untouched).
    listing = replace(listing)
    refs = []
    if listing.reference_price:
        refs.append((listing.reference_price, listing.reference_label or "its usual price"))
    if part and learned_typical:
        refs.append((learned_typical, f"its typical price over the last {settings.learn_window_days} days"))
    if refs:
        listing.reference_price, listing.reference_label = min(refs, key=lambda r: r[0])

    reasons: list[str] = []
    drop = drop_percent(price, listing.reference_price)
    if part:
        threshold = part.min_drop_percent if part.min_drop_percent is not None else settings.min_drop_percent
    else:
        threshold = settings.general_min_drop_percent
    if drop is not None and drop >= threshold:
        reasons.append(f"{drop:.0f}% below {listing.reference_label}")

    if part and part.alert_below is not None and price <= part.alert_below:
        reasons.append(f"Under your ${part.alert_below:,.0f} target for {part.name}")

    if listing.alert_all_matches and part and not reasons:
        reasons.append(f"New deal post for {part.name}")

    if not reasons:
        return None
    if listing.error_words:
        reasons.append("The post also calls it a possible price error")
    return Alert(listing=listing, part=part, reasons=reasons, drop_percent=drop)
