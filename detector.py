"""Decides whether a listing looks like a price error."""
from __future__ import annotations

from .config import Settings
from .matching import any_phrase_in, match_part, tokenize
from .models import Alert, Listing, Part


def drop_percent(price: float | None, reference: float | None) -> float | None:
    if not price or not reference or reference <= 0 or price >= reference:
        return None
    return (reference - price) / reference * 100


def evaluate(listing: Listing, parts: list[Part], settings: Settings) -> Alert | None:
    tokens = tokenize(listing.title)

    part = listing.part_hint
    if part is None:
        if any_phrase_in(tokens, settings.exclude):
            return None
        part = match_part(listing.title, parts)
    is_general = part is None and any_phrase_in(tokens, settings.general_keywords)
    if part is None and not is_general:
        return None

    price = listing.price
    if price is not None:
        floor = part.min_price if (part and part.min_price is not None) else settings.min_price
        if price < floor:
            return None

    reasons: list[str] = []
    drop = drop_percent(price, listing.reference_price)

    if part and part.alert_below is not None and price is not None and price <= part.alert_below:
        reasons.append(f"Under your ${part.alert_below:,.0f} target for {part.name}")

    if drop is not None:
        if part:
            threshold = part.min_drop_percent if part.min_drop_percent is not None else settings.min_drop_percent
        else:
            threshold = settings.general_min_drop_percent
        if drop >= threshold:
            label = listing.reference_label or "its usual price"
            reasons.append(f"{drop:.0f}% below {label}")

    if listing.error_words:
        reasons.append("Posted as a possible price error")

    if listing.alert_all_matches and part and not reasons:
        reasons.append(f"New deal post for {part.name}")

    if not reasons:
        return None
    return Alert(listing=listing, part=part, reasons=reasons, drop_percent=drop)
