"""Shared data types."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Part:
    """One thing you want to track, e.g. "RTX 5080"."""

    name: str
    match: list[str]
    exclude: list[str] = field(default_factory=list)
    alert_below: float | None = None
    min_drop_percent: float | None = None
    min_price: float | None = None
    amazon: list[str] = field(default_factory=list)  # ASINs to watch directly via Keepa


@dataclass
class Listing:
    """A product price seen at a store, normalized across sources."""

    source: str  # "keepa", "bestbuy", "slickdeals"
    store: str  # human-readable store name, e.g. "Amazon"
    item_id: str  # unique within the source
    title: str
    url: str
    price: float | None
    reference_price: float | None = None
    reference_label: str = ""
    image_url: str | None = None
    part_hint: Part | None = None  # set when the listing came from a direct watch
    error_words: bool = False  # the post itself says "price error" etc.
    alert_all_matches: bool = False  # alert on any new post matching a part
    note: str | None = None  # extra caution shown in the alert (e.g. marketplace seller info)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.item_id}"


@dataclass
class Alert:
    listing: Listing
    part: Part | None
    reasons: list[str]
    drop_percent: float | None
