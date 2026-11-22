"""Decides whether a listing looks like a price error."""
from __future__ import annotations

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
    learned_low: float | None = None,
    part=UNSET,
) -> Alert | None:
    """learned_low = lowest price the bot has seen for this part recently."""
    tokens = tokenize(listing.title)
    if part is UNSET:
        part = resolve_part(listing, parts, settings)
    if part is None and listing.part_hint is None and any_phrase_in(tokens, settings.exclude):
        return None
    is_general = part is None and any_phrase_in(tokens, settings.general_keywords)
    if part is None and not is_general:
        return None

    price = listing.price
    if price is not None and price < price_floor(part, settings):
        return None

    reasons: list[str] = []

    beat = None
    if part and learned_low and price is not None and settings.beat_low_percent > 0:
        beat = drop_percent(price, learned_low)
        if beat is not None and beat >= settings.beat_low_percent:
            reasons.append(
                f"{beat:.0f}% under the lowest price seen in the last {settings.learn_window_days} days "
                f"(${learned_low:,.2f})"
            )
            if not listing.reference_price:
                listing.reference_price = learned_low
                listing.reference_label = f"the lowest price in {settings.learn_window_days} days"

    drop = drop_percent(price, listing.reference_price)

    if part and part.alert_below is not None and price is not None and price <= part.alert_below:
        reasons.append(f"Under your ${part.alert_below:,.0f} target for {part.name}")

    if drop is not None and listing.reference_price != learned_low:
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
