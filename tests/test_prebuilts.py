"""Prebuilt PCs are kept apart from loose components and grouped by their GPU."""
import shutil
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from conftest import FakeResponse, FakeSession

from pricebot.__main__ import run
from pricebot.config import load_config
from pricebot.detector import evaluate, resolve_part
from pricebot.models import Listing
from pricebot.notify import alert_embed
from pricebot.state import State
from test_sources import rss

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def L(title, price=1000):
    return Listing("slickdeals", "Newegg", title, title, "u", price)


@pytest.mark.parametrize("title,expected", [
    ("Skytech Shadow Gaming PC Desktop – Ryzen 7 9800X3D, RTX 5070 12GB, 32GB DDR5", "Prebuilt PC: RTX 5070"),
    ("CyberPowerPC Gamer Supreme - Ryzen 7 7800X3D, GeForce RTX 5070 Ti 16GB", "Prebuilt PC: RTX 5070 Ti"),
    ("iBUYPOWER Y40 Gaming Desktop RTX 5080 Intel Core Ultra 7 265KF", "Prebuilt PC: RTX 5080"),
    ("HP OMEN 45L Gaming Desktop - Ryzen 9 9950X3D - RTX 5090 - 64GB", "Prebuilt PC: RTX 5090"),
    ("Origin PC Neuron RTX 4070 Ti Super", "Prebuilt PC: RTX 4070 family"),
    ("MSI Gaming GeForce RTX 5070 12G Ventus 2X OC Graphics Card", "RTX 5070"),
    ("CORSAIR Vengeance DDR5 32GB (2x16GB) 6000MHz Desktop Memory for Gaming PC", "DDR5 32GB kit"),
    ("Corsair RM850x 850 Watt ATX Power Supply for Gaming PC", "850W power supply"),
    ("ASUS TUF Gaming Laptop RTX 5070", None),
])
def test_prebuilt_classification(root, title, expected):
    c = load_config(root / "config.yaml")
    part = resolve_part(L(title), c.parts, c.settings)
    assert (part.name if part else None) == expected


def test_prebuilt_alert_shows_gpu_value_and_optional_partout(root):
    c = load_config(root / "config.yaml")
    title = "CyberPowerPC Gamer Xtreme RTX 5080 16GB Ryzen 7 9800X3D 32GB"
    # 40% under the prebuilt's learned normal price -> alert, with GPU value note
    a = evaluate(L(title, 1500), c.parts, c.settings, learned_typical=2500, gpu_normal=1699)
    assert a and a.part.name == "Prebuilt PC: RTX 5080"
    flip = next(f["value"] for f in alert_embed(a)["fields"] if f["name"].startswith("💰"))
    assert "The RTX 5080 alone is normally ~$1,699: this whole PC costs 0.88× that" in flip
    # Only 20% under: prebuilts need 35%, so no alert by default...
    assert evaluate(L(title, 2000), c.parts, c.settings, learned_typical=2500, gpu_normal=1699) is None
    # ...unless the part-out rule is switched on and the PC costs <= 1.2x its GPU
    st = replace(c.settings, prebuilt_partout_ratio=1.2)
    a = evaluate(L(title, 2000), c.parts, st, learned_typical=2500, gpu_normal=1699)
    assert a and "Costs only 1.18× the RTX 5080 inside it" in a.reasons[0]


def test_prebuilt_prices_never_pollute_gpu_prices(tmp_path, root, monkeypatch):
    shutil.copy(root / "config.yaml", tmp_path / "config.yaml")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/x/y")
    for k in ("KEEPA_API_KEY", "BESTBUY_API_KEY", "EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    import pricebot.notify as nt
    monkeypatch.setattr(nt.time, "sleep", lambda s: None)
    posts = [{"id": "p1", "title": "Skytech Gaming Desktop RTX 5070 Ryzen 7 $1,299 at Newegg", "body": ""},
             {"id": "g1", "title": "MSI GeForce RTX 5070 12GB Graphics Card $799 at Newegg", "body": ""}]
    s = FakeSession([("slickdeals.net", FakeResponse(200, content=rss(posts))),
                     ("dealnews.com", FakeResponse(200, content=rss([])))])
    run(str(tmp_path / "config.yaml"), str(tmp_path / "s.json"), now=NOW, session=s)
    hist = State.load(tmp_path / "s.json").history
    day = NOW.date().isoformat()
    assert hist["prices:RTX 5070"][day] == 799           # card price only
    assert hist["prices:Prebuilt PC: RTX 5070"][day] == 1299


def test_one_time_cleanup_of_old_prebuilt_prices(root):
    from pricebot.__main__ import _migrate
    c = load_config(root / "config.yaml")
    st = State()
    st.history["prices:RTX 5070"] = {"2026-11-23": 799, "2026-11-24": 1299, "2026-11-25": 829}  # 1299 = a prebuilt
    st.history["prices:RTX 3070"] = {"2026-11-23": 299, "2026-11-24": 899}   # no starting price -> vs lowest
    st.history["prices:RTX 3060"] = {"2026-11-23": 260, "2026-11-24": 310}   # normal variation, kept
    _migrate(st, c)
    assert st.history["prices:RTX 5070"] == {"2026-11-23": 799, "2026-11-25": 829}
    assert st.history["prices:RTX 3070"] == {"2026-11-23": 299}
    assert st.history["prices:RTX 3060"] == {"2026-11-23": 260, "2026-11-24": 310}
    st.history["prices:RTX 5070"]["2026-11-26"] = 1500
    _migrate(st, c)  # runs only once
    assert "2026-11-26" in st.history["prices:RTX 5070"]
