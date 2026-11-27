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
    starting_price: float | None = None  # normal price to use until the bot has learned one
    prebuilt: bool = False  # this entry is for prebuilt PCs, not a loose component
    gpu: str | None = None  # for prebuilts: name of the GPU entry inside (for part-out value)
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
    learn_only: bool = False  # just record the price (e.g. old posts on a feed's first run)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.item_id}"


@dataclass
class Alert:
    listing: Listing
    part: Part | None
    reasons: list[str]
    drop_percent: float | None
    basis: str = ""  # where the "normal price" came from, shown in the alert
    notes: list[str] = field(default_factory=list)  # extra lines for the alert (e.g. part-out value)
