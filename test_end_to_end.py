"""Full run with every store mocked, checking alerts, dedupe and failure warnings."""
import shutil
from datetime import datetime, timedelta, timezone

from conftest import FakeResponse, FakeSession

from pricebot.__main__ import run
from pricebot.state import State
from test_sources import DN_FEED, _deal, rss

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def make_session(bestbuy_status=200):
    deals = {"deals": {"dr": [_deal("B0AAAAAAA1", "ASUS TUF Gaming GeForce RTX 5090 32GB", 99999, 219999)]}, "tokensLeft": 50}
    bb = {"products": [{"sku": 111, "name": "PNY - GeForce RTX 5080 16GB", "salePrice": 579.99,
                        "regularPrice": 999.99, "url": "https://bestbuy.com/111", "condition": "New"}]}
    feed = rss([{"id": "9", "title": "RTX 5070 Ti $399 at Newegg", "body": ""}])
    return FakeSession([
        ("api.keepa.com/token", FakeResponse(200, {"tokensLeft": 50})),
        ("api.keepa.com/deal", FakeResponse(200, deals)),
        ("api.bestbuy.com", FakeResponse(bestbuy_status, bb)),
        ("slickdeals.net", FakeResponse(200, content=feed)),
        ("dealnews.com", FakeResponse(200, content=DN_FEED)),
    ])


def test_full_run(tmp_path, root, monkeypatch):
    shutil.copy(root / "config.yaml", tmp_path / "config.yaml")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/x/y")
    monkeypatch.setenv("KEEPA_API_KEY", "k")
    monkeypatch.setenv("BESTBUY_API_KEY", "b")
    import pricebot.sources.bestbuy as bb
    import pricebot.notify as nt
    monkeypatch.setattr(bb, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(nt.time, "sleep", lambda s: None)
    cfg, st = str(tmp_path / "config.yaml"), str(tmp_path / "data/state.json")

    s1 = make_session()
    assert run(cfg, st, now=NOW, session=s1) == 0
    titles = [e["title"] for p in s1.posts for e in p["embeds"]]
    assert any("RTX 5090" in t for t in titles)  # Amazon via Keepa deals
    assert any("RTX 5080" in t for t in titles)  # Best Buy
    assert not any("5070 Ti" in t for t in titles)  # Slickdeals seeded on first run
    assert "possible price errors" in s1.posts[0]["content"]

    # Second run 10 minutes later: same prices -> no repeat alerts
    s2 = make_session()
    assert run(cfg, st, now=NOW + timedelta(minutes=10), session=s2) == 0
    assert s2.posts == []

    # Best Buy breaks for 3 runs -> exactly one warning
    for i in range(4):
        s = make_session(bestbuy_status=403)
        run(cfg, st, now=NOW + timedelta(minutes=20 + 10 * i), session=s)
        warns = [e for p in s.posts for e in p["embeds"] if "isn't working" in e.get("title", "")]
        assert len(warns) == (1 if i == 2 else 0)

    state = State.load(st)
    assert "keepa:B0AAAAAAA1" in state.alerts and "bestbuy:111" in state.alerts


def test_dry_run_needs_no_webhook(tmp_path, root, monkeypatch, capsys):
    shutil.copy(root / "config.yaml", tmp_path / "config.yaml")
    for k in ("DISCORD_WEBHOOK_URL", "KEEPA_API_KEY", "BESTBUY_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    s = make_session()
    assert run(str(tmp_path / "config.yaml"), str(tmp_path / "s.json"), dry_run=True, now=NOW, session=s) == 0
    out = capsys.readouterr().out
    assert "keepa: skipped" in out and "bestbuy: skipped" in out
    assert not (tmp_path / "s.json").exists()


def test_bad_config_is_reported(tmp_path, capsys):
    (tmp_path / "config.yaml").write_text("parts:\n  - match: [x]\n")
    assert run(str(tmp_path / "config.yaml"), str(tmp_path / "s.json"), dry_run=True) == 2
    assert "needs at least a 'name'" in capsys.readouterr().out
