"""The bot learns each part's lowest recent price and alerts when a deal beats it."""
import shutil
from datetime import datetime, timedelta, timezone

from conftest import FakeResponse, FakeSession

from pricebot.__main__ import run
from pricebot.config import load_config
from pricebot.detector import evaluate
from pricebot.models import Listing
from pricebot.state import State
from test_sources import rss

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def post(title, price=None):
    return Listing(source="slickdeals", store="Newegg", item_id=title, title=title, url="u", price=price)


def test_recent_low_needs_enough_days():
    s = State()
    s.record_price("low:x", 500, NOW - timedelta(days=1))
    s.record_price("low:x", 520, NOW - timedelta(days=2))
    assert s.recent_low("low:x", NOW, 30, 3) is None  # only 2 days of data
    s.record_price("low:x", 480, NOW - timedelta(days=3))
    assert s.recent_low("low:x", NOW, 30, 3) == 480
    s.record_price("low:x", 300, NOW - timedelta(days=40))  # outside the 30-day window
    assert s.recent_low("low:x", NOW, 30, 3) == 480


def test_beating_learned_low(root):
    c = load_config(root / "config.yaml")
    part = next(p for p in c.parts if p.name == "RTX 4070 Super")  # no fixed target
    # 10% under a $480 low -> alert
    a = evaluate(post("ZOTAC RTX 4070 Super 12GB $429 at Newegg", 429), c.parts, c.settings, learned_low=480)
    assert a and a.part is part and "under the lowest price seen in the last 30 days" in a.reasons[0]
    assert a.listing.reference_price == 480  # shown struck-through in Discord
    # only 4% under -> no alert
    assert evaluate(post("ZOTAC RTX 4070 Super $459", 459), c.parts, c.settings, learned_low=480) is None
    # nothing learned yet -> no alert from this rule
    assert evaluate(post("ZOTAC RTX 4070 Super $429", 429), c.parts, c.settings, learned_low=None) is None


def test_full_run_learns_then_alerts(tmp_path, root, monkeypatch):
    shutil.copy(root / "config.yaml", tmp_path / "config.yaml")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/x/y")
    for k in ("KEEPA_API_KEY", "BESTBUY_API_KEY", "EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    import pricebot.notify as nt
    monkeypatch.setattr(nt.time, "sleep", lambda s: None)
    cfg, st = str(tmp_path / "config.yaml"), str(tmp_path / "state.json")

    def session_with(items):
        feed = rss(items)
        return FakeSession([("slickdeals.net", FakeResponse(200, content=feed)),
                            ("dealnews.com", FakeResponse(200, content=rss([])))])

    posts = []
    # Days 1-3: ordinary 7800X3D deals around $350-370 are posted (first run just learns)
    for day, price in enumerate([369, 355, 362]):
        posts.append({"id": f"d{day}", "title": f"AMD Ryzen 7 7800X3D ${price} at Newegg", "body": ""})
        s = session_with(posts)
        assert run(cfg, st, now=NOW + timedelta(days=day), session=s) == 0
        assert s.posts == []  # nothing special yet
    assert State.load(st).recent_low("low:Ryzen 7 7800X3D", NOW + timedelta(days=3), 30, 3) == 355

    # Day 4: a post at $339 (only 5% under the $355 low) -> no alert
    posts.append({"id": "d4", "title": "AMD Ryzen 7 7800X3D $339 at Micro Center", "body": ""})
    s = session_with(posts)
    run(cfg, st, now=NOW + timedelta(days=4), session=s)
    assert s.posts == []

    # Day 5: a post at $289 (15% under the new $339 low) -> alert
    posts.append({"id": "d5", "title": "AMD Ryzen 7 7800X3D $289 at Walmart", "body": ""})
    s = session_with(posts)
    run(cfg, st, now=NOW + timedelta(days=5), session=s)
    embeds = [e for p in s.posts for e in p["embeds"]]
    assert len(embeds) == 1 and "7800X3D" in embeds[0]["title"]
    why = next(f["value"] for f in embeds[0]["fields"] if f["name"].startswith("Why"))
    assert "15% under the lowest price seen in the last 30 days ($339.00)" in why
    assert "~~$339.00~~" in embeds[0]["description"]
