"""Posts alerts to a Discord channel through a webhook."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

from .http import TIMEOUT
from .models import Alert

RED, ORANGE, BLUE, GREY = 0xE53935, 0xFB8C00, 0x1E88E5, 0x757575
MAX_EMBEDS_PER_MESSAGE = 10


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def resale_lines(alert: Alert, fee_percent: float) -> list[str]:
    """Quick flip math: what you'd pay vs. the normal price, and rough profit after fees."""
    lst = alert.listing
    if lst.price is None or not lst.reference_price or lst.reference_price <= lst.price:
        return []
    normal, price = lst.reference_price, lst.price
    lines = [f"Normal **${normal:,.2f}** → you pay **${price:,.2f}** (**${normal - price:,.2f}** under)"]
    if fee_percent > 0:
        profit = normal * (1 - fee_percent / 100) - price
        word = "profit" if profit >= 0 else "loss"
        lines.append(f"Resold at normal price minus ~{fee_percent:g}% fees: ≈ **${profit:,.0f}** {word}")
    if alert.basis:
        lines.append(f"Normal price based on: {alert.basis}")
    lines.extend(alert.notes)
    return lines


def alert_embed(alert: Alert, fee_percent: float = 13) -> dict:
    lst = alert.listing
    lines = []
    if lst.price is not None:
        line = f"## ${lst.price:,.2f}"
        if lst.reference_price and lst.reference_price > lst.price:
            line += f"  ~~${lst.reference_price:,.2f}~~"
        lines.append(line)
    if alert.drop_percent is not None:
        lines.append(f"**{alert.drop_percent:.0f}% below** {lst.reference_label or 'usual price'}")
    if alert.drop_percent is not None and alert.drop_percent >= 90:
        lines.append("⚠️ Unusually low — double-check the seller, condition and that it's the actual part.")
    if lst.note:
        lines.append(lst.note)

    fields = [{"name": "Store", "value": lst.store, "inline": True}]
    if alert.part:
        fields.append({"name": "Tracking", "value": alert.part.name, "inline": True})
    flip = resale_lines(alert, fee_percent)
    if flip:
        fields.append({"name": "💰 Resale math (estimate)", "value": _clip("\n".join(flip), 1024)})
    fields.append({"name": "Why you're seeing this", "value": _clip("\n".join(f"• {r}" for r in alert.reasons), 1024)})

    big = (alert.drop_percent or 0) >= 50 or lst.error_words
    embed = {
        "title": _clip(lst.title, 256),
        "url": lst.url or None,
        "description": "\n".join(lines) or None,
        "color": RED if big else ORANGE,
        "fields": fields,
        "footer": {"text": f"via {lst.source} • prices can change fast, check before buying"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if lst.image_url:
        embed["thumbnail"] = {"url": lst.image_url}
    return {k: v for k, v in embed.items() if v is not None}


def info_embed(title: str, description: str, color: int = BLUE) -> dict:
    return {"title": _clip(title, 256), "description": _clip(description, 4000), "color": color}


class Discord:
    def __init__(self, webhook_url: str, mention: str = "", session: requests.Session | None = None,
                 fee_percent: float = 13):
        self.url = webhook_url
        self.mention = mention.strip()
        self.session = session or requests.Session()
        self.fee_percent = fee_percent

    def send(self, embeds: list[dict], content: str = "") -> None:
        for i in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE):
            chunk = embeds[i : i + MAX_EMBEDS_PER_MESSAGE]
            text = content if i == 0 else ""
            payload = {
                "username": "PC Price Alerts",
                "content": _clip(text, 2000),
                "embeds": chunk,
                "allowed_mentions": {"parse": ["users", "roles", "everyone"]},
            }
            self._post(payload)

    def send_alerts(self, alerts: list[Alert]) -> None:
        if not alerts:
            return
        noun = "possible price error" if len(alerts) == 1 else f"{len(alerts)} possible price errors"
        content = f"{self.mention} 🚨 {noun}".strip()
        self.send([alert_embed(a, self.fee_percent) for a in alerts], content)

    def _post(self, payload: dict) -> None:
        for attempt in range(4):
            resp = self.session.post(self.url, json=payload, params={"wait": "true"}, timeout=TIMEOUT)
            if resp.status_code == 429:
                try:
                    delay = float(resp.json().get("retry_after", 2))
                except ValueError:
                    delay = 2.0
                time.sleep(min(delay, 30) + 0.25)
                continue
            if resp.status_code in (401, 404):
                raise RuntimeError(
                    "Discord rejected the webhook URL (it may have been deleted). "
                    "Create a new webhook and update the DISCORD_WEBHOOK_URL secret."
                )
            if resp.status_code >= 400:
                raise RuntimeError(f"Discord error HTTP {resp.status_code}: {resp.text[:300]}")
            time.sleep(0.4)  # stay well under Discord's webhook rate limit
            return
        raise RuntimeError("Discord kept rate-limiting the webhook; gave up for this run")
