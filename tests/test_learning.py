"""The bot learns each part's typical price and alerts on deals 30%+ below it."""
import shutil
from datetime import datetime, timedelta, timezone

from conftest import FakeResponse, FakeSession

from pricebot.__main__ import run
from pricebot.state import State
from test_sources import rss

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def test_typical_price_window_and_min_days():
    s = State()
    s.record_price("prices:x", 500, NOW - timedelta(days=1))
    s.record_price("prices:x", 520, NOW - timedelta(days=2))
    assert s.typical_price("prices:x", NOW, min_days=3, days=30) is None  # only 2 days
    s.record_price("prices:x", 480, NOW - timedelta(days=3))
    assert s.typical_price("prices:x", NOW, min_days=3, days=30) == 500  # median
    s.record_price("prices:x", 100, NOW - timedelta(days=40))  # outside the window
    assert s.typical_price("prices:x", NOW, min_days=3, days=30) == 500


def test_full_run_learns_then_alerts_only_at_30_percent(tmp_path, root, monkeypatch):
    shutil.copy(root / "config.yaml", tmp_path / "config.yaml")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/x/y")
    for k in ("KEEPA_API_KEY", "BESTBUY_API_KEY", "EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    import pricebot.notify as nt
    monkeypatch.setattr(nt.time, "sleep", lambda s: None)
    cfg, st = str(tmp_path / "config.yaml"), str(tmp_path / "state.json")

    def check(day, posts):
        s = FakeSession([("slickdeals.net", FakeResponse(200, content=rss(posts))),
                         ("dealnews.com", FakeResponse(200, content=rss([])))])
        assert run(cfg, st, now=NOW + timedelta(days=day), session=s) == 0
        return [e for p in s.posts for e in p["embeds"]]

    posts = []
    # Days 0-3: ordinary 7800X3D deals around $350-370 get posted. The bot learns.
    for day, price in enumerate([369, 355, 362, 349]):
        posts.append({"id": f"d{day}", "title": f"AMD Ryzen 7 7800X3D ${price} at Newegg", "body": ""})
        assert check(day, posts) == []

    # Typical price is now the median of the daily prices (about $355-359)
    # Day 4: $299 is 17% under typical. A good sale, but not 30%: no alert.
    posts.append({"id": "d4", "title": "AMD Ryzen 7 7800X3D $299 at Micro Center", "body": "price error?"})
    assert check(4, posts) == []

    # Day 5: $239 is 33% under the typical $355 -> alert
    posts.append({"id": "d5", "title": "AMD Ryzen 7 7800X3D $239 at Walmart", "body": ""})
    embeds = check(5, posts)
    assert len(embeds) == 1 and "7800X3D" in embeds[0]["title"]
    why = next(f["value"] for f in embeds[0]["fields"] if f["name"].startswith("Why"))
    assert "% below its typical price over the last 30 days" in why
    assert embeds[0]["description"].startswith("## $239.00  ~~$")
