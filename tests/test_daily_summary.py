"""Once a day (after 9am local time) the bot posts a short 'still alive' summary."""
import shutil
from datetime import datetime, timedelta, timezone

from conftest import FakeResponse, FakeSession

from pricebot.__main__ import run
from test_sources import rss

# 13:00 UTC = 8am New York, 14:30 UTC = 9:30am New York
EARLY = datetime(2026, 11, 23, 13, 0, tzinfo=timezone.utc)


def test_daily_summary_once_per_day(tmp_path, root, monkeypatch):
    shutil.copy(root / "config.yaml", tmp_path / "config.yaml")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/x/y")
    for k in ("KEEPA_API_KEY", "BESTBUY_API_KEY", "EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    import pricebot.notify as nt
    monkeypatch.setattr(nt.time, "sleep", lambda s: None)
    cfg, st = str(tmp_path / "config.yaml"), str(tmp_path / "state.json")

    def check(when):
        s = FakeSession([("slickdeals.net", FakeResponse(200, content=rss([]))),
                         ("dealnews.com", FakeResponse(200, content=rss([])))])
        assert run(cfg, st, now=when, session=s) == 0
        return [e for p in s.posts for e in p["embeds"]]

    assert check(EARLY) == []                          # 8am: too early
    sent = check(EARLY + timedelta(minutes=90))        # 9:30am: summary
    assert len(sent) == 1 and "Daily check-in" in sent[0]["title"]
    assert "**2** checks" in sent[0]["description"]
    assert "✅ All sources working" in sent[0]["description"]
    assert check(EARLY + timedelta(hours=5)) == []     # same day: not again
    nxt = check(EARLY + timedelta(days=1, hours=2))    # next day 9am: again, counters reset
    assert len(nxt) == 1 and "**2** checks" in nxt[0]["description"]
