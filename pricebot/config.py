"""Loads config.yaml and environment secrets."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import Part

_ASIN_RE = re.compile(r"(?:/dp/|/gp/product/|/product/|^)([A-Z0-9]{10})(?:[/?#]|$)")


class ConfigError(Exception):
    pass


def parse_asin(value: str) -> str:
    """Accept a bare ASIN or any Amazon product link and return the ASIN."""
    value = str(value).strip()
    m = _ASIN_RE.search(value)
    if not m:
        raise ConfigError(
            f"Couldn't find an Amazon product ID (ASIN) in {value!r}. "
            "Paste the product link or the 10-character ASIN."
        )
    return m.group(1)


@dataclass
class Settings:
    min_drop_percent: float = 35
    general_min_drop_percent: float = 50
    min_price: float = 25
    realert_after_hours: float = 24
    mention: str = ""
    general_keywords: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass
class KeepaConfig:
    enabled: bool = True
    price_type: str = "amazon"  # amazon | new
    deals_every_minutes: int = 30
    deal_searches: list[dict[str, Any]] = field(default_factory=list)
    keep_tokens: int = 0


@dataclass
class BestBuyConfig:
    enabled: bool = True
    include_open_box: bool = False


@dataclass
class FeedsConfig:
    enabled: bool = True
    feeds: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EbayConfig:
    enabled: bool = True
    every_minutes: int = 15
    max_searches_per_run: int = 25
    min_seller_feedback_percent: float = 98.0
    min_seller_feedback_score: int = 50
    min_listings_for_typical: int = 6


@dataclass
class Config:
    settings: Settings
    parts: list[Part]
    keepa: KeepaConfig
    bestbuy: BestBuyConfig
    slickdeals: FeedsConfig
    dealnews: FeedsConfig = field(default_factory=FeedsConfig)
    ebay: EbayConfig = field(default_factory=EbayConfig)
    discord_webhook_url: str | None = None
    keepa_api_key: str | None = None
    bestbuy_api_key: str | None = None
    ebay_client_id: str | None = None
    ebay_client_secret: str | None = None


def _num(value: Any, name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{name} should be a number, got {value!r}") from None


def _str_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, (str, int)) for v in value):
        return [str(v) for v in value]
    raise ConfigError(f"{name} should be a list of text values")


def _parse_part(raw: Any, index: int) -> Part:
    if not isinstance(raw, dict) or not raw.get("name"):
        raise ConfigError(f"parts entry #{index + 1} needs at least a 'name'")
    name = str(raw["name"])
    where = f"part '{name}'"
    match = _str_list(raw.get("match"), f"{where} match") or [name]
    return Part(
        name=name,
        match=match,
        exclude=_str_list(raw.get("exclude"), f"{where} exclude"),
        alert_below=_num(raw.get("alert_below"), f"{where} alert_below"),
        min_drop_percent=_num(raw.get("min_drop_percent"), f"{where} min_drop_percent"),
        min_price=_num(raw.get("min_price"), f"{where} min_price"),
        amazon=[parse_asin(a) for a in _str_list(raw.get("amazon"), f"{where} amazon")],
    )


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def load_config(path: str | Path) -> Config:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    except yaml.YAMLError as exc:
        raise ConfigError(f"config.yaml has a formatting problem: {exc}") from None
    if not isinstance(raw, dict):
        raise ConfigError("config.yaml should contain sections like 'settings:' and 'parts:'")

    s = raw.get("settings") or {}
    settings = Settings(
        min_drop_percent=_num(s.get("min_drop_percent"), "min_drop_percent") or 35,
        general_min_drop_percent=_num(s.get("general_min_drop_percent"), "general_min_drop_percent") or 50,
        min_price=_num(s.get("min_price"), "min_price") or 0,
        realert_after_hours=_num(s.get("realert_after_hours"), "realert_after_hours") or 24,
        mention=str(s.get("mention") or ""),
        general_keywords=_str_list(s.get("general_keywords"), "general_keywords"),
        exclude=_str_list(s.get("exclude"), "exclude"),
    )

    parts = [_parse_part(p, i) for i, p in enumerate(raw.get("parts") or [])]

    k = raw.get("keepa") or {}
    price_type = str(k.get("price_type", "amazon")).lower()
    if price_type not in ("amazon", "new"):
        raise ConfigError("keepa.price_type must be 'amazon' or 'new'")
    keepa = KeepaConfig(
        enabled=bool(k.get("enabled", True)),
        price_type=price_type,
        deals_every_minutes=int(k.get("deals_every_minutes", 30)),
        deal_searches=list(k.get("deal_searches") or []),
        keep_tokens=int(k.get("keep_tokens", 0)),
    )

    b = raw.get("bestbuy") or {}
    bestbuy = BestBuyConfig(
        enabled=bool(b.get("enabled", True)),
        include_open_box=bool(b.get("include_open_box", False)),
    )

    e = raw.get("ebay") or {}
    ebay = EbayConfig(
        enabled=bool(e.get("enabled", True)),
        every_minutes=int(e.get("every_minutes", 15)),
        max_searches_per_run=int(e.get("max_searches_per_run", 25)),
        min_seller_feedback_percent=float(e.get("min_seller_feedback_percent", 98)),
        min_seller_feedback_score=int(e.get("min_seller_feedback_score", 50)),
        min_listings_for_typical=int(e.get("min_listings_for_typical", 6)),
    )

    return Config(
        settings=settings,
        parts=parts,
        keepa=keepa,
        bestbuy=bestbuy,
        slickdeals=_feeds(raw, "slickdeals"),
        dealnews=_feeds(raw, "dealnews"),
        ebay=ebay,
        discord_webhook_url=_env("DISCORD_WEBHOOK_URL"),
        keepa_api_key=_env("KEEPA_API_KEY"),
        bestbuy_api_key=_env("BESTBUY_API_KEY"),
        ebay_client_id=_env("EBAY_CLIENT_ID"),
        ebay_client_secret=_env("EBAY_CLIENT_SECRET"),
    )


def _feeds(raw: dict, section: str) -> FeedsConfig:
    data = raw.get(section) or {}
    feeds = data.get("feeds") or []
    for f in feeds:
        if not isinstance(f, dict) or not f.get("url"):
            raise ConfigError(f"each {section} feed needs a 'url'")
    return FeedsConfig(enabled=bool(data.get("enabled", True)), feeds=list(feeds))
