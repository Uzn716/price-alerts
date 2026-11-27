from datetime import datetime, timedelta, timezone

from conftest import FakeResponse, FakeSession

from pricebot.config import load_config
from pricebot.detector import evaluate
from pricebot.models import Listing
from pricebot.notify import alert_embed
from pricebot.sources.slickdeals import SlickdealsSource
from pricebot.state import State
from test_sources import rss

NOW = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)


def _post(title, price):
    return Listing(source="slickdeals", store="Newegg", item_id=title, title=title, url="u", price=price)


def test_alert_shows_resale_math_and_basis(root):
    c = load_config(root / "config.yaml")
    a = evaluate(_post("AMD Ryzen 7 7800X3D $219 at Newegg", 219), c.parts, c.settings,
                 learned_typical=349, learned_days=6)
    embed = alert_embed(a, fee_percent=13)
    flip = next(f["value"] for f in embed["fields"] if f["name"].startswith("💰"))
    assert "Normal **$349.00** → you pay **$219.00** (**$130.00** under)" in flip
    assert "≈ **$85** profit" in flip            # 349 * 0.87 - 219 = 84.63
    assert "learned from 6 days of prices" in flip

    # Before anything is learned, the starting price is the basis
    a = evaluate(_post("AMD Ryzen 7 7800X3D $219 at Newegg", 219), c.parts, c.settings)
    flip = next(f["value"] for f in alert_embed(a)["fields"] if f["name"].startswith("💰"))
    assert "researched starting estimate" in flip


def test_search_feeds_refresh_every_15_minutes(root):
    c = load_config(root / "config.yaml")
    hot = [f for f in c.slickdeals.feeds if not f.get("every_minutes")]
    searches = [f for f in c.slickdeals.feeds if f.get("every_minutes") == 15]
    assert len(hot) == 2 and len(searches) == 23
    state = State()

    def fetched_at(when):
        s = FakeSession([("slickdeals.net", FakeResponse(200, content=rss([])))])
        SlickdealsSource(c, state, s, when).fetch()
        return len(s.calls)

    assert fetched_at(NOW) == 25                          # first run: everything
    assert fetched_at(NOW + timedelta(minutes=5)) == 2    # only the 2 general feeds
    assert fetched_at(NOW + timedelta(minutes=10)) == 2
    assert fetched_at(NOW + timedelta(minutes=15)) == 25  # searches due again
