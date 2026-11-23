"""Remembers what the bot has already seen/alerted between runs.

GitHub Actions starts every run on a fresh machine, so this is saved to
data/state.json and committed back to the repository by the workflow.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HISTORY_DAYS = 90
MAX_SEEN_PER_FEED = 600
ALERT_MEMORY_DAYS = 30


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class State:
    def __init__(self, data: dict[str, Any] | None = None):
        data = data or {}
        self.alerts: dict[str, dict[str, Any]] = data.get("alerts", {})
        self.history: dict[str, dict[str, float]] = data.get("history", {})
        self.seen: dict[str, list[str]] = data.get("seen", {})
        self.keepa: dict[str, Any] = data.get("keepa", {})
        self.errors: dict[str, dict[str, Any]] = data.get("errors", {})
        self.meta: dict[str, Any] = data.get("meta", {})

    # ---- persistence -------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "State":
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            return cls(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            print(f"warning: {path} was unreadable; starting with a fresh state")
            return cls()

    def save(self, path: str | Path, now: datetime | None = None) -> None:
        self._prune(now or utcnow())
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "alerts": self.alerts,
            "history": self.history,
            "seen": self.seen,
            "keepa": self.keepa,
            "errors": self.errors,
            "meta": self.meta,
        }
        path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    def _prune(self, now: datetime) -> None:
        cutoff_day = (now - timedelta(days=HISTORY_DAYS)).date().isoformat()
        for key in list(self.history):
            days = {d: p for d, p in self.history[key].items() if d >= cutoff_day}
            if days:
                self.history[key] = days
            else:
                del self.history[key]
        alert_cutoff = now - timedelta(days=ALERT_MEMORY_DAYS)
        for key in list(self.alerts):
            if _parse_time(self.alerts[key].get("at")) < alert_cutoff:
                del self.alerts[key]
        for feed in self.seen:
            self.seen[feed] = self.seen[feed][-MAX_SEEN_PER_FEED:]

    # ---- price history (daily lowest price) ---------------------------
    def record_price(self, key: str, price: float, now: datetime | None = None) -> None:
        day = (now or utcnow()).date().isoformat()
        days = self.history.setdefault(key, {})
        if day not in days or price < days[day]:
            days[day] = round(price, 2)

    def typical_price(
        self, key: str, now: datetime | None = None, min_days: int = 5, days: int | None = None
    ) -> float | None:
        """Median of daily lows (excluding today, optionally only the last `days` days),
        once we have at least `min_days` days of prices."""
        now = now or utcnow()
        today = now.date().isoformat()
        cutoff = (now - timedelta(days=days)).date().isoformat() if days else ""
        values = [p for d, p in self.history.get(key, {}).items() if d != today and d >= cutoff]
        if len(values) < min_days:
            return None
        return statistics.median(values)

    def days_of_data(self, key: str, now: datetime | None = None, days: int = 30) -> int:
        """How many days (excluding today) of prices we have in the window."""
        now = now or utcnow()
        today = now.date().isoformat()
        cutoff = (now - timedelta(days=days)).date().isoformat()
        return sum(1 for d in self.history.get(key, {}) if d != today and d >= cutoff)

    # ---- alert de-duplication -----------------------------------------
    def should_alert(self, key: str, price: float | None, realert_hours: float, now: datetime | None = None) -> bool:
        now = now or utcnow()
        prev = self.alerts.get(key)
        if not prev:
            return True
        if price is not None and prev.get("price") and price < prev["price"] * 0.95:
            return True  # dropped noticeably further since the last alert
        return now - _parse_time(prev.get("at")) >= timedelta(hours=realert_hours)

    def mark_alerted(self, key: str, price: float | None, now: datetime | None = None) -> None:
        self.alerts[key] = {"price": price, "at": (now or utcnow()).isoformat()}

    # ---- feed items already processed ---------------------------------
    def is_seen(self, feed: str, item_id: str) -> bool:
        return item_id in self.seen.get(feed, [])

    def mark_seen(self, feed: str, item_id: str) -> None:
        items = self.seen.setdefault(feed, [])
        if item_id not in items:
            items.append(item_id)

    def feed_initialized(self, feed: str) -> bool:
        return feed in self.seen

    # ---- source health --------------------------------------------------
    def record_success(self, source: str) -> None:
        self.errors.pop(source, None)

    def record_failure(self, source: str, message: str) -> int:
        entry = self.errors.setdefault(source, {"count": 0, "warned": False})
        entry["count"] += 1
        entry["last_error"] = message[:300]
        return entry["count"]


def _parse_time(value: Any) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
